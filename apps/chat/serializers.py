"""Chat 입력 검증과 API 표현."""

from typing import Any

from rest_framework import serializers


class ChatSessionCreateSerializer(serializers.Serializer):
    """대화를 연다.

    `agent_id` 는 여전히 필수다. 다만 **그 값을 사람이 고르지는 않는다** —
    화면이 플랫폼의 정문(`agent:*` 를 가진 에이전트)을 자동으로 넣는다.

    ⚠ **옛 주석은 틀렸다 (2026-08-12).** 「어느 에이전트가 답할지는 사람이
    고른다(확정 ①), 서버가 알아서 고르는 라우터는 v1 에 없다」고 적혀 있었다.
    Chat 의 에이전트 선택기를 없앴고(`58ed034`), 정문이 필요하면 다른 에이전트에게
    **위임한다**(`agent:*`, `8025981`) — 라우팅이 없다는 서술은 더 이상 맞지 않는다.

    「고른 뒤에는 바꾸지 않는다」도 이제 다른 이유로 유지된다. 갈아탈 UI 가 없어서다.
    턴마다 어느 에이전트가 돌았는지는 `agent_run.agent_id` 에 남는다.
    """

    agent_id = serializers.CharField(max_length=5)
    proj_id = serializers.CharField(max_length=5, required=False, allow_null=True, default=None)
    title = serializers.CharField(max_length=200, required=False, allow_null=True, default=None)


class ChatMessageCreateSerializer(serializers.Serializer):
    content = serializers.CharField(max_length=10000)


class ChatSessionToolsSerializer(serializers.Serializer):
    """이 대화 전용 도구 목록을 저장한다(2026-08-18, Chat "+" 버튼).

    `tool_refs=null`이면 커스터마이즈를 지우고 에이전트 원래 값으로
    되돌린다 — 빈 리스트(`[]`)는 "이 대화에서 도구를 전부 껐다"는 다른
    뜻이라 `allow_null`로 따로 받는다(`required=True`로 필드 자체는 항상
    받되, 값 자체가 null일 수 있게).
    """

    tool_refs = serializers.ListField(
        child=serializers.CharField(max_length=100), allow_null=True, allow_empty=True
    )


class ChatConfirmSerializer(serializers.Serializer):
    """확인 카드의 승인.

    **무엇을 실행할지는 받지 않는다.** 승인 대상은 서버가 저장해 둔 그 호출이고,
    화면은 "그걸 승인한다"는 사실과 골라 낸 항목만 보낸다 — 실행할 인자를 화면이
    보내면 승인 게이트가 아무것도 막지 못한다.

    `selected` 는 확인 카드에서 체크한 항목의 인덱스다. 비우면 전체 승인이다.
    """

    selected = serializers.ListField(
        child=serializers.IntegerField(min_value=0), required=False, allow_empty=True, default=None
    )


def session_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": row["session_id"],
        "agent_id": row["agent_id"],
        # 신규(버전) 스키마 에이전트로 연 대화만 채워진다 — 레거시는 항상
        # `None`(services/agent_runtime/loader.py가 아직 이 값을 안 쓴다).
        # 화면이 "이 대화가 어느 실행 경로를 타는지"를 굳이 알 필요는 없지만,
        # 값이 있다는 사실 자체가 새 엔진으로 도는 대화라는 신호다.
        "agent_version_id": row.get("agent_version_id"),
        "agent_name": row.get("agent_name"),
        # None = 이 대화는 도구를 커스터마이즈 안 함(에이전트 원래 값을
        # 그대로 씀). 빈 리스트는 "이 대화에서 도구를 전부 껐다"는 실제
        # 선택이라 다른 뜻이다(2026-08-18, Chat "+" 버튼).
        "tool_refs_override": row.get("tool_refs_override"),
        "proj_id": row.get("proj_id"),
        "title": row.get("title"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def message_response(row: dict[str, Any]) -> dict[str, Any]:
    """`content.resume` 은 내보내지 않는다.

    재개에 필요한 모델 대화 상태(도구 원본 출력 포함)라 화면이 쓸 일이 없고,
    보내면 근거로 오해하기 좋은 원문이 그대로 노출된다. 서버 안에만 둔다.
    """

    content = dict(row["content"] or {})
    content.pop("resume", None)
    return {
        "message_id": row["message_id"],
        "role": row["role"],
        "content": content,
        "created_at": row.get("created_at"),
    }
