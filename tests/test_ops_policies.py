"""전역 정책 페이지가 여는 네 갈래(`/api/ops/policies/...`).

**`patch.object` 로 진짜 Repository 를 덮는 것이 이 파일의 핵심이다.** 그냥
`patch("...OpsPolicyRepository")` 로 통째 mock 하면 없는 메서드도 자동으로
생겨서, 메서드가 사라져도 테스트는 통과한다 — 실제로 2026-08-20 에 내장
가드레일 정책을 걷어내면서 `get_invite_ttl_days` 를 같이 지웠고, 이 페이지가
운영에서 안 열렸다. `patch.object` 는 없는 이름을 덮으려 하면 실패한다.

화면은 네 갈래를 `Promise.all` 로 한꺼번에 부른다 — **하나만 죽어도 페이지
전체가 안 열린다.** 그래서 네 개를 다 본다.
"""

from unittest.mock import patch

from django.test import SimpleTestCase

import apps.ops.tokens as ops_tokens
from backend.db import GuardrailEventRepository, OpsPolicyRepository


def admin_account():
    return {
        "account_id": "UA001",
        "email": "admin@halil.com",
        "display_name": "관리자",
        "password_hash": "unused",
        "account_status": "ACTIVE",
        "is_admin": True,
    }


@patch("apps.ops.authentication.AccountRepository.find_credentials_by_id", return_value=admin_account())
class OpsPoliciesLoadTests(SimpleTestCase):
    def _headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {ops_tokens.issue_token('UA001')}"}

    def test_초대_만료_기간을_읽는다(self, _admin):
        with patch.object(OpsPolicyRepository, "get_invite_ttl_days", return_value=14):
            response = self.client.get("/api/ops/policies/invite-ttl/", **self._headers())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["days"], 14)

    def test_가드레일_발동_기록을_읽는다(self, _admin):
        with patch.object(GuardrailEventRepository, "list_recent", return_value=[]):
            response = self.client.get("/api/ops/policies/guardrail/events/", **self._headers())

        self.assertEqual(response.status_code, 200)

    def test_공지를_읽는다(self, _admin):
        with patch.object(OpsPolicyRepository, "list_notices", return_value=[]):
            response = self.client.get("/api/ops/policies/notices/", **self._headers())

        self.assertEqual(response.status_code, 200)

    def test_정책_변경_이력을_읽는다(self, _admin):
        with patch.object(OpsPolicyRepository, "list_policy_changes", return_value=[]):
            response = self.client.get("/api/ops/policies/changes/", **self._headers())

        self.assertEqual(response.status_code, 200)

    def test_초대_만료_기간을_저장한다(self, _admin):
        """`set_` 쪽도 같이 지워졌다 — 저장 갈래까지 봐야 한다."""

        with patch.object(OpsPolicyRepository, "set_invite_ttl_days", return_value={"days": 30}) as saved:
            response = self.client.put(
                "/api/ops/policies/invite-ttl/",
                data='{"days": 30, "reason": "테스트"}',
                content_type="application/json",
                **self._headers(),
            )

        self.assertEqual(response.status_code, 200)
        _, kwargs = saved.call_args
        self.assertEqual(kwargs["days"], 30)
        self.assertEqual(kwargs["actor_account_id"], "UA001")
