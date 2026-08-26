"""비활성화된 스킬을 `skills_metadata`에서 걸러낸다(2026-08-26, §7).

deepagents의 `SkillsMiddleware.before_agent()`는 세션 시작 시 소스에 있는
스킬을 **전부** `state["skills_metadata"]`에 담는다 — 활성/비활성 구분이
없다. 이 미들웨어는 그 직후에 한 번 더 걸러서, `metadata.enabled`가
명시적으로 `"false"`인 항목만 목록에서 뺀다.

**순서가 중요하다.** `before_agent`를 가진 미들웨어는 langchain이 리스트
순서대로 노드 체인을 만들어 순차 실행한다(실측: `langchain/agents/
factory.py`의 `itertools.pairwise(middleware_w_before_agent)`) — 이
미들웨어가 `SkillsMiddleware`보다 **뒤**에 와야 방금 채워진 목록을 걸러낼
수 있다. `factory.py`가 이 프로젝트의 미들웨어 목록(§4-5)에 넣는 자리는
deepagents 기본 스택(Skills 포함) 뒤이므로 항상 이 순서가 보장된다.

파일 내용을 다시 읽지 않는다 — `skills_metadata`의 각 항목이 이미 스캔
때 만든 `SkillMetadata`(`metadata` 필드 포함)를 그대로 들고 있어서, 그
값만 보고 거른다.

Root에만 붙는다 — Child는 스킬 backend가 없다(`factory.py`의 4-6 분기).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain.agents.middleware.types import AgentMiddleware

if TYPE_CHECKING:
    from langchain.agents.middleware.types import AgentState
    from langgraph.runtime import Runtime

#: `skills/service.py`의 `_render_skill_md`가 쓰는 값과 같아야 한다.
_ENABLED_FALSE = "false"


def _is_enabled(skill: dict[str, Any]) -> bool:
    metadata = skill.get("metadata") or {}
    return str(metadata.get("enabled", "")).strip().lower() != _ENABLED_FALSE


class SkillVisibilityMiddleware(AgentMiddleware):
    """`skills_metadata`에서 `metadata.enabled == "false"`인 항목을 뺀다."""

    def before_agent(self, state: "AgentState", runtime: "Runtime[Any]") -> dict[str, Any] | None:  # noqa: ARG002
        skills = state.get("skills_metadata")
        if not skills:
            return None

        visible = [skill for skill in skills if _is_enabled(skill)]
        if len(visible) == len(skills):
            return None

        return {"skills_metadata": visible}


def build_skill_visibility_filter() -> SkillVisibilityMiddleware:
    return SkillVisibilityMiddleware()


__all__ = ["SkillVisibilityMiddleware", "build_skill_visibility_filter"]
