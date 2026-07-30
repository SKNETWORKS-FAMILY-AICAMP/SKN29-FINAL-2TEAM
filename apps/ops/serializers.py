"""관리자 로그인 입력 검증과 응답 표현."""

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
