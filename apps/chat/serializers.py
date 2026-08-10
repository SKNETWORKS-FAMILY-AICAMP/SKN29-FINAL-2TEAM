"""Chat 입력 검증과 API 표현."""

from typing import Any

from rest_framework import serializers


class ChatSessionCreateSerializer(serializers.Serializer):
    """대화를 연다.

    `agent_id` 는 필수다. **어느 에이전트가 답할지는 사람이 고른다**(8/11 확정 ①)
    — 질문을 보고 서버가 알아서 고르는 라우터는 v1 에 없다. 고른 뒤에는 바꾸지
    않는다. 대화 중간에 갈면 앞선 턴이 다른 스캐폴드·다른 도구로 만들어진 것이
    되어 이어지는 답의 근거가 흔들린다.
    """

    agent_id = serializers.CharField(max_length=5)
    proj_id = serializers.CharField(max_length=5, required=False, allow_null=True, default=None)
    title = serializers.CharField(max_length=200, required=False, allow_null=True, default=None)


class ChatMessageCreateSerializer(serializers.Serializer):
    content = serializers.CharField(max_length=10000)


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
        "agent_name": row.get("agent_name"),
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
