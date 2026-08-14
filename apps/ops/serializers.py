"""운영자 콘솔 입력 검증과 응답 표현."""

from typing import Any

from rest_framework import serializers


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=255)
    password = serializers.CharField(max_length=128, write_only=True)


class InviteTtlSerializer(serializers.Serializer):
    days = serializers.IntegerField()
    reason = serializers.CharField(allow_blank=True, required=False, default="")


class NoticeSerializer(serializers.Serializer):
    # 제목/내용/일정 필드는 Repository가 정확한 한글 문구로 검증하도록
    # 여기서는 타입만 확인하고 공백·누락 여부는 걸러내지 않는다(allow_blank/
    # required=False). status/schedule_mode는 값 종류 자체가 코드 오류에
    # 가까워 DRF 기본 메시지로 충분하다고 보고 ChoiceField로 막는다.
    title = serializers.CharField(max_length=200, allow_blank=True, required=False, default="")
    content = serializers.CharField(allow_blank=True, required=False, default="")
    status = serializers.ChoiceField(choices=["PUBLISHED", "SCHEDULED", "ENDED"])
    schedule_date = serializers.DateField(required=False, allow_null=True, default=None)
    schedule_time = serializers.TimeField(required=False, allow_null=True, default=None)
    schedule_mode = serializers.ChoiceField(choices=["FROM", "UNTIL"])
    reason = serializers.CharField(allow_blank=True, required=False, default="")


class NoticeDeleteSerializer(serializers.Serializer):
    reason = serializers.CharField(allow_blank=True, required=False, default="")


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
        "is_admin": row["is_admin"],
        "team_id": row["team_id"],
        "team_name": row["team_name"],
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
    "REVOKED": "운영자가 연결을 해제했습니다.",
}
_CONNECTOR_NEXT_ACTION = {
    "CONNECTED": "조치 없음",
    "EXPIRED": "계정 소유자가 설정에서 재연결",
    "ERROR": "계정 소유자가 설정에서 연결 재시도",
    "REVOKED": "계정 소유자가 설정에서 다시 연결",
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


def notice_row_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "notice_id": row["notice_id"],
        "title": row["title"],
        "content": row["content"],
        "status": row["status"],
        "schedule_at": row["schedule_at"],
        "schedule_mode": row["schedule_mode"],
        "created_by": row["created_by"],
        "created_by_name": row["created_by_name"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def policy_change_row_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "audit_id": row["audit_id"],
        "action": row["action"],
        "target_type": row["target_type"],
        "target_id": row["target_id"],
        "payload": row["payload"],
        "actor_account_id": row["actor_account_id"],
        "actor_display_name": row["actor_display_name"],
        "actor_email": row["actor_email"],
        "occurred_at": row["occurred_at"],
    }


class TeamOwnerTransferSerializer(serializers.Serializer):
    """팀 소유자를 누구에게 넘길지, 그리고 왜.

    「그 팀 계정인가·살아 있는가」는 여기서 못 본다(팀을 모른다) — Repository 가
    트랜잭션 안에서 본다.
    """

    account_id = serializers.CharField(max_length=5)
    reason = serializers.CharField(allow_blank=True, required=False, default="")


class ReasonSerializer(serializers.Serializer):
    """**왜 그렇게 했는지.** 대상은 경로에 있으므로 사유만 받는다.

    운영자 조치는 남의 것을 건드린다 — 계정을 세우고, 연결을 끊고, 초대를
    폐기한다. 무엇을 했는지는 감사 로그가 이미 남기지만 **왜 했는지는 그때 그
    사람 머릿속에만 있다.** 나중에 「이거 왜 이렇게 됐죠」에 답할 수 있어야 한다
    (2026-08-13에 잠금·연결 해제·초대 폐기까지 넓혔다).

    **비워 둘 수 있게 한다.** 급한 상황에서 사유 때문에 조치를 못 하면 그게 더
    나쁘다 — 사유는 기록을 돕는 것이지 관문이 아니다.
    """

    reason = serializers.CharField(allow_blank=True, required=False, default="")


class AdminGrantSerializer(serializers.Serializer):
    """운영자 권한을 켤지 끌지, 그리고 왜.

    사유는 선택이다(전역 정책의 다른 조치와 같다). 다만 **권한을 주고받은 기록은
    사유가 비어 있어도 남는다** — 누가 누구에게 언제가 먼저다.
    """

    is_admin = serializers.BooleanField()
    reason = serializers.CharField(allow_blank=True, required=False, default="")


class OpsModelRegisterSerializer(serializers.Serializer):
    """운영자가 팀에 모델을 등록할 때 받는 값.

    `AGENT_MODELS` 와 겹치는 이름은 거절한다 — 경로가 모델 이름으로 정해지므로
    기본 제공과 이름이 같으면 그 선택이 뜻을 잃는다.
    """

    team_id = serializers.CharField(max_length=5)
    label = serializers.CharField(max_length=60, trim_whitespace=True)
    base_url = serializers.URLField(max_length=300)
    api_key = serializers.CharField(max_length=200, trim_whitespace=True)
    model = serializers.CharField(max_length=100, trim_whitespace=True)

    def validate_model(self, value):
        from apps.agents.serializers import AGENT_MODELS

        if value in AGENT_MODELS:
            raise serializers.ValidationError(
                f"{value} 는 이미 기본 제공하는 모델입니다. 다른 모델을 고르세요."
            )
        return value


def ops_model_row_response(row: dict[str, Any]) -> dict[str, Any]:
    """**키는 절대 안 나간다.** 운영자 콘솔도 예외가 아니다."""

    return {
        "conn_id": row["conn_id"],
        "team_id": row["team_id"],
        "team_name": row["team_name"],
        "label": row["label"],
        "base_url": row["base_url"],
        "model": row["model"],
        "connected_at": row["connected_at"],
    }
