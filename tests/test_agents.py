"""Agent CRUD API 단위 테스트 (개발지시_3차 단계 2).

지키는 것 셋 — 팀 경계, **기본 제공 에이전트 보호**, 실존하지 않는 도구 거부.
"""

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.accounts.tokens import issue_token
from apps.agents.serializers import builtin_tool_response
from backend.db.errors import PermissionDenied, ReferenceNotFound

AGENT = {
    "agent_id": "AG002",
    "name": "회의록 정리",
    "description": "",
    "instruction": "결정사항만 뽑는다",
    "model": "gpt-5.6-luna",
    "reasoning_effort": "low",
    "max_iterations": 6,
    "is_prebuilt": False,
    "owner_name": "임준",
    "updated_at": None,
    "tool_refs": ["document_search"],
}


def auth_header(account_id="UA001"):
    return {"authorization": f"Bearer {issue_token(account_id)}"}


class ToolCatalogTests(SimpleTestCase):
    def test_내장_도구는_Registry_가_정본이다(self):
        """화면이 목록을 따로 적어 두면 Registry 가 바뀔 때 어긋난다."""

        from services.harness.registry import BUILTIN_TOOLS

        rows = builtin_tool_response()

        self.assertEqual({row["tool_ref"] for row in rows}, set(BUILTIN_TOOLS))

    def test_승인_필요_여부를_화면에_알려준다(self):
        by_ref = {row["tool_ref"]: row for row in builtin_tool_response()}

        self.assertTrue(by_ref["jira_create_issues"]["side_effect"])
        self.assertFalse(by_ref["document_search"]["side_effect"])


@patch("apps.agents.api_views.AgentCrudRepository")
class AgentApiTests(SimpleTestCase):
    def test_목록을_준다(self, repo):
        repo.list_for_team.return_value = [AGENT]

        response = self.client.get("/api/agents/", headers=auth_header())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["tool_refs"], ["document_search"])

    def test_만든다(self, repo):
        repo.create.return_value = AGENT

        response = self.client.post(
            "/api/agents/",
            {"name": "회의록 정리", "instruction": "결정사항만", "tool_refs": ["document_search"]},
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(repo.create.call_args.kwargs["tool_refs"], ["document_search"])

    def test_is_prebuilt_는_받지_않는다(self, repo):
        """화면에서 켤 수 있으면 「우리가 제공하는 것」 구분이 무의미해진다."""

        repo.create.return_value = AGENT

        self.client.post(
            "/api/agents/",
            {"name": "가짜 기본", "is_prebuilt": True, "tool_refs": []},
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertNotIn("is_prebuilt", repo.create.call_args.kwargs["fields"])

    def test_기본_제공_에이전트_수정은_403(self, repo):
        repo.update.side_effect = PermissionDenied("기본 제공 에이전트는 수정하거나 지울 수 없습니다.")

        response = self.client.put(
            "/api/agents/AG001/",
            {"name": "바꿔치기", "tool_refs": []},
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 403)

    def test_기본_제공_에이전트_삭제도_403(self, repo):
        repo.delete.side_effect = PermissionDenied("기본 제공 에이전트는 수정하거나 지울 수 없습니다.")

        response = self.client.delete("/api/agents/AG001/", headers=auth_header())

        self.assertEqual(response.status_code, 403)

    def test_없는_도구를_붙이면_409(self, repo):
        """저장되면 사용자는 체크했는데 에이전트는 못 쓰는 상태가 된다."""

        repo.create.side_effect = ReferenceNotFound("등록되지 않은 도구입니다: mcp:MT999")

        response = self.client.post(
            "/api/agents/",
            {"name": "x", "tool_refs": ["mcp:MT999"]},
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 409)

    def test_남의_팀_에이전트는_403(self, repo):
        repo.get.side_effect = PermissionDenied("이 에이전트에 접근할 수 없습니다.")

        response = self.client.get("/api/agents/AG999/", headers=auth_header())

        self.assertEqual(response.status_code, 403)

    def test_모르는_모델은_거절한다(self, _repo):
        response = self.client.post(
            "/api/agents/",
            {"name": "x", "model": "gpt-9", "tool_refs": []},
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 400)

    def test_tools_경로가_agent_id_에_먹히지_않는다(self, repo):
        repo.team_tool_refs.return_value = []

        response = self.client.get("/api/agents/tools/", headers=auth_header())

        self.assertEqual(response.status_code, 200)
        repo.get.assert_not_called()

    def test_로그인_없이는_401(self, _repo):
        self.assertEqual(self.client.get("/api/agents/").status_code, 401)


@patch("apps.agents.api_views.AgentRepository")
class MainModelApiTests(SimpleTestCase):
    """메인 모델 — 오케스트레이션하는 정문 에이전트의 모델.

    예전 Model 탭은 라디오가 아무 데도 저장되지 않았다. 저장되는 척하는 컨트롤을
    없애는 것이 이 API 의 목적이라, **실제로 쓰기가 도는지**를 본다.
    """

    def test_정문이_없으면_null_을_준다(self, repo):
        """임의의 기본값을 저장된 것처럼 보이면 안 된다 — 그게 옛 화면의 문제였다."""

        repo.main_model.return_value = None

        body = self.client.get("/api/agents/main-model/", headers=auth_header()).json()

        self.assertIsNone(body["model"])

    def test_모델을_바꾼다(self, repo):
        repo.set_main_model.return_value = {"agent_id": "AG001", "name": "코파일럿", "model": "gpt-5.6-sol"}

        response = self.client.put(
            "/api/agents/main-model/",
            {"model": "gpt-5.6-sol"},
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(repo.set_main_model.call_args.kwargs["model"], "gpt-5.6-sol")

    def test_고를_수_없는_모델은_거절한다(self, repo):
        """`-pro` 계열은 effort: low 를 안 받아 실행 시점에 400 이 난다 — 저장을 막는다."""

        response = self.client.put(
            "/api/agents/main-model/",
            {"model": "gpt-5.5-pro"},
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 400)
        repo.set_main_model.assert_not_called()

    def test_로그인_없이는_401(self, _repo):
        self.assertEqual(self.client.get("/api/agents/main-model/").status_code, 401)
