"""충돌한 스킬 이름의 대안을 후보 내용에서 생성한다."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from services.agent_runtime.models.factory import ModelConfigResolver, ModelFactory
from services.agent_runtime.skills.service import validate_skill_name

from .config import SKILL_EVAL_AUTHOR_EFFORT, SKILL_EVAL_AUTHOR_MODEL


class NameSuggestions(BaseModel):
    names: list[str] = Field(min_length=2, max_length=3)


def suggest_names(document: dict[str, object]) -> list[str]:
    """자동 변경하지 않고 사용자가 고를 수 있는 유효한 이름만 반환한다."""

    resolved = ModelConfigResolver().resolve(
        model=SKILL_EVAL_AUTHOR_MODEL,
        reasoning_effort=SKILL_EVAL_AUTHOR_EFFORT,
        team_id=None,
    )
    model = ModelFactory().create(resolved).with_structured_output(NameSuggestions)
    result = model.invoke([
        {
            "role": "system",
            "content": (
                "스킬의 기능과 범위를 잘 나타내는 서로 다른 이름을 제안하세요. "
                "이름은 영문 소문자, 숫자, 하이픈만 사용하고 64자를 넘지 않아야 합니다. "
                "기존 이름에 기계적인 번호나 임의 접미사만 붙이지 마세요."
            ),
        },
        {
            "role": "user",
            "content": json.dumps({
                "current_name": document.get("name"),
                "description": document.get("description"),
                "body": document.get("body"),
            }, ensure_ascii=False),
        },
    ])
    current = str(document.get("name") or "")
    valid: list[str] = []
    for name in result.names:
        candidate = name.strip()
        if candidate != current and candidate not in valid and validate_skill_name(candidate) is None:
            valid.append(candidate)
    return valid


__all__ = ["suggest_names"]
