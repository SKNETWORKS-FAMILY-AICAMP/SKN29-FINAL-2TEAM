"""tools/loader.py(ToolLoader) 테스트.

`adapt_builtin_tools()`는 지연 import라 mock으로 대체해 ToolLoader 자신의
로직(요청한 tool_refs만 골라내기, agent_model 전달, 없는 ref는 명시적으로
실패)만 검증한다 — 어댑터 자체의 정확성은 test_adapters.py가 본다.
"""

from unittest.mock import patch

from django.test import SimpleTestCase

from services.agent_runtime.context import RuntimeContext
from services.agent_runtime.exceptions import ToolUnavailableError
from services.agent_runtime.tools.loader import (
    Tool,
    ToolLoader,
    model_safe_tool_name,
    tool_ref_from_model_name,
)

# ToolLoader.load()는 services.harness.registry의 거대한 의존성 체인을 모듈
# import 시점에 끌어오지 않으려고 adapt_builtin_tools를 메서드 본문 안에서
# 지연 import한다(factory.py의 DependencyGraphSource.load()와 동일한 패턴).
# 그래서 이 이름은 loader.py의 모듈 속성으로 존재하지 않고, patch도 실제
# 정의/조회 대상인 adapters 모듈을 겨눠야 한다.
ADAPTERS_MODULE = "services.agent_runtime.tools.adapters"


def _fake_tool(ref: str) -> Tool:
    return Tool(ref=ref, name=ref, description="", input_schema={}, handler=lambda **_: None)


def _context() -> RuntimeContext:
    return RuntimeContext(account_id="AC1", team_id="TM1", role="leader")


class LoadTests(SimpleTestCase):
    def test_returns_only_requested_refs_in_requested_order(self):
        available = (_fake_tool("a"), _fake_tool("b"), _fake_tool("c"))
        with patch(f"{ADAPTERS_MODULE}.adapt_builtin_tools", return_value=available) as mock_adapt:
            result = ToolLoader().load(tool_refs=("c", "a"), context=_context())

        self.assertEqual([t.ref for t in result], ["c", "a"])
        mock_adapt.assert_called_once_with(agent_model=None)

    def test_passes_agent_model_through_to_adapter(self):
        with patch(f"{ADAPTERS_MODULE}.adapt_builtin_tools", return_value=(_fake_tool("task_extraction"),)) as mock_adapt:
            ToolLoader().load(
                tool_refs=("task_extraction",), context=_context(), agent_model="claude-sonnet-5"
            )

        mock_adapt.assert_called_once_with(agent_model="claude-sonnet-5")

    def test_missing_ref_raises_tool_unavailable_error(self):
        with patch(f"{ADAPTERS_MODULE}.adapt_builtin_tools", return_value=(_fake_tool("a"),)):
            with self.assertRaises(ToolUnavailableError):
                ToolLoader().load(tool_refs=("a", "nonexistent"), context=_context())

    def test_missing_ref_error_names_the_missing_ref(self):
        with patch(f"{ADAPTERS_MODULE}.adapt_builtin_tools", return_value=()):
            with self.assertRaises(ToolUnavailableError) as ctx:
                ToolLoader().load(tool_refs=("mystery_tool",), context=_context())

        self.assertIn("mystery_tool", str(ctx.exception))

    def test_mcp_ref_is_loaded_via_adapt_mcp_tools_when_requested(self):
        """`mcp:` 접두사 tool_ref가 요청되면 adapt_mcp_tools()로 팀의 MCP 도구를
        함께 조회해 반환한다(2026-08-14 연결)."""
        mcp_tool = _fake_tool("mcp:MT001")
        with patch(f"{ADAPTERS_MODULE}.adapt_builtin_tools", return_value=(_fake_tool("document_search"),)):
            with patch(f"{ADAPTERS_MODULE}.adapt_mcp_tools", return_value=(mcp_tool,)) as mock_mcp:
                result = ToolLoader().load(
                    tool_refs=("document_search", "mcp:MT001"), context=_context()
                )

        self.assertEqual([t.ref for t in result], ["document_search", "mcp:MT001"])
        mock_mcp.assert_called_once_with(team_id="TM1")

    def test_mcp_tools_are_not_queried_when_no_mcp_ref_requested(self):
        """내장 도구만 쓰는 요청은 MCP 조회(DB 왕복)를 하지 않는다."""
        with patch(f"{ADAPTERS_MODULE}.adapt_builtin_tools", return_value=(_fake_tool("document_search"),)):
            with patch(f"{ADAPTERS_MODULE}.adapt_mcp_tools") as mock_mcp:
                ToolLoader().load(tool_refs=("document_search",), context=_context())

        mock_mcp.assert_not_called()

    def test_unregistered_mcp_ref_is_skipped_not_fatal(self):
        """없는 `mcp:` 도구는 **건너뛰고 나머지로 돈다**(2026-08-22 변경).

        전에는 `ToolUnavailableError`로 막았다. 그때는 운영자가 MCP 서버를
        지우면 레거시 `agent_tool`에서 그 참조도 같이 지워 줘서 이 상황 자체가
        잘 안 생겼는데, 레거시 스키마를 폐기하면서 그 청소부가 없어졌다 —
        신규 `agent_version_tools`는 발행된 버전의 일부라 불변이라(02 §5.2)
        참조를 그 자리에서 지울 수 없다. 없는 서버의 도구 하나 때문에 에이전트
        전체가 못 도는 것보다, 그 도구만 빼고 도는 편이 낫다.
        """
        with patch(f"{ADAPTERS_MODULE}.adapt_builtin_tools", return_value=(_fake_tool("document_search"),)):
            with patch(f"{ADAPTERS_MODULE}.adapt_mcp_tools", return_value=()):
                result = ToolLoader().load(
                    tool_refs=("document_search", "mcp:unknown"), context=_context()
                )

        self.assertEqual([t.ref for t in result], ["document_search"])

    def test_unregistered_builtin_ref_still_raises_tool_unavailable_error(self):
        """내장 도구는 그대로 막는다 — 그건 운영 변경이 아니라 **정의가 틀린**
        것이고(오타·없어진 tool id), 조용히 빼면 에이전트가 이유 없이 다르게
        행동한다."""
        with patch(f"{ADAPTERS_MODULE}.adapt_builtin_tools", return_value=()):
            with self.assertRaises(ToolUnavailableError) as ctx:
                ToolLoader().load(tool_refs=("없는_내장도구",), context=_context())

        self.assertIn("없는_내장도구", str(ctx.exception))

    def test_empty_tool_refs_returns_empty_tuple(self):
        with patch(f"{ADAPTERS_MODULE}.adapt_builtin_tools", return_value=(_fake_tool("a"),)):
            result = ToolLoader().load(tool_refs=(), context=_context())

        self.assertEqual(result, ())

    def test_image_search_is_blocked_for_text_only_model(self):
        with patch(
            "services.agent_runtime.models.capabilities.supports_image_input",
            return_value=False,
        ), self.assertRaises(ToolUnavailableError):
            ToolLoader().load(
                tool_refs=("document_search_with_images",),
                context=_context(),
                agent_model="custom-text-model",
            )

    def test_image_search_is_loaded_for_image_capable_model(self):
        image_tool = _fake_tool("document_search_with_images")
        with patch(
            "services.agent_runtime.models.capabilities.supports_image_input",
            return_value=True,
        ), patch(
            f"{ADAPTERS_MODULE}.adapt_builtin_tools", return_value=(image_tool,)
        ):
            result = ToolLoader().load(
                tool_refs=("document_search_with_images",),
                context=_context(),
                agent_model="custom-vlm",
            )

        self.assertEqual([tool.ref for tool in result], ["document_search_with_images"])


class ToolNameManglingTests(SimpleTestCase):
    """model_safe_tool_name()/tool_ref_from_model_name() — OpenAI 함수 이름
    제약(`^[a-zA-Z0-9_-]+$`) 때문에 `mcp:<id>` 콜론을 치환하는 왕복 변환
    (2026-08-14 MCP 연결과 함께 추가 — factory.py._to_langchain_tool()이 씀)."""

    def test_colon_is_replaced_with_double_underscore(self):
        self.assertEqual(model_safe_tool_name("mcp:MT001"), "mcp__MT001")

    def test_round_trip_recovers_original_tool_ref(self):
        self.assertEqual(tool_ref_from_model_name(model_safe_tool_name("mcp:MT001")), "mcp:MT001")

    def test_refs_without_colon_pass_through_unchanged(self):
        self.assertEqual(model_safe_tool_name("document_search"), "document_search")
        self.assertEqual(tool_ref_from_model_name("document_search"), "document_search")
