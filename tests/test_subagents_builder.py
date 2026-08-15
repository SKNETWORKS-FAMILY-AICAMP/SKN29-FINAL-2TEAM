"""subagents/builder.py(build_subagent) 단위 테스트."""

from django.test import SimpleTestCase

from services.agent_runtime.context import RuntimeContext
from services.agent_runtime.definitions import AgentDefinition, SubagentDefinition
from services.agent_runtime.subagents.builder import build_subagent, definition_has_subagents


def _subagent_definition(**overrides) -> SubagentDefinition:
    fields = {
        "agent_id": "AG011",
        "agent_version_id": "AV023",
        "name": "Jira 작성자",
        "description": "",
        "system_prompt": "프롬프트",
        "model": "gpt-5.6-luna",
        "reasoning_effort": "low",
        "max_iterations": 6,
        "alias": "jira_writer",
        "delegation_description": "Jira 이슈를 생성한다.",
        "tool_refs": ("jira_get_issues",),
    }
    fields.update(overrides)
    return SubagentDefinition(**fields)


class BuildSubagentTests(SimpleTestCase):
    def test_calls_build_child_graph_with_agent_definition_and_no_grandchildren(self):
        captured = {}

        def _build_child_graph(definition, context):
            captured["definition"] = definition
            captured["context"] = context
            return "COMPILED_CHILD_GRAPH"

        context = RuntimeContext(account_id="AC001", team_id="TM001", role="leader")
        result = build_subagent(
            _subagent_definition(), context, build_child_graph=_build_child_graph
        )

        self.assertIsInstance(captured["definition"], AgentDefinition)
        self.assertEqual(captured["definition"].agent_id, "AG011")
        self.assertEqual(captured["definition"].subagents, ())
        self.assertEqual(captured["definition"].tool_refs, ("jira_get_issues",))
        self.assertIs(captured["context"], context)

        self.assertEqual(result["name"], "jira_writer")
        self.assertEqual(result["description"], "Jira 이슈를 생성한다.")
        self.assertEqual(result["runnable"], "COMPILED_CHILD_GRAPH")


class DefinitionHasSubagentsTests(SimpleTestCase):
    def test_subagent_definition_never_has_subagents_field(self):
        self.assertFalse(definition_has_subagents(_subagent_definition()))

    def test_agent_definition_with_subagents(self):
        definition = AgentDefinition(
            agent_id="AG001",
            agent_version_id="AV001",
            name="부모",
            description="",
            system_prompt="",
            model="claude-sonnet-5",
            reasoning_effort="low",
            max_iterations=6,
            subagents=(_subagent_definition(),),
        )

        self.assertTrue(definition_has_subagents(definition))

    def test_agent_definition_without_subagents(self):
        definition = AgentDefinition(
            agent_id="AG001",
            agent_version_id="AV001",
            name="부모",
            description="",
            system_prompt="",
            model="claude-sonnet-5",
            reasoning_effort="low",
            max_iterations=6,
        )

        self.assertFalse(definition_has_subagents(definition))
