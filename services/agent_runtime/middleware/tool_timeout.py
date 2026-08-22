"""MCP Tool 호출에 hard timeout을 건다.

정본: `docs/작업기록/Deep_Agents/2026-08-21_01_Tool_timeout_재설계.md`

**MCP 도구에만 건다.** 모든 도구에 일괄로 거는 전역 timeout은 쓰지 않는다 —
복잡한 검색처럼 정당하게 오래 걸리는 작업까지 끊긴다.

- 내장 도구는 이 저장소에 코드가 있어 실행시간을 알거나 통제할 수 있다.
  필요하면 도구 자신이 자기 timeout을 갖는 게 맞다(`FilesystemMiddleware`의
  `execute`가 `max_execute_timeout`으로 이미 그렇게 한다). 플랫폼이 또 다른
  값을 얹으면 두 값이 어긋날 뿐이다.
- MCP 도구는 사용자가 자유롭게 연결하는 임의의 외부 서버라 `tools/list`
  응답만으로 정상 실행시간을 알 수 없다(`2026-08-20_01` §3). "적당한 값"을
  추측하는 대신 "넘기면 확실히 문제인 값"(gunicorn worker timeout에서 역산,
  `runtime_policy.py`)만 건다.

**한계**: `ThreadPoolExecutor` + `future.result(timeout=...)`는 기다리기를
포기할 뿐 실행 중인 스레드를 죽이지 못한다(Python 자체의 한계). 포기한 뒤에도
handler는 백그라운드에서 계속 돌고, 반환값만 버려질 뿐 이미 시작된 부작용은
취소되지 않는다.

즉 **timeout은 "실패했다"가 아니라 "결과를 모른다"**는 뜻이다. 이 모호함이
무단 재시도로 이어지면 중복 실행이 나므로, 아래 `_TIMEOUT_MESSAGE`가 "실행
여부가 확인되지 않았다, 자동으로 다시 시도하지 말라"를 명시한다
(`2026-08-21_03_외부_Write_Tool_재시도_안전성.md` §4.1). 진짜 취소 전파는 이
미들웨어의 범위 밖이다(`2026-08-13_04` 7순위).
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import TYPE_CHECKING, Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import ToolMessage

from services.agent_runtime.tools.loader import MCP_TOOL_REF_PREFIX, tool_ref_from_model_name

if TYPE_CHECKING:
    from collections.abc import Callable

    from langchain.agents.middleware.types import ToolCallRequest

    from services.agent_runtime.context import RuntimeContext
    from services.agent_runtime.runtime_policy import RuntimeCapabilityPolicy

logger = logging.getLogger(__name__)

#: 프로세스 전체가 공유하는 실행기. 요청마다 새로 만들면 Django 워커가 사는
#: 동안 스레드가 계속 쌓인다 — 그래프 객체가 언제 GC되는지 통제할 수 없어
#: pool을 닫을 시점을 알 방법이 없다. 그래서 모듈 레벨에 하나만 둔다.
#:
#: `max_workers`는 실측값이 아니라 여유치다. 한 super-step에서 동시에 도는 MCP
#: tool_call 수(보통 한 자리)보다 넉넉히 잡았다. 그 이상 몰리면 이 pool 자체가
#: 병목이 되어 "도구가 느리다"가 아니라 "줄을 서고 있다"는 이유로 timeout이
#: 걸릴 수 있다.
_MAX_WORKERS = 32
_executor: ThreadPoolExecutor | None = None

#: timeout 시 모델에게 돌려줄 문구. **`side_effect` 여부로 가르지 않는다** —
#: 이 미들웨어는 MCP 도구에만 붙는데 MCP 도구는 `tools/adapters.py`가 전부
#: `side_effect=True`로 고정하므로 분기할 대상이 없다.
_TIMEOUT_MESSAGE = (
    "도구 실행이 {timeout}초를 넘어 응답을 기다리지 않고 중단했습니다. "
    "실제로 실행됐는지 확인되지 않았습니다 — 자동으로 다시 시도하지 말고, "
    "필요하면 사용자에게 재시도 여부를 확인하세요."
)


def _shared_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="mcp-tool-timeout")
    return _executor


class McpToolCallTimeoutMiddleware(AgentMiddleware):
    """MCP Tool 호출을 `runtime_policy.timeout_for_mcp_tool()` 초 안에 못
    끝내면 `ToolMessage(status="error")`로 되돌린다 — 그래프 실행 자체를
    죽이지 않고 모델이 스스로 다시 판단하게 한다.

    MCP가 아닌 호출(내장 도구, `task` 위임 등)은 아무것도 하지 않고 그대로
    handler에 넘긴다 — 모듈 docstring의 적용 범위 참고.

    Root/Child/general-purpose 전부에 붙인다(`middleware/factory.py`) —
    셋 다 팀이 연결한 MCP 도구를 그대로 부를 수 있다.
    """

    def __init__(
        self,
        *,
        runtime_policy: "RuntimeCapabilityPolicy",
        context: "RuntimeContext | None" = None,
        executor: ThreadPoolExecutor | None = None,
    ) -> None:
        super().__init__()
        self._runtime_policy = runtime_policy
        # timeout 사실을 남기려면 run_id/team_id가 필요하다. context가 없으면
        # 기록만 건너뛰고 timeout 동작 자체는 그대로다.
        self._context = context
        # 테스트가 자체 executor를 주입할 수 있게 열어 둔다(예: max_workers=1로
        # 좁혀서 pool 자체의 대기까지 재현하는 경우). 안 주면 공유 pool을 쓴다.
        self._executor = executor if executor is not None else _shared_executor()

    def wrap_tool_call(
        self, request: "ToolCallRequest", handler: "Callable[[ToolCallRequest], Any]"
    ) -> Any:
        # 모델이 부른 이름(`mcp__MT001`)을 저장소 tool_ref(`mcp:MT001`)로
        # 되돌린 뒤에 판단·조회한다 — `model_safe_tool_name()`이 콜론을
        # `__`로 바꿔서 내보내기 때문에, 되돌리지 않으면 접두사 검사도
        # override 조회도 둘 다 빗나간다.
        tool_ref = tool_ref_from_model_name(request.tool_call["name"])
        if not tool_ref.startswith(MCP_TOOL_REF_PREFIX):
            return handler(request)

        timeout = self._runtime_policy.timeout_for_mcp_tool(tool_ref)

        future = self._executor.submit(handler, request)
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError:
            self._record_timeout(tool_ref=tool_ref, tool_call_id=request.tool_call["id"])
            return ToolMessage(
                content=_TIMEOUT_MESSAGE.format(timeout=timeout),
                tool_call_id=request.tool_call["id"],
                name=request.tool_call["name"],
                status="error",
            )

    def _record_timeout(self, *, tool_ref: str, tool_call_id: str | None) -> None:
        """"결과를 확인 못 한 호출"로 남긴다(`2026-08-21_03` §4.2).

        모델이 이 실패를 보고 새 tool_call_id로 재시도하면 키가 달라 idempotency
        캐시에 안 걸리고 진짜로 다시 실행된다 — 원래 호출이 뒤늦게 성공했으면
        중복이 난다. 그 재시도의 승인 카드에 경고를 띄우려는 기록이다.

        **기록에 실패해도 timeout 처리는 그대로 간다** — 부가 정보지 실행의
        일부가 아니다.
        """
        context = self._context
        if context is None or not tool_call_id or not getattr(context, "run_id", None):
            return
        from backend.db.agent_platform import McpCallNoteRepository

        try:
            McpCallNoteRepository.record_timeout(
                run_id=context.run_id,
                langchain_tool_call_id=tool_call_id,
                tool_ref=tool_ref,
                team_id=context.team_id,
            )
        except Exception:  # noqa: BLE001 - 경고용 부가 정보다
            logger.warning(
                "MCP timeout 기록에 실패했다: %s (run_id=%s, tool_call_id=%s)",
                tool_ref,
                context.run_id,
                tool_call_id,
                exc_info=True,
            )


def build_mcp_tool_call_timeout_middleware(
    *, runtime_policy: "RuntimeCapabilityPolicy", context: "RuntimeContext | None" = None
) -> McpToolCallTimeoutMiddleware:
    return McpToolCallTimeoutMiddleware(runtime_policy=runtime_policy, context=context)


__all__ = ["McpToolCallTimeoutMiddleware", "build_mcp_tool_call_timeout_middleware"]
