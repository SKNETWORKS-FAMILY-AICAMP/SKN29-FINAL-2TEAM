"""MCP 서버 등록 입력 검증과 API 표현."""

from typing import Any

from rest_framework import serializers


class McpServerCreateSerializer(serializers.Serializer):
    """URL 검사는 여기서 하지 않는다.

    형식만 맞으면 통과하는 것과 **연결해도 되는 주소인가**는 다른 문제이고,
    후자는 DNS 를 풀어 봐야 안다(`services/mcp/security.py`). 직렬화기에
    네트워크 조회를 넣으면 검증 실패가 400 인지 502 인지 구분되지 않는다.
    """

    name = serializers.CharField(max_length=100)
    endpoint_url = serializers.CharField(max_length=500)
    # 토큰이 없는 공개 서버도 있다. 빈 문자열은 없는 것으로 본다.
    auth_token = serializers.CharField(
        max_length=4000, required=False, allow_blank=True, allow_null=True, default=None
    )


def server_response(row: dict[str, Any]) -> dict[str, Any]:
    """**토큰은 절대 내보내지 않는다**(11_MCP_설계 §4-2). 있는지 여부만 준다."""

    return {
        "mcp_server_id": row["mcp_server_id"],
        "name": row.get("name"),
        "endpoint_url": row.get("endpoint_url"),
        "status": row.get("status"),
        "last_checked_at": row.get("last_checked_at"),
        "has_token": row.get("has_token", False),
        "tools": row.get("tools") or [],
    }
