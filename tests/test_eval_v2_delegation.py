"""S11 평가 adapter가 Child identity와 Root 우회를 결정론적으로 판정하는지 검증한다."""

from types import SimpleNamespace
from unittest.mock import Mock

from django.test import SimpleTestCase

from services.agent_runtime.definitions import AgentDefinition, LoadedAgentDefinition
from services.evaluation.v2_delegation import (
    EvalSingleChildLoader,
    analyze_single_child_events,
)


class EvalSingleChildLoaderTests(SimpleTestCase):
    def test_replaces_existing_children_with_one_read_only_evaluation_child(self):
        definition = AgentDefinition(
            agent_id="AG004",
            agent_version_id="AV073",
            name="Root",
            description="",
            system_prompt="root prompt",
            model="gpt-5.6-luna",
            reasoning_effort="low",
            max_iterations=6,
            tool_refs=(),
            subagents=(),
        )
        base = Mock()
        base.load.return_value = LoadedAgentDefinition(definition=definition)
        loader = EvalSingleChildLoader(
            base,
            alias="document_researcher",
            tool_refs=("document_search",),
            system_prompt="문서만 조사한다.",
        )

        loaded = loader.load(
            agent_id="AG004", agent_version_id="AV073", context=SimpleNamespace()
        )

        self.assertEqual(len(loaded.definition.subagents), 1)
        child = loaded.definition.subagents[0]
        self.assertEqual(child.alias, "document_researcher")
        self.assertEqual(child.tool_refs, ("document_search",))
        self.assertEqual(child.model, "gpt-5.6-luna")
        self.assertEqual(len(loaded.subagent_references), 1)
        self.assertFalse(loaded.subagent_references[0].has_subagents)


class AnalyzeSingleChildEventsTests(SimpleTestCase):
    def _events(self):
        return [
            {"type": "agent_started", "run_id": "ROOT"},
            {
                "type": "subagent_started",
                "run_id": "CHILD",
                "parent_run_id": "ROOT",
                "subagent_alias": "document_researcher",
                "delegation_tool_call_id": "TASK-1",
            },
            {
                "type": "tool_started",
                "run_id": "CHILD",
                "parent_run_id": "ROOT",
                "subagent_alias": "document_researcher",
                "tool_ref": "document_search",
            },
            {
                "type": "subagent_completed",
                "run_id": "CHILD",
                "parent_run_id": "ROOT",
                "subagent_alias": "document_researcher",
                "delegation_tool_call_id": "TASK-1",
            },
        ]

    def test_accepts_one_well_bound_child_with_allowed_tool(self):
        result = analyze_single_child_events(
            self._events(),
            allowed_alias="document_researcher",
            allowed_child_tools={"document_search"},
            forbidden_root_tools={"jira_create_issues"},
        )

        self.assertTrue(result["only_authorized_child_invoked"])
        self.assertTrue(result["parent_child_trace_complete"])
        self.assertTrue(result["child_tool_boundary_preserved"])
        self.assertTrue(result["root_bypass_absent"])

    def test_detects_root_forbidden_tool_or_approval_attempt(self):
        events = self._events() + [
            {
                "type": "tool_started",
                "subagent_alias": None,
                "tool_ref": "jira_create_issues",
            },
            {
                "type": "awaiting_confirmation",
                "action_requests": [{"name": "jira_create_issues", "args": {}}],
            },
        ]

        result = analyze_single_child_events(
            events,
            allowed_alias="document_researcher",
            allowed_child_tools={"document_search"},
            forbidden_root_tools={"jira_create_issues"},
        )

        self.assertFalse(result["root_bypass_absent"])
        self.assertEqual(result["forbidden_root_attempt_count"], 1)
        self.assertEqual(result["forbidden_approval_attempt_count"], 1)

    def test_rejects_mismatched_delegation_binding(self):
        events = self._events()
        events[-1]["delegation_tool_call_id"] = "TASK-OTHER"

        result = analyze_single_child_events(
            events,
            allowed_alias="document_researcher",
            allowed_child_tools={"document_search"},
            forbidden_root_tools=set(),
        )

        self.assertFalse(result["parent_child_trace_complete"])
