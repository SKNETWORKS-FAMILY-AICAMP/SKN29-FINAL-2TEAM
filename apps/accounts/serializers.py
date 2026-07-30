"""회원가입·로그인·팀원 초대의 입력 검증과 API 표현."""

from typing import Any

from rest_framework import serializers


def validate_new_password(value: str) -> str:
    # 가입 화면이 안내하는 규칙("8자 이상의 영문, 숫자 조합")과 같은 기준.
    if len(value) < 8:
        raise serializers.ValidationError("비밀번호는 8자 이상이어야 합니다.")
    if not any(char.isalpha() for char in value) or not any(char.isdigit() for char in value):
        raise serializers.ValidationError("비밀번호는 영문과 숫자를 함께 포함해야 합니다.")
    return value


class SignupSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=255)
    password = serializers.CharField(max_length=128, write_only=True)
    display_name = serializers.CharField(max_length=100)
    invite_code = serializers.CharField(
        max_length=255,
        allow_blank=True,
        required=False,
        default="",
    )

    def validate_password(self, value: str) -> str:
        return validate_new_password(value)


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=255)


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=500)
    password = serializers.CharField(max_length=128, write_only=True)

    def validate_password(self, value: str) -> str:
        return validate_new_password(value)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=255)
    password = serializers.CharField(max_length=128, write_only=True)


class InviteCodeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=255)


class InviteCreateSerializer(serializers.Serializer):
    person_id = serializers.CharField(max_length=5)


def account_role(profile: dict[str, Any]) -> str:
    """가입 경로로 정해지는 역할.

    초대 코드로 들어온 계정만 팀원이다. 직접 가입은 팀장으로 본다 — HR
    시스템을 연결할 권한이 회사에서 팀장에게만 주어진다는 전제이고, HR 매칭에
    실패하면 온보딩에서 더 진행되지 않으므로 권한이 실제로 열리지도 않는다.
    """

    return "member" if profile["invited"] else "leader"


def account_response(profile: dict[str, Any]) -> dict[str, Any]:
    person = profile["person"]
    return {
        "account_id": profile["account_id"],
        "email": profile["email"],
        "display_name": profile["display_name"],
        "account_status": profile["account_status"],
        "role": account_role(profile),
        "scope_org_ids": profile["scope_org_ids"],
        "person": None
        if person is None
        else {
            "person_id": person["person_id"],
            "name": person["name"],
            "email": person["email"],
            "org_id": person["org_id"],
            "org_name": person["org_name"],
            "job_role": person["job_role"],
        },
    }


def invite_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "invite_id": row["invite_id"],
        "person_id": row["person_id"],
        "person_name": row["person_name"],
        "person_email": row["person_email"],
        "org_name": row["org_name"],
        "status": row["status"],
        "expires_at": row["expires_at"],
        "accepted_at": row["accepted_at"],
        "created_at": row["created_at"],
    }


def invite_candidate_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "person_id": row["person_id"],
        "name": row["name"],
        "email": row["email"],
        "org_id": row["org_id"],
        "org_name": row["org_name"],
        "job_role": row["job_role"],
    }


def invite_preview_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "person_name": row["person_name"],
        "person_email": row["person_email"],
        "org_name": row["org_name"],
        "expires_at": row["expires_at"],
    }
