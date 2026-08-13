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
        repo.list_all.return_value = []

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
