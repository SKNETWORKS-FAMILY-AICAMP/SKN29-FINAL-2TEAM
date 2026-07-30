from unittest.mock import patch

from django.test import SimpleTestCase

from apps.accounts.tokens import issue_token
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
