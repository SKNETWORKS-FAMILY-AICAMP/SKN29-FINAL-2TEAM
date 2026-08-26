"""factory.py(AgentRuntimeFactory, DependencyGraphSource) 단위 테스트.

model_config_resolver/model_factory/tool_loader는 Fake로 주입한다(02 §17.3 —
Mock으로 먼저 진행). compat.create_root_graph/create_child_graph는 patch해서
"Factory가 무엇을 넘기는가"만 검증한다 — deepagents가 그 인자로 실제 그래프를
잘 만드는지는 test_deepagents_compat.py의 몫이다.
RuntimeCapabilityPolicy·MiddlewareFactory·validate_subagents는 실물을 그대로 쓴다.
"""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from services.agent_runtime.context import RuntimeContext
from services.agent_runtime.definitions import AgentDefinition, SubagentDefinition, SubagentReference
from services.agent_runtime.exceptions import DelegationDepthError
from services.agent_runtime.factory import AgentRuntimeFactory, DependencyGraphSource, _to_langchain_tool
from services.agent_runtime.middleware.factory import MiddlewareFactory
from services.agent_runtime.models.factory import ResolvedModelConfig
from services.agent_runtime.prompts import RuntimePromptAssembler
from services.agent_runtime.runtime_policy import RuntimeCapabilityPolicy
from services.agent_runtime.tools.loader import Tool

FACTORY_MODULE = "services.agent_runtime.factory"


class _FakeDependencyGraphSource:
    def __init__(self):
        self.load_calls = []

    def load(self, team_id):
        self.load_calls.append(team_id)
        return {}


class _FakeModelConfigResolver:
    def __init__(self):
        self.resolve_calls = []

    def resolve(self, *, model, reasoning_effort, team_id):
        self.resolve_calls.append({"model": model, "reasoning_effort": reasoning_effort, "team_id": team_id})
        return ResolvedModelConfig(
            provider="anthropic", model_id=model, api_key="k", base_url=None, reasoning_effort=reasoning_effort
        )


class _FakeModelFactory:
    def __init__(self):
        self.create_calls = []

    def create(self, resolved):
        self.create_calls.append(resolved)
        return "FAKE_MODEL"


def _document_search_handler(query: str, team_id: str) -> str:
    return f"{team_id}:{query}"


def _fake_tools() -> tuple[Tool, ...]:
    read_tool = Tool(
        ref="document_search",
        name="document_search",
        description="문서를 검색한다.",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        handler=_document_search_handler,
        side_effect=False,
        injected_context=("team_id",),
    )
    write_tool = Tool(
        ref="task_register",
        name="task_register",
        description="업무를 등록한다.",
        input_schema={"type": "object", "properties": {}, "required": []},
        handler=lambda **kwargs: "registered",
        side_effect=True,
    )
    return (read_tool, write_tool)


class _FakeToolLoader:
    def __init__(self):
        self.load_calls = []

    def load(self, *, tool_refs, context, agent_model=None):
        self.load_calls.append({"tool_refs": tool_refs, "context": context, "agent_model": agent_model})
        return _fake_tools()


class _SkillToolLoader(_FakeToolLoader):
    def load(self, *, tool_refs, context, agent_model=None):
        self.load_calls.append(
            {"tool_refs": tool_refs, "context": context, "agent_model": agent_model}
        )
        return (
            *_fake_tools(),
            Tool(
                ref="skill_register",
                name="skill_register",
                description="스킬을 등록한다.",
                input_schema={
                    "type": "object",
                    "properties": {"scope": {"type": "string", "enum": ["PERSONAL", "TEAM"]}},
                    "required": ["scope"],
                },
                handler=lambda **kwargs: "registered",
                side_effect=True,
            ),
        )


class _FakeCheckpointerProvider:
    """`CheckpointerProvider`(services/agent_runtime/checkpoint/provider.py)를 대신한다.

    실물은 `.get()`이 실제 `PostgresSaver`(DB 연결)를 반환하므로, 단위 테스트에서는
    "Factory가 `.get()`을 호출해서 나온 값을 그대로 `create_root_graph(checkpointer=...)`에
    넘기는가"만 확인하면 된다 — 실제 Postgres/langgraph 객체는 안 쓴다.
    """

    def __init__(self, checkpointer: str = "FAKE_CHECKPOINTER"):
        self._checkpointer = checkpointer
        self.get_calls = 0

    def get(self):
        self.get_calls += 1
        return self._checkpointer


class _FakeMemoryProvider:
    """`MemoryProvider`(services/agent_runtime/memory/provider.py)를 대신한다.

    2026-08-18, Phase 3(§4-8) — `backend()`가 이제 `account_id`도 받으므로, Factory가
    `context.account_id`를 실제로 그대로 넘기는지 `backend_calls`로 확인할 수 있게 한다.
    2026-08-21 — `extra_routes`도 받는다(Skill 배선, `MemoryProvider.backend()`
    docstring 참고). `backend_calls`에 같이 기록해 Factory가 `skills_provider`가
    계산한 라우트를 그대로 전달하는지 확인할 수 있게 한다.
    """

    def __init__(self):
        self.paths_calls = 0
        self.backend_calls: list[dict] = []
        self.store_calls = 0
        self.system_prompt_calls = 0

    def paths(self):
        self.paths_calls += 1
        return ["/memories/users/preferences.md"]

    def backend(self, *, team_id: str, agent_id: str, account_id: str, extra_routes=None):
        self.backend_calls.append(
            {
                "team_id": team_id,
                "agent_id": agent_id,
                "account_id": account_id,
                "extra_routes": extra_routes,
            }
        )
        return "FAKE_BACKEND"

    def store(self):
        self.store_calls += 1
        return "FAKE_STORE"

    def system_prompt(self):
        self.system_prompt_calls += 1
        return "FAKE_MEMORY_SYSTEM_PROMPT"


class _FakeSkillsProvider:
    """`SkillsProvider`(services/agent_runtime/skills/provider.py)를 대신한다."""

    def __init__(self, sources=("/skills/personal/", "/skills/team/")):
        self._sources = list(sources)
        self.sources_calls = 0
        self.routes_calls: list[dict] = []
        self.system_prompt_calls = 0
        self.store_calls = 0

    def sources(self):
        self.sources_calls += 1
        return list(self._sources)

    def routes(self, *, account_id: str, team_id: str):
        self.routes_calls.append({"account_id": account_id, "team_id": team_id})
        return {"/skills/personal/": "FAKE_PERSONAL_ROUTE", "/skills/team/": "FAKE_TEAM_ROUTE"}

    def system_prompt(self):
        self.system_prompt_calls += 1
        return "FAKE_SKILLS_SYSTEM_PROMPT"

    def store(self):
        self.store_calls += 1
        return "FAKE_SKILLS_STORE"


def _definition(**overrides) -> AgentDefinition:
    fields = {
        "agent_id": "AG001",
        "agent_version_id": "AV001",
        "name": "부모",
        "description": "",
        "system_prompt": "너는 테스트용 에이전트다.",
        "model": "claude-sonnet-5",
        "reasoning_effort": "low",
        "max_iterations": 6,
        "tool_refs": ("document_search", "task_register"),
    }
    fields.update(overrides)
    return AgentDefinition(**fields)


def _factory(**kwargs):
    defaults = dict(
        dependency_graph=_FakeDependencyGraphSource(),
        model_config_resolver=_FakeModelConfigResolver(),
        model_factory=_FakeModelFactory(),
        tool_loader=_FakeToolLoader(),
        middleware_factory=MiddlewareFactory(runtime_policy=RuntimeCapabilityPolicy()),
        runtime_policy=RuntimeCapabilityPolicy(),
        prompt_assembler=RuntimePromptAssembler(),
    )
    defaults.update(kwargs)
    return AgentRuntimeFactory(**defaults), defaults


class DependencyGraphSourceTests(SimpleTestCase):
    @patch("backend.db.agent_platform._team_dependency_graph")
    @patch("backend.db.connection.database_connection")
    def test_delegates_to_shared_team_dependency_graph_query(self, mock_connection, mock_graph):
        mock_connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = "CURSOR"
        mock_graph.return_value = {"AG001": {"AG002"}}

        result = DependencyGraphSource().load("TM001")

        mock_graph.assert_called_once_with("CURSOR", team_id="TM001")
        self.assertEqual(result, {"AG001": {"AG002"}})


class BuildValidationAndModelTests(SimpleTestCase):
    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_calls_dependency_graph_and_model_resolver_with_context_values(self, mock_create_root):
        mock_create_root.return_value = "GRAPH"
        factory, deps = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        self.assertEqual(deps["dependency_graph"].load_calls, ["TM001"])
        self.assertEqual(
            deps["model_config_resolver"].resolve_calls,
            [{"model": "claude-sonnet-5", "reasoning_effort": "low", "team_id": "TM001"}],
        )
        self.assertEqual(deps["model_factory"].create_calls[0].provider, "anthropic")

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_passes_definition_model_to_tool_loader_as_agent_model(self, mock_create_root):
        """task_extraction 같은 도구가 "부른 에이전트가 고른 모델"을 알아야 한다
        (tools/adapters.py) — Factory가 definition.model을 그대로 넘겨야 한다."""
        mock_create_root.return_value = "GRAPH"
        factory, deps = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(model="gpt-5.6-luna"), context=context)

        self.assertEqual(deps["tool_loader"].load_calls[0]["agent_model"], "gpt-5.6-luna")


class BuildReturnsResolvedModelTests(SimpleTestCase):
    """2026-08-19, §4순위(Run Snapshot) — `build()`가 resolved_model을 함께
    반환하는지. `executor.py`가 이 값을 `EVENT_AGENT_STARTED`에 실어
    `agent_run.resolved_provider`/`resolved_endpoint_hash`로 남긴다(정본:
    `2026-08-19_01_실행_안정성_설계.md` §1).

    **2026-08-20에 반환 타입이 2-tuple → 3-tuple로 바뀌었다**(`17e8c62`,
    §10 Child Run Snapshot — 세 번째 자리는 Child alias별 resolved_model
    dict라 `subagent_started` 이벤트에도 provider/endpoint_hash를 채울 수
    있다). 이 테스트들은 그때 같이 안 고쳐져서 2-tuple로 언패킹한 채
    `ValueError: too many values to unpack`으로 깨져 있었다 — 2026-08-21에
    실제 반환 타입에 맞춘다(`2026-08-21_01` §8이 정리한 것과 같은 종류)."""

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_root_build_returns_graph_and_resolved_model(self, mock_create_root):
        mock_create_root.return_value = "GRAPH"
        factory, _ = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        graph, resolved, _child_models = factory.build(
            definition=_definition(model="claude-x"), context=context
        )

        self.assertEqual(graph, "GRAPH")
        self.assertEqual(resolved.provider, "anthropic")
        self.assertEqual(resolved.model_id, "claude-x")

    @patch(f"{FACTORY_MODULE}.create_child_graph")
    def test_child_build_also_returns_graph_and_resolved_model(self, mock_create_child):
        mock_create_child.return_value = "CHILD_GRAPH"
        factory, _ = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        graph, resolved, _child_models = factory.build(
            definition=_definition(), context=context, allow_subagents=False
        )

        self.assertEqual(graph, "CHILD_GRAPH")
        self.assertEqual(resolved.provider, "anthropic")

    @patch(f"{FACTORY_MODULE}.create_child_graph")
    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_a_childs_own_resolved_model_does_not_leak_into_the_roots(
        self, mock_create_root, mock_create_child
    ):
        """Child는 자기 model을 따로 가질 수 있다(SubagentReference와 무관하게
        `subagents/builder.py`가 `AgentDefinition.model`을 그대로 옮긴다) —
        Root의 반환값은 Root 자신의 resolved_model이어야지, 마지막으로 지어진
        Child 것이 섞이면 안 된다."""
        mock_create_root.return_value = "GRAPH"
        factory, _ = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")
        child = SubagentDefinition(
            agent_id="AG011",
            agent_version_id="AV023",
            name="Jira 작성자",
            description="",
            system_prompt="자식 프롬프트",
            model="gpt-child-model",
            reasoning_effort="low",
            max_iterations=4,
            alias="jira_writer",
            delegation_description="Jira 이슈를 생성한다.",
        )
        definition = _definition(model="claude-root-model", subagents=(child,))

        _graph, resolved, _child_models = factory.build(definition=definition, context=context)

        self.assertEqual(resolved.model_id, "claude-root-model")


class BuildDelegationDepthTests(SimpleTestCase):
    """Root를 지을 때도 고른 Child의 `has_subagents=True`를 거부해야 한다.

    2026-08-14 수정 전에는 `validate_subagents()`의 이 검사가 `allow_subagents`
    플래그에 묶여 있었는데, Root 빌드는 그 플래그를 `True`(Root/Child 그래프
    분기용, 검사와는 무관)로 넘겨서 검사가 통째로 빠졌다. 저장(`publish()`)은
    막혀 있었지만, 저장 없이 도는 Builder Test Run(`AgentDefinitionLoader
    .from_draft()`)은 이미 저장된, 자기 서브 에이전트를 가진 다른 에이전트를
    Child로 골라 2단계 위임을 그대로 실행할 수 있었다."""

    def test_root_build_rejects_a_chosen_child_that_itself_has_subagents(self):
        factory, _ = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")
        ref = SubagentReference(
            child_agent_id="AG011",
            child_version_id="AV023",
            alias="jira_writer",
            delegation_description="Jira 이슈를 생성한다.",
            is_active=True,
            can_execute=True,
            has_subagents=True,
        )

        with self.assertRaises(DelegationDepthError):
            factory.build(
                definition=_definition(),
                subagent_references=(ref,),
                context=context,
            )

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_root_build_accepts_a_leaf_child_without_grandchildren(self, mock_create_root):
        """음성 대조군 — `has_subagents=False`인 정상 Child는 그대로 통과한다."""
        mock_create_root.return_value = "GRAPH"
        factory, _ = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")
        ref = SubagentReference(
            child_agent_id="AG011",
            child_version_id="AV023",
            alias="jira_writer",
            delegation_description="Jira 이슈를 생성한다.",
            is_active=True,
            can_execute=True,
            has_subagents=False,
        )

        factory.build(definition=_definition(), subagent_references=(ref,), context=context)

        mock_create_root.assert_called_once()


class BuildToolAssemblyTests(SimpleTestCase):
    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_leader_gets_both_tools_bound_and_working(self, mock_create_root):
        mock_create_root.return_value = "GRAPH"
        factory, _ = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        tools_arg = mock_create_root.call_args.kwargs["tools"]
        names = {t.name for t in tools_arg}
        self.assertEqual(names, {"document_search", "task_register"})

        search_tool = next(t for t in tools_arg if t.name == "document_search")
        self.assertEqual(search_tool.invoke({"query": "q"}), "TM001:q")

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_member_still_sees_side_effect_tool(self, mock_create_root):
        """2026-08-19 정책 변경 — 노출은 역할과 무관하다. 예전엔 member가
        `task_register`를 아예 못 봐서 모델이 "그런 기능이 없다"고 답했는데
        (버그 리포트), 이제는 보이되 실행하면 막힌다(`ToolExecutionTimeRBACTests`
        참고)."""
        mock_create_root.return_value = "GRAPH"
        factory, _ = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="member")

        factory.build(definition=_definition(), context=context)

        tools_arg = mock_create_root.call_args.kwargs["tools"]
        names = {t.name for t in tools_arg}
        self.assertEqual(names, {"document_search", "task_register"})

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_leaders_write_tool_still_executes_normally_through_build(self, mock_create_root):
        """실행 직전 재검사(아래 클래스)가 정상 호출까지 막지는 않는지 확인한다."""
        mock_create_root.return_value = "GRAPH"
        factory, _ = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        tools_arg = mock_create_root.call_args.kwargs["tools"]
        write_tool = next(t for t in tools_arg if t.name == "task_register")
        self.assertEqual(write_tool.invoke({}), "registered")


class ToolExecutionTimeRBACTests(SimpleTestCase):
    """실행 직전 RBAC 재검사 — `_to_langchain_tool()`을 직접 호출해 확인한다.

    2026-08-19부터 이게 **유일한** 방어선이다(예전엔 노출 시점 필터
    `filter_tools_for_role()`도 있었는데, 그걸로 member에게서 도구를 통째로
    지우면 모델이 "그런 기능이 없다"고 답해 버려서(버그 리포트) 없앴다 —
    이제 모델은 도구를 항상 보고, 실행하려 하면 여기서 막힌다)."""

    def _write_tool(self) -> Tool:
        return Tool(
            ref="task_register",
            name="task_register",
            description="업무를 등록한다.",
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=lambda **kwargs: "registered",
            side_effect=True,
        )

    def _read_tool(self) -> Tool:
        return Tool(
            ref="document_list",
            name="document_list",
            description="문서 목록을 본다.",
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=lambda **kwargs: "listed",
            side_effect=False,
        )

    def test_member_can_now_execute_a_write_tool_under_the_default_policy(self):
        """**2026-08-20부터 기본 정책이 member의 쓰기 실행을 허용한다**
        (`17e8c62`). 그래서 기본 정책으로는 여기서 안 막히고 실제로 실행된다 —
        경계는 `interrupt_on`(자기 승인 HITL)으로 옮겨갔다
        (`BuildInterruptOnWiringTests`, `2026-08-21_02` 참고).

        예전 이 테스트는 member가 권한 거부 문구를 받는 걸 검증했는데, 그
        문구 경로 자체는 없어진 게 아니라 "정책이 그 역할을 막을 때"만 도는
        경로가 됐다 — 아래 `test_..._when_policy_restricts_the_role`이 그
        경로를 여전히 덮는다."""
        tool = self._write_tool()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="member")
        langchain_tool = _to_langchain_tool(tool, context=context, runtime_policy=RuntimeCapabilityPolicy())

        self.assertEqual(langchain_tool.invoke({}), "registered")

    def test_write_tool_is_refused_with_a_speakable_message_when_policy_restricts_the_role(self):
        """2026-08-19 — 크래시(`ToolPermissionError`)가 아니라 `ToolException`
        으로 바뀌었다. 승인 필요 도구를 못 부르는 건 흔한 정상 경로라, 대화를
        끊지 않고 모델이 사유를 그대로 전한다.

        기본 정책은 이제 member도 허용하므로(위 테스트), 이 경로를 재현하려면
        정책 자체를 좁혀야 한다 — `is_tool_allowed_for_role()`이 하드코딩이
        아니라 `write_tool_allowed_roles` 값을 실제로 읽는다는 것까지 같이
        확인된다."""
        tool = self._write_tool()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="member")
        langchain_tool = _to_langchain_tool(
            tool,
            context=context,
            runtime_policy=RuntimeCapabilityPolicy(write_tool_allowed_roles=frozenset({"leader"})),
        )

        self.assertEqual(
            langchain_tool.invoke({}),
            "'member' 역할은 'task_register' 도구를 실행할 권한이 없습니다. 팀장에게 요청해 주세요.",
        )

    def test_leader_calling_a_write_tool_directly_still_succeeds(self):
        tool = self._write_tool()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")
        langchain_tool = _to_langchain_tool(tool, context=context, runtime_policy=RuntimeCapabilityPolicy())

        self.assertEqual(langchain_tool.invoke({}), "registered")

    def test_member_calling_a_read_tool_directly_still_succeeds(self):
        tool = self._read_tool()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="member")
        langchain_tool = _to_langchain_tool(tool, context=context, runtime_policy=RuntimeCapabilityPolicy())

        self.assertEqual(langchain_tool.invoke({}), "listed")


class ToolExecutionErrorHandlingTests(SimpleTestCase):
    """2026-08-18 추가 — `agent_user_query_tool_check.py`로 실제 모델을 돌리다가
    발견한 문제의 회귀 테스트. `langchain.agents.factory.create_agent()`가 내부에서
    만드는 `ToolNode`는 `handle_tool_errors` 파라미터 자체를 우리에게 안 열어 주고
    (실측 — langchain/deepagents 소스 어디에도 없음), 기본 동작은 `ToolInvocationError`
    (인자 스키마 검증 실패)만 잡고 그 외는 전부 다시 raise한다. 그 결과 `task_list`를
    `project_id` 없이 부르는 것처럼 이 저장소가 "모델에게 그대로 보여줘도 되는 실패"로
    설계해 둔 `ToolInputError`(`services/harness/registry.py`)조차 그래프 실행 전체를
    죽였다 — 모델이 스스로 고칠 기회가 없었다. `_to_langchain_tool()`의 `_run()`이
    `tool.handler()` 호출을 직접 감싸서, 레거시 `services/harness/runner.py`의
    `SPEAKABLE_ERRORS`/`error_code_of()` 판단을 그대로 재사용해 크래시 대신 문자열
    tool 결과로 돌려주는지 확인한다."""

    def _tool(self, *, ref: str, handler) -> Tool:
        return Tool(
            ref=ref,
            name=ref,
            description="",
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=handler,
            side_effect=False,
        )

    def test_tool_input_error_message_reaches_model_instead_of_crashing(self):
        from services.harness.registry import ToolInputError

        def _handler(**kwargs):
            raise ToolInputError("어느 프로젝트의 업무인지 정해지지 않았습니다. 프로젝트를 먼저 고르세요.")

        tool = self._tool(ref="task_list", handler=_handler)
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")
        langchain_tool = _to_langchain_tool(tool, context=context, runtime_policy=RuntimeCapabilityPolicy())

        result = langchain_tool.invoke({})

        self.assertEqual(result, "어느 프로젝트의 업무인지 정해지지 않았습니다. 프로젝트를 먼저 고르세요.")

    def test_repository_permission_denied_message_reaches_model(self):
        from backend.db.errors import PermissionDenied

        def _handler(**kwargs):
            raise PermissionDenied("팀에 속하지 않은 계정입니다.")

        tool = self._tool(ref="document_list", handler=_handler)
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")
        langchain_tool = _to_langchain_tool(tool, context=context, runtime_policy=RuntimeCapabilityPolicy())

        result = langchain_tool.invoke({})

        self.assertEqual(result, "팀에 속하지 않은 계정입니다.")

    def test_unspeakable_error_hides_message_behind_class_name(self):
        """스피커블 목록에 없는 예외는 원문 대신 클래스 이름만 나가야 한다
        (`SPEAKABLE_ERRORS` 밖 = 문서 원문·토큰이 섞여 있을 수 있는 예외)."""

        def _handler(**kwargs):
            raise ValueError("내부 쿼리 원문이 섞여 있을 수 있는 진짜 예외 메시지")

        tool = self._tool(ref="document_search", handler=_handler)
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")
        langchain_tool = _to_langchain_tool(tool, context=context, runtime_policy=RuntimeCapabilityPolicy())

        result = langchain_tool.invoke({})

        self.assertEqual(result, "도구 실행 실패: ValueError")
        self.assertNotIn("내부 쿼리 원문", result)

    def _write_tool(self) -> Tool:
        return Tool(
            ref="task_register",
            name="task_register",
            description="업무를 등록한다.",
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=lambda **kwargs: "registered",
            side_effect=True,
        )


class ToLangchainToolNameTests(SimpleTestCase):
    """`_to_langchain_tool()`이 LangChain 함수 이름으로 `tool.ref`를 쓰는지
    확인한다(2026-08-14 추가 — 실제 라이브 실행에서 발견한 버그의 회귀 테스트).

    실제 `BUILTIN_TOOLS`(services/harness/registry.py)는 `Tool.name`을 사람이
    읽는 한국어 라벨로 채운다(예: "프로젝트 조회"). `_to_langchain_tool()`이
    `tool.name`을 LangChain `StructuredTool.name`(=OpenAI/Anthropic에 실제로
    나가는 함수 이름)으로 잘못 쓰면, OpenAI Responses API가 `Invalid
    'tools[N].name': string does not match pattern`(패턴은
    `^[a-zA-Z0-9_-]+$`)로 즉시 400을 낸다 — 실제로 `scripts/team_status_agent.py`
    로 라이브 실행해 재현했다. 기존 테스트들은 전부 `Tool(ref="x", name="x", ...)`
    처럼 `name`과 `ref`를 같은 값으로 만든 fixture를 썼어서 이 불일치를
    잡아내지 못했다 — 이 테스트는 실제 BUILTIN_TOOLS와 같은 모양(한국어
    `name`, 별개의 `ref`)으로 그 간극을 재현한다.
    """

    def _tool_with_korean_display_name(self) -> Tool:
        return Tool(
            ref="project_list",
            name="프로젝트 조회",
            description="우리 팀의 프로젝트와 진행률.",
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=lambda **kwargs: "ok",
            side_effect=False,
        )

    def test_langchain_tool_name_is_ref_not_korean_display_name(self):
        tool = self._tool_with_korean_display_name()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        langchain_tool = _to_langchain_tool(tool, context=context, runtime_policy=RuntimeCapabilityPolicy())

        self.assertEqual(langchain_tool.name, "project_list")
        self.assertNotEqual(langchain_tool.name, "프로젝트 조회")

    def test_langchain_tool_name_matches_openai_function_name_pattern(self):
        """OpenAI Responses API가 실제로 강제하는 패턴(`^[a-zA-Z0-9_-]+$`) —
        한국어·공백이 섞이면 이 정규식을 못 넘는다(실측: 위 클래스 docstring)."""
        tool = self._tool_with_korean_display_name()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        langchain_tool = _to_langchain_tool(tool, context=context, runtime_policy=RuntimeCapabilityPolicy())

        self.assertRegex(langchain_tool.name, r"^[a-zA-Z0-9_-]+$")

    def test_langchain_tool_still_invokes_the_original_handler(self):
        """이름만 바뀐 것이지 실행 자체는 그대로 handler로 간다."""
        tool = self._tool_with_korean_display_name()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        langchain_tool = _to_langchain_tool(tool, context=context, runtime_policy=RuntimeCapabilityPolicy())

        self.assertEqual(langchain_tool.invoke({}), "ok")

    def _mcp_style_tool(self) -> Tool:
        return Tool(
            ref="mcp:MT001",
            name="Jira 이슈 생성",
            description="Jira에 이슈를 만든다.",
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=lambda **kwargs: "mcp-ok",
            side_effect=True,
        )

    def test_mcp_style_ref_with_colon_is_mangled_for_openai_pattern(self):
        """mcp:<id>의 콜론은 OpenAI 함수 이름 패턴을 못 넘는다 —
        model_safe_tool_name()이 __로 바꿔야 한다(2026-08-14 MCP 연결,
        factory.py 콜론 치환 이관)."""
        tool = self._mcp_style_tool()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        langchain_tool = _to_langchain_tool(tool, context=context, runtime_policy=RuntimeCapabilityPolicy())

        self.assertEqual(langchain_tool.name, "mcp__MT001")
        self.assertRegex(langchain_tool.name, r"^[a-zA-Z0-9_-]+$")

    def test_mangled_mcp_tool_name_still_invokes_original_handler(self):
        tool = self._mcp_style_tool()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        langchain_tool = _to_langchain_tool(tool, context=context, runtime_policy=RuntimeCapabilityPolicy())

        self.assertEqual(langchain_tool.invoke({}), "mcp-ok")


class BuildMiddlewareAndGeneralPurposeTests(SimpleTestCase):
    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_root_includes_explicit_general_purpose_spec_with_middleware(self, mock_create_root):
        mock_create_root.return_value = "GRAPH"
        factory, _ = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        subagents_arg = mock_create_root.call_args.kwargs["subagents"]
        gp_spec = subagents_arg[0]
        self.assertEqual(gp_spec["name"], "general-purpose")
        self.assertTrue(gp_spec["middleware"])

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_general_purpose_spec_uses_this_app_s_description_not_the_deepagents_default(self, mock_create_root):
        from deepagents.middleware.subagents import GENERAL_PURPOSE_SUBAGENT

        from services.agent_runtime.prompts import GP_DESCRIPTION

        mock_create_root.return_value = "GRAPH"
        factory, _ = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        gp_spec = mock_create_root.call_args.kwargs["subagents"][0]
        self.assertEqual(gp_spec["description"], GP_DESCRIPTION)
        self.assertNotEqual(gp_spec["description"], GENERAL_PURPOSE_SUBAGENT["description"])

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_root_middleware_reflects_definition_max_iterations(self, mock_create_root):
        from langchain.agents.middleware import ModelCallLimitMiddleware

        mock_create_root.return_value = "GRAPH"
        factory, _ = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(max_iterations=6), context=context)

        middleware_arg = mock_create_root.call_args.kwargs["middleware"]
        model_limit = next(m for m in middleware_arg if isinstance(m, ModelCallLimitMiddleware))
        self.assertEqual(model_limit.run_limit, 6)

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_general_purpose_only_receives_non_side_effect_tools(self, mock_create_root):
        """2026-08-20, GP 피드백 검토 §3 채택 3 — GP는 이제 Root의 전체 도구를
        상속하지 않는다. `_fake_tools()`는 읽기 도구(`document_search`) 하나와
        쓰기 도구(`task_register`) 하나를 주므로, GP의 `tools`에는 읽기 도구만
        남아야 한다."""
        mock_create_root.return_value = "GRAPH"
        factory, _ = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        gp_spec = mock_create_root.call_args.kwargs["subagents"][0]
        gp_tool_names = {t.name for t in gp_spec["tools"]}
        self.assertIn("document_search", gp_tool_names)
        self.assertNotIn("task_register", gp_tool_names)

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_general_purpose_is_always_attached(self, mock_create_root):
        """2026-08-20, GP 피드백 검토 §3 채택 — GP를 켜고 끄는 스위치는 두지
        않는다. GP는 조회 도구만 쓸 수 있어(위 테스트) 위험하지 않으므로,
        모든 Root에 항상 붙는다."""
        mock_create_root.return_value = "GRAPH"
        factory, _ = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        subagents_arg = mock_create_root.call_args.kwargs["subagents"]
        names = [s.get("name") for s in subagents_arg if isinstance(s, dict)]
        self.assertIn("general-purpose", names)


class PromptAssemblyWiringTests(SimpleTestCase):
    """실행 시점에 공통 Runtime Scaffold가 실제로 붙는지(2026-08-14 추가) —
    Builder Test Run은 아직 레거시 harness를 쓰지만(별도 결정, 지금은 안 건드림),
    실제 실행 경로(Chat → AgentExecutor → Factory)에는 여기서 붙는다."""

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_root_system_prompt_is_scaffold_plus_agent_prompt_not_the_raw_db_value(self, mock_create_root):
        mock_create_root.return_value = "GRAPH"
        factory, _ = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(system_prompt="루트 지시문"), context=context)

        sent = mock_create_root.call_args.kwargs["system_prompt"]
        self.assertNotEqual(sent, "루트 지시문")  # 원본 그대로 넘기면 안 된다.
        self.assertIn("루트 지시문", sent)
        self.assertEqual(sent, RuntimePromptAssembler().assemble_root(agent_prompt="루트 지시문"))

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_general_purpose_spec_gets_scaffold_plus_deepagents_default_prompt(self, mock_create_root):
        from services.agent_runtime.compat import default_general_purpose_prompt

        mock_create_root.return_value = "GRAPH"
        factory, _ = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        gp_spec = mock_create_root.call_args.kwargs["subagents"][0]
        expected = RuntimePromptAssembler().assemble_general_purpose(
            gp_prompt=default_general_purpose_prompt()
        )
        self.assertEqual(gp_spec["system_prompt"], expected)

    def test_a_different_prompt_assembler_is_actually_used_not_ignored(self):
        """조립기가 실제로 쓰이는지 — 가짜 조립기를 넣어서 Factory가 그 결과를
        그대로 통과시키는지 직접 증명한다(스캐폴드 문구 자체를 다시 검증하는 게
        아니라 '연결이 되어 있는가'를 본다)."""

        class _FakeAssembler:
            def assemble_root(self, *, agent_prompt):
                return f"ROOT::{agent_prompt}"

            def assemble_child(self, *, agent_prompt):
                return f"CHILD::{agent_prompt}"

            def assemble_general_purpose(self, *, gp_prompt):
                return f"GP::{gp_prompt}"

        with patch(f"{FACTORY_MODULE}.create_root_graph") as mock_create_root:
            mock_create_root.return_value = "GRAPH"
            factory, _ = _factory(prompt_assembler=_FakeAssembler())
            context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

            factory.build(definition=_definition(system_prompt="X"), context=context)

            self.assertEqual(mock_create_root.call_args.kwargs["system_prompt"], "ROOT::X")
            gp_spec = mock_create_root.call_args.kwargs["subagents"][0]
            self.assertTrue(gp_spec["system_prompt"].startswith("GP::"))


class BuildChildRecursionTests(SimpleTestCase):
    @patch(f"{FACTORY_MODULE}.create_child_graph")
    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_subagent_definition_recurses_into_child_graph_and_wraps_compiled_subagent(
        self, mock_create_root, mock_create_child
    ):
        mock_create_root.return_value = "ROOT_GRAPH"
        mock_create_child.return_value = "CHILD_GRAPH"
        factory, _ = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        child = SubagentDefinition(
            agent_id="AG011",
            agent_version_id="AV023",
            name="Jira 작성자",
            description="",
            system_prompt="자식 프롬프트",
            model="gpt-5.6-luna",
            reasoning_effort="low",
            max_iterations=4,
            alias="jira_writer",
            delegation_description="Jira 이슈를 생성한다.",
            tool_refs=("document_search", "task_register"),
        )
        definition = _definition(subagents=(child,))

        factory.build(definition=definition, context=context)

        mock_create_child.assert_called_once()
        # 실행 시점에 공통 Scaffold가 붙는다(2026-08-14 추가) — 원본 문자열
        # 그대로가 아니라 RuntimePromptAssembler.assemble_child()로 조립된 값이어야
        # 한다. 조립 규칙 자체는 tests/test_prompts.py가 검증하므로 여기서는
        # "Factory가 assembler를 실제로 거쳐서 넘기는가"만 확인한다.
        expected = RuntimePromptAssembler().assemble_child(agent_prompt="자식 프롬프트")
        self.assertEqual(mock_create_child.call_args.kwargs["system_prompt"], expected)
        self.assertIn("자식 프롬프트", mock_create_child.call_args.kwargs["system_prompt"])

        subagents_arg = mock_create_root.call_args.kwargs["subagents"]
        compiled_child = next(s for s in subagents_arg if isinstance(s, dict) and s.get("name") == "jira_writer")
        self.assertEqual(compiled_child["description"], "Jira 이슈를 생성한다.")
        self.assertEqual(compiled_child["runnable"], "CHILD_GRAPH")


class BuildChildPathTests(SimpleTestCase):
    @patch(f"{FACTORY_MODULE}.create_child_graph")
    def test_allow_subagents_false_calls_create_child_graph_not_root(self, mock_create_child):
        mock_create_child.return_value = "CHILD_GRAPH"
        factory, _ = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        result = factory.build(definition=_definition(), context=context, allow_subagents=False)

        mock_create_child.assert_called_once()
        # 2026-08-19, §4순위(Run Snapshot) — build()는 (graph, resolved_model)
        # 튜플을 반환한다.
        self.assertEqual(result[0], "CHILD_GRAPH")


class BuildCheckpointerWiringTests(SimpleTestCase):
    """checkpointer_provider(2026-08-18, §5 Phase 1) 배선 — memory_provider와
    같은 "선택적 협력자 → 조건부 kwargs" 패턴을 따르는지 확인한다."""

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_no_checkpointer_provider_omits_checkpointer_kwarg_entirely(self, mock_create_root):
        """기본값(None)이면 예전과 동일하게 checkpointer 없이 돈다 — 기존 호출자
        (테스트 등)를 깨지 않는다."""
        mock_create_root.return_value = "GRAPH"
        factory, _ = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        self.assertNotIn("checkpointer", mock_create_root.call_args.kwargs)

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_checkpointer_provider_result_is_passed_to_create_root_graph(self, mock_create_root):
        mock_create_root.return_value = "GRAPH"
        provider = _FakeCheckpointerProvider()
        factory, _ = _factory(checkpointer_provider=provider)
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        self.assertEqual(mock_create_root.call_args.kwargs["checkpointer"], "FAKE_CHECKPOINTER")
        self.assertEqual(provider.get_calls, 1)

    @patch(f"{FACTORY_MODULE}.create_child_graph")
    def test_child_build_never_receives_a_checkpointer(self, mock_create_child):
        """Child에는 checkpointer 파라미터 자체가 없다(`create_child_graph`) —
        provider가 설정돼 있어도 `.get()`이 호출조차 안 되는지 확인한다."""
        mock_create_child.return_value = "CHILD_GRAPH"
        provider = _FakeCheckpointerProvider()
        factory, _ = _factory(checkpointer_provider=provider)
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context, allow_subagents=False)

        mock_create_child.assert_called_once()
        self.assertEqual(provider.get_calls, 0)


class BuildMemoryWiringTests(SimpleTestCase):
    """memory_provider 배선 — 2026-08-18, Phase 3(§4-8): `backend()`에 `account_id`가
    실제로 전달되는지, `memory_system_prompt`가 `create_root_graph`까지 그대로
    이어지는지 확인한다."""

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_no_memory_provider_omits_memory_kwargs_entirely(self, mock_create_root):
        """기본값(None)이면 예전과 동일하게 memory/backend/store 없이 돈다."""
        mock_create_root.return_value = "GRAPH"
        factory, _ = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        for key in ("memory", "backend", "store", "memory_system_prompt", "permissions"):
            self.assertNotIn(key, mock_create_root.call_args.kwargs)

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_context_account_id_is_passed_to_backend(self, mock_create_root):
        mock_create_root.return_value = "GRAPH"
        provider = _FakeMemoryProvider()
        factory, _ = _factory(memory_provider=provider)
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        self.assertEqual(
            provider.backend_calls,
            [{"team_id": "TM001", "agent_id": "AG001", "account_id": "AC001", "extra_routes": None}],
        )

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_memory_system_prompt_is_passed_to_create_root_graph(self, mock_create_root):
        mock_create_root.return_value = "GRAPH"
        provider = _FakeMemoryProvider()
        factory, _ = _factory(memory_provider=provider)
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        self.assertEqual(
            mock_create_root.call_args.kwargs["memory_system_prompt"], "FAKE_MEMORY_SYSTEM_PROMPT"
        )
        self.assertEqual(mock_create_root.call_args.kwargs["backend"], "FAKE_BACKEND")
        self.assertEqual(mock_create_root.call_args.kwargs["store"], "FAKE_STORE")
        self.assertEqual(provider.system_prompt_calls, 1)

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_permissions_kwarg_is_never_passed_even_with_memory_provider(
        self, mock_create_root
    ):
        """2026-08-19 — 팀 공유 메모리(`/memories/AGENTS.md`,
        `/memories/projects/*.md`)를 없애면서 `build_filesystem_permissions()`
        배선을 뺐다(정본: 2026-08-19_03_장기메모리_개인전용_최종구조.md §4). 그
        함수가 막던 "같은 팀 안에서 프로젝트 간 메모리 파일 접근"은 그 파일들
        자체가 더는 영구 저장에 안 가서 애초에 발생할 수 없다 — 격리할 대상이
        없어졌다. `middleware/permissions.py`의 함수 자체는 코드로 남아 있지만
        (다른 경로별 권한 제어가 필요해지면 재사용 대비), `factory.py`는 더
        이상 그걸 부르지 않는다 — memory_provider가 있어도 `context.project_id`
        가 있어도 `permissions`가 `create_root_graph`로 전달되지 않아야 한다."""
        mock_create_root.return_value = "GRAPH"
        provider = _FakeMemoryProvider()
        factory, _ = _factory(memory_provider=provider)
        context = RuntimeContext(
            account_id="AC001", team_id="TM001", role="leader", project_id="PJ001"
        )

        factory.build(definition=_definition(), context=context)

        self.assertNotIn("permissions", mock_create_root.call_args.kwargs)

    @patch(f"{FACTORY_MODULE}.create_child_graph")
    def test_child_build_never_touches_memory_provider(self, mock_create_child):
        """Child에는 memory 관련 파라미터 자체가 없다(`create_child_graph`) —
        provider가 설정돼 있어도 어떤 메서드도 호출되지 않는지 확인한다."""
        mock_create_child.return_value = "CHILD_GRAPH"
        provider = _FakeMemoryProvider()
        factory, _ = _factory(memory_provider=provider)
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context, allow_subagents=False)

        mock_create_child.assert_called_once()
        self.assertEqual(provider.backend_calls, [])
        self.assertEqual(provider.system_prompt_calls, 0)

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_memory_provider_adds_write_guard_to_root_middleware(self, mock_create_root):
        """2026-08-19, §1순위 — memory_provider가 있으면 write_guard
        (`MemoryWriteGuardMiddleware`)가 `custom_middleware`에 더해져
        `create_root_graph`로 간다."""
        from services.agent_runtime.memory.write_guard import MemoryWriteGuardMiddleware

        mock_create_root.return_value = "GRAPH"
        provider = _FakeMemoryProvider()
        factory, _ = _factory(memory_provider=provider)
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        middleware = mock_create_root.call_args.kwargs["middleware"]
        guards = [m for m in middleware if isinstance(m, MemoryWriteGuardMiddleware)]
        self.assertEqual(len(guards), 1)

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_no_memory_provider_omits_write_guard_from_root_middleware(self, mock_create_root):
        """막을 개인 장기 메모리 자체가 없으면(memory_provider 없음) write_guard도
        붙일 이유가 없다."""
        from services.agent_runtime.memory.write_guard import MemoryWriteGuardMiddleware

        mock_create_root.return_value = "GRAPH"
        factory, _ = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        middleware = mock_create_root.call_args.kwargs["middleware"]
        self.assertFalse(any(isinstance(m, MemoryWriteGuardMiddleware) for m in middleware))

    @patch(f"{FACTORY_MODULE}.create_child_graph")
    def test_child_build_never_receives_write_guard(self, mock_create_child):
        """Child는 진짜 StoreBackend가 없어(`2026-08-15_02` §2) write_guard가
        필요 없다 — memory_provider가 설정돼 있어도 Child의 middleware
        목록에는 안 들어간다."""
        from services.agent_runtime.memory.write_guard import MemoryWriteGuardMiddleware

        mock_create_child.return_value = "CHILD_GRAPH"
        provider = _FakeMemoryProvider()
        factory, _ = _factory(memory_provider=provider)
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context, allow_subagents=False)

        middleware = mock_create_child.call_args.kwargs["middleware"]
        self.assertFalse(any(isinstance(m, MemoryWriteGuardMiddleware) for m in middleware))

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_write_guard_does_not_replace_existing_custom_middleware(self, mock_create_root):
        """write_guard는 `custom_middleware`에 더해지는 것이지 갈아 끼우는 게
        아니다 — 기존 미들웨어(예: `ModelCallLimitMiddleware`)가 그대로 남아
        있어야 한다."""
        from langchain.agents.middleware import ModelCallLimitMiddleware

        mock_create_root.return_value = "GRAPH"
        provider = _FakeMemoryProvider()
        factory, _ = _factory(memory_provider=provider)
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        middleware = mock_create_root.call_args.kwargs["middleware"]
        self.assertTrue(any(isinstance(m, ModelCallLimitMiddleware) for m in middleware))


class BuildWriteLockWiringTests(SimpleTestCase):
    """2026-08-19, §5순위 — memory_provider가 있으면 write_lock
    (`MemoryWriteLockMiddleware`)도 write_guard와 함께 Root middleware에
    더해지는지 확인한다."""

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_memory_provider_adds_write_lock_to_root_middleware(self, mock_create_root):
        from services.agent_runtime.memory.write_lock import MemoryWriteLockMiddleware

        mock_create_root.return_value = "GRAPH"
        provider = _FakeMemoryProvider()
        factory, _ = _factory(memory_provider=provider)
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        middleware = mock_create_root.call_args.kwargs["middleware"]
        locks = [m for m in middleware if isinstance(m, MemoryWriteLockMiddleware)]
        self.assertEqual(len(locks), 1)

    def test_write_lock_namespace_matches_memory_backend_call(self):
        """write_lock의 namespace가 `memory_provider.backend(...)`에 넘긴
        (team_id, agent_id, account_id)와 같은 값·순서인지 — 같은 저장 위치를
        가리켜야 락이 의미가 있다."""
        from services.agent_runtime.memory.write_lock import MemoryWriteLockMiddleware

        with patch(f"{FACTORY_MODULE}.create_root_graph") as mock_create_root:
            mock_create_root.return_value = "GRAPH"
            provider = _FakeMemoryProvider()
            factory, _ = _factory(memory_provider=provider)
            context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

            factory.build(definition=_definition(agent_id="AG777"), context=context)

            middleware = mock_create_root.call_args.kwargs["middleware"]
            lock = next(m for m in middleware if isinstance(m, MemoryWriteLockMiddleware))
            self.assertEqual(lock._namespace, ("TM001", "AG777", "AC001"))
            self.assertEqual(
                provider.backend_calls,
                [{"team_id": "TM001", "agent_id": "AG777", "account_id": "AC001", "extra_routes": None}],
            )

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_no_memory_provider_omits_write_lock_from_root_middleware(self, mock_create_root):
        from services.agent_runtime.memory.write_lock import MemoryWriteLockMiddleware

        mock_create_root.return_value = "GRAPH"
        factory, _ = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        middleware = mock_create_root.call_args.kwargs["middleware"]
        self.assertFalse(any(isinstance(m, MemoryWriteLockMiddleware) for m in middleware))

    @patch(f"{FACTORY_MODULE}.create_child_graph")
    def test_child_build_never_receives_write_lock(self, mock_create_child):
        """Child는 StoreBackend가 없어 잠글 대상이 없다 — write_guard와 같은 이유."""
        from services.agent_runtime.memory.write_lock import MemoryWriteLockMiddleware

        mock_create_child.return_value = "CHILD_GRAPH"
        provider = _FakeMemoryProvider()
        factory, _ = _factory(memory_provider=provider)
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context, allow_subagents=False)

        middleware = mock_create_child.call_args.kwargs["middleware"]
        self.assertFalse(any(isinstance(m, MemoryWriteLockMiddleware) for m in middleware))

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_write_guard_runs_outside_write_lock_in_middleware_order(self, mock_create_root):
        """write_guard가 write_lock보다 middleware 목록 앞쪽(=바깥쪽)에 있어야
        한다 — write_guard가 내용을 거부할 때는 Postgres 락을 잡을 필요조차
        없어야 하므로(langchain의 wrap_tool_call 체이닝은 목록 앞쪽이 바깥쪽,
        `_chain_tool_call_wrappers` 실제 소스)."""
        from services.agent_runtime.memory.write_guard import MemoryWriteGuardMiddleware
        from services.agent_runtime.memory.write_lock import MemoryWriteLockMiddleware

        mock_create_root.return_value = "GRAPH"
        provider = _FakeMemoryProvider()
        factory, _ = _factory(memory_provider=provider)
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        middleware = mock_create_root.call_args.kwargs["middleware"]
        guard_index = next(i for i, m in enumerate(middleware) if isinstance(m, MemoryWriteGuardMiddleware))
        lock_index = next(i for i, m in enumerate(middleware) if isinstance(m, MemoryWriteLockMiddleware))
        self.assertLess(guard_index, lock_index)


class BuildSkillsWiringTests(SimpleTestCase):
    """skills_provider 배선(2026-08-21, 2026-08-25 memory 독립화) — 정본:
    2026-08-20_16_Skill_Middleware_설계.md.

    2026-08-25부터 Skill은 memory_provider 유무와 무관하게 skills_provider만
    있으면 붙는다 — memory_provider가 있으면 Memory가 만든 공유 backend에
    얹히고, 없으면 Skill 전용 backend를 따로 만든다(`build()`의 "공유
    backend/스토어" 절 참고). 아래 테스트들이 두 경로 다 확인한다.
    """

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_no_skills_provider_omits_skills_kwarg(self, mock_create_root):
        mock_create_root.return_value = "GRAPH"
        provider = _FakeMemoryProvider()
        factory, _ = _factory(memory_provider=provider)
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        self.assertNotIn("skills", mock_create_root.call_args.kwargs)
        # skills_provider가 없으면 이제 `skills_system_prompt` 키 자체를 안
        # 넣는다 — `create_root_graph`의 기본값(`None`)과 같아 무해하다.
        self.assertIsNone(mock_create_root.call_args.kwargs.get("skills_system_prompt"))
        gp_spec = mock_create_root.call_args.kwargs["subagents"][0]
        self.assertNotIn("skills", gp_spec)

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_skills_provider_without_memory_provider_still_wires_skills(self, mock_create_root):
        """2026-08-25 — memory_provider가 없어도 skills_provider만 있으면
        Skill 전용 backend를 따로 만들어 붙인다(더 이상 memory에 종속되지
        않는다)."""
        mock_create_root.return_value = "GRAPH"
        skills_provider = _FakeSkillsProvider()
        factory, _ = _factory(skills_provider=skills_provider)
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        self.assertEqual(
            mock_create_root.call_args.kwargs["skills"], ["/skills/personal/", "/skills/team/"]
        )
        self.assertEqual(mock_create_root.call_args.kwargs["skills_system_prompt"], "FAKE_SKILLS_SYSTEM_PROMPT")
        self.assertEqual(skills_provider.sources_calls, 1)
        self.assertEqual(len(skills_provider.routes_calls), 1)
        self.assertEqual(skills_provider.system_prompt_calls, 1)
        self.assertEqual(skills_provider.store_calls, 1)
        # memory=/memory_system_prompt=는 memory_provider가 없으니 안 들어간다 —
        # backend/store만 있고 메모리 자체는 여전히 안 붙는다.
        self.assertNotIn("memory", mock_create_root.call_args.kwargs)
        self.assertNotIn("memory_system_prompt", mock_create_root.call_args.kwargs)
        self.assertEqual(mock_create_root.call_args.kwargs["store"], "FAKE_SKILLS_STORE")

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_skills_only_backend_has_no_memory_route(self, mock_create_root):
        """Skill 전용 backend에는 `/memories/users/` 경로가 없다 — 메모리가
        꺼진 채로 스킬만 켠 것이므로, Skill 라우트만 들어가야 한다."""
        from deepagents.backends import CompositeBackend

        mock_create_root.return_value = "GRAPH"
        skills_provider = _FakeSkillsProvider()
        factory, _ = _factory(skills_provider=skills_provider)
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        backend = mock_create_root.call_args.kwargs["backend"]
        self.assertIsInstance(backend, CompositeBackend)
        self.assertEqual(set(backend.routes.keys()), {"/skills/personal/", "/skills/team/"})

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_skill_register_sync_middleware_included_when_skills_present(self, mock_create_root):
        """2026-08-26 — 스킬이 붙는 경로(메모리 유무와 무관)라면 항상
        `SkillRegisterSyncMiddleware`도 같이 붙어야 한다."""
        from services.agent_runtime.skills.sync import SkillRegisterSyncMiddleware

        mock_create_root.return_value = "GRAPH"
        skills_provider = _FakeSkillsProvider()
        factory, _ = _factory(skills_provider=skills_provider)
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        middleware = mock_create_root.call_args.kwargs["middleware"]
        sync_mw = next(m for m in middleware if isinstance(m, SkillRegisterSyncMiddleware))
        self.assertEqual(sync_mw._backend, mock_create_root.call_args.kwargs["backend"])

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_skill_register_sync_middleware_omitted_when_no_skills(self, mock_create_root):
        from services.agent_runtime.skills.sync import SkillRegisterSyncMiddleware

        mock_create_root.return_value = "GRAPH"
        factory, _ = _factory(memory_provider=_FakeMemoryProvider())
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        middleware = mock_create_root.call_args.kwargs["middleware"]
        self.assertFalse(any(isinstance(m, SkillRegisterSyncMiddleware) for m in middleware))

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_root_receives_skill_sources_when_both_providers_present(self, mock_create_root):
        mock_create_root.return_value = "GRAPH"
        memory_provider = _FakeMemoryProvider()
        skills_provider = _FakeSkillsProvider()
        factory, _ = _factory(memory_provider=memory_provider, skills_provider=skills_provider)
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        self.assertEqual(
            mock_create_root.call_args.kwargs["skills"], ["/skills/personal/", "/skills/team/"]
        )

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_root_receives_skills_system_prompt_when_both_providers_present(self, mock_create_root):
        """2026-08-22, Skill 우선순위 규칙 배선 — `memory_system_prompt`와 같은
        조건(둘 다 있을 때만)에서 `skills_system_prompt`도 `create_root_graph`
        까지 그대로 전달되는지 확인한다."""
        mock_create_root.return_value = "GRAPH"
        memory_provider = _FakeMemoryProvider()
        skills_provider = _FakeSkillsProvider()
        factory, _ = _factory(memory_provider=memory_provider, skills_provider=skills_provider)
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        self.assertEqual(
            mock_create_root.call_args.kwargs["skills_system_prompt"], "FAKE_SKILLS_SYSTEM_PROMPT"
        )
        self.assertEqual(skills_provider.system_prompt_calls, 1)

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_general_purpose_receives_the_same_skill_sources_as_root(self, mock_create_root):
        """설계 문서 "Root/GP/Child" 절 — GP는 자동 상속이 없으므로 Root와 같은
        목록을 gp_spec에 명시적으로 채워야 한다."""
        mock_create_root.return_value = "GRAPH"
        memory_provider = _FakeMemoryProvider()
        skills_provider = _FakeSkillsProvider()
        factory, _ = _factory(memory_provider=memory_provider, skills_provider=skills_provider)
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        gp_spec = mock_create_root.call_args.kwargs["subagents"][0]
        self.assertEqual(gp_spec["skills"], mock_create_root.call_args.kwargs["skills"])

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_skill_routes_are_merged_into_memory_backend_call(self, mock_create_root):
        mock_create_root.return_value = "GRAPH"
        memory_provider = _FakeMemoryProvider()
        skills_provider = _FakeSkillsProvider()
        factory, _ = _factory(memory_provider=memory_provider, skills_provider=skills_provider)
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        self.assertEqual(
            memory_provider.backend_calls[0]["extra_routes"],
            {"/skills/personal/": "FAKE_PERSONAL_ROUTE", "/skills/team/": "FAKE_TEAM_ROUTE"},
        )
        self.assertEqual(skills_provider.routes_calls, [{"account_id": "AC001", "team_id": "TM001"}])

    @patch(f"{FACTORY_MODULE}.create_child_graph")
    def test_child_build_never_touches_skills_provider(self, mock_create_child):
        """Child는 skills 배선을 전혀 안 탄다 — 설계 문서대로 옵트인 없인 기본으로
        Skill이 안 붙는다."""
        mock_create_child.return_value = "CHILD_GRAPH"
        memory_provider = _FakeMemoryProvider()
        skills_provider = _FakeSkillsProvider()
        factory, _ = _factory(memory_provider=memory_provider, skills_provider=skills_provider)
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context, allow_subagents=False)

        self.assertNotIn("skills", mock_create_child.call_args.kwargs)
        self.assertEqual(skills_provider.routes_calls, [])


class BuildMcpToolCallTimeoutWiringTests(SimpleTestCase):
    """2026-08-21, A-1 — `McpToolCallTimeoutMiddleware`가 Root/Child 둘 다에
    붙는지(`middleware/factory.py.build()`를 통해서), 그리고 write_guard/
    write_lock보다 middleware 목록 앞쪽(=바깥쪽)에 있는지 확인한다.

    2026-08-19의 같은 이름 테스트는 전역 timeout(모든 도구 대상)을 검증했는데,
    그 설계가 `17e8c62`에서 되돌려지면서 import부터 깨져 있었다
    (`2026-08-21_01` §8). 새 설계에 맞춰 다시 썼다 — 순서 검증(아래 세 번째)은
    그대로 유효하다: MCP 도구 timeout이 write_guard/lock보다 바깥이어야
    "락을 잡은 채로 timeout을 기다리는" 상태가 안 생긴다.
    """

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_root_receives_mcp_tool_call_timeout_middleware(self, mock_create_root):
        from services.agent_runtime.middleware.tool_timeout import McpToolCallTimeoutMiddleware

        mock_create_root.return_value = "GRAPH"
        factory, _ = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        middleware = mock_create_root.call_args.kwargs["middleware"]
        self.assertEqual(sum(isinstance(m, McpToolCallTimeoutMiddleware) for m in middleware), 1)

    @patch(f"{FACTORY_MODULE}.create_child_graph")
    def test_child_receives_mcp_tool_call_timeout_middleware(self, mock_create_child):
        from services.agent_runtime.middleware.tool_timeout import McpToolCallTimeoutMiddleware

        mock_create_child.return_value = "CHILD_GRAPH"
        factory, _ = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context, allow_subagents=False)

        middleware = mock_create_child.call_args.kwargs["middleware"]
        self.assertEqual(sum(isinstance(m, McpToolCallTimeoutMiddleware) for m in middleware), 1)

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_timeout_is_outside_write_guard_and_write_lock(self, mock_create_root):
        from services.agent_runtime.memory.write_guard import MemoryWriteGuardMiddleware
        from services.agent_runtime.memory.write_lock import MemoryWriteLockMiddleware
        from services.agent_runtime.middleware.tool_timeout import McpToolCallTimeoutMiddleware

        mock_create_root.return_value = "GRAPH"
        provider = _FakeMemoryProvider()
        factory, _ = _factory(memory_provider=provider)
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        middleware = mock_create_root.call_args.kwargs["middleware"]
        timeout_index = next(
            i for i, m in enumerate(middleware) if isinstance(m, McpToolCallTimeoutMiddleware)
        )
        guard_index = next(i for i, m in enumerate(middleware) if isinstance(m, MemoryWriteGuardMiddleware))
        lock_index = next(i for i, m in enumerate(middleware) if isinstance(m, MemoryWriteLockMiddleware))
        self.assertLess(timeout_index, guard_index)
        self.assertLess(guard_index, lock_index)


class BuildBuiltinWriteLockWiringTests(SimpleTestCase):
    """2026-08-21, 병렬실행 Phase 3 — 내장 쓰기 도구 직렬화가 Root/Child 둘 다에
    붙는지, 그리고 timeout 미들웨어보다 **안쪽**인지.

    순서가 중요하다: 바깥이 되면 "락을 쥔 채 timeout을 기다리는" 조합이 생겨,
    이 설계가 MCP에서 피하려던 문제(커넥션을 오래 붙잡기)를 내장 도구 쪽에서
    다시 만든다.
    """

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_root_receives_builtin_write_lock(self, mock_create_root):
        from services.agent_runtime.middleware.builtin_write_lock import BuiltinWriteLockMiddleware

        mock_create_root.return_value = "GRAPH"
        factory, _ = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        middleware = mock_create_root.call_args.kwargs["middleware"]
        self.assertEqual(sum(isinstance(m, BuiltinWriteLockMiddleware) for m in middleware), 1)

    @patch(f"{FACTORY_MODULE}.create_child_graph")
    def test_child_receives_builtin_write_lock(self, mock_create_child):
        from services.agent_runtime.middleware.builtin_write_lock import BuiltinWriteLockMiddleware

        mock_create_child.return_value = "CHILD_GRAPH"
        factory, _ = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context, allow_subagents=False)

        middleware = mock_create_child.call_args.kwargs["middleware"]
        self.assertEqual(sum(isinstance(m, BuiltinWriteLockMiddleware) for m in middleware), 1)

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_builtin_write_lock_is_inside_the_timeout(self, mock_create_root):
        from services.agent_runtime.middleware.builtin_write_lock import BuiltinWriteLockMiddleware
        from services.agent_runtime.middleware.tool_timeout import McpToolCallTimeoutMiddleware

        mock_create_root.return_value = "GRAPH"
        factory, _ = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        middleware = mock_create_root.call_args.kwargs["middleware"]
        timeout_index = next(
            i for i, m in enumerate(middleware) if isinstance(m, McpToolCallTimeoutMiddleware)
        )
        lock_index = next(
            i for i, m in enumerate(middleware) if isinstance(m, BuiltinWriteLockMiddleware)
        )
        self.assertLess(timeout_index, lock_index)


class BuildFilesystemExclusionWiringTests(SimpleTestCase):
    """`fs_excluded_tools`(2026-08-18, §5 Phase 6) 배선 — memory/checkpointer와
    달리 선택적 협력자가 아니라 `runtime_policy`에서 항상 읽으므로, Root/Child
    둘 다 매번 넘기는지 확인한다."""

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_root_always_receives_runtime_policy_excluded_builtin_tools(self, mock_create_root):
        mock_create_root.return_value = "GRAPH"
        factory, _ = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        self.assertEqual(
            mock_create_root.call_args.kwargs["fs_excluded_tools"],
            RuntimeCapabilityPolicy().excluded_builtin_tools,
        )

    @patch(f"{FACTORY_MODULE}.create_child_graph")
    def test_child_always_receives_runtime_policy_excluded_builtin_tools(self, mock_create_child):
        mock_create_child.return_value = "CHILD_GRAPH"
        factory, _ = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context, allow_subagents=False)

        self.assertEqual(
            mock_create_child.call_args.kwargs["fs_excluded_tools"],
            RuntimeCapabilityPolicy().excluded_builtin_tools,
        )

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_custom_runtime_policy_value_is_passed_through(self, mock_create_root):
        mock_create_root.return_value = "GRAPH"
        custom_policy = RuntimeCapabilityPolicy(excluded_builtin_tools=frozenset({"delete", "execute"}))
        factory, _ = _factory(
            runtime_policy=custom_policy,
            middleware_factory=MiddlewareFactory(runtime_policy=custom_policy),
        )
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        self.assertEqual(
            mock_create_root.call_args.kwargs["fs_excluded_tools"], frozenset({"delete", "execute"})
        )


class BuildInterruptOnWiringTests(SimpleTestCase):
    """`interrupt_on`(2026-08-18, §5 Phase 7) 배선 — `checkpointer_provider`가
    있을 때만 만든다(`HumanInTheLoopMiddleware.interrupt()`는 Checkpointer 없이
    재개가 안 되므로). `_fake_tools()`는 `document_search`(side_effect=False)와
    `task_register`(side_effect=True) 둘을 반환한다 — 후자만 남는다. `delete`는
    `runtime_policy.py`가 항상 부수효과 도구로 취급해 별도로 더해진다
    (2026-08-26, `DEFAULT_EXCLUDED_BUILTIN_TOOLS`에서 뺀 것과 같은 결정)."""

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_no_checkpointer_provider_interrupt_on_stays_none(self, mock_create_root):
        mock_create_root.return_value = "GRAPH"
        factory, _ = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        self.assertIsNone(mock_create_root.call_args.kwargs["interrupt_on"])

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_checkpointer_provider_derives_interrupt_on_from_side_effect_tools_and_delete(
        self, mock_create_root
    ):
        mock_create_root.return_value = "GRAPH"
        factory, _ = _factory(checkpointer_provider=_FakeCheckpointerProvider())
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        self.assertEqual(
            mock_create_root.call_args.kwargs["interrupt_on"],
            {"task_register": True, "delete": True},
        )

    @patch(f"{FACTORY_MODULE}.create_child_graph")
    def test_child_also_receives_interrupt_on_when_checkpointer_provider_set(
        self, mock_create_child
    ):
        mock_create_child.return_value = "CHILD_GRAPH"
        factory, _ = _factory(checkpointer_provider=_FakeCheckpointerProvider())
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context, allow_subagents=False)

        self.assertEqual(
            mock_create_child.call_args.kwargs["interrupt_on"],
            {"task_register": True, "delete": True},
        )

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_member_role_now_gets_interrupt_on_just_like_leader(
        self, mock_create_root
    ):
        """**2026-08-20부터 member도 `write_tool_allowed_roles`에 들어간다**
        (`17e8c62`). 그래서 `interrupt_on`도 leader와 똑같이 채워진다 —
        member가 `task_register`를 부르면 즉시 거부되는 게 아니라 승인 카드가
        뜨고, 본인이 승인해야 실행된다(자기 승인).

        예전 이 테스트는 정반대(`interrupt_on is None`)를 검증했고, 그 근거는
        "승인 카드를 띄우면 부른 본인이 눌러 승인해 버려서 권한 경계가
        뚫린다"였다. 그 판단이 2026-08-20에 뒤집혔다 — "팀원이 자기 업무를
        직접 등록할 수 있게 하고 싶다"는 요구를 받아 자기 승인을 허용하기로
        했다. 배경과 그 대가(호출별 승인 UI를 Phase 2로 앞당김)는
        `docs/설계 및 구현/3_중간발표 이후/작업기록/Deep_Agents/2026-08-21_02_MCP_승인_범위_변경_반영.md`.
        """

        mock_create_root.return_value = "GRAPH"
        factory, _ = _factory(checkpointer_provider=_FakeCheckpointerProvider())
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="member")

        factory.build(definition=_definition(), context=context)

        interrupt_on = mock_create_root.call_args.kwargs["interrupt_on"]
        self.assertIsNotNone(interrupt_on)
        self.assertIn("task_register", interrupt_on)

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_member_team_skill_registration_skips_confirmation_but_personal_still_requires_it(
        self, mock_create_root
    ):
        mock_create_root.return_value = "GRAPH"
        factory, _ = _factory(
            checkpointer_provider=_FakeCheckpointerProvider(),
            tool_loader=_SkillToolLoader(),
        )
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="member")

        factory.build(definition=_definition(), context=context)

        config = mock_create_root.call_args.kwargs["interrupt_on"]["skill_register"]
        def request(scope):
            return SimpleNamespace(tool_call={"args": {"scope": scope}})

        self.assertFalse(config["when"](request("TEAM")))
        self.assertTrue(config["when"](request("PERSONAL")))

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_leader_team_skill_registration_still_requires_confirmation(self, mock_create_root):
        mock_create_root.return_value = "GRAPH"
        factory, _ = _factory(
            checkpointer_provider=_FakeCheckpointerProvider(),
            tool_loader=_SkillToolLoader(),
        )
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        config = mock_create_root.call_args.kwargs["interrupt_on"]["skill_register"]
        request = SimpleNamespace(tool_call={"args": {"scope": "TEAM"}})
        self.assertTrue(config["when"](request))

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_member_skill_register_description_exposes_current_role_and_team_restriction(
        self, mock_create_root
    ):
        mock_create_root.return_value = "GRAPH"
        factory, _ = _factory(tool_loader=_SkillToolLoader())
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="member")

        factory.build(definition=_definition(), context=context)

        skill_tool = next(
            tool for tool in mock_create_root.call_args.kwargs["tools"] if tool.name == "skill_register"
        )
        self.assertIn("현재 요청자 역할은 'member'", skill_tool.description)
        self.assertIn("TEAM 범위로 호출하지 마세요", skill_tool.description)
