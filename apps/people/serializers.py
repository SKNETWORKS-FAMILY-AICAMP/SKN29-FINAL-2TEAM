"""현재 People SQL 스키마의 API 표현 변환."""

from typing import Any


def team_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "team_id": row["team_id"],
        "name": row["name"],
        "owner_account_id": row["owner_account_id"],
        "src_org_id": row["src_org_id"],
        "member_count": row.get("member_count"),
        "created_at": row["created_at"],
    }


def team_member_response(row: dict[str, Any]) -> dict[str, Any]:
    """팀 명부 한 줄.

    `team_member`는 사람 단위라 계정이 없어도 팀원이다. 계정과 초대는 있으면
    붙고 없으면 `null`이다 — 없는 것을 "미가입"처럼 서버가 단정하지 않고,
    무엇으로 보일지는 화면이 정한다.
    """

    added_at = row.get("added_at")
    invited_at = row.get("invited_at")

    return {
        "team_member_id": row["team_member_id"],
        "person_id": row["person_id"],
        "name": row.get("name"),
        "org_name": row.get("org_name"),
        # 직급이 아니라 직책에 가깝다(HR의 person.job_role).
        "job_role": row.get("job_role"),
        "added_at": added_at.isoformat() if added_at else None,
        # 이 팀의 계정을 쓰고 있는가. 없으면 아직 가입 전이다.
        "account_id": row.get("account_id"),
        "account_email": row.get("account_email"),
        "account_status": row.get("account_status"),
        # 팀을 만든 사람은 명부에서 뺄 수 없다.
        "is_owner": bool(row.get("is_owner")),
        # 가장 최근 초대 하나. 취소하고 다시 보낸 이력은 명부에서 볼 것이 아니다.
        "invite_id": row.get("invite_id"),
        "invite_status": row.get("invite_status"),
        "invited_at": invited_at.isoformat() if invited_at else None,
    }


def team_setting_response(row: dict[str, Any]) -> dict[str, Any]:
    """팀 업무량 기준.

    정한 값(`*_wk_hours` 등)과 안 정했을 때 쓰이는 값(`hr_*`, `default_*`)을 함께
    준다. 화면이 빈 칸에 회색 글씨로 "지금 기준"을 보여줄 수 있어야, 비워 둔 것이
    "모른다"가 아니라 "HR 값을 따른다"로 읽힌다.
    """

    return {
        "capacity_wk_hours": row["capacity_wk_hours"],
        "overload_pct": row["overload_pct"],
        "workload_weeks": row["workload_weeks"],
        "hr_wk_hours_min": row["hr_wk_hours_min"],
        "hr_wk_hours_max": row["hr_wk_hours_max"],
        "default_overload_pct": row["default_overload_pct"],
        "default_workload_weeks": row["default_workload_weeks"],
    }
