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

#: 내장 스킬 소스 — 계정·팀과 무관하게 전원에게 항상 보인다(2026-08-24,
#: skill-creator 기본 등록). 이 안에 실제로 쓰는 namespace는 하나뿐이지만,
#: 개인/팀과 같은 `prefix -> StoreBackend` 구조를 그대로 따라야
#: `SkillsMiddleware`가 개인/팀과 똑같이 취급한다 — 새 배선 방식을 만들지 않는다.
SKILLS_BUILTIN_PATH_PREFIX = "/skills/builtin/"

#: 개인 스킬 소스 — 요청한 계정 자신의 스킬만, namespace가 격리한다.
SKILLS_PERSONAL_PATH_PREFIX = "/skills/personal/"

#: 팀 스킬 소스 — 같은 team_id 소속 전원에게 보인다.
SKILLS_TEAM_PATH_PREFIX = "/skills/team/"

#: 사람이 개인/팀 스킬로 새로 만들 수 없는 이름(2026-08-24). skill-creator는
#: 항상 내장 소스에만 있어야 한다 — 같은 이름의 개인/팀 스킬을 허용하면
#: `SkillsMiddleware`의 "나중 소스가 이긴다" 규칙에 따라 내장 스킬이 조용히
#: 가려질 수 있다(위 `2026-08-22_02` 문서의 개인/팀 이름 겹침 문제와 같은
#: 위험 — 내장 스킬은 아예 이름 자체를 못 쓰게 막아 그 문제가 생길 여지를
#: 없앤다).
RESERVED_SKILL_NAMES = frozenset({"skill-creator"})


def skill_sources() -> list[str]:
    """`create_deep_agent(skills=...)`/서브에이전트 spec의 `skills` 키에 그대로 넘길 목록.

    **순서가 의미를 가진다** — deepagents `SkillsMiddleware`는 "나중 소스가 같은
    이름의 스킬을 덮어쓴다"(레이어링 규칙, `deepagents/middleware/skills.py`
    모듈 docstring). 내장 → 개인 → 팀 순서로 둬서, 더 넓은 합의를 거친 쪽이
    이긴다(설계 문서 "저장 구조" 절 — 팀이 개인을 이기는 규칙은 그대로 유지).
    실제로는 `RESERVED_SKILL_NAMES`가 이름 충돌 자체를 막으므로 내장 스킬이
    가려질 일은 없다 — 그래도 순서 규칙은 일관되게 지킨다.
    """
    return [SKILLS_BUILTIN_PATH_PREFIX, SKILLS_PERSONAL_PATH_PREFIX, SKILLS_TEAM_PATH_PREFIX]


def builtin_namespace() -> tuple[str, str]:
    """내장 스킬 namespace — 계정·팀 구분이 없다(전원이 같은 공간을 본다).
    `personal_namespace`/`team_namespace`와 같은 이유로 단일 진실 공급원이다."""
    return ("skill", "builtin")


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
    """`CompositeBackend(routes={...})`에 그대로 병합할 내장/개인/팀 스킬 라우트 세 개.

    `StoreBackend`는 deepagents가 제공하는, `BackendProtocol`을 완전히 구현한
    LangGraph `Store` 기반 백엔드다(Memory가 이미 쓰는 것과 같은 클래스,
    `memory/backend.py` 참고) — 새 백엔드를 만들지 않는다. 내장 라우트도
    같은 클래스를 재사용한다 — namespace가 계정·팀과 무관한 고정값이라는
    점만 다르다.
    """
    from deepagents.backends import StoreBackend

    return {
        SKILLS_BUILTIN_PATH_PREFIX: StoreBackend(namespace=lambda _rt: builtin_namespace()),
        SKILLS_PERSONAL_PATH_PREFIX: StoreBackend(namespace=lambda _rt: personal_namespace(account_id)),
        SKILLS_TEAM_PATH_PREFIX: StoreBackend(namespace=lambda _rt: team_namespace(team_id)),
    }


#: 2026-08-22, 사용자 실측 피드백 — "번역체 같다"는 답변 스타일 피드백을 줬는데
#: 등록해 둔 스킬이 안 불려지고, 대신 `MemoryMiddleware`가 "장기 기억에 저장할
#: 선호"로 판단해 버렸다. `deepagents/middleware/memory.py`의
#: `MEMORY_SYSTEM_PROMPT`를 실측하면 "사용자가 답변의 좋고 나쁨을 말하면
#: 패턴으로 기억해라"는 지침과 정확히 이 모양의 worked example(Example 2 —
#: 스타일 피드백 → `edit_file`로 저장)이 있는 반면, deepagents 기본
#: `SKILLS_SYSTEM_PROMPT`(`deepagents/middleware/skills.py`)의 worked example은
#: "최신 연구 조사해줘" 같은 명시적 작업 요청 하나뿐이고, "지금 답변에 대한
#: 스타일 피드백도 스킬을 켜는 신호"라는 언급이 없다. 즉 서로 다른 미들웨어가
#: 독립적으로 시스템 프롬프트를 얹는 지금 구조에서는, 어느 쪽 지침이 더
#: 구체적인지에 따라 모델의 판단이 갈린다 — Skill을 쓸지 말지가 전부 모델의
#: 자율 판단에 맡겨져 있다는 뜻이다.
#:
#: 최소한의 우선순위 규칙을 여기서 덧붙인다. Memory의 `_MEMORY_ROUTING_PROMPT`
#: (`memory/backend.py`)와 같은 방식 — 새 지침 체계를 만들지 않고, deepagents
#: 기본 프롬프트 뒤에 그대로 이어붙인다.
_SKILLS_ROUTING_PROMPT = """

## Skill usage rules — decide before you act

1. If the user's current request clearly matches a registered skill's
   description or usage condition, search for and read that skill FIRST —
   before responding, and before considering anything else (including
   whether to save something to memory).
2. A skill defines HOW to perform a task. Do not use a skill as a place to
   store the user's long-term preferences or facts about them — writing
   standing preferences to memory is a different system's job, not this one.
3. If the user asks you to revise the current answer, or comments on the
   style or manner of the current answer or task (e.g. "this sounds too
   translated", "make this shorter", "that's not quite right"), check for a
   matching skill FIRST. This is a live task to act on in this turn, not
   merely something to remember for later.
4. Only when the user explicitly signals a standing, future preference —
   words like "from now on", "always", "remember this" — consider that a
   candidate for memory instead. A one-time stylistic correction on the
   current answer is rule 3, not this one.
"""


def skills_system_prompt() -> str:
    """deepagents 기본 `SKILLS_SYSTEM_PROMPT`에 위 우선순위 규칙을 이어붙인다.

    `MemoryMiddleware.system_prompt`를 바꾸는 것과 같은 트릭이다 — compat
    레이어의 `create_root_graph(memory_system_prompt=...)`처럼,
    `SkillsMiddleware`도 `system_prompt=` 생성자 인자를 공개로 받으므로
    (`deepagents/middleware/skills.py` 실측), 같은 `.name`("SkillsMiddleware")을
    가진 커스텀 인스턴스를 `middleware=` 목록에 끼워 넣으면 deepagents가 자동
    생성한 것을 그 자리에서 치환한다(`_apply_custom_middleware`, 같은 소스).

    필수 포맷 슬롯(`{skills_locations}`/`{skills_load_warnings}`/`{skills_list}`)
    은 원본 `SKILLS_SYSTEM_PROMPT` 안에 그대로 있고, 여기서 이어붙이는 텍스트에는
    중괄호가 없어 `.format()` 호출에 영향을 주지 않는다.
    """

    from deepagents.middleware.skills import SKILLS_SYSTEM_PROMPT

    return SKILLS_SYSTEM_PROMPT + _SKILLS_ROUTING_PROMPT


__all__ = [
    "SKILLS_BUILTIN_PATH_PREFIX",
    "SKILLS_PERSONAL_PATH_PREFIX",
    "SKILLS_TEAM_PATH_PREFIX",
    "RESERVED_SKILL_NAMES",
    "skill_sources",
    "builtin_namespace",
    "personal_namespace",
    "team_namespace",
    "skill_md_path",
    "skill_routes",
    "skills_system_prompt",
]
