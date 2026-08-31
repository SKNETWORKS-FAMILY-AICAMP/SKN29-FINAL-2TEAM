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
    def setUp(self):
        super().setUp()
        # 리포지토리 배선 테스트가 로컬 UA001 시드에 의존하지 않게 한다.
        leader_guard = patch("apps.projects.api_views.require_leader", return_value=None)
        leader_guard.start()
        self.addCleanup(leader_guard.stop)

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
            "description": "문서 후보를 찾는 질의가 되는 문장",
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
        # 같은 dict 리터럴에 `"description": ""` 가 뒤에 또 있어서 늘 빈 문자열로
        # 나가던 것을 막는다(2026-08-12). 증상이 조용하다 — 상세 화면이 아니라
        # 「기준 문서 찾기」 재검색이 이름 하나로만 질의하게 된다.
        self.assertEqual(response.json()["description"], "문서 후보를 찾는 질의가 되는 문장")
        create.assert_called_once_with(
            name="AI 코파일럿 시연",
            # 설명을 안 보내면 None 이다. 빈 문자열로 바꾸지 않는다 —
            # 「안 적었다」와 「비워 뒀다」를 DB 에서 구분할 수 있어야 한다.
            description=None,
            status="DRAFT",
            tz="Asia/Seoul",
            owner_account_id="UA001",
        )
