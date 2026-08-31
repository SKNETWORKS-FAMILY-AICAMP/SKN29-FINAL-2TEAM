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


# `SimpleTestCase`는 Django ORM 접근만 막는다. 감사 로그(`log_audit`)는 psycopg로
# 자기 연결을 열기 때문에 그 차단을 지나쳐 **실제 개발 DB에 INSERT**된다. 실제로
# 테스트를 17번 돌린 흔적(SIGNUP·LOGIN 등 143행)이 로컬 DB에 쌓여 있었다.
# 여기서 통째로 막는다 — 테스트는 감사 로그를 남기지 않는다.
_audit_patchers = []


def setUpModule():
    # `list_person_skills`도 psycopg로 자기 연결을 연다. 프로필 조회 테스트가
    # 개발 DB의 mock_hr을 때리지 않도록 같이 막는다.
    for target in (
        "apps.accounts.api_views.log_audit",
        "apps.connectors.api_views.log_audit",
        "apps.accounts.api_views.list_person_skills",
    ):
        patcher = patch(target)
        patcher.start()
        _audit_patchers.append(patcher)


def tearDownModule():
    for patcher in _audit_patchers:
        patcher.stop()
    _audit_patchers.clear()


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


class PasswordChangeApiTests(SimpleTestCase):
    """로그인한 사용자가 스스로 바꾸는 경로."""

    def _post(self, body, account_id="UA001"):
        return self.client.post(
            "/api/auth/password/change/",
            body,
            content_type="application/json",
            headers={"authorization": f"Bearer {issue_token(account_id)}"},
        )

    def test_requires_login(self):
        response = self.client.post(
            "/api/auth/password/change/",
            {"current_password": "OldPass12", "password": "NewPass12"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    @patch("apps.accounts.api_views.AccountRepository.update_password")
    @patch("apps.accounts.api_views.AccountRepository.find_credentials_by_id")
    def test_changes_when_current_password_matches(self, find, update):
        find.return_value = {
            "account_id": "UA001",
            "password_hash": make_password("OldPass12"),
            "account_status": "ACTIVE",
        }

        response = self._post({"current_password": "OldPass12", "password": "NewPass34"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(update.call_args.kwargs["account_id"], "UA001")
        # 평문이 그대로 저장되면 안 된다.
        self.assertNotEqual(update.call_args.kwargs["password_hash"], "NewPass34")

    @patch("apps.accounts.api_views.AccountRepository.update_password")
    @patch("apps.accounts.api_views.AccountRepository.find_credentials_by_id")
    def test_wrong_current_password_writes_nothing(self, find, update):
        """토큰만으로 바꿀 수 있으면 자리를 비운 사이 남이 갈아 끼울 수 있다."""

        find.return_value = {
            "account_id": "UA001",
            "password_hash": make_password("OldPass12"),
            "account_status": "ACTIVE",
        }

        response = self._post({"current_password": "WrongPass12", "password": "NewPass34"})

        self.assertEqual(response.status_code, 400)
        update.assert_not_called()

    @patch("apps.accounts.api_views.AccountRepository.update_password")
    @patch("apps.accounts.api_views.AccountRepository.find_credentials_by_id")
    def test_weak_password_is_rejected_before_any_read(self, find, update):
        response = self._post({"current_password": "OldPass12", "password": "short"})

        self.assertEqual(response.status_code, 400)
        find.assert_not_called()
        update.assert_not_called()

    @patch("apps.accounts.api_views.AccountRepository.update_password")
    @patch("apps.accounts.api_views.AccountRepository.find_credentials_by_id")
    def test_same_password_is_rejected(self, find, update):
        response = self._post({"current_password": "SamePass12", "password": "SamePass12"})

        self.assertEqual(response.status_code, 400)
        update.assert_not_called()


class AvatarApiTests(SimpleTestCase):
    """프로필 사진. 형식은 Content-Type이 아니라 실제 바이트로 판정한다."""

    PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32

    def _headers(self):
        return {"authorization": f"Bearer {issue_token('UA001')}"}

    def test_requires_login(self):
        self.assertEqual(self.client.get("/api/auth/me/avatar/").status_code, 401)

    @patch("apps.accounts.api_views.AccountRepository.avatar_key", return_value=None)
    def test_missing_avatar_is_404(self, _key):
        response = self.client.get("/api/auth/me/avatar/", headers=self._headers())
        self.assertEqual(response.status_code, 404)

    @patch("apps.accounts.api_views.AccountRepository.set_avatar_key")
    @patch("apps.accounts.api_views.storage.save")
    def test_upload_stores_file_then_records_key(self, save, set_key):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from rest_framework.test import APIClient

        response = APIClient().put(
            "/api/auth/me/avatar/",
            data={"file": SimpleUploadedFile("me.png", self.PNG, content_type="image/png")},
            format="multipart",
            headers=self._headers(),
        )

        self.assertEqual(response.status_code, 200)
        save.assert_called_once()
        # 업로드된 파일명이 아니라 계정 id로 키를 만든다 — 이름에 `..`이 들어오면
        # 저장소 밖을 가리킬 수 있다.
        self.assertEqual(set_key.call_args.kwargs["avatar_key"], "avatar/UA001.png")

    @patch("apps.accounts.api_views.AccountRepository.set_avatar_key")
    @patch("apps.accounts.api_views.storage.save")
    def test_non_image_is_rejected_even_when_content_type_lies(self, save, set_key):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from rest_framework.test import APIClient

        response = APIClient().put(
            "/api/auth/me/avatar/",
            data={"file": SimpleUploadedFile("evil.png", b"<?php ?>", content_type="image/png")},
            format="multipart",
            headers=self._headers(),
        )

        self.assertEqual(response.status_code, 400)
        save.assert_not_called()
        set_key.assert_not_called()

    @patch("apps.accounts.api_views.AccountRepository.set_avatar_key")
    def test_delete_clears_the_key(self, set_key):
        response = self.client.delete("/api/auth/me/avatar/", headers=self._headers())

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(set_key.call_args.kwargs["avatar_key"])


class InviteApiTests(SimpleTestCase):
    def setUp(self):
        super().setUp()
        # 초대 API 계약은 권한 가드와 별도로 검증한다. 빈 CI DB에서도 실제
        # UA001 팀장 행을 요구하지 않도록 이 클래스의 권한 결과를 고정한다.
        leader_guard = patch("apps.accounts.api_views.require_leader", return_value=None)
        leader_guard.start()
        self.addCleanup(leader_guard.stop)

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


@patch("apps.accounts.permissions.AccountRepository.get_profile")
class LeaderOnlyGuardTests(SimpleTestCase):
    """**화면이 버튼을 감추는 것은 문지기가 아니다.**

    설정의 「권한」 탭이 「팀장만」이라고 선언한 넷 중 실제로 서버가 막던 것은
    커넥터 연결 하나뿐이었고, 초대·명부·팀 기준·MCP 는 API 를 직접 부르면 그대로
    통과했다(2026-08-13). 표가 지켜지지 않는 약속을 하고 있었다.

    **거절되는 쪽만 엔드포인트로 잰다.** 통과하는 쪽까지 여기서 재려면 뒤따르는
    Repository 를 전부 목으로 막아야 하는데, 이 저장소는 psycopg 직결이라
    `SimpleTestCase` 가 DB 접근을 안 막는다 — 하나라도 빠뜨리면 테스트가 개발
    DB 에 초대를 만들거나 팀원을 지운다. 통과 쪽은 아래 `RequireLeaderTests` 가
    함수 단위로 잰다.
    """

    #: 팀장 전용이라고 화면이 선언한 쓰기 경로 전부.
    #: MCP 쓰기 넷과 팀 메인 모델은 여기 없다 — 팀장 전용이 아니라 **팀에 아예
    #: 없어졌다**(2026-08-18 · 둘 다 운영자 콘솔로 갔다). 경로가 사라진 것은
    #: test_mcp.py 와 test_agents.py 가 각각 잰다.
    LEADER_ONLY = [
        ("/api/invites/", "post", {"person_id": "PB002"}),
        ("/api/invites/MI001/revoke/", "post", {}),
        ("/api/teams/members/", "post", {"person_id": "PB002"}),
        ("/api/teams/members/PB002/", "delete", None),
        ("/api/teams/settings/", "put", {"capacity_wk_hours": 40}),
        ("/api/team/folders/", "put", {"conn_id": "CN003", "folders": []}),
    ]

    def _call(self, url, method, body):
        headers = {"authorization": f"Bearer {issue_token('UA002')}"}
        send = getattr(self.client, method)
        if body is None:
            return send(url, headers=headers)
        return send(url, body, content_type="application/json", headers=headers)

    def test_팀원은_여섯_경로_전부에서_403(self, get_profile):
        get_profile.return_value = member_profile()

        for url, method, body in self.LEADER_ONLY:
            with self.subTest(url=url, method=method):
                response = self._call(url, method, body)

                self.assertEqual(response.status_code, 403, f"{method.upper()} {url}")
                # 왜 막혔는지 화면이 그대로 보여줄 수 있어야 한다.
                self.assertIn("팀장만", response.json()["detail"])

    def test_프로필을_못_읽으면_거절이_아니라_장애다(self, get_profile):
        """「내가 권한이 없나」와 「지금 서버가 이상한가」를 같은 코드로 뭉개지 않는다."""

        import psycopg

        get_profile.side_effect = psycopg.OperationalError("boom")

        response = self._call("/api/invites/", "post", {"person_id": "PB002"})

        self.assertEqual(response.status_code, 503)


@patch("apps.accounts.permissions.AccountRepository.get_profile")
class RequireLeaderTests(SimpleTestCase):
    """문지기 함수 자체. 통과하는 쪽은 여기서 잰다 — DB 에 닿지 않는다."""

    def test_팀장이면_통과한다(self, get_profile):
        from apps.accounts.permissions import require_leader

        get_profile.return_value = leader_profile()

        self.assertIsNone(require_leader("UA001", "팀장만 …"))

    def test_팀원이면_403_응답을_돌려준다(self, get_profile):
        from apps.accounts.permissions import require_leader

        get_profile.return_value = member_profile()

        denied = require_leader("UA002", "팀장만 팀원을 초대할 수 있습니다.")

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.data["detail"], "팀장만 팀원을 초대할 수 있습니다.")
