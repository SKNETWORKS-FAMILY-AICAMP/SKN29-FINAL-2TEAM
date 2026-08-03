"""유효 가용용량·현재 할당량·부하율 계산.

**순수 함수다.** DB도 LLM도 부르지 않고, 넘겨받은 값만으로 같은 입력에 항상 같은
결과를 낸다. 조회는 호출자가 HR 어댑터와 리포지토리로 따로 한다.

무엇을 계산하는가
----------------
"이 사람이 선택 기간에 쓸 수 있는 시간 중 얼마가 이미 배정됐는가"다. 사람이 실제로
느끼는 부담이 아니다 — Jira에 적힌 계획 공수와 HR에 적힌 근무조건만 본다. 난이도·
스트레스처럼 데이터로 확인할 수 없는 것은 계수로 섞지 않는다.

```
용량   = (주 근무시간 ÷ 5) × 창 안의 근무일 수 − 창과 겹치는 승인 부재 − 고정일정
할당   = Σ remaining  (창 안에 마감이 있거나, 마감 없이 이미 진행 중인 일)
부하율 = 할당 ÷ 용량 × 100
```

`× 0.8` 같은 버퍼는 곱하지 않는다. 설계 문서(기획서 v5 등)가 쓰는 형태가 감산항
(`− 고정 비프로젝트 일정시간`)이고, 그 원천인 `cal_event`는 채우는 경로가 없어
0으로 둔다. 근거 없는 승수로 그 자리를 메우면 용량이 조용히 20% 줄어든다.

주의해서 볼 것
-------------
- 부재는 **반드시 창으로 자른다.** 육아휴직 214일을 통째로 빼면 용량이 음수가 되고,
  부하율을 오름차순 정렬했을 때 휴직자가 "가장 여유 있는 사람"으로 올라온다.
- 하루 연차는 원천에서 `start_at = end_at`으로 온다. 날짜 단위로 읽어 그날 전체를
  차감한다 — 시각 차로 계산하면 0시간이 된다.
- `wk_hours`에는 이미 FTE가 반영돼 있다(실측: 20시간 = 40 × 0.5). 여기 FTE를 다시
  곱하면 반토막 난다.
- 상태는 `status_category`만 본다. 표시 문자열(`status`)은 사이트마다 다르다.
"""

from datetime import date, datetime, timedelta
from typing import Any

# 공휴일 캘린더가 없어 월~금을 근무일로 본다. 결과의 제한사항에 남긴다.
_WORKDAYS_PER_WEEK = 5

# `workload_result.load_rate`가 NUMERIC(5,2)라 999.99가 상한이다. 잘려도 분자·분모를
# 함께 돌려주므로 원값을 복원할 수 있다.
_LOAD_RATE_MAX = 999.99

BLOCKED_NO_SCHEDULE = "NO_SCHEDULE"
BLOCKED_ON_LEAVE = "ON_LEAVE"
BLOCKED_NO_CAPACITY = "NO_EFFECTIVE_CAPACITY"


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        return date.fromisoformat(value[:10])
    return None


def _workdays(start: date, end: date) -> set[date]:
    """`[start, end)`의 근무일. 끝은 포함하지 않는다."""

    days = set()
    cursor = start
    while cursor < end:
        if cursor.weekday() < _WORKDAYS_PER_WEEK:
            days.add(cursor)
        cursor += timedelta(days=1)
    return days


def _weekly_hours(profile: dict[str, Any]) -> float | None:
    """주 근무시간. 없으면 None이고 호출자가 `NO_SCHEDULE`로 판정한다.

    `wk_hours`가 이미 FTE를 반영한 실제 시간이라 그대로 쓴다. 없을 때만 계약
    시간에 FTE를 곱한다. **둘 다 없으면 40시간 같은 값을 가정하지 않는다** —
    가정하면 근무조건을 모르는 사람이 풀타임으로 계산돼 부하가 낮게 나온다.
    """

    wk_hours = profile.get("wk_hours")
    if wk_hours is not None:
        return float(wk_hours)

    default_hours = profile.get("def_wk_hours")
    fte = profile.get("fte")
    if default_hours is not None and fte is not None:
        return float(default_hours) * float(fte)
    return None


def _absent_workdays(
    absences: list[dict[str, Any]],
    *,
    workdays: set[date],
    period_start: date,
    period_end: date,
) -> set[date]:
    """창 안에서 부재로 덮인 근무일.

    집합이라 부재 구간이 겹쳐도 하루가 두 번 차감되지 않는다. `end_at`은 **포함**
    으로 읽는다 — 하루 연차가 `start_at = end_at`으로 오기 때문이다.
    """

    covered: set[date] = set()
    for absence in absences:
        start = _as_date(absence.get("start_at"))
        end = _as_date(absence.get("end_at"))
        if start is None or end is None:
            continue
        cursor = max(start, period_start)
        last = min(end, period_end - timedelta(days=1))
        while cursor <= last:
            if cursor in workdays:
                covered.add(cursor)
            cursor += timedelta(days=1)
    return covered


def _counts_in_horizon(task: dict[str, Any], *, period_end: date) -> bool:
    """이 업무의 잔여공수를 이번 창의 분자에 넣는가.

    마감이 창 끝보다 앞이면 넣는다(지난 마감도 포함 — 밀린 일은 지금 해야 한다).
    마감이 없어도 이미 진행 중이면 넣는다. 마감도 없고 시작도 안 한 일은 넣지 않고
    Backlog로 따로 보여준다 — 언젠가 할 일을 이번 창에 합치면 과부하가 실제보다
    커 보인다.
    """

    due = _as_date(task.get("due_at"))
    if due is not None:
        return due < period_end
    return task.get("status_category") == "IN_PROGRESS"


def _load_rate(hours: float, capacity: float | None) -> float | None:
    if capacity is None or capacity <= 0:
        return None
    return min(round(hours / capacity * 100, 2), _LOAD_RATE_MAX)


def calculate(
    *,
    period_start: date,
    period_end: date,
    profiles: list[dict[str, Any]],
    absences: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
) -> dict[str, Any]:
    """기간 `[period_start, period_end)`의 인원별 부하.

    `profiles`가 대상자를 정한다(재직 중인 팀원). `tasks`에 있지만 `profiles`에
    없는 담당자의 일은 개인 합계에 안 들어가고 `unmapped_assignee_count`로만
    잡힌다 — 버리지 않고 세어서 노출한다.
    """

    workdays = _workdays(period_start, period_end)

    by_person: dict[str, list[dict[str, Any]]] = {
        profile["person_id"]: [] for profile in profiles
    }
    unmapped = 0
    # 같은 이슈가 두 소스로 들어오면 그 사람 부하가 2배가 된다.
    seen_issues: set[Any] = set()
    for task in tasks:
        issue_id = task.get("jira_issue_id")
        if issue_id in seen_issues:
            continue
        seen_issues.add(issue_id)

        person_id = task.get("assignee_person_id")
        if person_id not in by_person:
            unmapped += 1
            continue
        by_person[person_id].append(task)

    absences_by_person: dict[str, list[dict[str, Any]]] = {}
    for absence in absences:
        absences_by_person.setdefault(absence["person_id"], []).append(absence)

    people = []
    for profile in sorted(profiles, key=lambda row: row["person_id"]):
        person_id = profile["person_id"]
        weekly_hours = _weekly_hours(profile)

        allocation = 0.0
        backlog_hours = 0.0
        backlog_count = 0
        missing_estimate = 0
        by_project: dict[str, float] = {}
        # 키 → 표시 이름. 예전에 저장한 소스는 이름이 없어 키로 대체된다.
        project_names: dict[str, str] = {}

        for task in by_person[person_id]:
            if task.get("status_category") == "DONE":
                continue
            remaining = task.get("remaining")
            if remaining is None:
                # 0으로 간주하면 공수를 안 적은 사람이 한가해 보인다.
                missing_estimate += 1
                continue
            remaining = float(remaining)

            if _counts_in_horizon(task, period_end=period_end):
                allocation += remaining
                project_key = task.get("project_key") or "UNKNOWN"
                by_project[project_key] = by_project.get(project_key, 0.0) + remaining
                project_names.setdefault(project_key, task.get("project_name") or project_key)
            elif task.get("due_at") is None:
                backlog_hours += remaining
                backlog_count += 1

        if weekly_hours is None:
            capacity: float | None = None
            gross = None
            absence_hours = None
            absent_count = 0
            blocked_reason: str | None = BLOCKED_NO_SCHEDULE
        else:
            daily_hours = weekly_hours / _WORKDAYS_PER_WEEK
            absent_days = _absent_workdays(
                absences_by_person.get(person_id, []),
                workdays=workdays,
                period_start=period_start,
                period_end=period_end,
            )
            absent_count = len(absent_days)
            gross = round(len(workdays) * daily_hours, 2)
            absence_hours = round(absent_count * daily_hours, 2)
            # 고정일정(`cal_event`)은 채우는 경로가 없어 0이다. 제한사항으로 노출한다.
            capacity = round(gross - absence_hours, 2)
            blocked_reason = None
            if capacity <= 0:
                blocked_reason = BLOCKED_ON_LEAVE if absent_days else BLOCKED_NO_CAPACITY

        allocation = round(allocation, 2)
        people.append(
            {
                "person_id": person_id,
                "name": profile.get("name"),
                "job_role": profile.get("job_role"),
                "gross_capacity": gross,
                "absence_hours": absence_hours,
                "absent_days": absent_count,
                "effective_capacity": capacity,
                "current_allocation": allocation,
                "remaining_capacity": (
                    None if blocked_reason is not None else round(capacity - allocation, 2)
                ),
                "load_rate": None if blocked_reason is not None else _load_rate(allocation, capacity),
                "blocked_reason": blocked_reason,
                "by_project": [
                    {
                        "project_key": key,
                        "project_name": project_names.get(key, key),
                        "hours": round(hours, 2),
                        "load_rate": None if blocked_reason is not None else _load_rate(hours, capacity),
                    }
                    for key, hours in sorted(by_project.items())
                ],
                "unscheduled_backlog_hours": round(backlog_hours, 2),
                "unscheduled_backlog_count": backlog_count,
                "missing_estimate_count": missing_estimate,
            }
        )

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "workdays": len(workdays),
        "people": people,
        "unmapped_assignee_count": unmapped,
        "missing_estimate_count": sum(person["missing_estimate_count"] for person in people),
        "unscheduled_backlog_hours": round(
            sum(person["unscheduled_backlog_hours"] for person in people), 2
        ),
        "limitations": [
            "공휴일 캘린더가 없어 월~금을 근무일로 계산했다.",
            "회의·돌발업무는 반영하지 않았다(cal_event를 채우는 경로가 없다).",
        ],
    }
