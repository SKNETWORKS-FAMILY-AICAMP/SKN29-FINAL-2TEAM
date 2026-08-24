"""명시적 스킬 호출("/스킬이름 ...") — Claude(클로드)의 슬래시 커맨드와 같은 방식
"""

from __future__ import annotations

import re
from typing import Any

#: `validate_skill_name`(`service.py`)과 같은 이름 규칙 — 소문자 영숫자와
#: 하이픈만, 앞뒤/연속 하이픈 금지. 스킬 이름이 아닌 것은 애초에 매칭이 안 돼
#: 평범한 채팅으로 흐르게 하려고 같은 정규식을 쓴다.
_INVOCATION_RE = re.compile(r"^/([a-z0-9]+(?:-[a-z0-9]+)*)(?:[ \t]+(.*))?$", re.DOTALL)


def parse_invocation(text: str) -> tuple[str, str] | None:
    """맨 앞이 `/스킬이름`이면 `(이름, 나머지 텍스트)`를, 아니면 `None`을 돌려준다.

    `text`는 사용자가 입력한 원문 그대로 받는다(마스킹 전) — 이름 자체가
    민감정보일 리 없고, 나머지 텍스트는 어차피 이 함수를 부른 쪽이 마스킹된
    값을 따로 쓴다.
    """

    stripped = text.lstrip()
    if not stripped.startswith("/"):
        return None
    match = _INVOCATION_RE.match(stripped)
    if match is None:
        return None
    name = match.group(1)
    rest = (match.group(2) or "").strip()
    return name, rest


def resolve_invocable_skill(*, account_id: str, team_id: str, name: str) -> dict[str, Any] | None:
    """호출 대상 스킬을 찾는다. 팀 스킬을 먼저 보고(이름이 겹치면 팀이 이긴다 —
    모듈 docstring 참고), 없으면 개인 스킬을 본다. 둘 다 없으면 `None` —
    호출부는 이 경우 평범한 채팅으로 그냥 흘려보내면 된다(오류로 막지 않는다,
    "/"로 시작하는 평범한 메모일 수도 있어서).
    """

    from .service import SkillNotFound, get_personal_skill, get_team_skill

    try:
        return {**get_team_skill(team_id, name), "scope": "team"}
    except SkillNotFound:
        pass
    try:
        return {**get_personal_skill(account_id, name), "scope": "personal"}
    except SkillNotFound:
        return None


_INVOCATION_WRAPPER = """<explicit_skill_invocation>
사용자가 "/{name}"로 이 스킬을 직접, 명시적으로 지정했다. 어떤 스킬이 맞는지
판단할 필요가 없다 — 이미 정해졌다. 아래는 그 스킬(SKILL.md)의 본문이다. 이
지침을 그대로 따라 사용자의 요청을 처리하라. 다른 스킬을 찾거나, 이 지침을
요약·생략하거나, "장기 기억에 저장할 선호"로 취급하지 마라 — 지금 이 요청에
바로 적용하라.

{body}
</explicit_skill_invocation>

사용자 요청: {request}"""


def build_invocation_input(*, name: str, body: str, request: str) -> str:
    """모델에게 보낼 입력으로 바꾼다. `request`가 비어 있으면(예: "/humanizer"만
    치고 아무 말도 안 붙였으면) 직전 대화 맥락에 스킬을 적용하라는 뜻으로
    받아들이게 안내한다."""

    return _INVOCATION_WRAPPER.format(
        name=name,
        body=body,
        request=request or "(추가 지시 없음 — 바로 앞 대화 맥락에 이 스킬 지침을 적용해서 답해줘)",
    )


__all__ = ["parse_invocation", "resolve_invocable_skill", "build_invocation_input"]
