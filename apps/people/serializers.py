"""현재 People SQL 스키마의 API 표현 변환."""

from typing import Any


def organization_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "org_id": row["org_id"],
        "organization_id": row["org_id"],
        "up_org_id": row["up_org_id"],
        "parent_organization_id": row["up_org_id"],
        "mgr_id": row["mgr_id"],
        "name": row["name"],
        "org_type": row["org_type"],
        "status": row["status"],
        "is_active": row["status"] == "ACTIVE",
    }


def person_response(row: dict[str, Any]) -> dict[str, Any]:
    fte = row["fte"]
    return {
        "person_id": row["person_id"],
        "emp_id": row["emp_id"],
        "employee_id": row["emp_id"],
        "name": row["name"],
        "email": row["email"],
        "org_id": row["org_id"],
        "organization": row["org_id"],
        "org_name": row["org_name"],
        "organization_name": row["org_name"],
        "job_role": row["job_role"],
        "level_id": row["level_id"],
        "level_name": row["level_name"],
        "emp_status": row["emp_status"],
        "employment_status": row["emp_status"],
        "timezone": row["tz"] or "Asia/Seoul",
        "fte": str(fte) if fte is not None else None,
        "weekly_hours": str(row["wk_hours"]) if row["wk_hours"] is not None else None,
        "default_weekly_hours": (
            str(row["def_wk_hours"]) if row["def_wk_hours"] is not None else None
        ),
    }


def team_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "team_id": row["team_id"],
        "name": row["name"],
        "owner_account_id": row["owner_account_id"],
        "src_org_id": row["src_org_id"],
        "member_count": row.get("member_count"),
        "created_at": row["created_at"],
    }
