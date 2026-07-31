from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

from django.test import SimpleTestCase, override_settings

from apps.accounts.tokens import issue_token
from apps.connectors.oauth import (
    GOOGLE_DRIVE,
    JIRA,
    GoogleDriveOAuth,
    JiraOAuth,
    OAuthError,
    decrypt_credential,
    encrypt_credential,
    issue_state,
)
from backend.db.errors import RecordNotFound, ReferenceNotFound

from .test_accounts import fresh_leader_profile, leader_profile, member_profile


def people_db_connection():
    return {
        "conn_id": "CN001",
        "connector_type": "PEOPLE_DB",
        "granted_scopes": ["org:read", "person:read"],
        "auth_status": "CONNECTED",
        "connected_at": "2026-07-30T09:00:00Z",
    }


def people_db_summary():
    return {
        "org_count": 9,
        "person_count": 56,
        "my_org_name": "개발팀",
        "my_org_person_count": 5,
        "scope_person_count": 18,
        "person": {
            "person_id": "PX002",
            "name": "임준",
            "email": "leader@halil.com",
            "org_id": "A002",
            "org_name": "개발팀",
            "job_role": "팀장",
        },
    }


def auth_header(account_id="UA001"):
    return {"authorization": f"Bearer {issue_token(account_id)}"}


def stored_credential(*, expired=False, **extra):
    """저장돼 있는 상태 그대로의 암호문."""

    offset = timedelta(hours=-1) if expired else timedelta(hours=1)
    return encrypt_credential(
        {
            "access_token": "stored-access-token",
            "refresh_token": "stored-refresh-token",
            "expires_at": (datetime.now(UTC) + offset).isoformat(),
            **extra,
        }
    )


def json_response(payload):
    return Mock(json=Mock(return_value=payload), raise_for_status=Mock())


class ConnectorListApiTests(SimpleTestCase):
    def test_requires_login(self):
        self.assertEqual(self.client.get("/api/connectors/").status_code, 401)

    @patch("apps.connectors.api_views.ConnectorRepository.list_for_account")
    def test_lists_only_the_callers_connections(self, list_for_account):
        list_for_account.return_value = [people_db_connection()]

        response = self.client.get("/api/connectors/", headers=auth_header())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["connector_type"], "PEOPLE_DB")
        list_for_account.assert_called_once_with("UA001")


class PeopleDbIdentityApiTests(SimpleTestCase):
    def person(self):
        return {
            "person_id": "PX002",
            "name": "임준",
            "email": "leader@halil.com",
            "org_id": "A002",
            "org_name": "개발팀",
            "job_role": "팀장",
        }

    def test_requires_login(self):
        self.assertEqual(self.client.get("/api/connectors/people-db/identity/").status_code, 401)

    @patch("apps.connectors.api_views.ConnectorRepository.find_identity")
    @patch("apps.connectors.api_views.AccountRepository.get_profile")
    def test_returns_the_matched_person_for_confirmation(self, get_profile, find_identity):
        get_profile.return_value = fresh_leader_profile()
        find_identity.return_value = self.person()

        response = self.client.get(
            "/api/connectors/people-db/identity/",
            headers=auth_header("UA009"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "임준")
        self.assertEqual(
            find_identity.call_args.kwargs,
            {"account_id": "UA009", "email": "nobody@halil.com"},
        )

    @patch(
        "apps.connectors.api_views.ConnectorRepository.find_identity",
        side_effect=RecordNotFound("가입한 이메일과 일치하는 직원 정보가 HR 시스템에 없습니다."),
    )
    @patch("apps.connectors.api_views.AccountRepository.get_profile")
    def test_unmatched_email_returns_404(self, get_profile, _find_identity):
        get_profile.return_value = fresh_leader_profile()

        response = self.client.get(
            "/api/connectors/people-db/identity/",
            headers=auth_header("UA009"),
        )

        self.assertEqual(response.status_code, 404)

    @patch("apps.connectors.api_views.ConnectorRepository.find_identity")
    @patch("apps.connectors.api_views.AccountRepository.get_profile")
    def test_member_cannot_look_up_hr_identity(self, get_profile, find_identity):
        get_profile.return_value = member_profile()

        response = self.client.get(
            "/api/connectors/people-db/identity/",
            headers=auth_header("UA002"),
        )

        self.assertEqual(response.status_code, 403)
        find_identity.assert_not_called()


class PeopleDbConnectApiTests(SimpleTestCase):
    def test_requires_login(self):
        self.assertEqual(self.client.post("/api/connectors/people-db/").status_code, 401)

    @patch("apps.connectors.api_views.ConnectorRepository.connect_people_db")
    @patch("apps.connectors.api_views.AccountRepository.get_profile")
    def test_leader_connects_and_gets_hr_summary(self, get_profile, connect):
        get_profile.return_value = leader_profile()
        connect.return_value = people_db_summary()

        response = self.client.post("/api/connectors/people-db/", headers=auth_header())

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["person"]["name"], "임준")
        self.assertEqual(body["my_org_person_count"], 5)
        self.assertEqual(body["scope_person_count"], 18)
        self.assertEqual(
            connect.call_args.kwargs,
            {"account_id": "UA001", "email": "leader@halil.com"},
        )

    @patch("apps.connectors.api_views.ConnectorRepository.connect_people_db")
    @patch("apps.connectors.api_views.AccountRepository.get_profile")
    def test_member_cannot_connect(self, get_profile, connect):
        get_profile.return_value = member_profile()

        response = self.client.post("/api/connectors/people-db/", headers=auth_header("UA002"))

        self.assertEqual(response.status_code, 403)
        connect.assert_not_called()

    @patch(
        "apps.connectors.api_views.ConnectorRepository.connect_people_db",
        side_effect=RecordNotFound("가입한 이메일과 일치하는 직원 정보가 HR 시스템에 없습니다."),
    )
    @patch("apps.connectors.api_views.AccountRepository.get_profile")
    def test_unmatched_hr_email_fails_instead_of_reporting_connected(self, get_profile, _connect):
        get_profile.return_value = fresh_leader_profile()

        response = self.client.post("/api/connectors/people-db/", headers=auth_header("UA009"))

        self.assertEqual(response.status_code, 404)
        self.assertIn("HR 시스템에 없습니다", response.json()["detail"])

    @patch(
        "apps.connectors.api_views.ConnectorRepository.connect_people_db",
        side_effect=ReferenceNotFound("HR 시스템에서 조직·직원 데이터를 찾을 수 없습니다."),
    )
    @patch("apps.connectors.api_views.AccountRepository.get_profile")
    def test_empty_hr_data_is_a_conflict(self, get_profile, _connect):
        get_profile.return_value = leader_profile()

        response = self.client.post("/api/connectors/people-db/", headers=auth_header())

        self.assertEqual(response.status_code, 409)


class PeopleDbSummaryApiTests(SimpleTestCase):
    def test_requires_login(self):
        self.assertEqual(self.client.get("/api/connectors/people-db/summary/").status_code, 401)

    @patch("apps.connectors.api_views.ConnectorRepository.people_db_summary")
    @patch("apps.connectors.api_views.ConnectorRepository.list_for_account", return_value=[])
    def test_hr_data_is_hidden_until_connected(self, _list, summary):
        response = self.client.get("/api/connectors/people-db/summary/", headers=auth_header())

        self.assertEqual(response.status_code, 404)
        summary.assert_not_called()


@override_settings(
    GOOGLE_DRIVE_CLIENT_ID="google-client-id",
    GOOGLE_DRIVE_CLIENT_SECRET="google-client-secret",
    GOOGLE_DRIVE_REDIRECT_URI="http://localhost:8000/api/connectors/google-drive/callback/",
)
class GoogleDriveOAuthApiTests(SimpleTestCase):
    @patch("apps.connectors.api_views.AccountRepository.get_profile")
    def test_authorize_requires_leader_and_returns_google_url(self, get_profile):
        get_profile.return_value = leader_profile()

        response = self.client.get(
            "/api/connectors/google-drive/authorize/",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 200)
        query = parse_qs(urlparse(response.json()["authorization_url"]).query)
        self.assertEqual(query["client_id"], ["google-client-id"])
        self.assertEqual(query["redirect_uri"], ["http://localhost:8000/api/connectors/google-drive/callback/"])
        self.assertEqual(query["access_type"], ["offline"])
        self.assertEqual(query["prompt"], ["consent"])
        self.assertIn("state", query)

    @patch("apps.connectors.api_views.AccountRepository.get_profile")
    def test_authorize_rejects_member(self, get_profile):
        get_profile.return_value = member_profile()

        response = self.client.get(
            "/api/connectors/google-drive/authorize/",
            headers=auth_header("UA002"),
        )

        self.assertEqual(response.status_code, 403)

    @patch("apps.connectors.api_views.ConnectorRepository.connect_oauth")
    @patch("apps.connectors.api_views.GoogleDriveOAuth.exchange_code")
    def test_callback_stores_encrypted_credential_then_redirects_without_secret(self, exchange_code, connect_oauth):
        exchange_code.return_value = {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "expires_at": "2026-08-01T00:00:00+00:00",
        }
        state = issue_state(account_id="UA001", connector_type=GOOGLE_DRIVE)

        response = self.client.get(
            "/api/connectors/google-drive/callback/",
            {"code": "authorization-code", "state": state},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            "http://localhost:5173/onboarding/connectors?connector=google-drive&status=ok",
        )
        self.assertNotIn("authorization-code", response["Location"])
        self.assertNotIn("access-token", response["Location"])
        self.assertEqual(connect_oauth.call_args.kwargs["account_id"], "UA001")
        self.assertEqual(connect_oauth.call_args.kwargs["connector_type"], GOOGLE_DRIVE)
        self.assertEqual(
            decrypt_credential(connect_oauth.call_args.kwargs["encrypted_credential"])["refresh_token"],
            "refresh-token",
        )

    @patch("apps.connectors.api_views.ConnectorRepository.connect_oauth")
    def test_callback_denial_has_only_fixed_error_redirect(self, connect_oauth):
        state = issue_state(account_id="UA001", connector_type=GOOGLE_DRIVE)

        response = self.client.get(
            "/api/connectors/google-drive/callback/",
            {"error": "access_denied", "state": state, "error_description": "secret-like-detail"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            "http://localhost:5173/onboarding/connectors?connector=google-drive&status=error",
        )
        self.assertNotIn("secret-like-detail", response["Location"])
        connect_oauth.assert_not_called()

    @override_settings(GOOGLE_DRIVE_CLIENT_ID="", GOOGLE_DRIVE_CLIENT_SECRET="")
    @patch("apps.connectors.api_views.AccountRepository.get_profile")
    def test_authorize_reports_unavailable_when_credentials_are_missing(self, get_profile):
        get_profile.return_value = leader_profile()

        response = self.client.get(
            "/api/connectors/google-drive/authorize/",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 503)


class OAuthCredentialCryptoTests(SimpleTestCase):
    def test_credential_round_trip_is_encrypted(self):
        payload = {"access_token": "a" * 120, "refresh_token": "r" * 60, "expires_at": "2026-08-01T00:00:00+00:00"}

        ciphertext = encrypt_credential(payload)

        self.assertNotIn(payload["access_token"], ciphertext)
        self.assertEqual(decrypt_credential(ciphertext), payload)


@override_settings(
    JIRA_CLIENT_ID="jira-client-id",
    JIRA_CLIENT_SECRET="jira-client-secret",
    JIRA_REDIRECT_URI="http://localhost:8000/api/connectors/jira/callback/",
)
class JiraOAuthApiTests(SimpleTestCase):
    @patch("apps.connectors.api_views.AccountRepository.get_profile")
    def test_authorize_returns_atlassian_url_with_resource_api_audience(self, get_profile):
        get_profile.return_value = leader_profile()

        response = self.client.get("/api/connectors/jira/authorize/", headers=auth_header())

        self.assertEqual(response.status_code, 200)
        query = parse_qs(urlparse(response.json()["authorization_url"]).query)
        self.assertEqual(query["audience"], ["api.atlassian.com"])
        self.assertEqual(query["client_id"], ["jira-client-id"])
        self.assertEqual(query["redirect_uri"], ["http://localhost:8000/api/connectors/jira/callback/"])
        self.assertEqual(query["scope"], ["read:jira-work read:jira-user offline_access"])
        self.assertIn("state", query)

    @patch("apps.connectors.api_views.ConnectorRepository.connect_oauth")
    @patch("apps.connectors.api_views.JiraOAuth.exchange_code")
    def test_callback_stores_cloud_id_and_redirects_without_credentials(self, exchange_code, connect_oauth):
        exchange_code.return_value = {
            "access_token": "jira-access-token",
            "refresh_token": "jira-refresh-token",
            "expires_at": "2026-08-01T00:00:00+00:00",
            "cloud_id": "cloud-123",
        }
        state = issue_state(account_id="UA001", connector_type=JIRA)

        response = self.client.get(
            "/api/connectors/jira/callback/",
            {"code": "jira-authorization-code", "state": state},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            "http://localhost:5173/onboarding/connectors?connector=jira&status=ok",
        )
        stored = decrypt_credential(connect_oauth.call_args.kwargs["encrypted_credential"])
        self.assertEqual(connect_oauth.call_args.kwargs["connector_type"], JIRA)
        self.assertEqual(stored["cloud_id"], "cloud-123")
        self.assertNotIn("jira-access-token", response["Location"])

    @patch("apps.connectors.api_views.ConnectorRepository.connect_oauth")
    def test_callback_denial_uses_fixed_error_redirect(self, connect_oauth):
        state = issue_state(account_id="UA001", connector_type=JIRA)

        response = self.client.get(
            "/api/connectors/jira/callback/",
            {"error": "access_denied", "state": state},
        )

        self.assertEqual(
            response["Location"],
            "http://localhost:5173/onboarding/connectors?connector=jira&status=error",
        )
        connect_oauth.assert_not_called()

    @patch("apps.connectors.api_views.ConnectorRepository.people_db_summary")
    @patch("apps.connectors.api_views.ConnectorRepository.list_for_account")
    def test_connected_account_sees_summary(self, list_for_account, summary):
        list_for_account.return_value = [people_db_connection()]
        summary.return_value = people_db_summary()

        response = self.client.get("/api/connectors/people-db/summary/", headers=auth_header())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["org_count"], 9)

    @patch("apps.connectors.api_views.ConnectorRepository.people_db_summary")
    @patch("apps.connectors.api_views.ConnectorRepository.list_for_account")
    def test_expired_connection_is_not_treated_as_connected(self, list_for_account, summary):
        expired = people_db_connection() | {"auth_status": "EXPIRED"}
        list_for_account.return_value = [expired]

        response = self.client.get("/api/connectors/people-db/summary/", headers=auth_header())

        self.assertEqual(response.status_code, 404)
        summary.assert_not_called()


@override_settings(
    GOOGLE_DRIVE_CLIENT_ID="google-client-id",
    GOOGLE_DRIVE_CLIENT_SECRET="google-client-secret",
    JIRA_CLIENT_ID="jira-client-id",
    JIRA_CLIENT_SECRET="jira-client-secret",
)
@patch("apps.connectors.clients.ConnectorRepository.update_credential")
@patch("apps.connectors.clients.ConnectorRepository.mark_expired")
@patch("apps.connectors.clients.ConnectorRepository.get_credential")
class CredentialRefreshTests(SimpleTestCase):
    """만료된 액세스 토큰은 조회 직전에 갱신되고 저장까지 마쳐야 한다."""

    @patch("apps.connectors.clients.requests.get")
    def test_valid_credential_is_used_without_refreshing(self, drive_get, get_credential, mark_expired, update):
        get_credential.return_value = stored_credential()
        drive_get.return_value = json_response({"files": []})

        response = self.client.get("/api/connectors/google-drive/folders/", headers=auth_header())

        self.assertEqual(response.status_code, 200)
        update.assert_not_called()
        mark_expired.assert_not_called()
        self.assertEqual(
            drive_get.call_args.kwargs["headers"]["Authorization"],
            "Bearer stored-access-token",
        )

    @patch("apps.connectors.clients.requests.get")
    @patch("apps.connectors.oauth.requests.post")
    def test_expired_credential_is_refreshed_and_saved(self, token_post, drive_get, get_credential, _expire, update):
        get_credential.return_value = stored_credential(expired=True)
        token_post.return_value = json_response({"access_token": "fresh-access-token", "expires_in": 3599})
        drive_get.return_value = json_response({"files": []})

        response = self.client.get("/api/connectors/google-drive/folders/", headers=auth_header())

        self.assertEqual(response.status_code, 200)
        # 갱신된 토큰으로 호출해야 하고, 다음 요청을 위해 저장돼 있어야 한다.
        self.assertEqual(
            drive_get.call_args.kwargs["headers"]["Authorization"],
            "Bearer fresh-access-token",
        )
        saved = decrypt_credential(update.call_args.kwargs["encrypted_credential"])
        self.assertEqual(saved["access_token"], "fresh-access-token")
        # Google은 갱신 응답에 refresh_token을 주지 않으므로 기존 값을 지켜야 한다.
        self.assertEqual(saved["refresh_token"], "stored-refresh-token")

    @patch("apps.connectors.oauth.requests.post")
    def test_failed_refresh_marks_expired_so_the_screen_can_reconnect(
        self, token_post, get_credential, mark_expired, update
    ):
        get_credential.return_value = stored_credential(expired=True)
        token_post.return_value = Mock(raise_for_status=Mock(side_effect=OAuthError("revoked")))

        response = self.client.get("/api/connectors/google-drive/folders/", headers=auth_header())

        self.assertEqual(response.status_code, 502)
        mark_expired.assert_called_once_with(account_id="UA001", connector_type=GOOGLE_DRIVE)
        update.assert_not_called()

    @patch("apps.connectors.clients.requests.get")
    @patch("apps.connectors.oauth.requests.post")
    def test_jira_refresh_replaces_the_rotated_refresh_token(
        self, token_post, jira_get, get_credential, _expire, update
    ):
        get_credential.return_value = stored_credential(expired=True, cloud_id="cloud-123")
        token_post.return_value = json_response(
            {"access_token": "fresh-jira-token", "refresh_token": "rotated-refresh-token", "expires_in": 3600}
        )
        jira_get.return_value = json_response({"values": []})

        response = self.client.get("/api/connectors/jira/projects/", headers=auth_header())

        self.assertEqual(response.status_code, 200)
        saved = decrypt_credential(update.call_args.kwargs["encrypted_credential"])
        self.assertEqual(saved["refresh_token"], "rotated-refresh-token")
        self.assertEqual(saved["cloud_id"], "cloud-123")


@patch("apps.connectors.clients.ConnectorRepository.get_credential")
class GoogleDriveFolderListApiTests(SimpleTestCase):
    def folder_page(self, *names, next_page_token=None):
        payload = {
            "files": [
                {"id": f"folder-{name}", "name": name, "modifiedTime": "2026-07-24T01:39:48.554Z"}
                for name in names
            ]
        }
        if next_page_token:
            payload["nextPageToken"] = next_page_token
        return json_response(payload)

    def test_requires_login(self, _get_credential):
        self.assertEqual(self.client.get("/api/connectors/google-drive/folders/").status_code, 401)

    @patch("apps.connectors.clients.requests.get")
    def test_defaults_to_my_drive_root(self, drive_get, get_credential):
        get_credential.return_value = stored_credential()
        drive_get.return_value = self.folder_page("SKN29")

        response = self.client.get("/api/connectors/google-drive/folders/", headers=auth_header())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [
                {
                    "folder_id": "folder-SKN29",
                    "name": "SKN29",
                    "modified_at": "2026-07-24T01:39:48.554Z",
                }
            ],
        )
        self.assertIn("'root' in parents", drive_get.call_args.kwargs["params"]["q"])

    @patch("apps.connectors.clients.requests.get")
    def test_descends_into_the_requested_parent_only(self, drive_get, get_credential):
        get_credential.return_value = stored_credential()
        drive_get.return_value = self.folder_page("산출물")

        response = self.client.get(
            "/api/connectors/google-drive/folders/",
            {"parent": "folder-SKN29"},
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("'folder-SKN29' in parents", drive_get.call_args.kwargs["params"]["q"])

    @patch("apps.connectors.clients.requests.get")
    def test_quote_in_parent_is_rejected_before_reaching_drive(self, drive_get, _get_credential):
        response = self.client.get(
            "/api/connectors/google-drive/folders/",
            {"parent": "x' or name != ''"},
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 400)
        drive_get.assert_not_called()

    @patch("apps.connectors.clients.requests.get")
    def test_all_pages_are_collected(self, drive_get, get_credential):
        get_credential.return_value = stored_credential()
        drive_get.side_effect = [
            self.folder_page("first", next_page_token="page-2"),
            self.folder_page("second"),
        ]

        response = self.client.get("/api/connectors/google-drive/folders/", headers=auth_header())

        self.assertEqual([row["name"] for row in response.json()], ["first", "second"])
        self.assertEqual(drive_get.call_args_list[1].kwargs["params"]["pageToken"], "page-2")

    def test_unconnected_account_gets_404(self, get_credential):
        get_credential.side_effect = RecordNotFound("Google Drive가 연결되지 않았습니다.")

        response = self.client.get("/api/connectors/google-drive/folders/", headers=auth_header())

        self.assertEqual(response.status_code, 404)

    @patch("apps.connectors.clients.requests.get")
    def test_ids_mode_resolves_names_one_by_one(self, drive_get, get_credential):
        get_credential.return_value = stored_credential()
        drive_get.side_effect = [
            json_response({"id": "folder-a", "name": "SKN29", "modifiedTime": "2026-07-24T01:39:48.554Z"}),
            json_response({"id": "folder-b", "name": "산출물", "modifiedTime": "2026-07-24T05:17:26.294Z"}),
        ]

        response = self.client.get(
            "/api/connectors/google-drive/folders/",
            {"ids": "folder-a,folder-b"},
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["name"] for row in response.json()], ["SKN29", "산출물"])
        # 검색이 아니라 개별 조회다 — Drive 검색식은 id 비교를 지원하지 않는다.
        self.assertTrue(drive_get.call_args_list[0].args[0].endswith("/folder-a"))

    @patch("apps.connectors.clients.requests.get")
    def test_ids_mode_drops_folders_that_are_gone(self, drive_get, get_credential):
        get_credential.return_value = stored_credential()
        drive_get.side_effect = [
            Mock(status_code=404, raise_for_status=Mock()),
            json_response({"id": "folder-b", "name": "산출물", "modifiedTime": None}),
        ]

        response = self.client.get(
            "/api/connectors/google-drive/folders/",
            {"ids": "deleted-folder,folder-b"},
            headers=auth_header(),
        )

        self.assertEqual([row["folder_id"] for row in response.json()], ["folder-b"])


@patch("apps.connectors.clients.ConnectorRepository.get_credential")
class GoogleDriveFileListApiTests(SimpleTestCase):
    def test_requires_login(self, _get_credential):
        self.assertEqual(self.client.get("/api/connectors/google-drive/files/").status_code, 401)

    @patch("apps.connectors.clients.requests.get")
    def test_parent_is_required(self, drive_get, _get_credential):
        response = self.client.get("/api/connectors/google-drive/files/", headers=auth_header())

        self.assertEqual(response.status_code, 400)
        drive_get.assert_not_called()

    @patch("apps.connectors.clients.requests.get")
    def test_folders_are_excluded_and_formats_are_flagged(self, drive_get, get_credential):
        get_credential.return_value = stored_credential()
        drive_get.return_value = json_response(
            {
                "files": [
                    {
                        "id": "file-plan",
                        "name": "[기획] 프로젝트 기획서_2Team.docx",
                        "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        "modifiedTime": "2026-07-24T05:20:18.540Z",
                    },
                    {
                        "id": "file-zip",
                        "name": "Apart Deal.zip",
                        "mimeType": "application/x-zip-compressed",
                        "modifiedTime": "2026-04-29T06:13:45.050Z",
                    },
                ]
            }
        )

        response = self.client.get(
            "/api/connectors/google-drive/files/",
            {"parent": "folder-산출물"},
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {row["file_id"]: row["supported"] for row in response.json()},
            {"file-plan": True, "file-zip": False},
        )
        query = drive_get.call_args.kwargs["params"]["q"]
        self.assertIn("'folder-산출물' in parents", query)
        self.assertIn("mimeType != 'application/vnd.google-apps.folder'", query)

    @patch("apps.connectors.clients.requests.get")
    def test_default_depth_does_not_descend(self, drive_get, get_credential):
        get_credential.return_value = stored_credential()
        drive_get.return_value = json_response({"files": []})

        self.client.get(
            "/api/connectors/google-drive/files/",
            {"parent": "folder-SKN29"},
            headers=auth_header(),
        )

        # 파일 조회 한 번뿐 — 하위 폴더를 찾는 두 번째 호출이 없어야 한다.
        self.assertEqual(drive_get.call_count, 1)

    @patch("apps.connectors.clients.requests.get")
    def test_depth_two_collects_files_from_child_folders(self, drive_get, get_credential):
        get_credential.return_value = stored_credential()
        drive_get.side_effect = [
            # SKN29의 파일
            json_response({"files": [{"id": "file-top", "name": "top.pdf", "mimeType": "application/pdf"}]}),
            # SKN29의 하위 폴더
            json_response({"files": [{"id": "folder-산출물", "name": "산출물"}]}),
            # 산출물의 파일
            json_response({"files": [{"id": "file-plan", "name": "기획서.docx", "mimeType": "application/pdf"}]}),
            # 산출물의 하위 폴더 — depth 2에서 멈추므로 호출되지 않는다
        ]

        response = self.client.get(
            "/api/connectors/google-drive/files/",
            {"parent": "folder-SKN29", "depth": "2"},
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [(row["file_id"], row["folder_path"]) for row in response.json()],
            [("file-top", ""), ("file-plan", "산출물")],
        )
        self.assertEqual(drive_get.call_count, 3)

    @patch("apps.connectors.clients.requests.get")
    def test_unlimited_depth_keeps_descending(self, drive_get, get_credential):
        get_credential.return_value = stored_credential()
        drive_get.side_effect = [
            json_response({"files": []}),
            json_response({"files": [{"id": "folder-a", "name": "a"}]}),
            json_response({"files": [{"id": "file-deep", "name": "deep.pdf", "mimeType": "application/pdf"}]}),
            json_response({"files": [{"id": "folder-b", "name": "b"}]}),
            json_response({"files": []}),
            json_response({"files": []}),
        ]

        response = self.client.get(
            "/api/connectors/google-drive/files/",
            {"parent": "folder-root", "depth": "unlimited"},
            headers=auth_header(),
        )

        self.assertEqual([row["folder_path"] for row in response.json()], ["a"])
        self.assertEqual(drive_get.call_count, 6)

    @patch("apps.connectors.clients.requests.get")
    def test_absurd_depth_is_rejected(self, drive_get, _get_credential):
        for value in ("999", "0", "deep"):
            response = self.client.get(
                "/api/connectors/google-drive/files/",
                {"parent": "folder-SKN29", "depth": value},
                headers=auth_header(),
            )
            self.assertEqual(response.status_code, 400, value)
        drive_get.assert_not_called()


@patch("apps.connectors.clients.ConnectorRepository.get_credential")
class JiraProjectListApiTests(SimpleTestCase):
    def test_requires_login(self, _get_credential):
        self.assertEqual(self.client.get("/api/connectors/jira/projects/").status_code, 401)

    @patch("apps.connectors.clients.requests.get")
    def test_lists_projects_from_the_connected_site(self, jira_get, get_credential):
        get_credential.return_value = stored_credential(cloud_id="cloud-123")
        jira_get.return_value = json_response(
            {
                "values": [
                    {
                        "key": "KAN",
                        "id": "10001",
                        "name": "SKN29_Final_2Team",
                        "projectTypeKey": "software",
                        "lead": {"displayName": "임준"},
                        "avatarUrls": {"48x48": "https://example.invalid/avatar"},
                    }
                ]
            }
        )

        response = self.client.get("/api/connectors/jira/projects/", headers=auth_header())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [
                {
                    "project_key": "KAN",
                    "project_id": "10001",
                    "name": "SKN29_Final_2Team",
                    "description": None,
                    "project_type": "software",
                    "lead_name": "임준",
                    "avatar_url": "https://example.invalid/avatar",
                }
            ],
        )
        self.assertIn("cloud-123", jira_get.call_args.args[0])
        # description·lead는 expand 없이는 응답에 담기지 않는다.
        self.assertEqual(jira_get.call_args.kwargs["params"]["expand"], "description,lead")

    @patch("apps.connectors.clients.requests.get")
    def test_missing_cloud_id_asks_for_reconnection(self, jira_get, get_credential):
        get_credential.return_value = stored_credential()

        response = self.client.get("/api/connectors/jira/projects/", headers=auth_header())

        self.assertEqual(response.status_code, 502)
        jira_get.assert_not_called()
