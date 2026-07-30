"""커넥터 연결 상태의 API 표현."""

from typing import Any


def connector_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "conn_id": row["conn_id"],
        "connector_type": row["connector_type"],
        "granted_scopes": row["granted_scopes"],
        "auth_status": row["auth_status"],
        "connected_at": row["connected_at"],
    }


def person_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "person_id": row["person_id"],
        "name": row["name"],
        "email": row["email"],
        "org_id": row["org_id"],
        "org_name": row["org_name"],
        "job_role": row["job_role"],
    }


def people_db_summary_response(summary: dict[str, Any]) -> dict[str, Any]:
    """연결 확인 화면이 쓰는 요약.

    `scope_person_count`는 본인 조직과 하위 조직을 합한 인원으로, 초대할 수
    있는 범위와 같은 기준이다(`팀원_초대_계정_매핑_정책.md` 핵심 원칙 4).
    """

    person = summary["person"]
    return {
        "org_count": summary["org_count"],
        "person_count": summary["person_count"],
        "my_org_name": summary["my_org_name"],
        "my_org_person_count": summary["my_org_person_count"],
        "scope_person_count": summary["scope_person_count"],
        "person": None if person is None else person_response(person),
    }
