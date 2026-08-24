"""외부 가드레일 공급자 등록 API(운영자 콘솔).

DB 는 띄우지 않고 Repository 를 mock 한다 — 이 저장소는 psycopg 직결이라 Django
테스트 DB 가 없다.

가장 중요하게 보는 것은 **자격증명이 새어 나가지 않는가**다. 목록 응답과 감사
로그 양쪽에 키가 실리면 안 된다.
"""

import json
from unittest.mock import patch

from django.test import SimpleTestCase

import apps.ops.tokens as ops_tokens

LIST_URL = "/api/ops/guardrails/"
DETAIL_URL = "/api/ops/guardrails/GP001/"
TEAM_ACTIVE_URL = "/api/ops/guardrails/teams/TE001/active/"
ON_FAILURE_URL = "/api/ops/guardrails/teams/TE001/on-failure/"


def admin_account(account_id="UA001"):
    return {
        "account_id": account_id,
        "email": "admin@halil.com",
        "display_name": "관리자",
        "password_hash": "unused",
        "account_status": "ACTIVE",
        "is_admin": True,
    }


def provider_row(**overrides):
    row = {
        "provider_id": "GP001",
        "is_active": False,
        "team_id": "TE001",
        "team_name": "개발팀",
        "name": "우리 회사 가드레일",
        "kind": "AZURE_CONTENT_SAFETY",
        "config": {"endpoint": "https://example.cognitiveservices.azure.com"},
        "status": "UNCHECKED",
        "last_checked_at": None,
        "has_credential": True,
        "created_by": "UA001",
        "created_at": "2026-08-20T12:00:00Z",
    }
    row.update(overrides)
    return row


@patch("apps.ops.authentication.AccountRepository.find_credentials_by_id", return_value=admin_account())
@patch("apps.ops.views.guardrails.log_audit")
@patch("apps.ops.views.guardrails.GuardrailProviderRepository")
class GuardrailProviderApiTests(SimpleTestCase):
    def _headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {ops_tokens.issue_token('UA001')}"}

    def test_목록에_자격증명은_안_나간다(self, repo, _audit, _admin):
        """있는지 여부만 준다 — 화면이 키를 다시 보여줄 이유가 없다."""

        repo.list_all.return_value = [provider_row()]

        body = self.client.get(LIST_URL, **self._headers()).json()

        self.assertEqual(body[0]["provider_id"], "GP001")
        self.assertTrue(body[0]["has_credential"])
        self.assertNotIn("credential", body[0])
        self.assertNotIn("credential_enc", body[0])

    def test_등록하면_팀과_종류가_그대로_넘어간다(self, repo, _audit, _admin):
        repo.create.return_value = provider_row()

        response = self.client.post(
            LIST_URL,
            data=json.dumps({
                "team_id": "TE001",
                "name": "우리 회사 가드레일",
                "kind": "AZURE_CONTENT_SAFETY",
                "config": {"endpoint": "https://example.cognitiveservices.azure.com"},
                "credential": {"api_key": "super-secret"},
            }),
            content_type="application/json",
            **self._headers(),
        )

        self.assertEqual(response.status_code, 201)
        _, kwargs = repo.create.call_args
        self.assertEqual(kwargs["team_id"], "TE001")
        self.assertEqual(kwargs["kind"], "AZURE_CONTENT_SAFETY")
        self.assertEqual(kwargs["credential"], {"api_key": "super-secret"})
        self.assertEqual(kwargs["registered_by"], "UA001")

    def test_감사_로그에_자격증명은_안_남는다(self, repo, audit, _admin):
        """감사 로그는 나중에 사람이 읽는 표다(MCP 등록과 같은 규칙)."""

        repo.create.return_value = provider_row()

        self.client.post(
            LIST_URL,
            data=json.dumps({
                "team_id": "TE001", "name": "우리 회사 가드레일",
                "kind": "AZURE_CONTENT_SAFETY", "config": {},
                "credential": {"api_key": "super-secret"},
            }),
            content_type="application/json",
            **self._headers(),
        )

        _, kwargs = audit.call_args
        self.assertNotIn("super-secret", json.dumps(kwargs["payload"], ensure_ascii=False))
        self.assertEqual(kwargs["action"], "OPS_GUARDRAIL_REGISTER")
        self.assertEqual(kwargs["target_id"], "TE001")

    def test_모르는_종류는_거절한다(self, _repo, _audit, _admin):
        response = self.client.post(
            LIST_URL,
            data=json.dumps({"team_id": "TE001", "name": "x", "kind": "MADE_UP"}),
            content_type="application/json",
            **self._headers(),
        )

        self.assertEqual(response.status_code, 400)

    def test_수정에서_자격증명_교체_의사는_명시해야_한다(self, repo, _audit, _admin):
        """안 보낸 것을 「지우라」로 읽으면 이름만 고쳐도 키가 날아간다."""

        repo.update.return_value = provider_row(name="이름만 수정")

        self.client.patch(
            DETAIL_URL,
            data=json.dumps({"name": "이름만 수정", "kind": "AZURE_CONTENT_SAFETY", "config": {}}),
            content_type="application/json",
            **self._headers(),
        )

        _, kwargs = repo.update.call_args
        self.assertFalse(kwargs["replace_credential"])
        self.assertIsNone(kwargs["credential"])

    def test_삭제도_기록에_남는다(self, repo, audit, _admin):
        repo.delete.return_value = {
            "provider_id": "GP001", "team_id": "TE001",
            "name": "우리 회사 가드레일", "kind": "AZURE_CONTENT_SAFETY",
        }

        response = self.client.delete(DETAIL_URL, **self._headers())

        self.assertEqual(response.status_code, 204)
        _, kwargs = audit.call_args
        self.assertEqual(kwargs["action"], "OPS_GUARDRAIL_DELETE")

    def test_관리자가_아니면_막는다(self, _repo, _audit, admin):
        admin.return_value = {**admin_account(), "is_admin": False}

        response = self.client.get(LIST_URL, **self._headers())

        self.assertEqual(response.status_code, 401)

    def test_그_팀이_쓸_것을_팀_단위로_정한다(self, repo, _audit, _admin):
        """**등록 목록이 아니라 팀 상세에서 고른다** — 목록은 전 팀의 등록물이라
        거기서 켜면 「어느 팀의 무엇을 켜는가」가 흐려진다."""

        repo.set_active_for_team.return_value = provider_row(is_active=True)

        response = self.client.put(
            TEAM_ACTIVE_URL,
            data=json.dumps({"provider_id": "GP001"}),
            content_type="application/json",
            **self._headers(),
        )

        self.assertEqual(response.status_code, 200)
        _, kwargs = repo.set_active_for_team.call_args
        self.assertEqual(kwargs["team_id"], "TE001")
        self.assertEqual(kwargs["provider_id"], "GP001")

    def test_비우면_아무것도_안_쓴다(self, repo, _audit, _admin):
        """등록을 지우지 않고 검사만 끄는 자리다."""

        repo.set_active_for_team.return_value = None

        response = self.client.put(
            TEAM_ACTIVE_URL,
            data=json.dumps({"provider_id": None}),
            content_type="application/json",
            **self._headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["provider_id"])
        _, kwargs = repo.set_active_for_team.call_args
        self.assertIsNone(kwargs["provider_id"])


@patch("apps.ops.authentication.AccountRepository.find_credentials_by_id", return_value=admin_account())
@patch("apps.ops.views.guardrails.log_audit")
@patch("apps.ops.views.guardrails.GuardrailProviderRepository")
class OnFailureTests(SimpleTestCase):
    """검사기를 못 불렀을 때의 동작은 **팀에** 붙는다.

    등록 한 건에 뒀더니 공급자를 갈아탈 때(키 교체·비교·시연) 정책이 조용히
    함께 바뀌었다 — 갈아타는 것은 우리가 의도한 사용법이라 더 나쁘다.
    """

    def _headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {ops_tokens.issue_token('UA001')}"}

    def test_팀_단위로_정한다(self, repo, _audit, _admin):
        repo.ON_FAILURE = ("OPEN", "CLOSED")
        repo.set_on_failure.return_value = {"team_id": "TE001", "on_failure": "CLOSED"}

        response = self.client.put(
            ON_FAILURE_URL,
            data=json.dumps({"on_failure": "CLOSED"}),
            content_type="application/json",
            **self._headers(),
        )

        self.assertEqual(response.status_code, 200)
        _, kwargs = repo.set_on_failure.call_args
        self.assertEqual(kwargs["team_id"], "TE001")
        self.assertEqual(kwargs["on_failure"], "CLOSED")

    def test_모르는_값은_거절한다(self, repo, _audit, _admin):
        repo.ON_FAILURE = ("OPEN", "CLOSED")

        response = self.client.put(
            ON_FAILURE_URL,
            data=json.dumps({"on_failure": "MAYBE"}),
            content_type="application/json",
            **self._headers(),
        )

        self.assertEqual(response.status_code, 400)
        repo.set_on_failure.assert_not_called()

    def test_바꾸면_기록에_남는다(self, repo, audit, _admin):
        """그 팀 대화가 막히기 시작하거나 막히지 않게 되는 일이다."""

        repo.ON_FAILURE = ("OPEN", "CLOSED")
        repo.set_on_failure.return_value = {"team_id": "TE001", "on_failure": "CLOSED"}

        self.client.put(
            ON_FAILURE_URL,
            data=json.dumps({"on_failure": "CLOSED"}),
            content_type="application/json",
            **self._headers(),
        )

        _, kwargs = audit.call_args
        self.assertEqual(kwargs["action"], "OPS_GUARDRAIL_ON_FAILURE")
        self.assertEqual(kwargs["target_id"], "TE001")

    def test_등록에는_더_이상_실리지_않는다(self, repo, _audit, _admin):
        """등록물의 속성이 아니다 — 보내도 무시된다."""

        repo.create.return_value = provider_row()

        self.client.post(
            LIST_URL,
            data=json.dumps({
                "team_id": "TE001", "name": "x",
                "kind": "AZURE_CONTENT_SAFETY", "on_failure": "CLOSED",
            }),
            content_type="application/json",
            **self._headers(),
        )

        self.assertNotIn("on_failure", repo.create.call_args[1])
