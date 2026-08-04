from unittest.mock import patch

from django.test import SimpleTestCase

from apps.accounts.tokens import issue_token


def auth_header(account_id="UA001"):
    return {"authorization": f"Bearer {issue_token(account_id)}"}


class HealthApiTests(SimpleTestCase):
    @patch(
        "apps.projects.api_views.database_status",
        return_value={"status": "ok", "people": "ready", "vector": "ready"},
    )
    def test_health_endpoint_returns_ok(self, _database_status):
        response = self.client.get("/api/health/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["database"]["status"], "ok")


class ProjectApiTests(SimpleTestCase):
    @patch("apps.projects.api_views.ProjectRepository.list_for_team")
    def test_project_list_uses_direct_repository(self, list_for_team):
        list_for_team.return_value = [
            {
                "proj_id": "PJ001",
                "name": "AI 코파일럿 시연",
                "status": "DRAFT",
                "tz": "Asia/Seoul",
                "owner_account_id": "UA001",
                "owner_name": None,
            }
        ]

        response = self.client.get("/api/projects/", headers=auth_header())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["proj_id"], "PJ001")
        self.assertEqual(response.json()[0]["project_id"], "PJ001")

    @patch("apps.projects.api_views.ProjectRepository.create")
    def test_project_create_uses_current_sql_fields(self, create):
        create.return_value = {
            "proj_id": "PJ001",
            "name": "AI 코파일럿 시연",
            "status": "DRAFT",
            "tz": "Asia/Seoul",
            "owner_account_id": "UA001",
            "owner_name": None,
        }

        response = self.client.post(
            "/api/projects/",
            {
                "name": "AI 코파일럿 시연",
                "status": "DRAFT",
                "tz": "Asia/Seoul",
            },
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 201)
        create.assert_called_once_with(
            name="AI 코파일럿 시연",
            status="DRAFT",
            tz="Asia/Seoul",
            owner_account_id="UA001",
        )
