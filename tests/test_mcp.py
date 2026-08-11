"""MCP 단위 테스트. 네트워크·DB 는 mock 한다.

가장 중요한 것은 **SSRF 차단**이다(11_MCP_설계 §4-1). 사용자가 임의 URL을
등록하는 구조라, 여기가 뚫리면 우리 서버가 내부망을 대신 두드려 준다.
그 다음이 **오류 코드** — 평가 §4·§5 의 집계 키라 문자열이 바뀌면 안 된다.
"""

import json
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from apps.accounts.tokens import issue_token
from services.mcp import client, security
from services.mcp.security import UnsafeEndpoint


def auth_header(account_id="UA001"):
    return {"authorization": f"Bearer {issue_token(account_id)}"}


def http(status_code=200, body=None, text=None):
    response = Mock()
    response.status_code = status_code
    payload = (text if text is not None else json.dumps(body or {})).encode("utf-8")
    response.iter_content = lambda chunk_size=None: iter([payload])
    response.close = Mock()
    return response


def rpc_ok(result):
    return http(body={"jsonrpc": "2.0", "id": 1, "result": result})


class SsrfTests(SimpleTestCase):
    @patch("services.mcp.security._resolve", return_value=["93.184.216.34"])
    def test_공인_https_는_통과한다(self, _resolve):
        self.assertEqual(
            security.validate("https://mcp.example.com/rpc"), "https://mcp.example.com/rpc"
        )

    def test_http_는_거절한다(self):
        """토큰이 평문으로 나간다. 로컬 개발용 예외를 두지 않는다."""

        with self.assertRaises(UnsafeEndpoint):
            security.validate("http://mcp.example.com/rpc")

    def test_localhost_는_이름으로_막는다(self):
        with self.assertRaises(UnsafeEndpoint):
            security.validate("https://localhost/rpc")

    def test_내부_도메인_접미사를_막는다(self):
        with self.assertRaises(UnsafeEndpoint):
            security.validate("https://jira.internal/rpc")

    @patch("services.mcp.security._resolve", return_value=["169.254.169.254"])
    def test_클라우드_메타데이터_주소를_막는다(self, _resolve):
        """169.254.169.254 는 인스턴스 자격증명이 나오는 자리다."""

        with self.assertRaises(UnsafeEndpoint):
            security.validate("https://evil.example.com/rpc")

    @patch("services.mcp.security._resolve")
    def test_사설_대역을_전부_막는다(self, resolve):
        for address in ("10.0.0.5", "172.16.0.1", "192.168.1.1", "127.0.0.1", "::1", "fd00::1"):
            resolve.return_value = [address]
            with self.assertRaises(UnsafeEndpoint, msg=address):
                security.validate("https://evil.example.com/rpc")

    @patch("services.mcp.security._resolve", return_value=["93.184.216.34", "10.0.0.5"])
    def test_한_이름이_공인과_사설을_함께_주면_막는다(self, _resolve):
        """첫 주소만 보면 실제 연결이 사설 쪽으로 갈 수 있다."""

        with self.assertRaises(UnsafeEndpoint):
            security.validate("https://mixed.example.com/rpc")

    def test_주소에_인증정보를_넣을_수_없다(self):
        with self.assertRaises(UnsafeEndpoint):
            security.validate("https://user:pw@internal@evil.example.com/rpc")

    @patch("services.mcp.security.validate")
    def test_호출_직전에_다시_검사한다(self, validate):
        """DNS 리바인딩 대비. 생략하면 등록 검사만으로는 못 막는다."""

        security.recheck("https://mcp.example.com/rpc")

        validate.assert_called_once_with("https://mcp.example.com/rpc")


@patch("services.mcp.client.security.recheck")
@patch("services.mcp.client.requests.post")
class ClientTests(SimpleTestCase):
    def test_연결_테스트가_도구_목록을_읽는다(self, post, _recheck):
        post.side_effect = [
            rpc_ok({"protocolVersion": "2025-06-18"}),
            rpc_ok({"tools": [
                {"name": "jira_create_issues", "description": "벌크 생성",
                 "inputSchema": {"type": "object"}},
                {"description": "이름 없는 도구는 버린다"},
            ]}),
        ]

        tools = client.initialize_and_list_tools(
            endpoint_url="https://mcp.example.com/rpc", auth_token="t"
        )

        self.assertEqual([t["name"] for t in tools], ["jira_create_issues"])
        # initialize 를 먼저 보낸다 — 건너뛰면 규격을 지키는 서버가 거절한다.
        self.assertEqual(post.call_args_list[0].kwargs["json"]["method"], "initialize")
        self.assertEqual(post.call_args_list[1].kwargs["json"]["method"], "tools/list")

    def test_토큰은_Authorization_헤더로만_나간다(self, post, _recheck):
        post.side_effect = [rpc_ok({}), rpc_ok({"tools": []})]

        client.initialize_and_list_tools(
            endpoint_url="https://mcp.example.com/rpc", auth_token="secret-token"
        )

        sent = post.call_args_list[0].kwargs
        self.assertEqual(sent["headers"]["Authorization"], "Bearer secret-token")
        self.assertNotIn("secret-token", json.dumps(sent["json"]))

    def test_SSE_응답도_읽는다(self, post, _recheck):
        """Streamable HTTP 는 같은 엔드포인트가 text/event-stream 으로도 답한다."""

        post.return_value = http(
            text='event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n\n'
        )

        result = client.call_tool(
            endpoint_url="https://mcp.example.com/rpc", auth_token=None,
            name="t", arguments={},
        )

        self.assertEqual(result, {"content": ""})

    def test_structuredContent_가_있으면_그것을_쓴다(self, post, _recheck):
        post.return_value = rpc_ok({"structuredContent": {"created": ["KAN-1", "KAN-2"]}})

        result = client.call_tool(
            endpoint_url="https://mcp.example.com/rpc", auth_token=None,
            name="jira_create_issues", arguments={},
        )

        self.assertEqual(result["created"], ["KAN-1", "KAN-2"])


@patch("services.mcp.client.security.recheck")
@patch("services.mcp.client.requests.post")
class ErrorMappingTests(SimpleTestCase):
    """오류 코드는 평가 §4·§5 의 집계 키다(11_MCP_설계 §6). 문자열이 계약이다."""

    def _code(self, post, response=None, exception=None):
        if exception is not None:
            post.side_effect = exception
        else:
            post.return_value = response
        with self.assertRaises(client.McpError) as caught:
            client.call_tool(
                endpoint_url="https://mcp.example.com/rpc", auth_token=None,
                name="t", arguments={},
            )
        return caught.exception.code

    def test_인증_만료는_401(self, post, _recheck):
        self.assertEqual(self._code(post, http(status_code=401)), "401")

    def test_403_도_401_로_모은다(self, post, _recheck):
        """화면 문구가 같다 — '설정 > MCP 에서 연결 확인'."""

        self.assertEqual(self._code(post, http(status_code=403)), "401")

    def test_rate_limit_은_429(self, post, _recheck):
        self.assertEqual(self._code(post, http(status_code=429)), "429")

    def test_타임아웃은_timeout(self, post, _recheck):
        import requests

        self.assertEqual(self._code(post, exception=requests.Timeout()), "timeout")

    def test_연결_실패는_unreachable(self, post, _recheck):
        import requests

        self.assertEqual(self._code(post, exception=requests.ConnectionError()), "unreachable")

    def test_도구_자체_실패는_validation(self, post, _recheck):
        """MCP 는 필수 필드 누락을 HTTP 오류가 아니라 isError 로 알린다."""

        post.return_value = rpc_ok(
            {"isError": True, "content": [{"type": "text", "text": "담당자가 지정되지 않았습니다."}]}
        )

        with self.assertRaises(client.McpError) as caught:
            client.call_tool(
                endpoint_url="https://mcp.example.com/rpc", auth_token=None,
                name="jira_create_issues", arguments={},
            )

        self.assertEqual(caught.exception.code, "validation")
        self.assertIn("담당자", str(caught.exception))

    def test_JSON_RPC_오류도_validation(self, post, _recheck):
        post.return_value = http(
            body={"jsonrpc": "2.0", "id": 1, "error": {"code": -32602, "message": "잘못된 인자"}}
        )

        self.assertEqual(self._code(post, http(
            body={"jsonrpc": "2.0", "id": 1, "error": {"code": -32602, "message": "잘못된 인자"}}
        )), "validation")

    def test_응답이_너무_크면_거절한다(self, post, _recheck):
        big = Mock()
        big.status_code = 200
        big.iter_content = lambda chunk_size=None: iter([b"x" * (3 * 1024 * 1024)])
        big.close = Mock()

        self.assertEqual(self._code(post, big), "validation")


@patch("apps.mcp.api_views.McpServerRepository")
class McpApiTests(SimpleTestCase):
    def test_위험한_주소는_저장_전에_거절한다(self, repo):
        """저장 뒤 검사면 위험한 주소가 DB 에 남는다."""

        response = self.client.post(
            "/api/mcp/servers/",
            {"name": "내부", "endpoint_url": "http://localhost:5432/rpc"},
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 400)
        repo.create.assert_not_called()

    @patch("apps.mcp.api_views.validate", return_value="https://mcp.example.com/rpc")
    def test_등록은_UNCHECKED_로_시작한다(self, _validate, repo):
        repo.create.return_value = {
            "mcp_server_id": "MS001", "name": "Jira", "endpoint_url": "https://mcp.example.com/rpc",
            "status": "UNCHECKED", "last_checked_at": None,
        }

        response = self.client.post(
            "/api/mcp/servers/",
            {
                "name": "Jira",
                "endpoint_url": "https://mcp.example.com/rpc",
                "auth_token": "SECRET-TOKEN-VALUE",
            },
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "UNCHECKED")
        # 토큰은 응답에 없다(§4-2).
        self.assertNotIn("auth_token", response.json())
        self.assertNotIn("SECRET-TOKEN-VALUE", json.dumps(response.json()))
        # 저장은 암호화 계층으로 넘긴다 — 평문이 그대로 컬럼에 들어가지 않는다.
        self.assertEqual(repo.create.call_args.kwargs["auth_token"], "SECRET-TOKEN-VALUE")

    @patch("apps.mcp.api_views.initialize_and_list_tools")
    def test_연결_테스트_성공이면_도구를_저장한다(self, discover, repo):
        repo.credentials.return_value = {
            "mcp_server_id": "MS001", "endpoint_url": "https://mcp.example.com/rpc",
            "auth_token": "t",
        }
        discover.return_value = [
            {"name": "jira_create_issues", "description": "d", "input_schema": {}}
        ]
        repo.save_tools.return_value = 1
        repo.list_for_team.return_value = []

        response = self.client.post(
            "/api/mcp/servers/MS001/test/", {}, content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "CONNECTED", "tool_count": 1})

    @patch("apps.mcp.api_views.initialize_and_list_tools")
    def test_연결_실패해도_등록은_남기고_ERROR_로_표시한다(self, discover, repo):
        """지우면 사용자가 고쳐 쓸 값이 사라지고, 왜 못 고르는지도 알 수 없다."""

        repo.credentials.return_value = {
            "mcp_server_id": "MS001", "endpoint_url": "https://mcp.example.com/rpc",
            "auth_token": None,
        }
        discover.side_effect = client.McpError("401", "인증 실패")

        response = self.client.post(
            "/api/mcp/servers/MS001/test/", {}, content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error_code"], "401")
        repo.mark_error.assert_called_once()
        repo.delete.assert_not_called()

    def test_로그인_없이는_401(self, _repo):
        self.assertEqual(self.client.get("/api/mcp/servers/").status_code, 401)
