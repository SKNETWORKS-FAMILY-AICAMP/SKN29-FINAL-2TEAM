"""factory.py(AgentRuntimeFactory, DependencyGraphSource) 단위 테스트.

model_config_resolver/model_factory/tool_loader는 Fake로 주입한다(02 §17.3 —
Mock으로 먼저 진행). compat.create_root_graph/create_child_graph는 patch해서
"Factory가 무엇을 넘기는가"만 검증한다 — deepagents가 그 인자로 실제 그래프를
잘 만드는지는 test_deepagents_compat.py/runtime_skeleton.py의 몫이다.
RuntimeCapabilityPolicy·MiddlewareFactory·validate_subagents는 실물을 그대로 쓴다.
"""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from services.agent_runtime.context import RuntimeContext
from services.agent_runtime.definitions import AgentDefinition, SubagentDefinition, SubagentReference
from services.agent_runtime.exceptions import DelegationDepthError, ToolPermissionError
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
    """

    def __init__(self):
        self.paths_calls = 0
        self.backend_calls: list[dict] = []
        self.store_calls = 0
        self.system_prompt_calls = 0

    def paths(self):
        self.paths_calls += 1
        return ["/memories/users/preferences.md"]

    def backend(self, *, team_id: str, agent_id: str, account_id: str):
        self.backend_calls.append({"team_id": team_id, "agent_id": agent_id, "account_id": account_id})
        return "FAKE_BACKEND"

    def store(self):
        self.store_calls += 1
        return "FAKE_STORE"

    def system_prompt(self):
        self.system_prompt_calls += 1
        return "FAKE_MEMORY_SYSTEM_PROMPT"


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
    def test_member_loses_side_effect_tool(self, mock_create_root):
        mock_create_root.return_value = "GRAPH"
        factory, _ = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="member")

        factory.build(definition=_definition(), context=context)

        tools_arg = mock_create_root.call_args.kwargs["tools"]
        names = {t.name for t in tools_arg}
        self.assertEqual(names, {"document_search"})

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
    """실행 직전 RBAC 재검사(2026-08-14 추가) — `_to_langchain_tool()`을 직접
    호출해, `filter_tools_for_role()`(노출 시점)을 거치지 않은 경우에도 실행
    시점 자체에서 막히는지 확인한다. 이게 진짜 요점이다: 노출 필터가 이미
    걸러 준 정상 경로만 보면 이 방어선이 실제로 도는지 증명이 안 된다 —
    필터에 버그가 있었거나 새 Tool에 `side_effect` 표시를 빠뜨린 경우를
    가정한 시나리오다."""

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

    def test_member_calling_a_write_tool_directly_is_blocked_even_without_exposure_filter(self):
        tool = self._write_tool()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="member")
        langchain_tool = _to_langchain_tool(tool, context=context, runtime_policy=RuntimeCapabilityPolicy())

        with self.assertRaises(ToolPermissionError):
            langchain_tool.invoke({})

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


class SpeakableToolErrorTests(SimpleTestCase):
    """도구가 낸 **사람이 고칠 수 있는 사유**는 모델에게 돌려준다(2026-08-18 QA).

    그냥 올리면 LangGraph `ToolNode`가 실행을 통째로 죽이고, 화면에는 사유 없이
    「요청을 끝내지 못했습니다」만 남는다. 실제로 §B-0 ②에서 `task_extraction`이
    「어느 프로젝트의 업무를 뽑을지 정해지지 않았습니다. 프로젝트를 먼저
    고르세요.」라고 정확히 말했는데 **그 문장이 버려졌다.**

    기준은 레거시(`services/harness/runner.SPEAKABLE_ERRORS`)와 같은 목록을 쓴다 —
    두 엔진이 다른 목록을 들면 같은 실패가 한쪽에서만 설명된다.
    """

    def _tool(self, *, ref: str = "task_extraction", handler) -> Tool:
        return Tool(
            ref=ref,
            name=ref,
            description="업무를 뽑는다.",
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=handler,
            side_effect=False,
        )

    def _invoke(self, handler, *, ref: str = "task_extraction"):
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")
        langchain_tool = _to_langchain_tool(
            self._tool(ref=ref, handler=handler), context=context, runtime_policy=RuntimeCapabilityPolicy()
        )
        return langchain_tool.invoke({})

    def test_말할_수_있는_오류는_사유를_담아_돌려준다(self):
        """`{"error": ...}` 딕셔너리가 아니라 `ToolException`을 거쳐 문자열로 온다
        (2026-08-19 — main과 합의: 같은 목록을 쓰되, `ToolException` +
        `handle_tool_error=True`로 바꿔서 `tool_completed.status`가 OK로
        마스킹되지 않고 FAILED로 정확히 남게 했다. `factory.py`의 `_run()`
        docstring 주석 참고)."""
        from services.harness.registry import ToolInputError

        def boom(**_kwargs):
            raise ToolInputError("프로젝트를 먼저 고르세요.")

        self.assertEqual(self._invoke(boom), "프로젝트를 먼저 고르세요.")

    def test_repository_permission_denied_message_reaches_model(self):
        from backend.db.errors import PermissionDenied

        def boom(**_kwargs):
            raise PermissionDenied("팀에 속하지 않은 계정입니다.")

        self.assertEqual(self._invoke(boom, ref="document_list"), "팀에 속하지 않은 계정입니다.")

    def test_그_밖의_예외는_그대로_올린다(self):
        """라이브러리·드라이버 예외 문자열에는 쿼리·문서 원문·토큰이 섞일 수 있다 —
        삼키면 진짜 장애가 「도구가 뭐라고 했다」로 둔갑한다."""

        def boom(**_kwargs):
            raise RuntimeError("connection reset by peer")

        with self.assertRaises(RuntimeError):
            self._invoke(boom)

    def test_tool_input_error_message_reaches_model_instead_of_crashing(self):
        from services.harness.registry import ToolInputError

        def _handler(**kwargs):
            raise ToolInputError("어느 프로젝트의 업무인지 정해지지 않았습니다. 프로젝트를 먼저 고르세요.")

        tool = self._tool(ref="task_list", handler=_handler)
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")
        langchain_tool = _to_langchain_tool(tool, context=context, runtime_policy=RuntimeCapabilityPolicy())

        result = langchain_tool.invoke({})

        self.assertEqual(result, "어느 프로젝트의 업무인지 정해지지 않았습니다. 프로젝트를 먼저 고르세요.")


class ToolIdempotencyTests(SimpleTestCase):
    """Phase 8(외부 Write Tool Idempotency, 2026-08-19) — `_to_langchain_tool()`의
    `_run()`이 `tool.handler()`를 부르기 전에 `ToolCallRepository.
    find_successful_result()`로 이미 성공한 실행이 있는지 조회하는지 확인한다.

    `runtime`(langgraph가 실제 그래프 실행 중에만 채워 주는 `ToolRuntime`)은
    `langchain_tool.invoke({...})`로는 재현이 안 된다(실측 확인 — 그래프 밖
    호출은 항상 `runtime=None`). 그래서 `StructuredTool.func`(=`_run` 그 자체)를
    직접 불러서 `runtime`을 흉내 낸 값으로 넘긴다 — `_run()`의 판단 로직만
    본다는 뜻이고, `ToolRuntime` 주입 메커니즘 자체가 실제로 동작하는지는
    이 테스트의 범위가 아니다(직접 최소 재현 스크립트로 별도 확인했다)."""

    REPOSITORY = "backend.db.agent_platform.ToolCallRepository"

    def _write_tool(self, *, handler=None) -> Tool:
        return Tool(
            ref="task_register",
            name="task_register",
            description="업무를 등록한다.",
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=handler or (lambda **kwargs: "새로 등록됨"),
            side_effect=True,
        )

    def _read_tool(self, *, handler=None) -> Tool:
        return Tool(
            ref="document_list",
            name="document_list",
            description="문서 목록을 본다.",
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=handler or (lambda **kwargs: "새로 조회됨"),
            side_effect=False,
        )

    def _run_fn(self, tool: Tool, *, context: RuntimeContext):
        langchain_tool = _to_langchain_tool(tool, context=context, runtime_policy=RuntimeCapabilityPolicy())
        return langchain_tool.func

    @patch(REPOSITORY)
    def test_side_effect_tool_returns_cached_result_without_calling_handler(self, repo):
        repo.find_successful_result.return_value = "이미 등록된 결과"
        calls = []
        tool = self._write_tool(handler=lambda **kwargs: calls.append(1) or "새로 등록됨")
        context = RuntimeContext(
            account_id="AC001", team_id="TM001", role="leader", session_id="SESSION-1"
        )
        run_fn = self._run_fn(tool, context=context)

        result = run_fn(runtime=SimpleNamespace(tool_call_id="call-1"))

        self.assertEqual(result, "이미 등록된 결과")
        self.assertEqual(calls, [])  # handler가 아예 안 불렸다
        repo.find_successful_result.assert_called_once_with(
            session_id="SESSION-1", langchain_tool_call_id="call-1"
        )

    @patch(REPOSITORY)
    def test_side_effect_tool_calls_handler_when_nothing_cached(self, repo):
        repo.find_successful_result.return_value = None
        tool = self._write_tool()
        context = RuntimeContext(
            account_id="AC001", team_id="TM001", role="leader", session_id="SESSION-1"
        )
        run_fn = self._run_fn(tool, context=context)

        result = run_fn(runtime=SimpleNamespace(tool_call_id="call-1"))

        self.assertEqual(result, "새로 등록됨")

    @patch(REPOSITORY)
    def test_read_only_tool_never_checked(self, repo):
        """읽기 전용 도구는 대상에서 뺀다 — 다시 불러도 부작용이 없다."""
        tool = self._read_tool()
        context = RuntimeContext(
            account_id="AC001", team_id="TM001", role="leader", session_id="SESSION-1"
        )
        run_fn = self._run_fn(tool, context=context)

        result = run_fn(runtime=SimpleNamespace(tool_call_id="call-1"))

        self.assertEqual(result, "새로 조회됨")
        repo.find_successful_result.assert_not_called()

    @patch(REPOSITORY)
    def test_side_effect_tool_without_runtime_skips_check_and_still_executes(self, repo):
        """그래프 밖에서 직접 부르는 기존 경로(`langchain_tool.invoke({...})`) —
        `runtime`이 `None`이면 조회를 건너뛰고 평소대로 실행한다. 이 보호는
        "있으면 더 안전"이지 실행 자체를 막는 필수 조건이 아니다."""
        tool = self._write_tool()
        context = RuntimeContext(
            account_id="AC001", team_id="TM001", role="leader", session_id="SESSION-1"
        )
        langchain_tool = _to_langchain_tool(tool, context=context, runtime_policy=RuntimeCapabilityPolicy())

        result = langchain_tool.invoke({})

        self.assertEqual(result, "새로 등록됨")
        repo.find_successful_result.assert_not_called()

    @patch(REPOSITORY)
    def test_side_effect_tool_without_session_id_skips_check(self, repo):
        """session 없이 도는 실행(평가 스크립트 등) — session_id가 없으면 조회할
        범위 자체가 없으므로 건너뛴다."""
        tool = self._write_tool()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader", session_id=None)
        run_fn = self._run_fn(tool, context=context)

        result = run_fn(runtime=SimpleNamespace(tool_call_id="call-1"))

        self.assertEqual(result, "새로 등록됨")
        repo.find_successful_result.assert_not_called()

    @patch(REPOSITORY)
    def test_permission_check_runs_before_idempotency_check(self, repo):
        """캐시가 있어도 역할 권한이 없으면 여전히 막힌다 — 캐시된 결과가
        권한 검사를 우회하는 경로가 되면 안 된다."""
        repo.find_successful_result.return_value = "이미 등록된 결과"
        tool = self._write_tool()
        context = RuntimeContext(
            account_id="AC001", team_id="TM001", role="member", session_id="SESSION-1"
        )
        run_fn = self._run_fn(tool, context=context)

        with self.assertRaises(ToolPermissionError):
            run_fn(runtime=SimpleNamespace(tool_call_id="call-1"))

        repo.find_successful_result.assert_not_called()


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
    def test_root_middleware_reflects_definition_max_iterations(self, mock_create_root):
        from langchain.agents.middleware import ModelCallLimitMiddleware

        mock_create_root.return_value = "GRAPH"
        factory, _ = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(max_iterations=6), context=context)

        middleware_arg = mock_create_root.call_args.kwargs["middleware"]
        model_limit = next(m for m in middleware_arg if isinstance(m, ModelCallLimitMiddleware))
        self.assertEqual(model_limit.run_limit, 6)


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
        self.assertEqual(result, "CHILD_GRAPH")


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
            [{"team_id": "TM001", "agent_id": "AG001", "account_id": "AC001"}],
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
    `task_register`(side_effect=True) 둘을 반환한다 — 후자만 남아야 한다."""

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_no_checkpointer_provider_interrupt_on_stays_none(self, mock_create_root):
        mock_create_root.return_value = "GRAPH"
        factory, _ = _factory()
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        self.assertIsNone(mock_create_root.call_args.kwargs["interrupt_on"])

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_checkpointer_provider_derives_interrupt_on_from_side_effect_tools_only(
        self, mock_create_root
    ):
        mock_create_root.return_value = "GRAPH"
        factory, _ = _factory(checkpointer_provider=_FakeCheckpointerProvider())
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")

        factory.build(definition=_definition(), context=context)

        self.assertEqual(
            mock_create_root.call_args.kwargs["interrupt_on"], {"task_register": True}
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
            mock_create_child.call_args.kwargs["interrupt_on"], {"task_register": True}
        )

    @patch(f"{FACTORY_MODULE}.create_root_graph")
    def test_no_side_effect_tools_after_role_filter_leaves_interrupt_on_none(
        self, mock_create_root
    ):
        """member는 write_tool_allowed_roles(기본 leader만)에 안 들어 있어서
        `task_register`가 노출 시점에 이미 걸러진다 — 그 뒤에 남는 도구가 전부
        side_effect=False면 interrupt_on도 None이어야 한다."""

        mock_create_root.return_value = "GRAPH"
        factory, _ = _factory(checkpointer_provider=_FakeCheckpointerProvider())
        context = RuntimeContext(account_id="AC001", team_id="TM001", role="member")

        factory.build(definition=_definition(), context=context)

        self.assertIsNone(mock_create_root.call_args.kwargs["interrupt_on"])
