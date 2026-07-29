from unittest.mock import patch

from django.test import SimpleTestCase


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
    @patch("apps.projects.api_views.ProjectRepository.list_all")
    def test_project_list_uses_direct_repository(self, list_all):
        list_all.return_value = [
            {
                "proj_id": "PJ001",
                "name": "AI 코파일럿 시연",
                "status": "DRAFT",
                "tz": "Asia/Seoul",
                "owner_account_id": None,
                "owner_name": None,
            }
        ]

        response = self.client.get("/api/projects/")

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
            "owner_account_id": None,
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
        )

        self.assertEqual(response.status_code, 201)
        create.assert_called_once_with(
            name="AI 코파일럿 시연",
            status="DRAFT",
            tz="Asia/Seoul",
            owner_account_id=None,
        )
