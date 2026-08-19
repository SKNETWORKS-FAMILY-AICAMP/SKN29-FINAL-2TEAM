"""모든 Tool 호출에 공통 timeout을 건다.

정본: `docs/작업기록/Deep_Agents/2026-08-19_01_실행_안정성_설계.md` §3
("타임아웃 / 취소 전파" 중 "Tool별 timeout"). `FilesystemMiddleware`는
`execute` 도구에만 `max_execute_timeout`(기본 3600초, 실제 소스 확인)이
있고 그 외 harness 내장 도구·MCP 도구에는 timeout 개념이 아예 없다(같은
문서). LangGraph 자체의 `Pregel.set_timeout()`/`step_timeout`은
`create_deep_agent()`가 공개 파라미터로 노출하지 않아 이 프로젝트에서
직접 못 쓴다(같은 문서 — 컴파일된 그래프 내부 구조에 의존해야 해서
위험하다고 판단) — 그래서 설계가 제안한 대로 우리 쪽 `wrap_tool_call`
미들웨어로 만든다.

**한계(정직하게 기록)**: `concurrent.futures.ThreadPoolExecutor` +
`future.result(timeout=...)`는 "기다리기를 포기"할 뿐 실행 중인 스레드를
강제로 죽이지 못한다(Python 자체의 한계 — 설계 문서 §3도 이 방식을 그대로
지정했다). 시간 초과로 포기한 뒤에도 그 handler는 백그라운드에서 계속
돌다가 나중에 끝난다 — 반환값은 버려지지만, 이미 시작된 부작용(예: 외부
API 호출)까지 취소되는 건 아니라는 뜻이다. 진짜 취소가 필요하면 handler
자신이 취소 신호를 받아 스스로 멈춰야 하는데, 그건 이 미들웨어의 범위를
넘는다 — 같은 설계 문서의 "Run 전체 wall-clock timeout + 취소 전파"는
별도 항목(계획 문서 7순위)으로 남아 있다.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import TYPE_CHECKING, Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import ToolMessage

from services.agent_runtime.tools.loader import tool_ref_from_model_name

if TYPE_CHECKING:
    from collections.abc import Callable

    from langchain.agents.middleware.types import ToolCallRequest

    from services.agent_runtime.runtime_policy import RuntimeCapabilityPolicy

#: 프로세스 전체에서 공유하는 실행기. 그래프(=요청)마다 새
#: `ThreadPoolExecutor`를 만들면 Django 워커가 오래 살아있는 동안 스레드가
#: 계속 쌓인다 — 요청이 끝나도 이 코드가 pool을 명시적으로 닫을 시점을 알
#: 방법이 없다(그래프 객체가 언제 GC되는지 통제 못 함). 그래서 미들웨어
#: 인스턴스가 아니라 모듈 레벨에 하나만 두고 프로세스 전체가 공유한다.
#: `max_workers`(정직하게 기록 — 실측으로 정한 값이 아니라 여유치다): 한
#: super-step 안에서 동시에 도는 tool_call 수(보통 한 자리 수)보다 넉넉히
#: 잡아 뒀다. 그 이상 요청이 한꺼번에 몰리면 이 pool 자체가 병목이 되어
#: "도구가 느리다"가 아니라 "이 pool에 줄을 서고 있다"는 이유로 timeout이
#: 걸릴 수 있다.
_MAX_WORKERS = 32
_executor: ThreadPoolExecutor | None = None


def _shared_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="tool-timeout")
    return _executor


class ToolCallTimeoutMiddleware(AgentMiddleware):
    """모든 Tool 호출을 `runtime_policy.timeout_for_tool()` 초 안에 못 끝내면
    `ToolMessage(status="error")`로 되돌린다 — 그래프 실행 자체를 죽이지
    않고 모델이 스스로 다시 판단하게 한다(모듈 docstring, 설계 문서 §3의
    판단 그대로).

    Root/Child/general-purpose 전부에 붙인다(`middleware/factory.py`) —
    "harness 내장 도구·MCP 도구엔 timeout 개념이 아예 없다"는 문제는 셋
    다에 똑같이 해당한다.
    """

    def __init__(
        self,
        *,
        runtime_policy: "RuntimeCapabilityPolicy",
        executor: ThreadPoolExecutor | None = None,
    ) -> None:
        super().__init__()
        self._runtime_policy = runtime_policy
        # 테스트가 자체 executor를 주입할 수 있게 열어 둔다(예: max_workers=1로
        # 좁혀서 pool 자체의 대기까지 재현하는 경우). 안 주면 공유 pool을 쓴다.
        self._executor = executor if executor is not None else _shared_executor()

    def wrap_tool_call(
        self, request: "ToolCallRequest", handler: "Callable[[ToolCallRequest], Any]"
    ) -> Any:
        tool_ref = tool_ref_from_model_name(request.tool_call["name"])
        timeout = self._runtime_policy.timeout_for_tool(tool_ref)

        future = self._executor.submit(handler, request)
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError:
            return ToolMessage(
                content=(
                    f"도구 실행이 {timeout}초를 넘어 응답을 기다리지 않고 중단했습니다. "
                    "다시 시도하거나 다른 방법을 시도할 수 있습니다."
                ),
                tool_call_id=request.tool_call["id"],
                name=request.tool_call["name"],
                status="error",
            )


def build_tool_call_timeout_middleware(
    *, runtime_policy: "RuntimeCapabilityPolicy"
) -> ToolCallTimeoutMiddleware:
    return ToolCallTimeoutMiddleware(runtime_policy=runtime_policy)


__all__ = ["ToolCallTimeoutMiddleware", "build_tool_call_timeout_middleware"]
