"""Compiled Deep Agent graph를 raw event stream으로 실행한다."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any

from langgraph.types import Command


class DeepAgentStreamAdapter:
    """graph stream을 EventMapper가 읽을 수 있는 형식으로 반환한다."""

    def stream(
        self,
        *,
        runtime: Any,
        user_input: str = "",
        conversation_messages: Sequence[dict[str, Any]] = (),
        thread_id: str | None = None,
        resume: dict[str, Any] | None = None,
        callbacks: Sequence[Any] = (),
        trace_metadata: dict[str, Any] | None = None,
        max_concurrency: int | None = None,
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

        `"messages"`도 구독한다(2026-08-18 추가) — reasoning 텍스트를 실시간
        스트리밍하려면 필요하다. `"updates"`는 모델 노드 하나가 통째로 끝나야만
        나오는 완성된 `AIMessage`라, reasoning도 다 끝난 뒤에야 한 덩어리로
        받는다 — `"messages"`는 OpenAI가 보내는 토큰·조각 단위 델타
        (`AIMessageChunk`)를 그 자리에서 받는다(`events.py`의
        `_classify_reasoning_delta` 참고). `subgraphs=True`+복수 모드라
        3-tuple `(namespace, "messages", (chunk, metadata))`로 온다(langgraph
        1.2.11 `Pregel.stream` docstring: `"messages"`는 항상 `(token, metadata)`
        2-tuple).

        `resume`(2026-08-19, §0순위 — HITL resume API): `HumanInTheLoopMiddleware`
        의 interrupt로 멈춘 실행을 재개할 때만 넘긴다. 있으면 `user_input`/
        `conversation_messages`는 완전히 무시하고 `Command(resume=resume)`을
        입력으로 보낸다 — 실제 langgraph 문서 예제(`langgraph/types.py`
        `interrupt()` docstring)가 재개를 이렇게 하는 것과 같다. `resume`은
        `{"decisions": [...]}` 형태를 기대한다(`HumanInTheLoopMiddleware
        .after_model`이 `interrupt(hitl_request)["decisions"]`로 그대로
        읽는 값, 실제 설치된 `langchain` 소스로 확인). `thread_id` 없이
        재개하는 건 의미가 없다 — 어느 대화를 잇는지 특정할 방법이 없어
        `ValueError`로 막는다(langgraph 자신도 `Command(resume=...)`을
        checkpointer 없이 쓰면 같은 이유로 막는다, `pregel/_loop.py`
        `_first()` 실제 소스 — "Cannot use Command(resume=...) without
        checkpointer").

        `callbacks`/`trace_metadata`는 2026-08-19 추가(Langfuse 연동,
        `tracing/callbacks.py`) — LangChain의 `config["callbacks"]`/
        `config["metadata"]`에 그대로 얹는다. 재개 경로에도 똑같이 붙인다 —
        승인을 기다리다 재개된 실행도 실제 모델·도구 호출이라 트레이싱
        대상에서 뺄 이유가 없다. 비어 있으면(키 없어서 Langfuse가 꺼진
        기본 상태) 아무 것도 안 붙는다 — `runtime.stream()` 호출 모양이
        이전과 완전히 같다.

        `max_concurrency`는 2026-08-21 추가(병렬실행 Phase 1,
        `2026-08-20_02_에이전트_병렬실행_설계.md` §5.1) — LangGraph config의
        같은 이름 키로 그대로 실린다. 한 AIMessage에 tool call이 여러 개
        있어도 executor가 이 수 이상을 동시에 실행하지 않고 나머지를
        대기시킨다(실측: sync 경로는 `get_executor_for_config()`의
        `ThreadPoolExecutor(max_workers=...)`, async 경로는
        `AsyncBackgroundExecutor`의 `asyncio.Semaphore(...)`). 재개 경로에도
        똑같이 붙인다 — 승인 후 풀리는 복수 side-effect 호출이야말로 상한이
        필요한 자리다. `None`이면(안 넘긴 호출자) 아무 것도 안 붙어서
        LangGraph 기본 동작(무제한)이 그대로 유지된다.
        """
        if resume is not None:
            if not thread_id:
                msg = "resume에는 thread_id가 있어야 합니다 — 재개할 대화를 특정할 수 없습니다."
                raise ValueError(msg)
            stream_kwargs = {
                "stream_mode": ["updates", "custom", "messages"],
                "subgraphs": True,
                "config": {"configurable": {"thread_id": thread_id}},
            }
            config = stream_kwargs["config"]
            if max_concurrency is not None:
                config["max_concurrency"] = max_concurrency
            if callbacks or trace_metadata:
                if callbacks:
                    config["callbacks"] = list(callbacks)
                if trace_metadata:
                    config["metadata"] = trace_metadata
            yield from runtime.stream(Command(resume=resume), **stream_kwargs)
            return

        new_turn = {"role": "user", "content": user_input}
        if thread_id:
            input_state: Any = {"messages": [new_turn]}
        else:
            input_state = {"messages": [*conversation_messages, new_turn]}

        stream_kwargs: dict[str, Any] = {
            "stream_mode": ["updates", "custom", "messages"],
            "subgraphs": True,
        }
        if thread_id:
            stream_kwargs["config"] = {"configurable": {"thread_id": thread_id}}
        if max_concurrency is not None:
            stream_kwargs.setdefault("config", {})["max_concurrency"] = max_concurrency
        if callbacks or trace_metadata:
            config = stream_kwargs.setdefault("config", {})
            if callbacks:
                config["callbacks"] = list(callbacks)
            if trace_metadata:
                config["metadata"] = trace_metadata

        yield from runtime.stream(input_state, **stream_kwargs)


__all__ = ["DeepAgentStreamAdapter"]
