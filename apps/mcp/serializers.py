"""MCP 서버 등록 입력 검증과 API 표현."""

from typing import Any

from rest_framework import serializers


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
