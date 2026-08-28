"""「업무 추출 에이전트」(prebuilt) 프로비저닝과 `task_extraction` 의 화면 숨김.

`DATABASES = {}` 라 실제 DB 는 안 띄운다(다른 테스트와 같은 제약). 커서를 목으로
바꿔 **어떤 SQL 을 어떤 값으로 쏘는지**를 검증한다. 실제 행 생성은
`DB/migrations/2026-08-30_task_extraction_agent.sql` 적용 후 psql 로 확인한다.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import SimpleTestCase

from backend.db.agent_platform import (
    TASK_EXTRACTION_AGENT_PROMPT,
    TASK_EXTRACTION_AGENT_TOOLS,
    provision_task_extraction_agent,
)


def _short_code_cursor() -> MagicMock:
    """`next_short_code()` 가 부르는 두 번의 fetchone(live_max, purged_max)에
    항상 0 을 주는 커서."""
    cursor = MagicMock()
    cursor.fetchone.return_value = {"coalesce": 0}
    return cursor


class ProvisionTests(SimpleTestCase):
    def test_creates_a_prebuilt_active_agent_named_task_extraction(self):
        cursor = _short_code_cursor()

        agent_id = provision_task_extraction_agent(
            cursor, team_id="TE001", owner_account_id="UA002"
        )
        self.assertTrue(agent_id.startswith("AG"))

        inserts = [
            c.args for c in cursor.execute.call_args_list if "INSERT INTO agents" in c.args[0]
        ]
        self.assertEqual(len(inserts), 1)
        params = inserts[0][1]
        self.assertIn("업무 추출 에이전트", params)
        self.assertIn("TE001", params)
        self.assertIn("UA002", params)
        # is_prebuilt=true, status='ACTIVE', is_default_chat=false 는 SQL 문 리터럴.
        self.assertIn("'ACTIVE', true, false", inserts[0][0])

    def test_version_uses_sol_and_attaches_the_four_tools(self):
        cursor = _short_code_cursor()
        provision_task_extraction_agent(cursor, team_id="TE001", owner_account_id="UA002")

        version_inserts = [
            c.args for c in cursor.execute.call_args_list
            if "INSERT INTO agent_versions" in c.args[0]
        ]
        self.assertEqual(len(version_inserts), 1)
        vparams = version_inserts[0][1]
        self.assertIn("gpt-5.6-sol", vparams)
        self.assertIn(TASK_EXTRACTION_AGENT_PROMPT, vparams)

        tool_inserts = [
            c.args[1][1] for c in cursor.execute.call_args_list
            if "INSERT INTO agent_version_tools" in c.args[0]
        ]
        self.assertEqual(sorted(tool_inserts), sorted(TASK_EXTRACTION_AGENT_TOOLS))
        self.assertIn("task_extraction", tool_inserts)

    def test_points_the_agent_at_the_new_version_last(self):
        cursor = _short_code_cursor()
        provision_task_extraction_agent(cursor, team_id="TE001", owner_account_id="UA002")

        last_sql = cursor.execute.call_args_list[-1].args[0]
        self.assertIn("UPDATE agents SET current_version_id", last_sql)


class HiddenToolTests(SimpleTestCase):
    def test_task_extraction_is_registered_but_agent_only(self):
        from services.harness.registry import AGENT_ONLY_TOOL_REFS, BUILTIN_TOOLS

        self.assertIn("task_extraction", BUILTIN_TOOLS)
        self.assertIn("task_extraction", AGENT_ONLY_TOOL_REFS)

    def test_task_extraction_is_absent_from_the_pick_list_but_present_in_the_validation_catalog(self):
        from apps.agents.serializers import builtin_tool_response

        pick_refs = {row["tool_ref"] for row in builtin_tool_response()}
        self.assertNotIn("task_extraction", pick_refs)

        # 검증 카탈로그(_tool_catalog)는 저장된 참조가 막히지 않게 도로 넣는다.
        from apps.agents.api_views import _tool_catalog
        from unittest.mock import patch

        with patch(
            "apps.agents.api_views.AgentCrudRepository.team_tool_refs", return_value=[]
        ):
            catalog = _tool_catalog("UA002")
        self.assertIn("task_extraction", catalog)

    def test_default_chat_set_excludes_task_extraction(self):
        from services.harness.registry import DEFAULT_CHAT_TOOL_REFS

        self.assertNotIn("task_extraction", DEFAULT_CHAT_TOOL_REFS)
