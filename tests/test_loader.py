"""loader.py(AgentDefinitionLoader) 단위 테스트.

정본: docs/작업기록/Deep_Agents/2026-08-13_02_Deep-Agent_런타임_공통_계약_v1.md §6

DB는 안 띄운다 — `AgentVersionRepository`/`AgentSubagentRepository`를 mock한다
(tests/test_model_factory.py와 같은 패턴). 이 파일이 보는 것은 "Repository가 준 dict를
정확한 타입으로 조립하는가"와 "언제 Repository를 다시 안 부르는가"이지, SQL 자체가
아니다.
"""

from unittest.mock import patch

from django.test import SimpleTestCase

from backend.db.errors import PermissionDenied, RecordNotFound
from services.agent_runtime.context import RuntimeContext
from services.agent_runtime.exceptions import AgentVersionNotFound, DelegationDepthError
from services.agent_runtime.loader import AgentDefinitionLoader

LOADER_MODULE = "services.agent_runtime.loader"


def _context() -> RuntimeContext:
    return RuntimeContext(account_id="AC001", team_id="TM001", role="leader")


def _definition_row(**overrides) -> dict:
    row = {
        "agent_id": "AG001",
        "agent_version_id": "AV001",
        "name": "메인 에이전트",
        "description": "설명",
        "system_prompt": "프롬프트",
        "model": "claude-sonnet-5",
        "reasoning_effort": "low",
        "max_iterations": 6,
        "tool_refs": ["document_search"],
        "agent_status": "ACTIVE",
    }
    row.update(overrides)
    return row


def _child_ref_row(**overrides) -> dict:
    row = {
        "child_agent_id": "AG011",
        "child_version_id": "AV023",
        "alias": "jira_writer",
        "delegation_description": "Jira 이슈를 생성한다.",
        "is_active": True,
        "can_execute": True,
        "has_subagents": False,
    }
    row.update(overrides)
    return row


class LoadTests(SimpleTestCase):
    def setUp(self):
        self.loader = AgentDefinitionLoader()
        self.context = _context()

    @patch(f"{LOADER_MODULE}.AgentSubagentRepository.list_for_parent_version", return_value=[])
    @patch(f"{LOADER_MODULE}.AgentVersionRepository.get_definition")
    def test_builds_definition_with_no_subagents(self, mock_get_definition, _mock_list):
        mock_get_definition.return_value = _definition_row()

        loaded = self.loader.load(agent_id="AG001", agent_version_id="AV001", context=self.context)

        self.assertEqual(loaded.definition.agent_id, "AG001")
        self.assertEqual(loaded.definition.tool_refs, ("document_search",))
        self.assertEqual(loaded.definition.subagents, ())
        self.assertEqual(loaded.subagent_references, ())

    @patch(f"{LOADER_MODULE}.AgentVersionRepository.get_definition")
    def test_maps_record_not_found_to_agent_version_not_found(self, mock_get_definition):
        mock_get_definition.side_effect = RecordNotFound("no")

        with self.assertRaises(AgentVersionNotFound):
            self.loader.load(agent_id="AG001", agent_version_id="AV001", context=self.context)

    @patch(f"{LOADER_MODULE}.AgentVersionRepository.get_definition")
    def test_maps_permission_denied_to_agent_version_not_found(self, mock_get_definition):
        """다른 팀 소속이라는 사실을 별도로 알려주지 않는다 — 존재하지 않는 것과 같은 404."""

        mock_get_definition.side_effect = PermissionDenied("no")

        with self.assertRaises(AgentVersionNotFound):
            self.loader.load(agent_id="AG001", agent_version_id="AV001", context=self.context)

    @patch(f"{LOADER_MODULE}.AgentSubagentRepository.list_for_parent_version")
    @patch(f"{LOADER_MODULE}.AgentVersionRepository.get_definition")
    def test_builds_full_subagent_definition_for_active_executable_child(
        self, mock_get_definition, mock_list
    ):
        parent_row = _definition_row()
        child_row = _definition_row(
            agent_id="AG011", agent_version_id="AV023", model="gpt-5.6-luna", tool_refs=["jira_get_issues"]
        )
        mock_get_definition.side_effect = [parent_row, child_row]
        # 부모 자신의 후보 목록 조회 1회뿐이다 — 각 자식의 has_subagents는 이미 그 행에
        # EXISTS 서브쿼리로 같이 실려 온다(AgentSubagentRepository.list_for_parent_version
        # 구현 참고). 자식마다 이 메서드를 또 부르지 않는다.
        mock_list.return_value = [_child_ref_row()]

        loaded = self.loader.load(agent_id="AG001", agent_version_id="AV001", context=self.context)

        mock_list.assert_called_once()
        self.assertEqual(len(loaded.definition.subagents), 1)
        subagent = loaded.definition.subagents[0]
        self.assertEqual(subagent.agent_id, "AG011")
        self.assertEqual(subagent.alias, "jira_writer")
        self.assertEqual(subagent.tool_refs, ("jira_get_issues",))

        self.assertEqual(loaded.subagent_references[0].child_agent_id, "AG011")
        self.assertEqual(loaded.subagent_references[0].is_active, True)

    @patch(f"{LOADER_MODULE}.AgentSubagentRepository.list_for_parent_version")
    @patch(f"{LOADER_MODULE}.AgentVersionRepository.get_definition")
    def test_passes_through_has_subagents_without_raising(self, mock_get_definition, mock_list):
        """부모 자신의 후보 목록에서는 has_subagents=True를 거부하지 않는다 — 그건
        validate_subagents()(factory.py) 한 곳의 책임이다(§7.1)."""

        parent_row = _definition_row()
        child_row = _definition_row(agent_id="AG011", agent_version_id="AV023")
        mock_get_definition.side_effect = [parent_row, child_row]
        mock_list.return_value = [_child_ref_row(has_subagents=True)]

        loaded = self.loader.load(agent_id="AG001", agent_version_id="AV001", context=self.context)

        self.assertTrue(loaded.subagent_references[0].has_subagents)
        self.assertEqual(len(loaded.definition.subagents), 1)

    @patch(f"{LOADER_MODULE}.AgentSubagentRepository.list_for_parent_version")
    @patch(f"{LOADER_MODULE}.AgentVersionRepository.get_definition")
    def test_skips_fetch_and_uses_placeholder_when_child_not_executable(
        self, mock_get_definition, mock_list
    ):
        """can_execute=False면 get_definition()을 아예 다시 안 부른다 — 어차피
        PermissionDenied로 실패할 호출을 시도하지 않는다."""

        mock_get_definition.return_value = _definition_row()
        mock_list.return_value = [_child_ref_row(can_execute=False)]

        loaded = self.loader.load(agent_id="AG001", agent_version_id="AV001", context=self.context)

        mock_get_definition.assert_called_once()  # 부모용 1회만, 자식용은 없음
        subagent = loaded.definition.subagents[0]
        self.assertEqual(subagent.system_prompt, "")
        self.assertEqual(subagent.tool_refs, ())
        self.assertFalse(loaded.subagent_references[0].can_execute)

    @patch(f"{LOADER_MODULE}.AgentSubagentRepository.list_for_parent_version")
    @patch(f"{LOADER_MODULE}.AgentVersionRepository.get_definition")
    def test_uses_placeholder_when_executable_child_fetch_unexpectedly_fails(
        self, mock_get_definition, mock_list
    ):
        """can_execute=True였는데도 못 읽으면(데이터 경합 등) 전체를 실패시키지 않고
        자리 채움으로 내린다 — 관련 없는 다른 서브 에이전트까지 로딩이 실패하면 안 된다."""

        mock_get_definition.side_effect = [_definition_row(), RecordNotFound("race")]
        mock_list.return_value = [_child_ref_row()]

        loaded = self.loader.load(agent_id="AG001", agent_version_id="AV001", context=self.context)

        subagent = loaded.definition.subagents[0]
        self.assertEqual(subagent.system_prompt, "")
        self.assertTrue(loaded.subagent_references[0].can_execute)  # ref 자체는 원본 값 유지


class LoadChildOnlyTests(SimpleTestCase):
    """`include_subagents=False` — 자식 자신을 로딩하는 경로."""

    def setUp(self):
        self.loader = AgentDefinitionLoader()
        self.context = _context()

    @patch(f"{LOADER_MODULE}.AgentSubagentRepository.list_for_parent_version", return_value=[])
    @patch(f"{LOADER_MODULE}.AgentVersionRepository.get_definition")
    def test_returns_empty_subagents_when_child_has_none(self, mock_get_definition, _mock_list):
        mock_get_definition.return_value = _definition_row(agent_id="AG011", agent_version_id="AV023")

        loaded = self.loader.load(
            agent_id="AG011", agent_version_id="AV023", context=self.context, include_subagents=False
        )

        self.assertEqual(loaded.definition.subagents, ())
        self.assertEqual(loaded.subagent_references, ())

    @patch(f"{LOADER_MODULE}.AgentSubagentRepository.list_for_parent_version")
    @patch(f"{LOADER_MODULE}.AgentVersionRepository.get_definition")
    def test_raises_when_child_secretly_has_subagents(self, mock_get_definition, mock_list):
        """이 결과(subagents=())를 나중에 검사할 다른 코드가 없다 — 여기서 안 막으면
        조용히 사라진다(§6.2)."""

        mock_get_definition.return_value = _definition_row(agent_id="AG011", agent_version_id="AV023")
        mock_list.return_value = [_child_ref_row()]

        with self.assertRaises(DelegationDepthError):
            self.loader.load(
                agent_id="AG011", agent_version_id="AV023", context=self.context, include_subagents=False
            )


class FromDraftTests(SimpleTestCase):
    def setUp(self):
        self.loader = AgentDefinitionLoader()
        self.context = _context()

    def _draft(self, **overrides) -> dict:
        draft = {
            "name": "초안 에이전트",
            "description": "설명",
            "system_prompt": "프롬프트",
            "model": "claude-sonnet-5",
            "reasoning_effort": "low",
            "max_iterations": 6,
            "tool_refs": ["document_search"],
            "subagents": [],
        }
        draft.update(overrides)
        return draft

    def test_agent_id_and_version_are_none(self):
        loaded = self.loader.from_draft(draft=self._draft(), context=self.context)

        self.assertIsNone(loaded.definition.agent_id)
        self.assertIsNone(loaded.definition.agent_version_id)
        self.assertEqual(loaded.definition.tool_refs, ("document_search",))

    def test_agent_id_passes_through_when_draft_supplies_it(self):
        """레거시 에이전트를 옮긴 draft(legacy_bridge.draft_from_legacy_agent())는
        agent_id를 실어 보낸다 — agent_run.agent_id(NOT NULL)를 채우려면
        여기서 그대로 통과시켜야 한다(2026-08-14 추가). agent_version_id는
        draft 개념 자체에 없어서 항상 None이다."""
        loaded = self.loader.from_draft(draft=self._draft(agent_id="AG005"), context=self.context)

        self.assertEqual(loaded.definition.agent_id, "AG005")
        self.assertIsNone(loaded.definition.agent_version_id)

    def test_missing_subagents_key_defaults_to_empty(self):
        draft = self._draft()
        del draft["subagents"]

        loaded = self.loader.from_draft(draft=draft, context=self.context)

        self.assertEqual(loaded.definition.subagents, ())

    @patch(f"{LOADER_MODULE}.AgentSubagentRepository.list_for_parent_version", return_value=[])
    @patch(f"{LOADER_MODULE}.AgentVersionRepository.get_definition")
    def test_resolves_valid_candidate(self, mock_get_definition, _mock_list):
        mock_get_definition.return_value = _definition_row(agent_id="AG011", agent_version_id="AV023")
        draft = self._draft(
            subagents=[
                {
                    "child_agent_id": "AG011",
                    "child_version_id": "AV023",
                    "alias": "jira_writer",
                    "delegation_description": "Jira 이슈를 생성한다.",
                }
            ]
        )

        loaded = self.loader.from_draft(draft=draft, context=self.context)

        self.assertTrue(loaded.subagent_references[0].can_execute)
        self.assertTrue(loaded.subagent_references[0].is_active)
        self.assertEqual(loaded.definition.subagents[0].alias, "jira_writer")

    @patch(f"{LOADER_MODULE}.AgentVersionRepository.get_definition")
    def test_unresolvable_candidate_becomes_inactive_placeholder(self, mock_get_definition):
        mock_get_definition.side_effect = PermissionDenied("다른 팀")
        draft = self._draft(
            subagents=[
                {
                    "child_agent_id": "AG999",
                    "child_version_id": "AV999",
                    "alias": "other_team",
                    "delegation_description": "설명",
                }
            ]
        )

        loaded = self.loader.from_draft(draft=draft, context=self.context)

        ref = loaded.subagent_references[0]
        self.assertFalse(ref.is_active)
        self.assertFalse(ref.can_execute)
        self.assertEqual(loaded.definition.subagents[0].system_prompt, "")

    @patch(f"{LOADER_MODULE}.AgentSubagentRepository.list_for_parent_version")
    @patch(f"{LOADER_MODULE}.AgentVersionRepository.get_definition")
    def test_candidate_with_grandchildren_passes_through_without_raising(
        self, mock_get_definition, mock_list
    ):
        mock_get_definition.return_value = _definition_row(agent_id="AG011", agent_version_id="AV023")
        mock_list.return_value = [_child_ref_row()]  # 자식 버전 자신도 서브 에이전트를 가짐
        draft = self._draft(
            subagents=[
                {
                    "child_agent_id": "AG011",
                    "child_version_id": "AV023",
                    "alias": "jira_writer",
                    "delegation_description": "설명",
                }
            ]
        )

        loaded = self.loader.from_draft(draft=draft, context=self.context)

        self.assertTrue(loaded.subagent_references[0].has_subagents)
