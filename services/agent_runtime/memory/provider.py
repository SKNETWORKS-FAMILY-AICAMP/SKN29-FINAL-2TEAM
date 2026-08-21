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

    def backend(
        self,
        *,
        team_id: str,
        agent_id: str,
        account_id: str,
        extra_routes: dict[str, Any] | None = None,
    ) -> "CompositeBackend":
        """`extra_routes`(2026-08-21): Skill 라우트를 병합해 넘길 자리 —
        `build_memory_backend()` docstring의 "extra_routes" 참고. 이 Provider
        자신은 Skill을 모른다 — `factory.py`가 `SkillsProvider.routes(...)`로
        계산한 값을 그대로 전달만 한다(파사드는 조립하지 않는다)."""
        from services.agent_runtime.memory.backend import build_memory_backend

        return build_memory_backend(
            team_id=team_id, agent_id=agent_id, account_id=account_id, extra_routes=extra_routes
        )

    def store(self) -> "PostgresStore":
        from services.agent_runtime.memory.store import get_memory_store

        return get_memory_store()

    def system_prompt(self) -> str:
        """2026-08-18, Phase 3(§4-8) — `MemoryMiddleware.system_prompt`에 이어붙일
        라우팅 안내가 포함된 값. `factory.py`가 `compat.create_root_graph
        (memory_system_prompt=...)`로 그대로 넘긴다."""
        from services.agent_runtime.memory.backend import memory_system_prompt

        return memory_system_prompt()


__all__ = ["MemoryProvider"]
