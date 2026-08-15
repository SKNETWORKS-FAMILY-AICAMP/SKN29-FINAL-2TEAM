"""factory.py(AgentRuntimeFactory, DependencyGraphSource) 단위 테스트.

model_config_resolver/model_factory/tool_loader는 Fake로 주입한다(02 §17.3 —
Mock으로 먼저 진행). compat.create_root_graph/create_child_graph는 patch해서
"Factory가 무엇을 넘기는가"만 검증한다 — deepagents가 그 인자로 실제 그래프를
잘 만드는지는 test_deepagents_compat.py/runtime_skeleton.py의 몫이다.
RuntimeCapabilityPolicy·MiddlewareFactory·validate_subagents는 실물을 그대로 쓴다.
"""

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
