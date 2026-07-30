"""운영자 콘솔 입력 검증과 응답 표현."""

from typing import Any

from rest_framework import serializers


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=255)
    password = serializers.CharField(max_length=128, write_only=True)


def admin_response(account: dict[str, Any]) -> dict[str, Any]:
    return {
        "account_id": account["account_id"],
        "email": account["email"],
        "display_name": account["display_name"],
    }


def account_row_response(row: dict[str, Any]) -> dict[str, Any]:
    link_count = row["link_count"]
    if link_count == 0:
        mapping_status = "UNMAPPED"
    elif link_count == 1:
        mapping_status = "LINKED"
    else:
        mapping_status = "DUPLICATE"

    person = None
    if row["person_id"] is not None:
        person = {
            "person_id": row["person_id"],
            "name": row["person_name"],
            "org_id": row["org_id"],
            "org_name": row["org_name"],
        }

    return {
        "account_id": row["account_id"],
        "email": row["email"],
        "display_name": row["display_name"],
        "account_status": row["account_status"],
        "mapping_status": mapping_status,
        "link_count": link_count,
        "person": person,
        "services": row["services"] or [],
    }


# `connector_conn.auth_status`는 저장된 값 그대로 노출하고, 사람이 읽을 진단·다음
# 조치 문구는 여기서만 만든다(DB에는 그런 컬럼이 없음). CHECK 제약이 없는 컬럼이라
# 스키마 주석에 없는 값이 들어올 수도 있어, 두 매핑 다 기본값을 둔다.
_CONNECTOR_DIAGNOSIS = {
    "CONNECTED": "정상",
    "EXPIRED": "인증이 만료됐습니다.",
    "ERROR": "연결 중 오류가 발생했습니다.",
}
_CONNECTOR_NEXT_ACTION = {
    "CONNECTED": "조치 없음",
    "EXPIRED": "계정 소유자가 설정에서 재연결",
    "ERROR": "계정 소유자가 설정에서 연결 재시도",
}


def connector_row_response(row: dict[str, Any]) -> dict[str, Any]:
    auth_status = row["auth_status"]

    person = None
    if row["person_id"] is not None:
        person = {
            "person_id": row["person_id"],
            "name": row["person_name"],
            "org_id": row["org_id"],
            "org_name": row["org_name"],
        }

    return {
        "conn_id": row["conn_id"],
        "account_id": row["account_id"],
        "owner_email": row["owner_email"],
        "connector_type": row["connector_type"],
        "auth_status": auth_status,
        "connected_at": row["connected_at"],
        "person": person,
        "diagnosis": _CONNECTOR_DIAGNOSIS.get(auth_status, f"알 수 없는 연결 상태입니다: {auth_status}"),
        "next_action": _CONNECTOR_NEXT_ACTION.get(auth_status, "계정 소유자에게 연결 상태 확인 요청"),
    }
