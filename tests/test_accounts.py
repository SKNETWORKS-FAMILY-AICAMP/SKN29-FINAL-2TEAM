from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.hashers import make_password
from django.core import mail
from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.accounts.tokens import (
    TOKEN_MAX_AGE_SECONDS,
    InvalidToken,
    hash_invite_code,
    issue_password_reset_token,
    issue_token,
    read_token,
)
from backend.db.errors import DuplicateRecord, PermissionDenied, RecordNotFound


def leader_profile(account_id="UA001", email="leader@halil.com"):
    """HR 연결까지 마친 팀장. 직접 가입했으므로 invited=False."""

    return {
        "account_id": account_id,
        "email": email,
        "display_name": "임준",
        "account_status": "ACTIVE",
        "person": {
            "person_id": "PX002",
            "name": "임준",
            "email": email,
            "org_id": "A002",
            "org_name": "개발팀",
            "job_role": "팀장",
        },
        "invited": False,
        "scope_org_ids": ["A002", "A003", "A004"],
    }


def member_profile():
    """초대 코드로 들어온 팀원."""

    profile = leader_profile(account_id="UA002", email="member@halil.com")
    profile["display_name"] = "성주연"
    profile["person"] = {
        "person_id": "PB002",
        "name": "성주연",
        "email": "member@halil.com",
        "org_id": "A002",
        "org_name": "개발팀",
        "job_role": "사원",
    }
    profile["invited"] = True
    return profile


def fresh_leader_profile():
    """가입 직후. HR을 아직 연결하지 않아 PERSON도 조직 범위도 없다."""

    profile = leader_profile(account_id="UA009", email="nobody@halil.com")
    profile["person"] = None
    profile["scope_org_ids"] = []
    return profile


class TokenTests(SimpleTestCase):
    def test_token_round_trip(self):
        self.assertEqual(read_token(issue_token("UA001")), "UA001")

    def test_tampered_token_is_rejected(self):
        with self.assertRaises(InvalidToken):
            read_token(issue_token("UA001") + "x")

    def test_invite_code_hash_ignores_surrounding_whitespace(self):
        self.assertEqual(hash_invite_code("  abc123  "), hash_invite_code("abc123"))


class SignupApiTests(SimpleTestCase):
    @patch("apps.accounts.api_views.AccountRepository.create")
    def test_direct_signup_is_a_leader_without_hr_link_yet(self, create):
        create.return_value = fresh_leader_profile()

        response = self.client.post(
            "/api/auth/signup/",
            {"email": "nobody@halil.com", "password": "halil1234", "display_name": "임준"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(read_token(body["token"]), "UA009")
        # 가입 경로가 역할을 정한다. HR 매칭은 People DB 커넥터 연결 때 일어난다.
        self.assertEqual(body["account"]["role"], "leader")
        self.assertIsNone(body["account"]["person"])
        self.assertEqual(body["account"]["scope_org_ids"], [])
        self.assertIsNone(create.call_args.kwargs["invite_token_hash"])

    @patch("apps.accounts.api_views.AccountRepository.create")
    def test_invited_signup_is_a_member(self, create):
        create.return_value = member_profile()

        response = self.client.post(
            "/api/auth/signup/",
            {
                "email": "member@halil.com",
                "password": "halil1234",
                "display_name": "성주연",
                "invite_code": " abc123 ",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(create.call_args.kwargs["invite_token_hash"], hash_invite_code("abc123"))
        self.assertEqual(response.json()["account"]["role"], "member")
        self.assertEqual(response.json()["account"]["person"]["person_id"], "PB002")

    @patch("apps.accounts.api_views.AccountRepository.create")
    def test_signup_stores_hashed_password_only(self, create):
        create.return_value = leader_profile()

        self.client.post(
            "/api/auth/signup/",
            {"email": "leader@halil.com", "password": "halil1234", "display_name": "윤수아"},
            content_type="application/json",
        )

        self.assertNotIn("halil1234", create.call_args.kwargs["password_hash"])

    def test_signup_rejects_password_without_digit(self):
        response = self.client.post(
            "/api/auth/signup/",
            {"email": "leader@halil.com", "password": "abcdefgh", "display_name": "윤수아"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.json())

    @patch("apps.accounts.api_views.AccountRepository.create", side_effect=DuplicateRecord("이미 가입된 이메일입니다."))
    def test_signup_duplicate_email_returns_conflict(self, _create):
        response = self.client.post(
            "/api/auth/signup/",
            {"email": "leader@halil.com", "password": "halil1234", "display_name": "윤수아"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)

    @patch(
        "apps.accounts.api_views.AccountRepository.create",
        side_effect=RecordNotFound("사용할 수 없는 초대 코드입니다."),
    )
    def test_signup_with_dead_invite_code_returns_not_found(self, _create):
        response = self.client.post(
            "/api/auth/signup/",
            {
                "email": "member@halil.com",
                "password": "halil1234",
                "display_name": "권다인",
                "invite_code": "dead-code",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)


class LoginApiTests(SimpleTestCase):
    def credentials(self, status="ACTIVE"):
        return {
            "account_id": "UA001",
            "email": "leader@halil.com",
            "password_hash": make_password("halil1234"),
            "display_name": "윤수아",
            "account_status": status,
        }

    @patch("apps.accounts.api_views.AccountRepository.get_profile", return_value=leader_profile())
    @patch("apps.accounts.api_views.AccountRepository.touch_last_login")
    @patch("apps.accounts.api_views.AccountRepository.find_credentials")
    def test_login_success_returns_token_and_role(self, find, touch, _profile):
        find.return_value = self.credentials()

        response = self.client.post(
            "/api/auth/login/",
            {"email": "leader@halil.com", "password": "halil1234"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(read_token(response.json()["token"]), "UA001")
        self.assertEqual(response.json()["account"]["role"], "leader")
        touch.assert_called_once_with("UA001")

    @patch("apps.accounts.api_views.AccountRepository.get_profile", return_value=leader_profile())
    @patch("apps.accounts.api_views.AccountRepository.touch_last_login")
    @patch("apps.accounts.api_views.AccountRepository.find_credentials")
    def test_login_returns_token_expiry(self, find, _touch, _profile):
        """프론트엔드가 만료된 세션을 스스로 버리려면 만료 시각이 필요하다."""

        find.return_value = self.credentials()

        response = self.client.post(
            "/api/auth/login/",
            {"email": "leader@halil.com", "password": "halil1234"},
            content_type="application/json",
        )

        expires_at = parse_datetime(response.json()["expires_at"])
        self.assertIsNotNone(expires_at)
        expected = timezone.now() + timedelta(seconds=TOKEN_MAX_AGE_SECONDS)
        self.assertLess(abs((expires_at - expected).total_seconds()), 60)

    @patch("apps.accounts.api_views.AccountRepository.find_credentials")
    def test_login_with_wrong_password_returns_401(self, find):
        find.return_value = self.credentials()

        response = self.client.post(
            "/api/auth/login/",
            {"email": "leader@halil.com", "password": "wrongpass1"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)

    @patch("apps.accounts.api_views.AccountRepository.find_credentials", return_value=None)
    def test_unknown_email_gives_same_detail_as_wrong_password(self, _find):
        response = self.client.post(
            "/api/auth/login/",
            {"email": "nobody@halil.com", "password": "halil1234"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "이메일 또는 비밀번호가 올바르지 않습니다.")

    @patch("apps.accounts.api_views.AccountRepository.find_credentials")
    def test_locked_account_cannot_login(self, find):
        find.return_value = self.credentials(status="LOCKED")

        response = self.client.post(
            "/api/auth/login/",
            {"email": "leader@halil.com", "password": "halil1234"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)


@override_settings(FRONTEND_BASE_URL="http://localhost:5173")
class PasswordResetRequestApiTests(SimpleTestCase):
    def credentials(self, status="ACTIVE"):
        return {
            "account_id": "UA001",
            "email": "leader@halil.com",
            "password_hash": make_password("halil1234"),
            "display_name": "임준",
            "account_status": status,
        }

    @patch("apps.accounts.api_views.AccountRepository.find_credentials")
    def test_request_sends_mail_with_reset_link(self, find):
        find.return_value = self.credentials()

        response = self.client.post(
            "/api/auth/password-reset/",
            {"email": "leader@halil.com"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["leader@halil.com"])
        self.assertIn("http://localhost:5173/reset-password?token=", mail.outbox[0].body)

    @patch("apps.accounts.api_views.AccountRepository.find_credentials", return_value=None)
    def test_unknown_email_sends_nothing_but_looks_identical(self, _find):
        response = self.client.post(
            "/api/auth/password-reset/",
            {"email": "nobody@halil.com"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)
        self.assertIn("가입된 이메일이라면", response.json()["detail"])

    @patch("apps.accounts.api_views.AccountRepository.find_credentials")
    def test_locked_account_gets_no_mail(self, find):
        find.return_value = self.credentials(status="LOCKED")

        response = self.client.post(
            "/api/auth/password-reset/",
            {"email": "leader@halil.com"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    @patch("apps.accounts.api_views.AccountRepository.find_credentials")
    @patch("apps.accounts.api_views.send_password_reset_mail", side_effect=OSError("SMTP down"))
    def test_smtp_failure_does_not_leak_to_the_client(self, _send, find):
        find.return_value = self.credentials()

        with self.assertLogs("apps.accounts.api_views", level="ERROR"):
            response = self.client.post(
                "/api/auth/password-reset/",
                {"email": "leader@halil.com"},
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)


class PasswordResetConfirmApiTests(SimpleTestCase):
    CURRENT_HASH = make_password("halil1234")

    def account(self, password_hash=None, status="ACTIVE"):
        return {
            "account_id": "UA001",
            "email": "leader@halil.com",
            "password_hash": password_hash or self.CURRENT_HASH,
            "display_name": "임준",
            "account_status": status,
        }

    def token(self, password_hash=None):
        return issue_password_reset_token(
            account_id="UA001",
            password_hash=password_hash or self.CURRENT_HASH,
        )

    @patch("apps.accounts.api_views.AccountRepository.update_password")
    @patch("apps.accounts.api_views.AccountRepository.find_credentials_by_id")
    def test_confirm_updates_password(self, find, update):
        find.return_value = self.account()

        response = self.client.post(
            "/api/auth/password-reset/confirm/",
            {"token": self.token(), "password": "newpass123"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(update.call_args.kwargs["account_id"], "UA001")
        self.assertNotIn("newpass123", update.call_args.kwargs["password_hash"])

    @patch("apps.accounts.api_views.AccountRepository.update_password")
    @patch("apps.accounts.api_views.AccountRepository.find_credentials_by_id")
    def test_token_dies_once_the_password_changed(self, find, update):
        # 발급 시점의 비밀번호와 지금 저장된 비밀번호가 다르면 이미 쓴 링크다.
        find.return_value = self.account(password_hash=make_password("already-changed1"))

        response = self.client.post(
            "/api/auth/password-reset/confirm/",
            {"token": self.token(), "password": "newpass123"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("이미 사용됐거나", response.json()["detail"])
        update.assert_not_called()

    @patch("apps.accounts.api_views.AccountRepository.find_credentials_by_id")
    def test_tampered_token_is_rejected(self, find):
        find.return_value = self.account()

        response = self.client.post(
            "/api/auth/password-reset/confirm/",
            {"token": self.token() + "x", "password": "newpass123"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        find.assert_not_called()

    @patch("apps.accounts.api_views.AccountRepository.update_password")
    @patch("apps.accounts.api_views.AccountRepository.find_credentials_by_id")
    def test_weak_password_is_rejected_before_any_write(self, find, update):
        find.return_value = self.account()

        response = self.client.post(
            "/api/auth/password-reset/confirm/",
            {"token": self.token(), "password": "abcdefgh"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.json())
        update.assert_not_called()


class CurrentAccountApiTests(SimpleTestCase):
    def test_missing_token_is_rejected(self):
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    def test_garbage_token_is_rejected(self):
        response = self.client.get("/api/auth/me/", headers={"authorization": "Bearer garbage"})
        self.assertEqual(response.status_code, 401)

    @patch("apps.accounts.api_views.AccountRepository.get_profile", return_value=leader_profile())
    def test_valid_token_returns_profile(self, get_profile):
        response = self.client.get(
            "/api/auth/me/",
            headers={"authorization": f"Bearer {issue_token('UA001')}"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["account_id"], "UA001")
        get_profile.assert_called_once_with("UA001")


class InviteApiTests(SimpleTestCase):
    def auth_header(self):
        return {"authorization": f"Bearer {issue_token('UA001')}"}

    @patch("apps.accounts.api_views.MemberInviteRepository.preview")
    def test_preview_needs_no_login_and_names_the_person(self, preview):
        preview.return_value = {
            "invite_id": "MI001",
            "person_name": "권다인",
            "person_email": "user008@halil.com",
            "org_name": "백엔드파트",
            "expires_at": "2026-08-12T07:25:13Z",
        }

        response = self.client.post(
            "/api/invites/preview/",
            {"code": "abc123"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["person_name"], "권다인")
        preview.assert_called_once_with(hash_invite_code("abc123"))

    @patch(
        "apps.accounts.api_views.MemberInviteRepository.preview",
        side_effect=RecordNotFound("사용할 수 없는 초대 코드입니다."),
    )
    def test_preview_of_dead_code_returns_404(self, _preview):
        response = self.client.post(
            "/api/invites/preview/",
            {"code": "dead"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)

    @patch("apps.accounts.api_views.MemberInviteRepository.create")
    def test_create_returns_plaintext_code_matching_stored_hash(self, create):
        create.return_value = {
            "invite_id": "MI001",
            "person_id": "PB006",
            "person_name": "권다인",
            "person_email": "user008@halil.com",
            "org_name": "백엔드파트",
            "status": "PENDING",
            "expires_at": "2026-08-12T07:25:13Z",
            "accepted_at": None,
            "created_at": "2026-07-29T07:25:13Z",
        }

        response = self.client.post(
            "/api/invites/",
            {"person_id": "PB006"},
            content_type="application/json",
            headers=self.auth_header(),
        )

        self.assertEqual(response.status_code, 201)
        code = response.json()["code"]
        self.assertEqual(create.call_args.kwargs["token_hash"], hash_invite_code(code))
        self.assertEqual(create.call_args.kwargs["invited_by"], "UA001")

    def test_create_requires_login(self):
        response = self.client.post(
            "/api/invites/",
            {"person_id": "PB006"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)

    @patch(
        "apps.accounts.api_views.MemberInviteRepository.create",
        side_effect=PermissionDenied("본인이 관리하는 조직의 직원만 초대할 수 있습니다."),
    )
    def test_create_outside_managed_org_returns_403(self, _create):
        response = self.client.post(
            "/api/invites/",
            {"person_id": "PQ001"},
            content_type="application/json",
            headers=self.auth_header(),
        )

        self.assertEqual(response.status_code, 403)

    @patch("apps.accounts.api_views.MemberInviteRepository.revoke")
    def test_revoke_scopes_to_the_logged_in_inviter(self, revoke):
        response = self.client.post(
            "/api/invites/MI001/revoke/",
            content_type="application/json",
            headers=self.auth_header(),
        )

        self.assertEqual(response.status_code, 204)
        revoke.assert_called_once_with(invite_id="MI001", account_id="UA001")
