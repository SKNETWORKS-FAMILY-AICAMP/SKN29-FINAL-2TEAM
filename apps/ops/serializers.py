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
    "CONNECTED": "연결 정보 저장됨",
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


def guardrail_event_row_response(row: dict[str, Any]) -> dict[str, Any]:
    """가드레일 발동 한 건.

    `detail`을 그대로 내보내도 되는 이유는 **원문이 애초에 안 담기기 때문**이다
    (`GuardrailEventRepository` docstring). 건수·카테고리·점수뿐이라 임계값을
    조정하려면 이 값이 화면에 보여야 한다.
    """

    return {
        "event_id": str(row["event_id"]),
        "stage": row["stage"],
        "rule": row["rule"],
        "action": row["action"],
        "detail": row["detail"],
        "occurred_at": row["occurred_at"],
        "account_id": row["account_id"],
        "account_display_name": row["account_display_name"],
        "team_id": row["team_id"],
        "team_name": row["team_name"],
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
    supports_image_input = serializers.BooleanField(default=False)

    def validate_model(self, value):
        from apps.agents.serializers import AGENT_MODELS

        if value in AGENT_MODELS:
            raise serializers.ValidationError(
                f"{value} 는 이미 기본 제공하는 모델입니다. 다른 모델을 고르세요."
            )
        return value


class OpsMcpRegisterSerializer(serializers.Serializer):
    """운영자가 팀에 커스텀 도구 서버를 등록할 때 받는 값.

    **주소 검사는 여기서 하지 않는다.** 형식이 맞는 것과 연결해도 되는 주소인가는
    다른 문제이고, 후자는 DNS 를 풀어 봐야 안다(`services/mcp/security.py`).
    직렬화기에 네트워크 조회를 넣으면 실패가 400 인지 502 인지 구분되지 않는다.
    """

    team_id = serializers.CharField(max_length=5)
    name = serializers.CharField(max_length=100)
    endpoint_url = serializers.CharField(max_length=500)
    # 토큰이 없는 공개 서버도 있다. 빈 문자열은 없는 것으로 본다.
    auth_token = serializers.CharField(
        max_length=4000, required=False, allow_blank=True, allow_null=True, default=None
    )


class OpsMcpUpdateSerializer(OpsMcpRegisterSerializer):
    """수정 입력. 이름·주소는 등록과 같은 규칙이고 **토큰만 다르다.**

    화면은 저장된 토큰을 다시 보여주지 않는다(`server_response` 가 `has_token` 만
    준다). 그래서 「안 보냄」을 「지우라」로 읽으면 이름만 고쳐도 토큰이 날아간다 —
    바꾸려는 의사를 `replace_token` 으로 명시하게 한다.
    """

    replace_token = serializers.BooleanField(required=False, default=False)


def ops_mcp_row_response(row: dict[str, Any]) -> dict[str, Any]:
    """**토큰은 절대 안 나간다**(§4-2). 운영자 콘솔도 예외가 아니다."""

    return {
        "mcp_server_id": row["mcp_server_id"],
        "team_id": row["team_id"],
        "team_name": row["team_name"],
        "name": row["name"],
        "endpoint_url": row["endpoint_url"],
        "status": row["status"],
        "last_checked_at": row["last_checked_at"],
        "has_token": row["has_token"],
        "tool_count": row["tool_count"],
    }


def ops_model_row_response(row: dict[str, Any]) -> dict[str, Any]:
    """**키는 절대 안 나간다.** 운영자 콘솔도 예외가 아니다."""

    return {
        "conn_id": row["conn_id"],
        "team_id": row["team_id"],
        "team_name": row["team_name"],
        "label": row["label"],
        "base_url": row["base_url"],
        "model": row["model"],
        "supports_image_input": row.get("supports_image_input", False),
        "connected_at": row["connected_at"],
    }


class PurgeConfirmSerializer(serializers.Serializer):
    """완전 삭제 확인. **화면만 막으면 API 직접 호출이 열린 채로 남는다.**

    팀은 팀 이름, 계정은 이메일을 그대로 받는다 — 이름은 겹칠 수 있어서
    (실제로 「개발팀」이 둘이었다, 2026-08-19) 계정 쪽은 이메일이 맞다.
    """

    confirm_name = serializers.CharField(max_length=255)


class OpsGuardrailRegisterSerializer(serializers.Serializer):
    """운영자가 팀에 외부 가드레일을 등록할 때 받는 값.

    **`config` 와 `credential` 의 내용은 여기서 안 본다.** 공급자마다 필요한 키가
    달라서(Azure 는 엔드포인트, Bedrock 은 guardrail ID·리전, OpenAI Guardrails 는
    설정 JSON), 종류별 검사는 그 공급자를 아는 자리(`services/guardrails`)가
    한다 — 직렬화기에 세 벌의 조건문을 두면 종류가 늘 때마다 두 곳을 고쳐야 한다.

    **비밀값은 `credential` 로만 받는다.** `config` 는 목록 응답에 그대로 실리므로
    거기 키를 넣으면 화면과 감사 로그로 새어 나간다.
    """

    team_id = serializers.CharField(max_length=5)
    name = serializers.CharField(max_length=100)
    kind = serializers.ChoiceField(
        choices=["OPENAI_GUARDRAILS", "BEDROCK_GUARDRAILS", "AZURE_CONTENT_SAFETY"]
    )
    config = serializers.DictField(required=False, default=dict)
    credential = serializers.DictField(
        required=False, allow_null=True, default=None, write_only=True
    )


class OpsGuardrailUpdateSerializer(OpsGuardrailRegisterSerializer):
    """수정 입력. **자격증명만 규칙이 다르다.**

    화면은 저장된 값을 다시 보여주지 않는다(`ops_guardrail_row_response` 가
    `has_credential` 만 준다). 「안 보냄」을 「지우라」로 읽으면 이름만 고쳐도 키가
    날아가므로, 바꾸려는 의사를 `replace_credential` 로 명시하게 한다 — MCP 의
    `replace_token` 과 같은 규칙이다.

    `team_id` 는 안 받는다. 팀을 옮기는 것은 다른 팀 대화의 검사 경로를 바꾸는
    일이라, 지우고 다시 등록하는 편이 기록에도 정확하다.
    """

    team_id = None
    replace_credential = serializers.BooleanField(required=False, default=False)

    def get_fields(self):
        fields = super().get_fields()
        fields.pop("team_id", None)
        return fields


def ops_guardrail_row_response(row: dict[str, Any]) -> dict[str, Any]:
    """등록 한 건. **자격증명은 있는지 여부만 나간다.**"""

    return {
        "provider_id": row["provider_id"],
        "team_id": row.get("team_id"),
        "team_name": row.get("team_name"),
        "name": row["name"],
        "kind": row["kind"],
        "config": row.get("config") or {},
        "status": row["status"],
        "is_active": bool(row.get("is_active")),
        "last_checked_at": row.get("last_checked_at"),
        "has_credential": bool(row.get("has_credential")),
        "created_by": row.get("created_by"),
        "created_at": row.get("created_at"),
    }
