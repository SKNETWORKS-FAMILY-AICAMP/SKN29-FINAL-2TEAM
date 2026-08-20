"""middleware/tool_timeout.py(ToolCallTimeoutMiddleware) 단위 테스트.

`ToolCallRequest`는 실제 `langchain.agents.middleware.types` 클래스를 그대로
쓴다(mock 아님) — `test_memory_write_guard.py`와 같은 관례. 실제 시간을
기다리는 걸 피하려고, 느린 handler는 `threading.Event`로 "타임아웃이 지날
때까지 붙잡아 두는" 최소 시간만 잠들게 하고, 짧은 timeout(0.05초 등)을 써서
전체 스위트가 느려지지 않게 한다.
"""

import threading
import time
from unittest.mock import Mock

from django.test import SimpleTestCase
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage

from services.agent_runtime.middleware.tool_timeout import (
    ToolCallTimeoutMiddleware,
    build_tool_call_timeout_middleware,
)
from services.agent_runtime.runtime_policy import RuntimeCapabilityPolicy


def _request(*, name: str, args: dict | None = None, tool_call_id: str = "call-1") -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "args": args or {}, "id": tool_call_id}, tool=None, state={}, runtime=None
    )


class BuildToolCallTimeoutMiddlewareTests(SimpleTestCase):
    def test_returns_a_configured_middleware(self):
        policy = RuntimeCapabilityPolicy()

        middleware = build_tool_call_timeout_middleware(runtime_policy=policy)

        self.assertIsInstance(middleware, ToolCallTimeoutMiddleware)
        self.assertIs(middleware._runtime_policy, policy)


class FastHandlerPassthroughTests(SimpleTestCase):
    def test_result_within_timeout_is_returned_unchanged(self):
        policy = RuntimeCapabilityPolicy(tool_call_timeout_seconds=5)
        middleware = ToolCallTimeoutMiddleware(runtime_policy=policy)
        handler = Mock(return_value="handled")
        request = _request(name="document_search", args={"query": "q"})

        result = middleware.wrap_tool_call(request, handler)

        handler.assert_called_once_with(request)
        self.assertEqual(result, "handled")

    def test_mcp_tool_name_is_reversed_to_ref_before_looking_up_timeout(self):
        """`document__MT001`처럼 모델에 나간 이름(`model_safe_tool_name`이
        콜론을 `__`로 바꾼 형태)은 override 조회 전에 `tool_ref_from_model_name`으로
        되돌려야 한다 — 그래야 `tool_call_timeout_overrides`에 원래 tool_ref
        (`mcp:MT001`)로 등록해 둔 값이 실제로 걸린다."""
        policy = RuntimeCapabilityPolicy(
            tool_call_timeout_seconds=5, tool_call_timeout_overrides={"mcp:MT001": 0.05}
        )
        middleware = ToolCallTimeoutMiddleware(runtime_policy=policy)
        started = threading.Event()

        def _slow(_request):
            started.set()
            time.sleep(1)
            return "too-late"

        request = _request(name="mcp__MT001", args={})

        result = middleware.wrap_tool_call(request, _slow)

        self.assertTrue(started.wait(timeout=1))
        self.assertIsInstance(result, ToolMessage)
        self.assertEqual(result.status, "error")


class TimeoutExceededTests(SimpleTestCase):
    def test_slow_handler_returns_error_tool_message_without_waiting_full_duration(self):
        policy = RuntimeCapabilityPolicy(tool_call_timeout_seconds=0.05)
        middleware = ToolCallTimeoutMiddleware(runtime_policy=policy)
        started = threading.Event()

        def _slow(_request):
            started.set()
            time.sleep(2)
            return "too-late"

        request = _request(name="document_search", tool_call_id="call-42")

        start = time.monotonic()
        result = middleware.wrap_tool_call(request, _slow)
        elapsed = time.monotonic() - start

        self.assertTrue(started.wait(timeout=1))
        self.assertLess(elapsed, 1.5)  # 2초를 다 기다리지 않았는지
        self.assertIsInstance(result, ToolMessage)
        self.assertEqual(result.status, "error")
        self.assertEqual(result.tool_call_id, "call-42")
        self.assertEqual(result.name, "document_search")
        self.assertIn("0.05", result.content)

    def test_per_tool_override_is_used_over_default(self):
        policy = RuntimeCapabilityPolicy(
            tool_call_timeout_seconds=5, tool_call_timeout_overrides={"slow_tool": 0.05}
        )
        middleware = ToolCallTimeoutMiddleware(runtime_policy=policy)

        def _slow(_request):
            time.sleep(2)
            return "too-late"

        request = _request(name="slow_tool")

        result = middleware.wrap_tool_call(request, _slow)

        self.assertIsInstance(result, ToolMessage)
        self.assertEqual(result.status, "error")

    def test_tool_without_override_keeps_using_default_even_when_other_tool_has_override(self):
        policy = RuntimeCapabilityPolicy(
            tool_call_timeout_seconds=5, tool_call_timeout_overrides={"slow_tool": 0.05}
        )
        middleware = ToolCallTimeoutMiddleware(runtime_policy=policy)
        handler = Mock(return_value="handled")
        request = _request(name="document_search")

        result = middleware.wrap_tool_call(request, handler)

        handler.assert_called_once_with(request)
        self.assertEqual(result, "handled")


class InjectedExecutorTests(SimpleTestCase):
    """공유 pool이 아니라 테스트가 주입한 executor를 실제로 쓰는지 — pool 자체가
    좁아 대기(queue)로 인해 timeout이 걸리는 경우까지 재현 가능해야 한다."""

    def test_uses_injected_executor_instead_of_shared_pool(self):
        from concurrent.futures import ThreadPoolExecutor

        policy = RuntimeCapabilityPolicy(tool_call_timeout_seconds=5)
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            middleware = ToolCallTimeoutMiddleware(runtime_policy=policy, executor=executor)
            handler = Mock(return_value="handled")
            request = _request(name="document_search")

            result = middleware.wrap_tool_call(request, handler)

            self.assertEqual(result, "handled")
            self.assertIs(middleware._executor, executor)
        finally:
            executor.shutdown(wait=False)
