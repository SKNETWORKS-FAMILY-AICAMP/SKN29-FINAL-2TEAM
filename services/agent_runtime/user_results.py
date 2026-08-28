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
USER_RESULT_ABSENCES_MAX = 20
USER_RESULT_JIRA_UPCOMING_MAX = 5
USER_RESULT_ITEMS_MAX = 20
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


def _workload_limitation(value: Any) -> str | None:
    """계산기 내부 표현을 작업 과정에 맞는 사용자 문장으로 바꾼다."""

    text = _text(value)
    if text is None:
        return None
    replacements = {
        "공휴일 캘린더가 없어 월~금을 근무일로 계산했다.":
            "공휴일 정보가 없어 월요일부터 금요일까지를 근무일로 계산했습니다.",
        "회의·돌발업무는 반영하지 않았다(cal_event를 채우는 경로가 없다).":
            "회의와 돌발 업무는 반영되지 않았습니다.",
    }
    return replacements.get(text, text)


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
        [
            text
            for value in raw_limitations[:USER_RESULT_LIMITATIONS_MAX]
            if (text := _workload_limitation(value))
        ]
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


def _absence_result(data: dict[str, Any]) -> dict[str, Any]:
    raw_period = data.get("period")
    period = raw_period if isinstance(raw_period, dict) else {}
    raw_absences = data.get("absences")
    absences = raw_absences if isinstance(raw_absences, list) else []
    shown_absences: list[dict[str, Any]] = []
    for raw in absences[:USER_RESULT_ABSENCES_MAX]:
        if not isinstance(raw, dict):
            continue
        shown_absences.append(
            {
                "name": _text(raw.get("name")),
                "absence_type": _text(raw.get("absence_type")),
                "start_at": _text(raw.get("start_at")),
                "end_at": _text(raw.get("end_at")),
            }
        )
    return {
        "version": USER_RESULT_VERSION,
        "kind": "absence_list",
        "period_start": _text(period.get("start")),
        "period_end": _text(period.get("end")),
        "absence_count": len(absences),
        "absences": shown_absences,
    }


def _jira_result(data: dict[str, Any]) -> dict[str, Any]:
    raw_counts = data.get("counts")
    counts = raw_counts if isinstance(raw_counts, dict) else {}
    raw_upcoming = data.get("upcoming")
    upcoming = raw_upcoming if isinstance(raw_upcoming, list) else []
    shown_upcoming: list[dict[str, Any]] = []
    for raw in upcoming[:USER_RESULT_JIRA_UPCOMING_MAX]:
        if not isinstance(raw, dict):
            continue
        shown_upcoming.append(
            {
                "key": _text(raw.get("key")),
                "title": _text(raw.get("title")),
                "due": _text(raw.get("due")),
            }
        )
    return {
        "version": USER_RESULT_VERSION,
        "kind": "jira_get_issues",
        "project_key": _text(data.get("project_key")),
        "total": _number(data.get("total")),
        "counts": {
            "to_do": _number(counts.get("TO_DO")),
            "in_progress": _number(counts.get("IN_PROGRESS")),
            "done": _number(counts.get("DONE")),
            "unknown": _number(counts.get("UNKNOWN")),
        },
        "upcoming": shown_upcoming,
    }


def _datetime_result(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": USER_RESULT_VERSION,
        "kind": "current_datetime",
        "date": _text(data.get("date")),
        "time": _text(data.get("time")),
        "timezone": _text(data.get("timezone")),
        "weekday_kr": _text(data.get("weekday_kr")),
    }


def _people_result(data: dict[str, Any]) -> dict[str, Any]:
    raw_members = data.get("members")
    members = raw_members if isinstance(raw_members, list) else []
    shown: list[dict[str, Any]] = []
    for raw in members[:USER_RESULT_ITEMS_MAX]:
        if not isinstance(raw, dict):
            continue
        shown.append(
            {
                "name": _text(raw.get("name")),
                "job_role": _text(raw.get("job_role")),
                "org_name": _text(raw.get("org_name")),
            }
        )
    return {
        "version": USER_RESULT_VERSION,
        "kind": "people_list",
        "member_count": len(members),
        "members": shown,
    }


def _projects_result(data: dict[str, Any]) -> dict[str, Any]:
    raw_projects = data.get("projects")
    projects = raw_projects if isinstance(raw_projects, list) else []
    shown: list[dict[str, Any]] = []
    for raw in projects[:USER_RESULT_ITEMS_MAX]:
        if not isinstance(raw, dict):
            continue
        shown.append(
            {
                "name": _text(raw.get("name")),
                "status": _text(raw.get("status")),
                "progress": _number(raw.get("progress")),
            }
        )
    return {
        "version": USER_RESULT_VERSION,
        "kind": "project_list",
        "project_count": len(projects),
        "projects": shown,
    }


def _tasks_result(data: dict[str, Any]) -> dict[str, Any]:
    raw_tasks = data.get("tasks")
    tasks = raw_tasks if isinstance(raw_tasks, list) else []
    shown: list[dict[str, Any]] = []
    for raw in tasks[:USER_RESULT_ITEMS_MAX]:
        if not isinstance(raw, dict):
            continue
        shown.append(
            {
                "title": _text(raw.get("title")),
                "status": _text(raw.get("status")),
                "priority": _text(raw.get("priority")),
                "due_at": _text(raw.get("due_at")),
                "effort_hours": _number(raw.get("effort_hours")),
                "required_role": _text(raw.get("required_role")),
            }
        )
    return {
        "version": USER_RESULT_VERSION,
        "kind": "task_list",
        "task_count": len(tasks),
        "tasks": shown,
    }


def _documents_result(data: dict[str, Any]) -> dict[str, Any]:
    raw_documents = data.get("documents")
    documents = raw_documents if isinstance(raw_documents, list) else []
    raw_pending = data.get("not_collected")
    pending = raw_pending if isinstance(raw_pending, list) else []

    shown_documents: list[dict[str, Any]] = []
    for raw in documents[:USER_RESULT_ITEMS_MAX]:
        if not isinstance(raw, dict):
            continue
        shown_documents.append(
            {
                "file_name": _text(raw.get("file_name")),
                "project": _text(raw.get("project")),
                "role": _text(raw.get("role")),
                "search_ready": raw.get("search_ready") if isinstance(raw.get("search_ready"), bool) else None,
            }
        )

    shown_pending: list[dict[str, Any]] = []
    for raw in pending[:USER_RESULT_ITEMS_MAX]:
        if not isinstance(raw, dict):
            continue
        shown_pending.append(
            {
                "file_name": _text(raw.get("file_name")),
                "folder": _text(raw.get("folder")),
                "supported": raw.get("supported") if isinstance(raw.get("supported"), bool) else None,
            }
        )

    return {
        "version": USER_RESULT_VERSION,
        "kind": "document_list",
        "document_count": len(documents),
        "documents": shown_documents,
        "not_collected_count": len(pending),
        "not_collected": shown_pending,
        "truncated": data.get("truncated") is True,
        "storage_unavailable": bool(data.get("storage_error")),
    }


def build_user_result(*, tool_ref: str, content: Any) -> dict[str, Any] | None:
    """지원하는 내장 도구의 사용자 표시용 결과를 만든다.

    알 수 없는 내장·MCP·사용자 도구는 반환 구조와 민감 필드를 보장할 수
    없으므로 ``None``으로 두고 기존 상태·축약 출력 표시로 돌아간다.
    """

    data = _mapping(content)
    if data is None:
        return None
    builders = {
        "get_current_datetime": _datetime_result,
        "people_list": _people_result,
        "workload_report": _workload_result,
        "project_list": _projects_result,
        "task_list": _tasks_result,
        "document_list": _documents_result,
        "absence_list": _absence_result,
        "jira_get_issues": _jira_result,
    }
    builder = builders.get(tool_ref)
    return builder(data) if builder is not None else None
