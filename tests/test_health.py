from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient


class HealthApiTests(TestCase):
    def test_health_endpoint_returns_ok(self):
        response = self.client.get("/api/health/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")


class ProjectApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="pm", password="test-password")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_project_and_analysis_run_can_be_created(self):
        project_response = self.client.post(
            "/api/projects/",
            {"name": "AI 코파일럿 시연", "code": "DEMO-001", "description": "종단 시연", "status": "DRAFT"},
            format="json",
        )

        self.assertEqual(project_response.status_code, 201)
        project_id = project_response.json()["project_id"]

        run_response = self.client.post(f"/api/projects/{project_id}/analysis-runs/", format="json")

        self.assertEqual(run_response.status_code, 201)
        self.assertEqual(run_response.json()["status"], "CREATED")
        self.assertEqual(run_response.json()["readiness_status"], "PENDING")
