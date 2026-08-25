"""승인 카드에 "지금 이걸 승인해도 되나"를 판단할 재료를 붙인다.

정본:
  `docs/설계 및 구현/중간발표 이후/작업기록/Deep_Agents/2026-08-21_04_MCP_동시_쓰기_경고_설계.md`
  `docs/설계 및 구현/중간발표 이후/작업기록/Deep_Agents/2026-08-21_03_외부_Write_Tool_재시도_안전성.md` §4.2

**막지 않고 알린다.** 원래 설계(`2026-08-20_02` §5.2)는 같은 MCP 서버 호출을
advisory lock으로 줄 세우는 것이었는데, 두 가지 이유로 폐기했다:

1. 그 lock은 즉시 끝나는 로컬 쓰기용이라(`memory/write_lock.py` — 락을 쥔 채
   handler를 부른다) 최대 480초짜리 MCP 호출에 쓰면 대기하는 호출마다 전용
   DB 커넥션을 그만큼 붙잡는다.
2. 더 근본적으로, MCP 서버가 동시 접속을 못 받는 게 아니다. 우리가 모르는 건
   "그 요청이 하는 일이 동시에 일어나도 안전한가"이고 이건 `tools/list`로는
   애초에 알 수 없다 — 정보가 없는 채로 기다리게 해도 그 정보 부족이
   해결되지는 않는다.

그래서 아는 사실만 정직하게 보여주고 판단은 승인하는 사람에게 맡긴다. 이
저장소가 `runtime_policy.is_tool_allowed_for_role()`(존재를 숨기지 않고 사유를
알려준다)과 `2026-08-21_03`(자동 차단 대신 경고)에서 이미 두 번 택한 방향과
같다.

**세 가지를 본다**(전부 실패해도 승인 흐름 자체는 안 막는다 — 부가 정보지
게이트가 아니다):

1. 같은 배치(한 AIMessage)에 같은 MCP 서버를 쓰는 다른 호출이 있는지.
   DB의 "실행 중" 표시만으로는 못 잡는다 — 이 시점엔 어느 쪽도 아직 승인
   전이라 아무것도 실행을 시작하지 않았다(`2026-08-21_04` §3.2).
2. 다른 실행이 지금 같은 MCP 서버에 호출을 돌리고 있는지(`mcp_call_note`의
   ACTIVE 행).
3. 이 run에서 같은 도구가 timeout으로 끝난 적 있는지(TIMED_OUT 행) — timeout은
   "실패"가 아니라 "결과를 모름"이라 재시도가 중복 실행이 될 수 있다.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage

from services.agent_runtime.tools.loader import MCP_TOOL_REF_PREFIX, tool_ref_from_model_name

if TYPE_CHECKING:
    from collections.abc import Callable

    from services.agent_runtime.context import RuntimeContext

logger = logging.getLogger(__name__)

#: `HumanInTheLoopMiddleware`가 `description` 없이 쓰는 기본 문구와 같은 모양
#: (실측: langchain `human_in_the_loop.py`의 `_create_action_and_config()` —
#: `f"{self.description_prefix}\n\nTool: {tool_name}\nArgs: {tool_args}"`).
#: 우리가 `description`을 직접 만들면 그 기본 경로를 안 타므로, 같은 정보를
#: 여기서 다시 만든 뒤 경고만 덧붙인다.
_DESCRIPTION_PREFIX = "Tool execution requires approval"

_SAME_BATCH_WARNING = (
    "⚠ 이 승인에는 같은 MCP 서버를 쓰는 다른 작업도 함께 걸려 있습니다. "
    "둘 다 승인하면 동시에 실행됩니다 — 같은 대상을 건드리는 작업이라면 "
    "하나씩 나눠서 승인하세요."
)
_ACTIVE_WARNING = (
    "⚠ 다른 실행이 지금 같은 MCP 서버에 작업을 진행 중입니다. "
    "같은 대상을 건드리는 작업이라면 끝날 때까지 기다리는 편이 안전합니다."
)
_TIMEOUT_WARNING = (
    "⚠ 이 대화에서 같은 도구가 응답 시간을 넘겨 결과를 확인하지 못한 적이 "
    "있습니다. 그 작업이 이미 실행됐을 수 있으니, 승인 전에 실제로 처리됐는지 "
    "확인하세요."
)


def _mcp_tool_calls_in_batch(state: Any) -> list[dict[str, Any]]:
    """지금 승인 대기에 걸린 그 AIMessage의 MCP tool_call들.

    `HumanInTheLoopMiddleware.after_model()`이 마지막 AIMessage의 `tool_calls`를
    훑어 카드를 만들므로(실측), 같은 것을 여기서도 본다.
    """
    messages = (state or {}).get("messages") or []
    last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
    if last_ai is None or not last_ai.tool_calls:
        return []
    return [
        call
        for call in last_ai.tool_calls
        if tool_ref_from_model_name(call.get("name") or "").startswith(MCP_TOOL_REF_PREFIX)
    ]


def _warnings_for(
    *, tool_call: dict[str, Any], state: Any, context: "RuntimeContext", stale_after_seconds: int
) -> list[str]:
    """이 tool_call에 붙일 경고 문구들. 없으면 빈 목록."""
    tool_ref = tool_ref_from_model_name(tool_call.get("name") or "")
    if not tool_ref.startswith(MCP_TOOL_REF_PREFIX):
        return []

    from backend.db.agent_platform import McpCallNoteRepository

    warnings: list[str] = []
    batch = _mcp_tool_calls_in_batch(state)
    my_id = tool_call.get("id")

    # ① 같은 배치 — DB를 안 보고 state만으로 판단할 수는 없다(서버가 같은지
    #    알아야 한다). 대신 배치 전체의 서버를 **한 번의 왕복으로** 푼다.
    sibling_refs = tuple(
        {
            tool_ref_from_model_name(call.get("name") or "")
            for call in batch
            if call.get("id") != my_id
        }
    )
    if sibling_refs:
        server_ids = McpCallNoteRepository.server_ids_for_tool_refs((tool_ref, *sibling_refs))
        mine = server_ids.get(tool_ref)
        if mine is not None and any(server_ids.get(ref) == mine for ref in sibling_refs):
            warnings.append(_SAME_BATCH_WARNING)

    # ② 이미 돌고 있는 다른 실행. 같은 배치의 형제들은 아직 시작도 안 했지만
    #    (승인 전) 혹시 남아 있는 표시가 있어도 ①이 이미 알렸으므로 뺀다.
    if McpCallNoteRepository.has_other_active_on_same_server(
        tool_ref=tool_ref,
        team_id=context.team_id,
        exclude_tool_call_ids=tuple(
            call["id"] for call in batch if call.get("id")
        ),
        stale_after_seconds=stale_after_seconds,
    ):
        warnings.append(_ACTIVE_WARNING)

    # ③ 이 run에서 같은 도구가 timeout난 적 있는지.
    if context.run_id and McpCallNoteRepository.has_timeout_in_run(
        run_id=context.run_id, tool_ref=tool_ref
    ):
        warnings.append(_TIMEOUT_WARNING)

    return warnings


def build_confirmation_description(
    *, context: "RuntimeContext", stale_after_seconds: int
) -> "Callable[[dict[str, Any], Any, Any], str]":
    """`InterruptOnConfig["description"]`에 넣을 콜백을 만든다.

    langchain이 이 콜백을 `(tool_call, state, runtime)`으로 부른다(실측:
    `human_in_the_loop.py`의 `_create_action_and_config()`). `state`가 통째로
    넘어오는 덕분에 같은 배치의 다른 tool_call을 여기서 직접 볼 수 있다 —
    이게 §3.2의 "DB만으로는 못 잡는 사각지대"를 메우는 열쇠다.

    **경고를 만들다 실패해도 카드는 그대로 뜬다.** DB가 잠깐 안 되는 것 때문에
    승인 자체가 막히면 안 된다 — 이건 판단을 돕는 부가 정보지 게이트가 아니다.
    """

    def describe(tool_call: dict[str, Any], state: Any, runtime: Any) -> str:
        base = (
            f"{_DESCRIPTION_PREFIX}\n\n"
            f"Tool: {tool_call.get('name')}\nArgs: {tool_call.get('args')}"
        )
        try:
            warnings = _warnings_for(
                tool_call=tool_call,
                state=state,
                context=context,
                stale_after_seconds=stale_after_seconds,
            )
        except Exception:  # noqa: BLE001 - 부가 정보지 승인 게이트가 아니다
            logger.warning(
                "승인 카드 경고를 만들지 못했다: %s", tool_call.get("name"), exc_info=True
            )
            return base
        if not warnings:
            return base
        return base + "\n\n" + "\n".join(warnings)

    return describe


__all__ = ["build_confirmation_description"]
