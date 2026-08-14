"""시험용 MCP 서버. **개발 환경에서만 쓴다.**

우리 클라이언트(`services/mcp/client.py`)가 진짜 서버를 상대로 도는지 확인할
자리가 없었다 — 단위 테스트는 전부 `requests.post` 를 목으로 막아서, 핸드셰이크
순서나 응답 모양이 실제로 맞는지는 한 번도 검증된 적이 없다(2026-08-13).

우리 클라이언트가 쓰는 것은 셋뿐이라 그것만 구현한다:
`initialize` → `tools/list` → `tools/call`. 전송은 JSON-RPC 2.0 over HTTP POST
하나씩이다(SSE 세션도 stdio 도 쓰지 않는다).

**응답 형식을 둘 다 낸다.** `?sse=1` 을 붙이면 `text/event-stream` 으로 답한다 —
클라이언트의 SSE 파싱 경로(`_parse` 의 `data:` 찾기)가 실제로 동작하는지 보려면
그 모양을 내 주는 서버가 필요하다.

토큰을 설정하면(`MCP_DEV_TOKEN`) `Authorization: Bearer` 를 검사한다. 안 맞으면
401 — 클라이언트가 인증 실패를 어떻게 표시하는지 확인하는 용도다.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = os.environ.get("MCP_DEV_TOKEN", "").strip()
PORT = int(os.environ.get("MCP_DEV_PORT", "9000"))

TOOLS = [
    {
        "name": "echo",
        "description": "받은 문장을 그대로 돌려준다. 연결이 살아 있는지 보는 용도다.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "돌려받을 문장"}},
            "required": ["text"],
        },
    },
    {
        "name": "add",
        "description": "두 수를 더한다. 인자가 제대로 전달되는지 보는 용도다.",
        "inputSchema": {
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
            "required": ["a", "b"],
        },
    },
]


def _result(method: str, params: dict) -> dict:
    if method == "initialize":
        return {
            "protocolVersion": params.get("protocolVersion", "2025-06-18"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "halil-dev-mcp", "version": "0.1.0"},
        }
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if name == "echo":
            return {"content": [{"type": "text", "text": str(args.get("text", ""))}]}
        if name == "add":
            return {"content": [{"type": "text", "text": str(args.get("a", 0) + args.get("b", 0))}]}
        # 규격상 도구 실패는 JSON-RPC 오류가 아니라 isError 다.
        return {"content": [{"type": "text", "text": f"없는 도구: {name}"}], "isError": True}
    raise KeyError(method)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # noqa: A003 - 부모 시그니처
        print(f"[dev-mcp] {fmt % args}", flush=True)

    def do_POST(self):  # noqa: N802 - 부모 시그니처
        # ⚠ **응답보다 먼저 본문을 다 읽는다.** HTTP/1.1 은 연결을 재사용하는데,
        # 본문을 남긴 채 응답하면 그 바이트가 소켓에 남아 **다음 요청의 요청 줄로
        # 읽힌다.** 앞단 Caddy 가 업스트림 연결을 풀에 두고 돌려쓰므로, 토큰 없는
        # 요청 하나가 뒤따르는 정상 요청을 깨뜨린다(2026-08-14 실측:
        # `Unsupported method ('{"jsonrpc":...}POST')` 501).
        # 공개 주소라 스캐너가 인증 없이 두드리고 가는 것만으로도 재현된다.
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""

        if TOKEN and self.headers.get("Authorization") != f"Bearer {TOKEN}":
            self._send(401, json.dumps({"error": "unauthorized"}), "application/json")
            return

        try:
            message = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._send(400, json.dumps({"error": "bad json"}), "application/json")
            return

        method = message.get("method", "")
        try:
            payload = {"jsonrpc": "2.0", "id": message.get("id"), "result": _result(method, message.get("params") or {})}
        except KeyError:
            payload = {
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }

        body = json.dumps(payload, ensure_ascii=False)
        if self.path.endswith("sse=1"):
            # 규격을 지키는 서버는 event 줄을 먼저 보낸다 — 클라이언트가 그것을
            # 건너뛰고 첫 `data:` 를 찾는지 확인하는 모양이다.
            self._send(200, f"event: message\ndata: {body}\n\n", "text/event-stream")
        else:
            self._send(200, body, "application/json")

    def _send(self, code: int, body: str, content_type: str):
        raw = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


if __name__ == "__main__":
    print(f"[dev-mcp] listening on :{PORT} (token={'설정됨' if TOKEN else '없음'})", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
