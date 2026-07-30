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
