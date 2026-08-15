"""`AgentRuntimeFactory`가 주입받는 얇은 파사드 — 장기 메모리 3종 세트(경로·backend·store)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from deepagents.backends import CompositeBackend
    from langgraph.store.postgres import PostgresStore


class MemoryProvider:
    """Root graph에만 붙인다 — Child(서브에이전트)는 메모리 없이 그대로 둔다
    (MVP 범위 축소, `factory.py`의 `build()` 참고). 다른 협력자들(`ModelFactory`,
    `ToolLoader` 등)과 같은 생성자 주입 스타일을 따른다.
    """

    def paths(self) -> list[str]:
        from services.agent_runtime.memory.backend import memory_paths

        return memory_paths()

    def backend(self, *, team_id: str, agent_id: str) -> "CompositeBackend":
        from services.agent_runtime.memory.backend import build_memory_backend

        return build_memory_backend(team_id=team_id, agent_id=agent_id)

    def store(self) -> "PostgresStore":
        from services.agent_runtime.memory.store import get_memory_store

        return get_memory_store()


__all__ = ["MemoryProvider"]
