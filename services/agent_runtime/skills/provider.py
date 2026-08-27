"""`AgentRuntimeFactory`가 주입받는 얇은 파사드 — `memory/provider.py`의 `MemoryProvider`와 같은 스타일."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from deepagents.backends import StoreBackend
    from langgraph.store.postgres import PostgresStore


class SkillsProvider:
    """Root(및 Root와 같은 backend를 공유하는 general-purpose)에만 붙인다.

    Child(서브에이전트)는 기본으로 안 붙는다 — deepagents 자체가 이미 그렇게
    동작한다(서브에이전트 spec에 `skills` 키가 있을 때만 옵트인,
    `deepagents/graph.py` 실측 — 설계 문서 "Root/GP/Child" 절). 이 Provider는
    그 옵트인 목록/라우트를 계산해 줄 뿐, Child에 강제로 붙이는 로직은 두지
    않는다.
    """

    def sources(self) -> list[str]:
        from services.agent_runtime.skills.backend import skill_sources

        return skill_sources()

    def routes(self, *, account_id: str, team_id: str) -> dict[str, "StoreBackend"]:
        from services.agent_runtime.skills.backend import skill_routes
        from services.agent_runtime.skills.service import migrate_legacy_inactive_skills

        # 그래프가 활성 source를 스캔하기 전에 구버전 ``enabled=false`` 파일을
        # 비활성 namespace로 옮긴다. 따라서 첫 대화부터 Root·GP에 노출되지 않는다.
        migrate_legacy_inactive_skills(account_id)
        return skill_routes(account_id=account_id, team_id=team_id)

    def system_prompt(self) -> str:
        """2026-08-22 추가 — `MemoryProvider.system_prompt()`와 같은 자리.
        `factory.py`가 이 값으로 커스텀 `SkillsMiddleware`를 만들어
        `compat.create_root_graph(skills_system_prompt=...)`에 넘긴다."""
        from services.agent_runtime.skills.backend import skills_system_prompt

        return skills_system_prompt()

    def store(self) -> "PostgresStore":
        """2026-08-25 추가 — `memory_provider`가 없을 때 `factory.py`가 Skill
        전용 backend를 만들면서 쓴다. `MemoryProvider.store()`와 똑같이
        `get_memory_store()`를 부른다 — 이름이 memory지만 실제로는 이
        저장소가 쓰는 프로세스 전역 Postgres Store 싱글턴이다. Skill 전용
        인프라가 따로 있는 게 아니라, 같은 저장소를 재사용할 뿐이다."""
        from services.agent_runtime.memory.store import get_memory_store

        return get_memory_store()


__all__ = ["SkillsProvider"]
