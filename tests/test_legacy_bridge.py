"""legacy_bridge.py(draft_from_legacy_agent) 단위 테스트.

`AgentRepository`(레거시)만 mock한다 — DB는 안 띄운다. 새 스키마
(`agents`/`agent_versions`)는 이 파일이 아예 건드리지 않으므로 나올 일이 없다.
"""

from unittest.mock import patch

from django.test import SimpleTestCase

from services.agent_runtime.exceptions import AgentDefinitionNotFound
from services.agent_runtime.legacy_bridge import draft_from_legacy_agent

BRIDGE_MODULE = "services.agent_runtime.legacy_bridge"


def _agent_row(**overrides) -> dict:
    row = {
        "agent_id": "AG001",
        "team_id": "TM001",
        "name": "레거시 에이전트",
        "description": "설명",
        "instruction": "너는 우리 팀 업무를 돕는 에이전트다.",
        "model": "claude-sonnet-5",
        "reasoning_effort": "low",
        "max_iterations": 10,
        "is_prebuilt": False,
        "status": "ACTIVE",
    }
    row.update(overrides)
    return row


class DraftFromLegacyAgentTests(SimpleTestCase):
    @patch(f"{BRIDGE_MODULE}.AgentRepository.tool_refs", return_value=["document_search", "web_search"])
    @patch(f"{BRIDGE_MODULE}.AgentRepository.get")
    def test_instruction_becomes_system_prompt(self, mock_get, _mock_tool_refs):
        mock_get.return_value = _agent_row(instruction="너는 친절한 비서다.")

        draft = draft_from_legacy_agent(agent_id="AG001", team_id="TM001")

        self.assertEqual(draft["system_prompt"], "너는 친절한 비서다.")
        self.assertNotIn("instruction", draft)

    @patch(f"{BRIDGE_MODULE}.AgentRepository.tool_refs", return_value=["document_search"])
    @patch(f"{BRIDGE_MODULE}.AgentRepository.get")
    def test_tool_refs_come_from_agent_tool_table(self, mock_get, mock_tool_refs):
        mock_get.return_value = _agent_row()

        draft = draft_from_legacy_agent(agent_id="AG001", team_id="TM001")

        mock_tool_refs.assert_called_once_with("AG001")
        self.assertEqual(draft["tool_refs"], ("document_search",))

    @patch(f"{BRIDGE_MODULE}.AgentRepository.tool_refs", return_value=[])
    @patch(f"{BRIDGE_MODULE}.AgentRepository.get")
    def test_agent_id_is_carried_in_the_draft(self, mock_get, _mock_tool_refs):
        """agent_run.agent_id(NOT NULL)를 채우려면 draft가 실제 agent_id를
        실어 보내야 한다 — loader.py의 from_draft()가 그대로 통과시킨다."""
        mock_get.return_value = _agent_row(agent_id="AG042")

        draft = draft_from_legacy_agent(agent_id="AG042", team_id="TM001")

        self.assertEqual(draft["agent_id"], "AG042")

    @patch(f"{BRIDGE_MODULE}.AgentRepository.tool_refs", return_value=[])
    @patch(f"{BRIDGE_MODULE}.AgentRepository.get")
    def test_null_model_and_effort_fall_back_to_legacy_harness_defaults(self, mock_get, _mock_tool_refs):
        mock_get.return_value = _agent_row(model=None, reasoning_effort=None)

        draft = draft_from_legacy_agent(agent_id="AG001", team_id="TM001")

        self.assertEqual(draft["model"], "gpt-5.6-luna")
        self.assertEqual(draft["reasoning_effort"], "low")

    @patch(f"{BRIDGE_MODULE}.AgentRepository.tool_refs", return_value=[])
    @patch(f"{BRIDGE_MODULE}.AgentRepository.get")
    def test_set_model_and_effort_are_preserved_not_overridden(self, mock_get, _mock_tool_refs):
        mock_get.return_value = _agent_row(model="gpt-4o", reasoning_effort="high")

        draft = draft_from_legacy_agent(agent_id="AG001", team_id="TM001")

        self.assertEqual(draft["model"], "gpt-4o")
        self.assertEqual(draft["reasoning_effort"], "high")

    @patch(f"{BRIDGE_MODULE}.AgentRepository.tool_refs", return_value=[])
    @patch(f"{BRIDGE_MODULE}.AgentRepository.get")
    def test_max_iterations_passes_through_unchanged(self, mock_get, _mock_tool_refs):
        """레거시 max_iterations 기본값(10)은 새 스키마 기본값(6)과 다르다 —
        여기서 바꿔치기하지 않는다."""
        mock_get.return_value = _agent_row(max_iterations=10)

        draft = draft_from_legacy_agent(agent_id="AG001", team_id="TM001")

        self.assertEqual(draft["max_iterations"], 10)

    @patch(f"{BRIDGE_MODULE}.AgentRepository.tool_refs", return_value=[])
    @patch(f"{BRIDGE_MODULE}.AgentRepository.get")
    def test_subagents_always_empty(self, mock_get, _mock_tool_refs):
        """레거시 A2A(agent: tool_ref)는 새 엔진 subagents 구조와 다른
        메커니즘이라 여기서 번역하지 않는다."""
        mock_get.return_value = _agent_row()

        draft = draft_from_legacy_agent(agent_id="AG001", team_id="TM001")

        self.assertEqual(draft["subagents"], [])

    @patch(f"{BRIDGE_MODULE}.AgentRepository.get")
    def test_different_team_is_treated_as_not_found(self, mock_get):
        """다른 팀 소속이면 존재 자체를 노출하지 않는다 — 403이 아니라 404."""
        mock_get.return_value = _agent_row(team_id="TM999")

        with self.assertRaises(AgentDefinitionNotFound):
            draft_from_legacy_agent(agent_id="AG001", team_id="TM001")

    @patch(f"{BRIDGE_MODULE}.AgentRepository.get")
    def test_missing_agent_raises_agent_definition_not_found(self, mock_get):
        from backend.db.errors import RecordNotFound

        mock_get.side_effect = RecordNotFound("존재하지 않는 에이전트입니다: AG999")

        with self.assertRaises(AgentDefinitionNotFound):
            draft_from_legacy_agent(agent_id="AG999", team_id="TM001")
