"""Skill 저장 경로·namespace — `services.agent_runtime.memory.backend`와 같은 패턴.

정본: docs/작업기록/Deep_Agents/2026-08-20_16_Skill_Middleware_설계.md
("저장 구조 — Store만 사용" 절)

**경로는 계정·팀 ID를 안 담는다.** Memory의 `/memories/users/preferences.md`가
이미 같은 설계다(`memory/backend.py`의 `MEMORY_USERS_PATH_PREFIX` — 모든 계정이
같은 문자열 경로를 쓰고, 격리는 `StoreBackend(namespace=...)`가 한다). Skill도
그대로 따른다: `/skills/personal/{name}/SKILL.md`, `/skills/team/{name}/SKILL.md`
— 계정 A와 계정 B가 똑같은 경로 문자열을 쓰지만, 실제로 접근하는 namespace가
서로 달라(아래 `personal_namespace`) 다른 저장 공간을 본다. 경로 문자열
조작만으로는 다른 계정·팀 것을 볼 방법이 없다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from deepagents.backends import StoreBackend

#: 개인 스킬 소스 — 요청한 계정 자신의 스킬만, namespace가 격리한다.
SKILLS_PERSONAL_PATH_PREFIX = "/skills/personal/"

#: 팀 스킬 소스 — 같은 team_id 소속 전원에게 보인다.
SKILLS_TEAM_PATH_PREFIX = "/skills/team/"


def skill_sources() -> list[str]:
    """`create_deep_agent(skills=...)`/서브에이전트 spec의 `skills` 키에 그대로 넘길 목록.

    **순서가 의미를 가진다** — deepagents `SkillsMiddleware`는 "나중 소스가 같은
    이름의 스킬을 덮어쓴다"(레이어링 규칙, `deepagents/middleware/skills.py`
    모듈 docstring). 팀 스킬을 뒤에 둬서, 같은 이름의 개인/팀 스킬이 있으면 더
    넓은 합의를 거친 팀 스킬이 이긴다(설계 문서 "저장 구조" 절).
    """
    return [SKILLS_PERSONAL_PATH_PREFIX, SKILLS_TEAM_PATH_PREFIX]


def personal_namespace(account_id: str) -> tuple[str, str, str]:
    """이 계정의 개인 스킬 namespace. `skill_register`/`StoreBackend` 둘 다 이 함수로 계산해야
    같은 저장 공간을 가리킨다 — 각자 다시 만들지 않는다(단일 진실 공급원)."""
    return ("skill", "personal", account_id)


def team_namespace(team_id: str) -> tuple[str, str]:
    """이 팀의 팀 스킬 namespace. `personal_namespace`와 같은 이유로 단일 진실 공급원이다."""
    return ("skill", "team", team_id)


def skill_md_path(prefix: str, name: str) -> str:
    """스킬 디렉터리 안의 `SKILL.md` 전체 경로.

    `SkillsMiddleware`가 기대하는 구조 그대로다(`deepagents/middleware/skills.py`
    `_list_skills_with_errors()` 실측 — `backend.ls(source)`로 하위 디렉터리를
    찾은 뒤 각 디렉터리 안의 `SKILL.md`를 내려받는다). `skill_register`가 쓸 때도,
    `SkillsMiddleware`가 읽을 때도 이 함수로 만든 경로가 같아야 한다.
    """
    return f"{prefix}{name}/SKILL.md"


def skill_routes(*, account_id: str, team_id: str) -> dict[str, "StoreBackend"]:
    """`CompositeBackend(routes={...})`에 그대로 병합할 개인/팀 스킬 라우트 두 개.

    `StoreBackend`는 deepagents가 제공하는, `BackendProtocol`을 완전히 구현한
    LangGraph `Store` 기반 백엔드다(Memory가 이미 쓰는 것과 같은 클래스,
    `memory/backend.py` 참고) — 새 백엔드를 만들지 않는다.
    """
    from deepagents.backends import StoreBackend

    return {
        SKILLS_PERSONAL_PATH_PREFIX: StoreBackend(namespace=lambda _rt: personal_namespace(account_id)),
        SKILLS_TEAM_PATH_PREFIX: StoreBackend(namespace=lambda _rt: team_namespace(team_id)),
    }


__all__ = [
    "SKILLS_PERSONAL_PATH_PREFIX",
    "SKILLS_TEAM_PATH_PREFIX",
    "skill_sources",
    "personal_namespace",
    "team_namespace",
    "skill_md_path",
    "skill_routes",
]
