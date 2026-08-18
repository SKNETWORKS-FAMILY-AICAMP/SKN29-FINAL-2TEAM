"""Compiled Deep Agent graph를 raw event stream으로 실행한다."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any


class DeepAgentStreamAdapter:
    """graph stream을 EventMapper가 읽을 수 있는 형식으로 반환한다."""

    def stream(
        self,
        *,
        runtime: Any,
        user_input: str,
        conversation_messages: Sequence[dict[str, Any]] = (),
        thread_id: str | None = None,
    ) -> Iterator[Any]:
        """Root와 Child를 포함한 updates event를 3-tuple로 반환한다.

        `conversation_messages`는 이번 발화 **앞의** 턴들이다(`{"role", "content"}`
        평문 메시지, 도구 원본 없음 — apps/chat/api_views.py `_history()`가 만드는
        모양 그대로).

        `thread_id`는 2026-08-18(§5 Phase 1)에 추가됐다 — `context.session_id`를
        그대로 받는다(`executor.py`가 넘긴다). **`thread_id`가 있고 없고에 따라
        입력 메시지를 완전히 다르게 조립한다**:

        - `thread_id`가 없으면(기본값, 기존 동작 그대로): 매 호출이 콜드
          스타트라고 가정하고 `conversation_messages`를 그대로 앞에 붙인다
          (레거시 Harness의 `messages` 파라미터와 같은 자리).
        - `thread_id`가 있으면: **`conversation_messages`를 붙이지 않고 이번
          발화만 보낸다.** Checkpointer(`checkpoint/checkpointer.py`)가 이
          thread의 이전 턴들을 이미 그래프 state로 갖고 있어서, 여기서 그
          이전 턴들을 다시 붙이면 LangGraph의 `add_messages` reducer가 "새
          메시지"로 오인해(우리가 만드는 평문 메시지에는 LangGraph가 같은
          메시지로 인식할 고유 id가 없다) 턴마다 중복이 누적된다 — 검증:
          `2026-08-13_04_..._세부계획.md` §5 Phase 1 "같은 thread_id로 두 번
          연속 호출했을 때 상태가 실제로 이어지는지".

        **주의(결합 전제)**: 위 분기는 "`thread_id`가 있으면 곧 Checkpointer가
        실제로 붙어 있다"는 전제에 기대고 있다 — 이 전제가 깨지면(예: Root
        graph를 `checkpointer` 없이 만들어 놓고 `context.session_id`만 있는
        상태로 호출) 이전 턴이 그래프에도, 여기서 보내는 입력에도 없어 통째로
        사라진다. 지금 유일한 실제 조립 지점인 `bootstrap.py`
        `build_default_executor()`는 Root를 만들 때 memory/checkpointer
        Provider를 항상 함께 넘기므로 이 전제가 깨지지 않는다 — 새 조립
        경로를 추가할 때는 이 전제를 유지할 것.

        `"custom"`도 함께 구독한다 — 도구 핸들러가 `get_stream_writer()`로 직접
        흘려보내는 진행 이벤트(tools/adapters.py, 제너레이터 도구용)를 받으려면
        필요하다. `"custom"`을 구독하지 않아도 `get_stream_writer()` 호출 자체는
        안전한 no-op이라(2026-08-13 실행 확인) 이 도구를 안 쓰는 그래프에는
        영향이 없다.
        """
        new_turn = {"role": "user", "content": user_input}
        if thread_id:
            input_state = {"messages": [new_turn]}
        else:
            input_state = {"messages": [*conversation_messages, new_turn]}

        stream_kwargs: dict[str, Any] = {"stream_mode": ["updates", "custom"], "subgraphs": True}
        if thread_id:
            stream_kwargs["config"] = {"configurable": {"thread_id": thread_id}}

        yield from runtime.stream(input_state, **stream_kwargs)


__all__ = ["DeepAgentStreamAdapter"]
