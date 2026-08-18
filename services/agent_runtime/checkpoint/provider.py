"""`AgentRuntimeFactory`가 주입받는 얇은 파사드 — Checkpointer 하나."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langgraph.checkpoint.postgres import PostgresSaver


class CheckpointerProvider:
    """Root graph에만 붙인다 — Child(서브에이전트)는 별도 Checkpointer가 필요 없다
    (LangGraph는 상위 그래프에 붙인 Checkpointer를 서브그래프 실행에도 그대로
    적용한다 — Memory의 `backend`/`store`와 달리 Child용 파라미터 자체가 없다).
    `MemoryProvider`(`memory/provider.py`)와 같은 생성자 주입 스타일을 따른다 —
    실물 `PostgresSaver`를 직접 import하지 않고 호출 시점에만 지연 import해서,
    이 파사드를 참조하는 것만으로 `langgraph.checkpoint.postgres`가 끌려 들어오지
    않게 한다.
    """

    def get(self) -> "PostgresSaver":
        from services.agent_runtime.checkpoint.checkpointer import get_checkpointer

        return get_checkpointer()


__all__ = ["CheckpointerProvider"]
