"""에이전트 API 단위 테스트.

2026-08-22에 레거시 비버전 스키마(`agent`/`agent_tool`)의 CRUD를 지우면서
그 엔드포인트를 겨냥하던 `AgentApiTests`도 같이 없앴다. 남은 것은 어느
스키마든 공유하는 카탈로그(도구·커스텀 모델)와, 옮겨 간 메인 모델 API가
여기 없다는 것을 지키는 테스트다.
"""

from unittest.mock import patch

import psycopg
from django.test import SimpleTestCase

from apps.accounts.tokens import issue_token
from apps.agents.serializers import builtin_tool_response

def auth_header(account_id="UA001"):
    return {"authorization": f"Bearer {issue_token(account_id)}"}


class ToolCatalogTests(SimpleTestCase):
    def test_내장_도구는_Registry_가_정본이다(self):
        """화면이 목록을 따로 적어 두면 Registry 가 바뀔 때 어긋난다.

        `ALWAYS_ON_TOOL_REFS`(예: `skill_register`, 2026-08-22)만 예외다 —
        고르고 말고가 없는 도구라 화면 목록에서 뺀다(`builtin_tool_response()`
        docstring 참고)."""

        from services.harness.registry import ALWAYS_ON_TOOL_REFS, BUILTIN_TOOLS

        rows = builtin_tool_response()

        self.assertEqual({row["tool_ref"] for row in rows}, set(BUILTIN_TOOLS) - ALWAYS_ON_TOOL_REFS)

    def test_고르고_말고가_없는_도구는_목록에서_빠진다(self):
        rows = builtin_tool_response()
        self.assertNotIn("skill_register", {row["tool_ref"] for row in rows})

    def test_승인_필요_여부를_화면에_알려준다(self):
        by_ref = {row["tool_ref"]: row for row in builtin_tool_response()}

        self.assertTrue(by_ref["jira_create_issues"]["side_effect"])
        self.assertFalse(by_ref["document_search"]["side_effect"])

    def test_기본값_초기화_집합을_화면에_알려준다(self):
        """채팅 「+」의 「기본값으로 초기화」가 되돌릴 고정 집합(`is_default`)."""

        by_ref = {row["tool_ref"]: row for row in builtin_tool_response()}

        self.assertTrue(by_ref["table_export"]["is_default"])
        self.assertFalse(by_ref["diagram_create"]["is_default"])
        self.assertFalse(by_ref["file_inspect"]["is_default"])
        self.assertFalse(by_ref["document_sync"]["is_default"])

    def test_P0_기존도구를_최종_카테고리와_서비스로_표시한다(self):
        by_ref = {row["tool_ref"]: row for row in builtin_tool_response()}

        self.assertEqual(
            {row["category"] for row in by_ref.values()},
            {"검색", "문서", "업무", "팀", "데이터", "계산", "시각화"},
        )
        self.assertEqual(by_ref["jira_create_issues"]["provider"], "Jira")
        self.assertEqual(by_ref["jira_create_issues"]["capability"], "등록")
        self.assertTrue(by_ref["jira_create_issues"]["requires_connection"])
        self.assertEqual(by_ref["document_create"]["name"], "Word 만들기")
        self.assertEqual(by_ref["table_export"]["name"], "Excel 만들기")
        self.assertEqual(by_ref["data_quality_check"]["category"], "데이터")
        self.assertEqual(by_ref["calculate"]["capability"], "계산")


class MainModelGoneTests(SimpleTestCase):
    """메인 모델 API 는 **팀 쪽에 없다**(2026-08-18 멘토링).

    기본 채팅 모델은 운영자가 팀별로 정한다(`/api/ops/models/teams/<id>/default/` ·
    `tests/test_ops.py::OpsTeamDefaultModelTests`). 화면에서만 감추면 API 가 그대로
    열려 있으므로, **경로가 사라졌다는 것 자체를 여기서 지킨다** — 8/13 에 모델
    등록을 옮길 때와 같은 방식이다.

    2026-08-22 갱신: 레거시 `agent` 스키마를 폐기하면서 `agents/<agent_id>/`
    라우트가 없어졌다. 그전에는 이 주소가 거기 잡혀서(`agent_id="main-model"`)
    상태 코드가 「경로가 없다」의 증거가 못 됐는데, 이제는 정말로 아무 데도
    안 잡힌다 — 그래서 해석 자체가 실패하는 것을 본다.
    """

    def test_경로가_어디에도_안_잡힌다(self):
        from django.urls import Resolver404, resolve

        with self.assertRaises(Resolver404):
            resolve("/api/agents/main-model/")

    def test_모델을_바꿀_수_없다(self):
        """폼만 없애면 API 를 그대로 부를 수 있다 — 그건 규칙이 아니라 장식이다."""

        response = self.client.put(
            "/api/agents/main-model/",
            {"model": "gpt-5.6-sol"},
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 404)


@patch("apps.agents.api_views.CustomModelRepository")
class CustomModelApiTests(SimpleTestCase):
    """이 팀에 등록된 모델 API — **읽기 전용이다.**

    등록하고 지우는 것은 운영자 콘솔이 한다(2026-08-13 멘토링). 화면에서만 감추면
    규칙이 아니라서, **쓰기 메서드가 API 에 남아 있지 않은지**를 여기서 지킨다.
    """

    def test_목록을_준다(self, customs):
        customs.list_for_account.return_value = [
            {"conn_id": "CN002", "label": "Google Gemini", "base_url": "https://x/v1",
             "model": "models/gemini-3.6-flash", "connected_at": None}
        ]

        response = self.client.get("/api/agents/custom-models/", headers=auth_header())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["model"], "models/gemini-3.6-flash")

    def test_팀은_등록하거나_지울_수_없다(self, customs):
        """셀프서비스 경로를 없앤 것이 UI 뿐이면 API 를 그대로 부를 수 있다."""

        post = self.client.post(
            "/api/agents/custom-models/", {}, content_type="application/json", headers=auth_header()
        )
        delete = self.client.delete("/api/agents/custom-models/", headers=auth_header())

        self.assertEqual(post.status_code, 405)
        self.assertEqual(delete.status_code, 405)
        customs.add.assert_not_called()

    def test_로그인_없이는_401(self, _customs):
        self.assertEqual(self.client.get("/api/agents/custom-models/").status_code, 401)
