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
    ) -> Iterator[Any]:
        """Root와 Child를 포함한 updates event를 3-tuple로 반환한다.

        `conversation_messages`는 이번 발화 **앞의** 턴들이다(`{"role", "content"}`
        평문 메시지, 도구 원본 없음 — apps/chat/api_views.py `_history()`가 만드는
        모양 그대로). 없으면 매 턴이 콜드 스타트라 "그것 말고 또 있나?" 같은
        말이 통하지 않는다 — 그래서 기본값도 빈 튜플이 아니라 호출부가 항상
        채워 보내는 것을 기대한다(레거시 Harness의 `messages` 파라미터와 같은 자리).

        `"custom"`도 함께 구독한다 — 도구 핸들러가 `get_stream_writer()`로 직접
        흘려보내는 진행 이벤트(tools/adapters.py, 제너레이터 도구용)를 받으려면
        필요하다. `"custom"`을 구독하지 않아도 `get_stream_writer()` 호출 자체는
        안전한 no-op이라(2026-08-13 실행 확인) 이 도구를 안 쓰는 그래프에는
        영향이 없다.

        `"messages"`도 구독한다(2026-08-18 추가) — reasoning 텍스트를 실시간
        스트리밍하려면 필요하다. `"updates"`는 모델 노드 하나가 통째로 끝나야만
        나오는 완성된 `AIMessage`라, reasoning도 다 끝난 뒤에야 한 덩어리로
        받는다 — `"messages"`는 OpenAI가 보내는 토큰·조각 단위 델타
        (`AIMessageChunk`)를 그 자리에서 받는다(`events.py`의
        `_classify_reasoning_delta` 참고). `subgraphs=True`+복수 모드라
        3-tuple `(namespace, "messages", (chunk, metadata))`로 온다(langgraph
        1.2.11 `Pregel.stream` docstring: `"messages"`는 항상 `(token, metadata)`
        2-tuple).
        """
        yield from runtime.stream(
            {"messages": [*conversation_messages, {"role": "user", "content": user_input}]},
            stream_mode=["updates", "custom", "messages"],
            subgraphs=True,
        )


__all__ = ["DeepAgentStreamAdapter"]
