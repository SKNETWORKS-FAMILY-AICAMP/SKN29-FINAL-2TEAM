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
