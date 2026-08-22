import json
from unittest.mock import patch

from django.test import SimpleTestCase

import apps.accounts.tokens as account_tokens
import apps.ops.tokens as ops_tokens
from apps.ops.authentication import REVOKED_DETAIL

OVERVIEW_URL = "/api/ops/overview/"


def admin_account(account_id="UA001", **overrides):
    account = {
        "account_id": account_id,
        "email": "admin@halil.com",
        "display_name": "관리자",
        "password_hash": "unused",
        "account_status": "ACTIVE",
        "is_admin": True,
    }
    account.update(overrides)
    return account


class OpsAuthenticationTests(SimpleTestCase):
    """운영자 콘솔은 고권한 API라, 요청마다 DB를 재확인해서 권한이 꺼지면
    토큰이 아직 유효 기간 안이어도 즉시 막혀야 한다(`apps/ops/authentication.py`)."""

    @patch("apps.ops.authentication.AccountRepository.find_credentials_by_id")
    def test_admin_flag_turned_off_is_rejected(self, find_credentials_by_id):
        find_credentials_by_id.return_value = admin_account(is_admin=False)
        token = ops_tokens.issue_token("UA001")

        response = self.client.get(OVERVIEW_URL, HTTP_AUTHORIZATION=f"Bearer {token}")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], REVOKED_DETAIL)

    @patch("apps.ops.authentication.AccountRepository.find_credentials_by_id")
    def test_locked_admin_account_is_rejected(self, find_credentials_by_id):
        find_credentials_by_id.return_value = admin_account(account_status="LOCKED")
        token = ops_tokens.issue_token("UA001")

        response = self.client.get(OVERVIEW_URL, HTTP_AUTHORIZATION=f"Bearer {token}")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], REVOKED_DETAIL)

    def test_regular_account_token_is_rejected(self):
        """`apps/accounts/tokens.py`는 salt가 달라서, 일반 로그인 토큰으로는
        서명 검증 자체가 실패해 DB까지 가지 않는다."""

        token = account_tokens.issue_token("UA001")

        response = self.client.get(OVERVIEW_URL, HTTP_AUTHORIZATION=f"Bearer {token}")

        self.assertEqual(response.status_code, 401)

    @patch("apps.ops.tokens.TOKEN_MAX_AGE_SECONDS", -1)
    def test_expired_ops_token_is_rejected(self):
        token = ops_tokens.issue_token("UA001")

        response = self.client.get(OVERVIEW_URL, HTTP_AUTHORIZATION=f"Bearer {token}")

        self.assertEqual(response.status_code, 401)

    def test_missing_token_is_rejected(self):
        response = self.client.get(OVERVIEW_URL)

        self.assertEqual(response.status_code, 401)


@patch("apps.ops.authentication.AccountRepository.find_credentials_by_id", return_value=admin_account())
@patch("apps.ops.views.models.log_audit")
@patch("apps.ops.views.models.CustomModelRepository")
@patch("apps.ops.views.models.TeamRepository")
class OpsTeamDefaultModelTests(SimpleTestCase):
    """기본 채팅 모델 — **팀이 화면에서 고르지 않는다**(2026-08-18 멘토링).

    설정의 Model 탭을 걷어내고 여기로 옮겼다. **팀별**이라는 것이 요점이다 —
    전역 하나로 두면 계약·리전 요건이 다른 회사를 못 받는다(8/13 에 커스텀
    모델을 팀 단위로 붙인 것과 같은 이유).
    """

    URL = "/api/ops/models/teams/TE001/default/"

    def _headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {ops_tokens.issue_token('UA001')}"}

    def test_고를_수_있는_것을_함께_준다(self, teams, customs, _audit, _admin):
        """이름을 외워 적게 하지 않는다 — 오타는 실행 시점 404 이고,
        그때 죽는 것은 우리가 아니라 그 팀의 대화다."""

        teams.default_model.return_value = "gpt-5.6-luna"
        customs.models_for_team.return_value = {"models/gemini-3.6-flash"}

        body = self.client.get(self.URL, **self._headers()).json()

        self.assertEqual(body["model"], "gpt-5.6-luna")
        self.assertIn("models/gemini-3.6-flash", body["choices"])

    def test_정한_적이_없으면_null_을_준다(self, teams, customs, _audit, _admin):
        """임의의 기본값을 저장된 것처럼 보이면 안 된다 — 팀 화면에서 지켜 온 규칙이다.

        2026-08-22 전에는 이게 「그 팀에 정문 에이전트가 없다」는 뜻이었다. 값이
        `team.default_model`로 옮겨오면서 그 상태는 없어지고, 이제는 순수하게
        「아직 안 정했다」만 남는다."""

        teams.default_model.return_value = None
        customs.models_for_team.return_value = set()

        body = self.client.get(self.URL, **self._headers()).json()

        self.assertIsNone(body["model"])

    def test_그_팀에만_쓴다(self, teams, customs, _audit, _admin):
        customs.models_for_team.return_value = set()
        teams.set_default_model.return_value = "gpt-5.6-sol"

        response = self.client.put(
            self.URL, {"model": "gpt-5.6-sol"}, content_type="application/json", **self._headers()
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(teams.set_default_model.call_args.kwargs["team_id"], "TE001")

    def test_그_팀이_못_쓰는_모델은_거절한다(self, teams, customs, _audit, _admin):
        """아무 문자열이나 받으면 저장은 되고 실행 시점에 404 로 죽는다 —
        운영자는 저장됐으니 맞다고 믿는다."""

        customs.models_for_team.return_value = set()

        response = self.client.put(
            self.URL, {"model": "없는-모델"}, content_type="application/json", **self._headers()
        )

        self.assertEqual(response.status_code, 400)
        teams.set_default_model.assert_not_called()

    def test_다른_팀에_등록된_모델도_거절한다(self, teams, customs, _audit, _admin):
        """권한 범위는 여전히 팀이다 — 남의 팀에 붙은 모델을 이 팀에 걸면 실행이 죽는다."""

        customs.models_for_team.return_value = {"models/gemini-3.6-flash"}

        response = self.client.put(
            self.URL, {"model": "models/other-team-only"},
            content_type="application/json", **self._headers(),
        )

        self.assertEqual(response.status_code, 400)
        teams.set_default_model.assert_not_called()

    def test_바꾼_것을_기록에_남긴다(self, teams, customs, audit, _admin):
        """남의 팀 대화가 도는 모델을 바꾸는 일이다."""

        customs.models_for_team.return_value = set()
        teams.set_default_model.return_value = "gpt-5.6-sol"

        self.client.put(
            self.URL, {"model": "gpt-5.6-sol"}, content_type="application/json", **self._headers()
        )

        self.assertEqual(audit.call_args.kwargs["action"], "OPS_TEAM_MODEL_SET")
        self.assertEqual(audit.call_args.kwargs["target_id"], "TE001")

    def test_운영자_아니면_막힌다(self, teams, _customs, _audit, _admin):
        response = self.client.put(
            self.URL, {"model": "gpt-5.6-sol"}, content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {account_tokens.issue_token('UA001')}",
        )

        self.assertEqual(response.status_code, 401)
        teams.set_default_model.assert_not_called()


@patch("apps.ops.authentication.AccountRepository.find_credentials_by_id", return_value=admin_account())
@patch("apps.ops.views.mcp.log_audit")
@patch("apps.ops.views.mcp.McpServerRepository")
class OpsMcpTests(SimpleTestCase):
    """팀별 커스텀 도구 등록 — **팀이 스스로 등록하지 않는다**(2026-08-18 멘토링).

    모델(§2026-08-13)과 같은 모양이다. 팀 설정에는 목록만 남고 등록·수정·삭제·
    연결 확인이 여기로 왔다. SSRF 차단은 팀 쪽에 있던 그대로 따라와야 한다 —
    운영자가 넣는다고 안전해지지 않는다. 주소는 고객에게 받아 옮겨 적는 값이다.
    """

    URL = "/api/ops/mcp/"
    BODY = {
        "team_id": "TE001",
        "name": "Jira",
        "endpoint_url": "https://mcp.example.com/rpc",
    }

    def _headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {ops_tokens.issue_token('UA001')}"}

    def test_위험한_주소는_저장_전에_거절한다(self, repo, _audit, _admin):
        """저장 뒤 검사면 위험한 주소가 DB 에 남는다(11_MCP_설계 §4-1)."""

        response = self.client.post(
            self.URL,
            {**self.BODY, "endpoint_url": "http://localhost:5432/rpc"},
            content_type="application/json",
            **self._headers(),
        )

        self.assertEqual(response.status_code, 400)
        repo.create.assert_not_called()

    @patch("apps.ops.views.mcp.validate", return_value="https://mcp.example.com/rpc")
    def test_그_팀에_등록한다(self, _validate, repo, _audit, _admin):
        repo.create.return_value = {
            "mcp_server_id": "MS001", "name": "Jira",
            "endpoint_url": "https://mcp.example.com/rpc",
            "status": "UNCHECKED", "last_checked_at": None, "has_token": True, "tools": [],
        }

        response = self.client.post(
            self.URL, {**self.BODY, "auth_token": "SECRET-TOKEN-VALUE"},
            content_type="application/json", **self._headers(),
        )

        self.assertEqual(response.status_code, 201)
        kwargs = repo.create.call_args.kwargs
        self.assertEqual(kwargs["team_id"], "TE001")
        # 등록한 사람이 남아야 나중에 팀장이 붙인 것으로 오해하지 않는다.
        self.assertEqual(kwargs["registered_by"], "UA001")
        # 등록 직후는 아직 도구를 못 읽은 상태다 — 실패와 다르다.
        self.assertEqual(response.json()["status"], "UNCHECKED")

    @patch("apps.ops.views.mcp.validate", return_value="https://mcp.example.com/rpc")
    def test_토큰은_응답에도_감사로그에도_안_나간다(self, _validate, repo, audit, _admin):
        """감사 로그는 나중에 사람이 읽는 표다(§4-2)."""

        repo.create.return_value = {
            "mcp_server_id": "MS001", "name": "Jira",
            "endpoint_url": "https://mcp.example.com/rpc",
            "status": "UNCHECKED", "last_checked_at": None, "has_token": True, "tools": [],
        }

        response = self.client.post(
            self.URL, {**self.BODY, "auth_token": "SECRET-TOKEN-VALUE"},
            content_type="application/json", **self._headers(),
        )

        self.assertNotIn("SECRET-TOKEN-VALUE", response.content.decode())
        self.assertTrue(response.json()["has_token"])
        self.assertNotIn("SECRET-TOKEN-VALUE", json.dumps(audit.call_args.kwargs["payload"]))

    def test_수정도_위험한_주소를_저장_전에_거절한다(self, repo, _audit, _admin):
        """고칠 때만 검사를 건너뛰면 등록에서 막은 주소가 수정으로 들어온다."""

        response = self.client.patch(
            f"{self.URL}MS001/",
            {**self.BODY, "endpoint_url": "http://localhost:5432/rpc"},
            content_type="application/json", **self._headers(),
        )

        self.assertEqual(response.status_code, 400)
        repo.update.assert_not_called()

    @patch("apps.ops.views.mcp.validate", return_value="https://mcp.example.com/new")
    def test_수정도_기록에_남는다(self, _validate, repo, audit, _admin):
        """등록·삭제만 남기고 수정을 빠뜨리면, **주소가 언제 어디로 바뀌었는지**
        아무 데도 안 남는다. 그 팀의 호출이 다른 곳으로 나가게 하는 일이라
        새로 심는 것과 무게가 같다. 토큰은 남기지 않고 바뀌었는지만 적는다."""

        repo.update.return_value = {
            "mcp_server_id": "MS001", "name": "Jira",
            "endpoint_url": "https://mcp.example.com/new",
            "status": "UNCHECKED", "last_checked_at": None, "has_token": True, "tools": [],
        }

        response = self.client.patch(
            f"{self.URL}MS001/",
            {**self.BODY, "endpoint_url": "https://mcp.example.com/new",
             "auth_token": "SECRET-TOKEN-VALUE", "replace_token": True},
            content_type="application/json", **self._headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(audit.call_args.kwargs["action"], "OPS_MCP_UPDATE")
        payload = audit.call_args.kwargs["payload"]
        self.assertEqual(payload["mcp_server_id"], "MS001")
        self.assertEqual(payload["endpoint_url"], "https://mcp.example.com/new")
        self.assertIs(payload["token_replaced"], True)
        self.assertNotIn("SECRET-TOKEN-VALUE", json.dumps(payload))

    @patch("apps.ops.views.mcp.validate", return_value="https://mcp.example.com/rpc")
    def test_토큰을_안_보내면_그대로_둔다(self, _validate, repo, _audit, _admin):
        """화면이 저장된 토큰을 다시 보여주지 않는다 — 안 보낸 것을 「지우라」로
        읽으면 이름만 고쳐도 토큰이 날아간다."""

        repo.update.return_value = {
            "mcp_server_id": "MS001", "name": "새 이름",
            "endpoint_url": "https://mcp.example.com/rpc",
            "status": "CONNECTED", "last_checked_at": None, "has_token": True, "tools": [],
        }

        response = self.client.patch(
            f"{self.URL}MS001/", {**self.BODY, "name": "새 이름"},
            content_type="application/json", **self._headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIs(repo.update.call_args.kwargs["replace_token"], False)
        self.assertTrue(response.json()["has_token"])

    @patch("apps.ops.views.mcp.initialize_and_list_tools")
    def test_연결_확인_성공이면_도구를_저장한다(self, discover, repo, _audit, _admin):
        repo.credentials.return_value = {
            "mcp_server_id": "MS001", "endpoint_url": "https://mcp.example.com/rpc",
            "auth_token": "t",
        }
        discover.return_value = [{"name": "jira_create_issues", "description": "d", "input_schema": {}}]
        repo.save_tools.return_value = 1

        response = self.client.post(
            f"{self.URL}MS001/test/", {"team_id": "TE001"},
            content_type="application/json", **self._headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "CONNECTED", "tool_count": 1})

    @patch("apps.ops.views.mcp.initialize_and_list_tools")
    def test_연결_실패해도_등록은_남기고_ERROR_로_표시한다(self, discover, repo, _audit, _admin):
        """지우면 고쳐 쓸 값이 사라지고, 그 팀이 왜 못 고르는지도 알 수 없다."""

        from services.mcp import client

        repo.credentials.return_value = {
            "mcp_server_id": "MS001", "endpoint_url": "https://mcp.example.com/rpc",
            "auth_token": None,
        }
        discover.side_effect = client.McpError("401", "인증 실패")

        response = self.client.post(
            f"{self.URL}MS001/test/", {"team_id": "TE001"},
            content_type="application/json", **self._headers(),
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error_code"], "401")
        repo.mark_error.assert_called_once()
        repo.delete.assert_not_called()

    @patch("apps.ops.views.mcp.validate", return_value="https://mcp.example.com/rpc")
    @patch("apps.ops.views.mcp.initialize_and_list_tools")
    def test_연결_확인만_하면_아무것도_저장하지_않는다(self, discover, _validate, repo, _audit, _admin):
        """안 되는 것을 등록해 두면 그 팀의 대화가 조용히 실패한다."""

        discover.return_value = [{"name": "create_issue", "description": "d", "input_schema": {}}]

        response = self.client.post(
            f"{self.URL}probe/",
            {"endpoint_url": "https://mcp.example.com/rpc", "auth_token": "t"},
            content_type="application/json", **self._headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tools"], ["create_issue"])
        repo.create.assert_not_called()

    def test_연결_확인도_위험한_주소는_두드리지_않는다(self, repo, _audit, _admin):
        """저장을 안 한다고 안전해지지 않는다 — 우리 서버가 내부망을 대신 두드린다."""

        response = self.client.post(
            f"{self.URL}probe/",
            {"endpoint_url": "http://localhost:5432/rpc"},
            content_type="application/json", **self._headers(),
        )

        self.assertEqual(response.status_code, 400)

    def test_probe_가_서버_상세로_잡히지_않는다(self, _repo, _audit, _admin):
        """`mcp/probe/` 가 `mcp/<server_id>/` 뒤에 있으면 상세로 잡힌다."""

        from django.urls import resolve

        self.assertEqual(resolve(f"{self.URL}probe/").url_name, "api_ops_mcp_probe")
        self.assertEqual(resolve(f"{self.URL}MS001/").url_name, "api_ops_mcp_detail")

    def test_팀_없이는_지우지_않는다(self, repo, _audit, _admin):
        """`server_id` 하나로 지우면 어느 팀 것인지 확인하는 자물쇠가 없어진다."""

        response = self.client.delete(f"{self.URL}MS001/", **self._headers())

        self.assertEqual(response.status_code, 400)
        repo.delete.assert_not_called()

    def test_운영자_아니면_막힌다(self, repo, _audit, _admin):
        response = self.client.post(
            self.URL, self.BODY, content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {account_tokens.issue_token('UA001')}",
        )

        self.assertEqual(response.status_code, 401)
        repo.create.assert_not_called()


@patch("apps.ops.authentication.AccountRepository.find_credentials_by_id", return_value=admin_account())
@patch("apps.ops.views.models.log_audit")
@patch("apps.ops.views.models.CustomModelRepository")
class OpsModelRegisterTests(SimpleTestCase):
    """팀별 모델 등록 — **팀이 스스로 등록하지 않는다**(2026-08-13 멘토링).

    권한 범위는 여전히 팀이다. 등록하는 사람만 운영자로 바뀐다.
    """

    URL = "/api/ops/models/"
    BODY = {
        "team_id": "TE001",
        "label": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key": "AIza-x",
        "model": "models/gemini-3.6-flash",
    }

    def _headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {ops_tokens.issue_token('UA001')}"}

    @patch("apps.ops.views.models._verify", return_value=None)
    def test_그_팀에_등록한다(self, _verify, repo, _audit, _admin):
        repo.models_for_team.return_value = set()

        response = self.client.post(
            self.URL, self.BODY, content_type="application/json", **self._headers()
        )

        self.assertEqual(response.status_code, 201)
        kwargs = repo.add_for_team.call_args.kwargs
        self.assertEqual(kwargs["team_id"], "TE001")
        # 등록한 사람이 남아야 소유 계정만 보고 팀장이 등록한 것으로 오해하지 않는다.
        self.assertEqual(kwargs["registered_by"], "UA001")

    @patch("apps.ops.views.models._verify", return_value=None)
    def test_같은_팀에_같은_모델을_두_번_등록하지_않는다(self, _verify, repo, _audit, _admin):
        repo.models_for_team.return_value = {"models/gemini-3.6-flash"}

        response = self.client.post(
            self.URL, self.BODY, content_type="application/json", **self._headers()
        )

        self.assertEqual(response.status_code, 400)
        repo.add_for_team.assert_not_called()

    @patch("apps.ops.views.models._verify", return_value="이 주소와 모델로 답을 받지 못했습니다.")
    def test_안_도는_주소는_등록하지_않는다(self, _verify, repo, _audit, _admin):
        """등록해 두면 그 팀의 대화가 조용히 실패하고, 팀은 운영자가 등록했으니 되는 줄 안다."""

        repo.models_for_team.return_value = set()

        response = self.client.post(
            self.URL, self.BODY, content_type="application/json", **self._headers()
        )

        self.assertEqual(response.status_code, 400)
        repo.add_for_team.assert_not_called()

    def test_기본_제공_이름은_거절한다(self, repo, _audit, _admin):
        response = self.client.post(
            self.URL,
            {**self.BODY, "model": "gpt-5.6-luna"},
            content_type="application/json",
            **self._headers(),
        )

        self.assertEqual(response.status_code, 400)
        repo.add_for_team.assert_not_called()

    def test_키는_목록에_안_나온다(self, repo, _audit, _admin):
        repo.list_all.return_value = [
            {
                "conn_id": "CN002", "team_id": "TE001", "team_name": "개발팀",
                "label": "Google Gemini", "base_url": "https://x/v1",
                "model": "models/gemini-3.6-flash", "connected_at": None,
            }
        ]

        body = self.client.get(self.URL, **self._headers()).json()

        self.assertNotIn("api_key", body[0])
        self.assertEqual(body[0]["team_name"], "개발팀")

    def test_운영자가_아니면_못_본다(self, repo, _audit, _admin):
        token = account_tokens.issue_token("UA001")

        response = self.client.get(self.URL, HTTP_AUTHORIZATION=f"Bearer {token}")

        self.assertEqual(response.status_code, 401)
        repo.list_all.assert_not_called()

    @patch("apps.ops.views.models._verify", return_value=None)
    def test_등록_응답은_목록을_다시_만들지_않는다(self, _verify, repo, _audit, _admin):
        """목록을 만들다 실패하면 **이미 끝난 등록이 실패로 보고된다.**

        운영자는 안 됐다고 믿고 다시 누르고, 그때는 중복이라 거절당한다 — 무슨
        일이 벌어진 건지 아무도 모른다(2026-08-13 검토).
        """

        repo.models_for_team.return_value = set()

        self.client.post(self.URL, self.BODY, content_type="application/json", **self._headers())

        repo.list_all.assert_not_called()

    def test_지울_때_무엇을_지웠는지_남긴다(self, repo, audit, _admin):
        """행을 지우고 나면 conn_id 는 아무것도 안 가리킨다. 그 값만 남기면
        나중에 「어느 팀의 무슨 모델이 없어졌나」를 복원할 수 없다."""

        repo.remove_by_conn_id.return_value = {
            "team_id": "TE001", "model": "models/gemini-3.6-flash",
            "label": "Google Gemini", "base_url": "https://x/v1",
        }

        response = self.client.delete(f"{self.URL}CN002/", **self._headers())

        self.assertEqual(response.status_code, 204)
        kwargs = audit.call_args.kwargs
        self.assertEqual(kwargs["target_type"], "TEAM")
        self.assertEqual(kwargs["target_id"], "TE001")
        self.assertEqual(kwargs["payload"]["model"], "models/gemini-3.6-flash")

    def test_쓰는_에이전트가_있으면_못_지운다(self, repo, _audit, _admin):
        """지우면 그 에이전트는 실행 시점에 없는 모델을 부르다 죽는다."""

        from backend.db.errors import ReferenceNotFound

        repo.remove_by_conn_id.side_effect = ReferenceNotFound(
            "이 모델을 쓰는 에이전트가 있습니다: 회의록 정리."
        )

        response = self.client.delete(f"{self.URL}CN002/", **self._headers())

        self.assertEqual(response.status_code, 409)

    def test_모델_목록을_받아_온다(self, repo, _audit, _admin):
        """**이름을 외워 적게 하지 않는다** — 오타 하나가 실행 시점 404 가 된다."""

        with patch("openai.OpenAI") as client:
            client.return_value.models.list.return_value.data = [
                type("M", (), {"id": "models/gemini-3.6-flash"}),
                type("M", (), {"id": "models/gemini-3.6-pro"}),
            ]
            response = self.client.post(
                f"{self.URL}probe/",
                {"base_url": "https://x/v1", "api_key": "k"},
                content_type="application/json",
                **self._headers(),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["models"], ["models/gemini-3.6-flash", "models/gemini-3.6-pro"])

    def test_목록을_못_주면_이유를_준다(self, repo, _audit, _admin):
        """Anthropic 호환 경로는 401 이다. 그때는 화면이 직접 입력으로 넘어간다."""

        with patch("openai.OpenAI", side_effect=RuntimeError("401")):
            response = self.client.post(
                f"{self.URL}probe/",
                {"base_url": "https://x/v1", "api_key": "k"},
                content_type="application/json",
                **self._headers(),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["models"], [])
        self.assertTrue(response.json()["detail"])

    def test_probe_가_conn_id_에_먹히지_않는다(self, repo, _audit, _admin):
        """`models/probe/` 가 `models/<conn_id>/` 뒤에 있으면 삭제로 잡힌다."""

        from django.urls import resolve

        self.assertEqual(resolve("/api/ops/models/probe/").url_name, "api_ops_model_probe")


@patch("apps.ops.authentication.AccountRepository.find_credentials_by_id", return_value=admin_account())
@patch("apps.ops.views.accounts.OpsAccountRepository")
class OpsAdminGrantApiTests(SimpleTestCase):
    """운영자 권한 부여·회수.

    원래 이 경로는 API 에 없었다(`grant_admin.py` 로만 켰다). 콘솔이 자기 자신을
    관리하지 못하는 문제라 열되, 취지를 지키는 안전장치를 함께 둔다.
    """

    URL = "/api/ops/accounts/UA002/admin/"

    def _headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {ops_tokens.issue_token('UA001')}"}

    def test_권한을_준다(self, repo, _admin):
        repo.set_admin.return_value = {"account_id": "UA002", "is_admin": True}

        response = self.client.post(
            self.URL,
            {"is_admin": True, "reason": "운영 인수인계"},
            content_type="application/json",
            **self._headers(),
        )

        self.assertEqual(response.status_code, 200)
        kwargs = repo.set_admin.call_args.kwargs
        self.assertTrue(kwargs["is_admin"])
        self.assertEqual(kwargs["reason"], "운영 인수인계")
        # 누가 줬는지가 감사 기록의 핵심이다.
        self.assertEqual(kwargs["actor_account_id"], "UA001")

    def test_사유는_없어도_된다(self, repo, _admin):
        repo.set_admin.return_value = {"account_id": "UA002", "is_admin": False}

        response = self.client.post(
            self.URL, {"is_admin": False}, content_type="application/json", **self._headers()
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(repo.set_admin.call_args.kwargs["reason"], "")

    def test_is_admin_은_필수다(self, repo, _admin):
        """켜는지 끄는지를 안 주면 무엇을 하려는지 알 수 없다."""

        response = self.client.post(
            self.URL, {"reason": "x"}, content_type="application/json", **self._headers()
        )

        self.assertEqual(response.status_code, 400)
        repo.set_admin.assert_not_called()

    def test_운영자가_아니면_못_부른다(self, repo, _admin):
        token = account_tokens.issue_token("UA001")

        response = self.client.post(
            self.URL,
            {"is_admin": True},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 401)
        repo.set_admin.assert_not_called()

    def test_본인_권한_회수는_403(self, repo, _admin):
        """실수로 스스로를 잠그면 되돌릴 방법이 없다."""

        from backend.db.errors import PermissionDenied

        repo.set_admin.side_effect = PermissionDenied("본인의 운영자 권한은 내릴 수 없습니다.")

        response = self.client.post(
            self.URL, {"is_admin": False}, content_type="application/json", **self._headers()
        )

        self.assertEqual(response.status_code, 403)

    def test_마지막_운영자_회수는_400(self, repo, _admin):
        """콘솔에 아무도 못 들어가는 상태를 화면에서 만들 수 있으면 안 된다."""

        from backend.db.errors import RepositoryError as RepoError

        repo.set_admin.side_effect = RepoError("마지막 운영자입니다.")

        response = self.client.post(
            self.URL, {"is_admin": False}, content_type="application/json", **self._headers()
        )

        self.assertEqual(response.status_code, 400)


@patch("apps.ops.authentication.AccountRepository.find_credentials_by_id", return_value=admin_account())
@patch("apps.ops.views.teams.OpsTeamRepository")
class OpsTeamOwnerTransferTests(SimpleTestCase):
    """팀 소유자 이전.

    **팀장이 나가면 그 팀을 아무도 손댈 수 없었다** — `owner_account_id` 를 바꾸는
    경로가 어디에도 없었다(2026-08-13 PM 지적).
    """

    URL = "/api/ops/teams/TE001/owner/"

    def _headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {ops_tokens.issue_token('UA001')}"}

    def test_후보는_그_팀_계정만_준다(self, repo, _admin):
        """계정 전체에서 고르게 하면 남의 팀 사람을 고를 수 있다."""

        repo.candidates.return_value = [
            {"account_id": "UA002", "email": "a@b.c", "display_name": "홍길동"}
        ]

        response = self.client.get(self.URL, **self._headers())

        self.assertEqual(response.status_code, 200)
        repo.candidates.assert_called_once_with("TE001")

    def test_넘긴다(self, repo, _admin):
        repo.transfer_owner.return_value = {
            "team_id": "TE001", "owner_account_id": "UA002", "moved_models": 1,
        }

        response = self.client.post(
            self.URL,
            {"account_id": "UA002", "reason": "팀장 퇴사"},
            content_type="application/json",
            **self._headers(),
        )

        self.assertEqual(response.status_code, 200)
        kwargs = repo.transfer_owner.call_args.kwargs
        self.assertEqual(kwargs["new_owner_account_id"], "UA002")
        self.assertEqual(kwargs["actor_account_id"], "UA001")
        self.assertEqual(kwargs["reason"], "팀장 퇴사")
        # 모델이 따라간 사실을 화면이 말할 수 있어야 한다.
        self.assertEqual(response.json()["moved_models"], 1)

    def test_남의_팀_계정에는_못_넘긴다(self, repo, _admin):
        """테넌트 경계가 그 자리에서 무너진다."""

        from backend.db.errors import PermissionDenied

        repo.transfer_owner.side_effect = PermissionDenied("이 팀에 속한 계정에게만 넘길 수 있습니다.")

        response = self.client.post(
            self.URL, {"account_id": "UA999"}, content_type="application/json", **self._headers()
        )

        self.assertEqual(response.status_code, 403)

    def test_정지된_계정에는_못_넘긴다(self, repo, _admin):
        from backend.db.errors import RepositoryError as RepoError

        repo.transfer_owner.side_effect = RepoError("정지된 계정에는 넘길 수 없습니다.")

        response = self.client.post(
            self.URL, {"account_id": "UA002"}, content_type="application/json", **self._headers()
        )

        self.assertEqual(response.status_code, 400)

    def test_account_id_는_필수다(self, repo, _admin):
        response = self.client.post(
            self.URL, {"reason": "x"}, content_type="application/json", **self._headers()
        )

        self.assertEqual(response.status_code, 400)
        repo.transfer_owner.assert_not_called()

    def test_운영자가_아니면_못_부른다(self, repo, _admin):
        token = account_tokens.issue_token("UA001")

        response = self.client.get(self.URL, HTTP_AUTHORIZATION=f"Bearer {token}")

        self.assertEqual(response.status_code, 401)
        repo.candidates.assert_not_called()


@patch("apps.ops.authentication.AccountRepository.find_credentials_by_id", return_value=admin_account())
@patch("apps.ops.views.accounts.OpsAccountRepository")
class OpsAccountDetailTests(SimpleTestCase):
    """계정 상세가 별도 페이지가 되면서 생긴 경로.

    목록 아래 섹션일 때는 목록이 이미 들고 있는 값을 썼다. 페이지가 갈리면
    **주소로 바로 들어올 수 있어야** 하므로 한 건을 줄 자리가 필요하다.
    """

    def _headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {ops_tokens.issue_token('UA001')}"}

    def test_한_건을_준다(self, repo, _admin):
        repo.get.return_value = {
            "account_id": "UA002", "email": "a@b.c", "display_name": "홍길동",
            "account_status": "ACTIVE", "is_admin": False, "team_id": "TE001",
            "team_name": "개발팀", "link_count": 1, "person_id": None,
            "person_name": None, "org_id": None, "org_name": None, "services": ["JIRA"],
        }

        response = self.client.get("/api/ops/accounts/UA002/", **self._headers())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["email"], "a@b.c")
        repo.get.assert_called_once_with("UA002")

    def test_없는_계정은_404(self, repo, _admin):
        from backend.db.errors import RecordNotFound

        repo.get.side_effect = RecordNotFound("존재하지 않는 계정입니다: UA999")

        response = self.client.get("/api/ops/accounts/UA999/", **self._headers())

        self.assertEqual(response.status_code, 404)

    def test_상세_경로가_조치_경로를_먹지_않는다(self, repo, _admin):
        """`accounts/<id>/` 를 `accounts/<id>/lock/` 보다 앞에 두면 잠금이 상세로 잡힌다."""

        from django.urls import resolve

        self.assertEqual(resolve("/api/ops/accounts/UA001/").url_name, "api_ops_account_detail")
        self.assertEqual(resolve("/api/ops/accounts/UA001/lock/").url_name, "api_ops_account_lock")
        self.assertEqual(resolve("/api/ops/accounts/UA001/admin/").url_name, "api_ops_account_admin")


@patch("apps.ops.authentication.AccountRepository.find_credentials_by_id", return_value=admin_account())
@patch("apps.ops.views.invites.OpsInviteRepository")
class OpsInviteDetailTests(SimpleTestCase):
    """초대 상세도 별도 페이지가 되면서 한 건을 줄 자리가 필요해졌다."""

    def _headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {ops_tokens.issue_token('UA001')}"}

    def test_한_건을_준다(self, repo, _admin):
        repo.get.return_value = {
            "invite_id": "IV001", "person_id": "PE001", "person_name": "홍길동",
            "person_email": "a@b.c", "org_id": "A001", "org_name": "개발본부",
            "invited_by": "UA001", "inviter_email": "x@y.z", "status": "PENDING",
            "expires_at": None, "accepted_at": None, "created_at": None,
            "linked_account_id": None, "linked_account_email": None,
            "linked_account_duplicate": False,
        }

        response = self.client.get("/api/ops/invites/IV001/", **self._headers())

        self.assertEqual(response.status_code, 200)
        repo.get.assert_called_once_with("IV001")

    def test_없는_초대는_404(self, repo, _admin):
        from backend.db.errors import RecordNotFound

        repo.get.side_effect = RecordNotFound("존재하지 않는 초대입니다: IV999")

        response = self.client.get("/api/ops/invites/IV999/", **self._headers())

        self.assertEqual(response.status_code, 404)

    def test_상세_경로가_조치_경로를_먹지_않는다(self, repo, _admin):
        from django.urls import resolve

        self.assertEqual(resolve("/api/ops/invites/IV001/").url_name, "api_ops_invite_detail")
        self.assertEqual(resolve("/api/ops/invites/IV001/discard/").url_name, "api_ops_invite_discard")
        self.assertEqual(resolve("/api/ops/invites/IV001/unlink/").url_name, "api_ops_invite_unlink")


@patch("apps.ops.authentication.AccountRepository.find_credentials_by_id", return_value=admin_account())
@patch("apps.ops.views.invites.OpsInviteRepository")
@patch("apps.ops.views.accounts.OpsAccountRepository")
class OpsActionReasonTests(SimpleTestCase):
    """**무엇을 했는지는 감사 로그가 이미 남긴다. 왜 했는지가 없었다.**

    권한 부여·회수와 소유자 이전·연결 해제만 사유를 받고 있었는데, 남의 계정을
    세우고 직원 연결을 끊고 초대를 폐기하는 것도 나중에 답해야 하는 건 같다
    (2026-08-13 지적).
    """

    def _headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {ops_tokens.issue_token('UA001')}"}

    def _post(self, url, body):
        return self.client.post(url, body, content_type="application/json", **self._headers())

    def test_계정_조치가_사유를_넘긴다(self, accounts, _invites, _admin):
        cases = [
            ("/api/ops/accounts/UA002/lock/", accounts.lock, "퇴사자 계정"),
            ("/api/ops/accounts/UA002/unlock/", accounts.unlock, "오인 정지 정정"),
            ("/api/ops/accounts/UA002/unlink-person/", accounts.unlink_all, "동명이인 오연결"),
        ]
        for url, method, why in cases:
            with self.subTest(url=url):
                method.reset_mock()
                method.return_value = {"account_id": "UA002"}

                response = self._post(url, {"reason": why})

                self.assertEqual(response.status_code, 200)
                self.assertEqual(method.call_args.kwargs["reason"], why)

    def test_초대_조치가_사유를_넘긴다(self, _accounts, invites, _admin):
        cases = [
            ("/api/ops/invites/IV001/discard/", invites.discard),
            ("/api/ops/invites/IV001/unlink/", invites.unlink_by_invite),
        ]
        for url, method in cases:
            with self.subTest(url=url):
                method.reset_mock()
                method.return_value = {"invite_id": "IV001"}

                response = self._post(url, {"reason": "잘못 보낸 초대"})

                self.assertEqual(response.status_code, 200)
                self.assertEqual(method.call_args.kwargs["reason"], "잘못 보낸 초대")

    def test_사유가_없어도_막지_않는다(self, accounts, _invites, _admin):
        """급할 때 사유 때문에 조치를 못 하면 그게 더 나쁘다 — 관문이 아니라 기록이다."""

        accounts.lock.return_value = {"account_id": "UA002"}

        response = self._post("/api/ops/accounts/UA002/lock/", {})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(accounts.lock.call_args.kwargs["reason"], "")


@patch("apps.ops.authentication.AccountRepository.find_credentials_by_id", return_value=admin_account())
@patch("apps.ops.views.connectors.OpsConnectorRepository")
class OpsConnectorRevokeTests(SimpleTestCase):
    """연결 강제 해제.

    **끊는 쪽이 제품 어디에도 없었다** — 토큰이 샜거나 엉뚱한 계정으로 연결된 것을
    고객도 운영자도 못 끊었다(2026-08-13 PM 요청).
    """

    URL = "/api/ops/connectors/CN003/revoke/"

    def _headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {ops_tokens.issue_token('UA001')}"}

    def test_끊는다(self, repo, _admin):
        repo.revoke.return_value = {
            "conn_id": "CN003", "connector_type": "GOOGLE_DRIVE",
            "auth_status": "REVOKED", "affected_sources": 2,
        }

        response = self.client.post(
            self.URL, {"reason": "토큰 유출"}, content_type="application/json", **self._headers()
        )

        self.assertEqual(response.status_code, 200)
        kwargs = repo.revoke.call_args.kwargs
        self.assertEqual(kwargs["conn_id"], "CN003")
        self.assertEqual(kwargs["actor_account_id"], "UA001")
        self.assertEqual(kwargs["reason"], "토큰 유출")
        # 무엇이 멈추는지 화면이 말할 수 있어야 한다.
        self.assertEqual(response.json()["affected_sources"], 2)

    def test_사유는_없어도_된다(self, repo, _admin):
        """급할 때 사유 때문에 못 끊는 일이 없어야 한다."""

        repo.revoke.return_value = {
            "conn_id": "CN003", "connector_type": "JIRA",
            "auth_status": "REVOKED", "affected_sources": 0,
        }

        response = self.client.post(self.URL, {}, content_type="application/json", **self._headers())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(repo.revoke.call_args.kwargs["reason"], "")

    def test_본인_확인용_연결은_못_끊는다(self, repo, _admin):
        """People DB·등록 모델은 이 화면의 것이 아니다. 거부는 Repository 가 한다."""

        from backend.db.errors import RepositoryError as RepoError

        repo.revoke.side_effect = RepoError("구글 드라이브·Jira 연결만 해제할 수 있습니다.")

        response = self.client.post(self.URL, {}, content_type="application/json", **self._headers())

        self.assertEqual(response.status_code, 400)

    def test_운영자가_아니면_못_끊는다(self, repo, _admin):
        token = account_tokens.issue_token("UA001")

        response = self.client.post(self.URL, {}, content_type="application/json",
                                    HTTP_AUTHORIZATION=f"Bearer {token}")

        self.assertEqual(response.status_code, 401)
        repo.revoke.assert_not_called()

    def test_상세_경로가_해제_경로를_먹지_않는다(self, repo, _admin):
        from django.urls import resolve

        self.assertEqual(resolve("/api/ops/connectors/CN003/").url_name, "api_ops_connector_detail")
        self.assertEqual(resolve("/api/ops/connectors/CN003/revoke/").url_name, "api_ops_connector_revoke")


@patch("apps.ops.authentication.AccountRepository.find_credentials_by_id", return_value=admin_account())
@patch("apps.ops.views.teams.OpsTeamRepository")
class OpsTeamContentTests(SimpleTestCase):
    """고객이 「에이전트가 이상해요」라고 할 때 운영자가 볼 것이 아무것도 없었다.

    **경계는 유지한다** — 무엇을 들고 있고 무슨 일이 있었는지는 보되, 대화 내용과
    문서 원문은 주지 않는다.
    """

    URL = "/api/ops/teams/TE001/content/"

    def _headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {ops_tokens.issue_token('UA001')}"}

    def test_에이전트와_실행을_준다(self, repo, _admin):
        # **팀이 만든 것**을 예로 든다. 우리가 넣는 코파일럿은 여기까지 오지 않는다 —
        # Repository 가 `is_prebuilt` 로 거른다.
        repo.agents.return_value = [
            {"agent_id": "AG001", "name": "회의록 정리", "model": "gpt-5.6-luna", "tool_refs": ["document_search"]}
        ]
        repo.runs.return_value = [
            {"run_id": "r1", "agent_name": "회의록 정리", "status": "FAILED", "failed_tools": ["jira_get_issues (401)"]}
        ]

        body = self.client.get(self.URL, **self._headers()).json()

        self.assertEqual(body["agents"][0]["name"], "회의록 정리")
        # 왜 실패했는지가 그 줄에 있어야 운영자가 답할 수 있다.
        self.assertEqual(body["runs"][0]["failed_tools"], ["jira_get_issues (401)"])
        repo.agents.assert_called_once_with("TE001")
        repo.runs.assert_called_once_with("TE001")

    def test_대화나_문서는_주지_않는다(self, repo, _admin):
        """열람 통제 장치가 없는 상태에서 고객의 업무 내용까지 열지 않는다."""

        repo.agents.return_value = []
        repo.runs.return_value = []

        body = self.client.get(self.URL, **self._headers()).json()

        self.assertEqual(set(body), {"agents", "runs"})

    def test_운영자가_아니면_못_본다(self, repo, _admin):
        token = account_tokens.issue_token("UA001")

        response = self.client.get(self.URL, HTTP_AUTHORIZATION=f"Bearer {token}")

        self.assertEqual(response.status_code, 401)
        repo.agents.assert_not_called()


@patch("apps.ops.authentication.AccountRepository.find_credentials_by_id", return_value=admin_account())
@patch("apps.ops.views.usage.OpsUsageRepository")
class OpsUsageTests(SimpleTestCase):
    """사용 현황 — 관측성의 「요약」 층(2026-08-21).

    실행 이력은 2026-08-13 부터 쌓였는데 집계해 보여주는 자리가 없었다.
    """

    URL = "/api/ops/usage/"

    def _headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {ops_tokens.issue_token('UA001')}"}

    @staticmethod
    def _summary(**overrides):
        summary = {
            "window_days": 30,
            "runs": {
                "runs": 23, "runs_done": 20, "runs_failed": 3,
                "token_in": 158836, "token_out": 2811, "runs_without_tokens": 0,
            },
            "tools": {"calls": 20, "calls_ok": 16, "calls_failed": 4},
            "guardrail": {"events": 13, "blocked": 8},
            "by_team": [{"team_id": "TE001", "team_name": "개발팀", "runs": 23,
                         "runs_done": 20, "token_in": 158836, "token_out": 2811}],
            "by_model": [{"model": "gpt-5.6-luna", "resolved_provider": "openai",
                          "runs": 2, "token_in": 20395, "token_out": 651}],
            "by_tool": [{"tool_ref": "document_search", "calls": 1, "calls_ok": 1,
                         "calls_pending": 0, "avg_ms": 8823}],
        }
        summary.update(overrides)
        return summary

    def test_집계를_그대로_준다(self, repo, _admin):
        repo.summary.return_value = self._summary()

        body = self.client.get(self.URL, **self._headers()).json()

        self.assertEqual(body["window_days"], 30)
        self.assertEqual(body["runs"]["token_in"], 158836)
        self.assertEqual(body["by_tool"][0]["tool_ref"], "document_search")
        repo.summary.assert_called_once_with()

    def test_운영자가_아니면_막힌다(self, repo, admin):
        """감사 로그와 같은 경계다 — 이 표는 전 팀의 사용량을 보여준다."""
        admin.return_value = admin_account(is_admin=False)

        response = self.client.get(self.URL, **self._headers())

        self.assertEqual(response.status_code, 401)
        repo.summary.assert_not_called()

    def test_못_잰_실행_수를_숨기지_않는다(self, repo, _admin):
        """합계만 주면 「적게 썼다」와 「못 쟀다」가 같은 모양이 된다."""
        repo.summary.return_value = self._summary(
            runs={"runs": 10, "runs_done": 9, "runs_failed": 1,
                  "token_in": 100, "token_out": 20, "runs_without_tokens": 7}
        )

        body = self.client.get(self.URL, **self._headers()).json()

        self.assertEqual(body["runs"]["runs_without_tokens"], 7)

