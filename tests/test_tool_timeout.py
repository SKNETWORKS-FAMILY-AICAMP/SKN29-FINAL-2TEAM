"""middleware/tool_timeout.py(McpToolCallTimeoutMiddleware) 단위 테스트.

정본: `docs/설계 및 구현/중간발표 이후/작업기록/Deep_Agents/2026-08-21_01_Tool_timeout_재설계.md`

`ToolCallRequest`는 실제 `langchain.agents.middleware.types` 클래스를 그대로
쓴다(mock 아님) — `test_memory_write_guard.py`와 같은 관례. 실제 시간을
기다리는 걸 피하려고, 느린 handler는 `threading.Event`로 "타임아웃이 지날
때까지 붙잡아 두는" 최소 시간만 잠들게 하고, 짧은 timeout(0.05초 등)을 써서
전체 스위트가 느려지지 않게 한다.

**2026-08-21 재작성**: 이 파일은 2026-08-19의 전역 300초 설계
(`ToolCallTimeoutMiddleware`, 모든 도구 대상)를 검증하고 있었는데, 그 모듈이
`17e8c62`에서 삭제되면서 import 자체가 깨진 채로 남아 있었다. 새 설계
(MCP 도구 전용, gunicorn 한도에서 역산한 값)에 맞춰 다시 썼다 — "MCP가
아닌 호출은 건드리지 않는다"가 이 파일의 새 핵심 검증 항목이다.
"""

import threading
import time
from unittest.mock import Mock

from django.test import SimpleTestCase
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage

from services.agent_runtime.middleware.tool_timeout import (
    McpToolCallTimeoutMiddleware,
    build_mcp_tool_call_timeout_middleware,
)
from services.agent_runtime.runtime_policy import RuntimeCapabilityPolicy


def _request(*, name: str, args: dict | None = None, tool_call_id: str = "call-1") -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "args": args or {}, "id": tool_call_id}, tool=None, state={}, runtime=None
    )


def _slow_handler(started: threading.Event | None = None, seconds: float = 2):
    def _slow(_request):
        if started is not None:
            started.set()
        time.sleep(seconds)
        return "too-late"

    return _slow


class BuildMcpToolCallTimeoutMiddlewareTests(SimpleTestCase):
    def test_returns_a_configured_middleware(self):
        policy = RuntimeCapabilityPolicy()

        middleware = build_mcp_tool_call_timeout_middleware(runtime_policy=policy)

        self.assertIsInstance(middleware, McpToolCallTimeoutMiddleware)
        self.assertIs(middleware._runtime_policy, policy)


class NonMcpToolsAreNotTouchedTests(SimpleTestCase):
    """2026-08-21 재설계의 핵심 — 내장 도구는 이 미들웨어의 대상이 아니다.

    `2026-08-21_01` §3: 내장 도구는 우리가 코드를 직접 쓰므로 필요하면 그
    도구 자신이 timeout을 갖는 게 맞다. 플랫폼이 또 다른 값을 얹으면 두
    값이 어긋날 뿐이다.
    """

    def test_builtin_tool_is_passed_straight_through(self):
        policy = RuntimeCapabilityPolicy(mcp_tool_call_timeout_seconds=5)
        middleware = McpToolCallTimeoutMiddleware(runtime_policy=policy)
        handler = Mock(return_value="handled")
        request = _request(name="document_search", args={"query": "q"})

        result = middleware.wrap_tool_call(request, handler)

        handler.assert_called_once_with(request)
        self.assertEqual(result, "handled")

    def test_slow_builtin_tool_is_not_cut_off(self):
        """내장 도구가 아무리 느려도 이 미들웨어는 끊지 않는다 — 아예
        executor에 넘기지도 않고 그대로 부른다."""
        policy = RuntimeCapabilityPolicy(mcp_tool_call_timeout_seconds=0.05)
        middleware = McpToolCallTimeoutMiddleware(runtime_policy=policy)
        request = _request(name="document_search")

        result = middleware.wrap_tool_call(request, _slow_handler(seconds=0.2))

        self.assertEqual(result, "too-late")

    def test_task_delegation_is_passed_straight_through(self):
        """`task`(Child 위임)도 MCP가 아니므로 대상이 아니다."""
        policy = RuntimeCapabilityPolicy(mcp_tool_call_timeout_seconds=5)
        middleware = McpToolCallTimeoutMiddleware(runtime_policy=policy)
        handler = Mock(return_value="delegated")

        result = middleware.wrap_tool_call(_request(name="task"), handler)

        handler.assert_called_once()
        self.assertEqual(result, "delegated")


class McpFastHandlerPassthroughTests(SimpleTestCase):
    def test_result_within_timeout_is_returned_unchanged(self):
        policy = RuntimeCapabilityPolicy(mcp_tool_call_timeout_seconds=5)
        middleware = McpToolCallTimeoutMiddleware(runtime_policy=policy)
        handler = Mock(return_value="handled")
        request = _request(name="mcp__MT001", args={"query": "q"})

        result = middleware.wrap_tool_call(request, handler)

        handler.assert_called_once_with(request)
        self.assertEqual(result, "handled")


class McpTimeoutExceededTests(SimpleTestCase):
    def test_slow_mcp_handler_returns_error_tool_message_without_waiting_full_duration(self):
        policy = RuntimeCapabilityPolicy(mcp_tool_call_timeout_seconds=0.05)
        middleware = McpToolCallTimeoutMiddleware(runtime_policy=policy)
        started = threading.Event()
        request = _request(name="mcp__MT001", tool_call_id="call-42")

        start = time.monotonic()
        result = middleware.wrap_tool_call(request, _slow_handler(started))
        elapsed = time.monotonic() - start

        self.assertTrue(started.wait(timeout=1))
        self.assertLess(elapsed, 1.5)  # 2초를 다 기다리지 않았는지
        self.assertIsInstance(result, ToolMessage)
        self.assertEqual(result.status, "error")
        self.assertEqual(result.tool_call_id, "call-42")
        self.assertEqual(result.name, "mcp__MT001")
        self.assertIn("0.05", result.content)

    def test_timeout_message_says_execution_is_unconfirmed_and_forbids_auto_retry(self):
        """`2026-08-21_03` §4.1 — timeout은 "실패"가 아니라 "결과를 모름"이다.
        모델이 무단 재시도해서 중복 실행이 나지 않게 문구로 막는다(프롬프트
        수준 방어라 강제는 아니지만, 문구 자체는 계약으로 고정한다)."""
        policy = RuntimeCapabilityPolicy(mcp_tool_call_timeout_seconds=0.05)
        middleware = McpToolCallTimeoutMiddleware(runtime_policy=policy)

        result = middleware.wrap_tool_call(_request(name="mcp__MT001"), _slow_handler())

        self.assertIn("확인되지 않았습니다", result.content)
        self.assertIn("자동으로 다시 시도하지", result.content)

    def test_mcp_tool_name_is_reversed_to_ref_before_looking_up_timeout(self):
        """`mcp__MT001`처럼 모델에 나간 이름(`model_safe_tool_name`이 콜론을
        `__`로 바꾼 형태)은 override 조회 전에 `tool_ref_from_model_name`으로
        되돌려야 한다 — 그래야 `mcp_tool_call_timeout_overrides`에 원래
        tool_ref(`mcp:MT001`)로 등록해 둔 값이 실제로 걸린다."""
        policy = RuntimeCapabilityPolicy(
            mcp_tool_call_timeout_seconds=5, mcp_tool_call_timeout_overrides={"mcp:MT001": 0.05}
        )
        middleware = McpToolCallTimeoutMiddleware(runtime_policy=policy)
        started = threading.Event()

        result = middleware.wrap_tool_call(_request(name="mcp__MT001"), _slow_handler(started))

        self.assertTrue(started.wait(timeout=1))
        self.assertIsInstance(result, ToolMessage)
        self.assertEqual(result.status, "error")

    def test_mcp_tool_without_override_keeps_using_default(self):
        policy = RuntimeCapabilityPolicy(
            mcp_tool_call_timeout_seconds=5, mcp_tool_call_timeout_overrides={"mcp:MT001": 0.05}
        )
        middleware = McpToolCallTimeoutMiddleware(runtime_policy=policy)
        handler = Mock(return_value="handled")
        request = _request(name="mcp__MT999")

        result = middleware.wrap_tool_call(request, handler)

        handler.assert_called_once_with(request)
        self.assertEqual(result, "handled")


class InjectedExecutorTests(SimpleTestCase):
    """공유 pool이 아니라 테스트가 주입한 executor를 실제로 쓰는지 — pool 자체가
    좁아 대기(queue)로 인해 timeout이 걸리는 경우까지 재현 가능해야 한다."""

    def test_uses_injected_executor_instead_of_shared_pool(self):
        from concurrent.futures import ThreadPoolExecutor

        policy = RuntimeCapabilityPolicy(mcp_tool_call_timeout_seconds=5)
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            middleware = McpToolCallTimeoutMiddleware(runtime_policy=policy, executor=executor)
            handler = Mock(return_value="handled")
            request = _request(name="mcp__MT001")

            result = middleware.wrap_tool_call(request, handler)

            self.assertEqual(result, "handled")
            self.assertIs(middleware._executor, executor)
        finally:
            executor.shutdown(wait=False)
