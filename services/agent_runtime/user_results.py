"""도구 원본 결과에서 일반 사용자에게 허용된 표시 필드만 추린다.

모델은 도구 원본 전체를 계속 받는다. 이 모듈의 결과는 ``tool_completed``
스트림에 선택 필드로 실어 작업 과정 UI에만 사용한다. 원본 결과의 의미를
재해석하거나 다시 계산하지 않고, 도구별 허용 목록에 있는 값만 복사한다.
"""

from __future__ import annotations

import json
from typing import Any


USER_RESULT_VERSION = 1
USER_RESULT_PEOPLE_MAX = 20
USER_RESULT_LIMITATIONS_MAX = 5
USER_RESULT_TEXT_MAX = 240


def _mapping(content: Any) -> dict[str, Any] | None:
    if isinstance(content, dict):
        return content
    if not isinstance(content, str):
        return None
    try:
        value = json.loads(content)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _text(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return value[:USER_RESULT_TEXT_MAX]


def _number(value: Any) -> int | float | None:
    # bool은 int의 하위 타입이지만 숫자 결과로 표시하면 안 된다.
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _workload_result(data: dict[str, Any]) -> dict[str, Any]:
    raw_people = data.get("people")
    people = raw_people if isinstance(raw_people, list) else []
    shown_people: list[dict[str, Any]] = []
    for raw in people[:USER_RESULT_PEOPLE_MAX]:
        if not isinstance(raw, dict):
            continue
        shown_people.append(
            {
                "name": _text(raw.get("name")),
                "job_role": _text(raw.get("job_role")),
                "effective_capacity": _number(raw.get("effective_capacity")),
                "current_allocation": _number(raw.get("current_allocation")),
                "remaining_capacity": _number(raw.get("remaining_capacity")),
                "load_rate": _number(raw.get("load_rate")),
                "blocked_reason": _text(raw.get("blocked_reason")),
            }
        )

    raw_limitations = data.get("limitations")
    limitations = (
        [text for value in raw_limitations[:USER_RESULT_LIMITATIONS_MAX] if (text := _text(value))]
        if isinstance(raw_limitations, list)
        else []
    )
    return {
        "version": USER_RESULT_VERSION,
        "kind": "workload_report",
        "period_start": _text(data.get("period_start")),
        "period_end": _text(data.get("period_end")),
        "workdays": _number(data.get("workdays")),
        "as_of": _text(data.get("as_of")),
        "workload_weeks": _number(data.get("workload_weeks")),
        "people_count": len(people),
        "people": shown_people,
        "warnings": {
            "missing_estimate_count": _number(data.get("missing_estimate_count")),
            "unmapped_assignee_count": _number(data.get("unmapped_assignee_count")),
            "unscheduled_backlog_hours": _number(data.get("unscheduled_backlog_hours")),
            "limitations": limitations,
        },
    }


def build_user_result(*, tool_ref: str, content: Any) -> dict[str, Any] | None:
    """지원하는 내장 도구의 사용자 표시용 결과를 만든다.

    알 수 없는 내장·MCP·사용자 도구는 반환 구조와 민감 필드를 보장할 수
    없으므로 ``None``으로 두고 기존 상태·축약 출력 표시로 돌아간다.
    """

    if tool_ref != "workload_report":
        return None
    data = _mapping(content)
    return _workload_result(data) if data is not None else None
