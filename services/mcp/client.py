"""MCP Client — JSON-RPC 2.0 over HTTP (11_MCP_설계 §3·§4-3·§6).

공식 SDK 를 쓰지 않는다. 우리가 필요한 것은 `initialize` · `tools/list` ·
`tools/call` 셋뿐이고, 전부 JSON-RPC 한 번씩이다. SDK 를 넣으면 그 전송 계층
(stdio·SSE 세션 관리)까지 함께 들어오는데 서버 쪽은 우리가 등록하는 HTTP
엔드포인트라 쓸 일이 없다.

**오류 코드는 평가의 집계 키다**(11_MCP_설계 §6, 4_평가_설계 §4·§5). 여기서
쓰는 문자열이 그대로 `tool_call.error_code` 에 들어가므로 마음대로 늘리지 않는다.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import requests

from . import security

logger = logging.getLogger(__name__)

#: 호출 타임아웃(초). (연결, 읽기).
#:
#: 남의 서버다. 오래 잡고 있으면 Loop 전체가 그만큼 멈춘다 — 실패를 빨리
#: 돌려주고 에이전트가 다른 길을 찾게 하는 편이 낫다(설계 §4-3: 기본 30s).
TIMEOUT = (10, 30)

#: 응답 크기 상한. 남의 서버가 100MB 를 주면 우리 메모리가 먼저 죽는다.
MAX_RESPONSE_BYTES = 2 * 1024 * 1024

#: 프로토콜 버전. 서버가 다른 버전을 말해도 거절하지 않는다 — 우리가 쓰는
#: 세 메서드는 버전 사이에 바뀌지 않았고, 엄격히 막으면 멀쩡한 서버가 안 붙는다.
PROTOCOL_VERSION = "2025-06-18"


class McpError(Exception):
    """MCP 호출 실패. `code` 가 tool_call.error_code 로 그대로 들어간다."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def initialize_and_list_tools(*, endpoint_url: str, auth_token: str | None) -> list[dict[str, Any]]:
    """연결 테스트. 등록 화면이 부른다.

    `initialize` 를 먼저 보내는 이유는 그것이 핸드셰이크라서다 — 건너뛰고
    `tools/list` 만 보내면 규격을 지키는 서버가 거절한다.
    """

    security.recheck(endpoint_url)
    _rpc(endpoint_url, auth_token, "initialize", {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": {"name": "halil", "version": "1.0"},
    })
    result = _rpc(endpoint_url, auth_token, "tools/list", {})
    tools = result.get("tools")
    if not isinstance(tools, list):
        raise McpError("validation", "서버가 tools 목록을 주지 않았습니다.")
    return [_tool_row(tool) for tool in tools if isinstance(tool, dict) and tool.get("name")]


def call_tool(
    *, endpoint_url: str, auth_token: str | None, name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    """도구 하나를 부른다.

    MCP 는 도구 자체의 실패를 **HTTP 오류가 아니라 결과의 `isError`** 로 알린다
    (필수 필드 누락 같은 것). 전송 실패와 구분해서 `validation` 으로 매핑한다 —
    화면이 "담당자 미지정" 같은 사유를 그 자리에 보여줘야 한다.
    """

    security.recheck(endpoint_url)
    result = _rpc(endpoint_url, auth_token, "tools/call", {"name": name, "arguments": arguments})

    if result.get("isError"):
        raise McpError("validation", _text_of(result) or f"{name} 실행이 거부됐습니다.")

    # structuredContent 가 있으면 그것이 정본이다. 없으면 text 를 모아 준다.
    if isinstance(result.get("structuredContent"), dict):
        return result["structuredContent"]
    return {"content": _text_of(result)}


def _tool_row(tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": str(tool["name"])[:200],
        "description": tool.get("description") or "",
        # 스키마가 없으면 모델이 인자를 지어낸다. 빈 객체로 두면 "인자 없음"이라
        # 명시된 것이라 차라리 낫다.
        "input_schema": tool.get("inputSchema") or {"type": "object", "properties": {}},
    }


def _text_of(result: dict[str, Any]) -> str:
    parts = [
        item.get("text", "")
        for item in result.get("content") or []
        if isinstance(item, dict) and item.get("type") == "text"
    ]
    return "\n".join(part for part in parts if part).strip()


def _rpc(endpoint_url: str, auth_token: str | None, method: str, params: dict[str, Any]) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        # Streamable HTTP 서버는 둘 중 하나로 답한다. 둘 다 받겠다고 해야
        # 규격을 지키는 서버가 406 을 내지 않는다.
        "Accept": "application/json, text/event-stream",
    }
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    try:
        response = requests.post(
            endpoint_url, json=payload, headers=headers, timeout=TIMEOUT, stream=True
        )
    except requests.Timeout as exc:
        raise McpError("timeout", f"MCP 서버가 시간 안에 응답하지 않았습니다: {method}") from exc
    except requests.RequestException as exc:
        raise McpError("unreachable", f"MCP 서버에 연결하지 못했습니다: {method}") from exc

    if response.status_code in (401, 403):
        raise McpError("401", "MCP 서버 인증에 실패했습니다. 설정 > MCP 에서 연결을 확인하세요.")
    if response.status_code == 429:
        raise McpError("429", "MCP 서버가 요청 한도를 초과했다고 답했습니다. 잠시 후 다시 시도하세요.")
    if response.status_code >= 400:
        raise McpError("unreachable", f"MCP 서버가 오류를 반환했습니다: HTTP {response.status_code}")

    body = _read_capped(response)
    message = _parse(body)

    if "error" in message:
        error = message["error"] or {}
        raise McpError("validation", str(error.get("message") or "MCP 서버가 오류를 반환했습니다."))
    result = message.get("result")
    if not isinstance(result, dict):
        raise McpError("validation", f"MCP 응답에 result 가 없습니다: {method}")
    return result


def _read_capped(response: requests.Response) -> str:
    """상한까지만 읽는다. Content-Length 를 믿지 않는다 — 안 주는 서버가 있다."""

    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=64 * 1024):
        total += len(chunk)
        if total > MAX_RESPONSE_BYTES:
            response.close()
            raise McpError("validation", "MCP 응답이 너무 큽니다.")
        chunks.append(chunk)
    return b"".join(chunks).decode("utf-8", errors="replace")


def _parse(body: str) -> dict[str, Any]:
    """JSON 이거나 SSE 다.

    Streamable HTTP 는 같은 엔드포인트가 `application/json` 으로도
    `text/event-stream` 으로도 답할 수 있다. 후자면 `data:` 줄에 JSON-RPC
    메시지가 실려 온다 — 우리는 요청 하나에 응답 하나라 첫 메시지면 된다.
    """

    text = body.strip()
    # `data:` 로 시작하는지만 보면 안 된다. 규격대로 `event: message` 를 먼저
    # 보내는 서버가 흔하고, 그러면 첫 글자가 `e` 라 그냥 지나쳐 JSON 파싱이
    # 터진다. 어느 줄에 있든 첫 `data:` 를 찾는다.
    if not text.startswith("{"):
        for line in text.splitlines():
            if line.startswith("data:"):
                text = line[len("data:") :].strip()
                break
    try:
        message = json.loads(text)
    except json.JSONDecodeError as exc:
        raise McpError("validation", "MCP 응답을 JSON 으로 읽을 수 없습니다.") from exc
    if not isinstance(message, dict):
        raise McpError("validation", "MCP 응답이 JSON 객체가 아닙니다.")
    return message
