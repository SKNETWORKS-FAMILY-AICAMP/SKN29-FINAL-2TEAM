"""백그라운드 등록 결과를 다음 사용자 턴의 스킬 카탈로그에 반영한다.

`skill_register`는 이제 파일을 즉시 쓰지 않고 job만 만든다. 따라서 도구 호출
직후 한 파일을 읽던 옛 `SkillRegisterSyncMiddleware`는 사용할 수 없다. 이
미들웨어는 Root 실행이 시작될 때 실제 스킬 source를 다시 스캔해, 같은 세션의
checkpointer에 남아 있던 오래된 `skills_metadata`를 최신 Store 상태로 바꾼다.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from langchain.agents.middleware.types import AgentMiddleware, AgentState

if TYPE_CHECKING:
    from deepagents.backends import BackendProtocol
    from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)


class SkillCatalogState(AgentState):
    skill_catalog_revision: int


class SkillCatalogRefreshMiddleware(AgentMiddleware[SkillCatalogState]):
    state_schema = SkillCatalogState

    def __init__(self, *, backend: "BackendProtocol", sources: list[str], account_id: str) -> None:
        super().__init__()
        self._backend = backend
        self._sources = tuple(sources)
        self._account_id = account_id

    def before_agent(self, state: SkillCatalogState, runtime: "Runtime[Any]") -> dict[str, Any] | None:  # noqa: ARG002
        from .versioning import catalog_revision

        current_revision = catalog_revision(self._account_id)
        previous_revision = state.get("skill_catalog_revision")
        # 첫 턴은 SkillsMiddleware가 이미 source를 읽었다. 여기서 다시 읽지
        # 않고 그 시점의 revision만 checkpoint에 심는다.
        if previous_revision is None:
            return {"skill_catalog_revision": current_revision}
        if previous_revision == current_revision:
            return None

        from deepagents.middleware.skills import _list_skills_with_errors

        skills = []
        for source in self._sources:
            loaded, error = _list_skills_with_errors(self._backend, source)
            if error:
                logger.warning("스킬 카탈로그 갱신 중 source를 읽지 못함: %s (%s)", source, error)
            skills.extend(loaded)
        return {"skills_metadata": skills, "skill_catalog_revision": current_revision}


def build_skill_catalog_refresh(
    *, backend: "BackendProtocol", sources: list[str], account_id: str
) -> SkillCatalogRefreshMiddleware:
    return SkillCatalogRefreshMiddleware(backend=backend, sources=sources, account_id=account_id)


__all__ = ["SkillCatalogRefreshMiddleware", "build_skill_catalog_refresh"]
