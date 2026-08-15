"""middleware/factory.py(MiddlewareFactory) 단위 테스트.

실제 ModelCallLimitMiddleware/ToolCallLimitMiddleware(langchain)를 만들어서
runtime_policy.py 값이 그대로 반영되는지 확인한다(mock 아님).
"""

from django.test import SimpleTestCase
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware

from services.agent_runtime.definitions import AgentDefinition
from services.agent_runtime.middleware.factory import MiddlewareFactory
from services.agent_runtime.runtime_policy import RuntimeCapabilityPolicy


def _definition(**overrides) -> AgentDefinition:
    fields = {
        "agent_id": "AG001",
        "agent_version_id": "AV001",
        "name": "테스트",
        "description": "",
        "system_prompt": "",
        "model": "claude-sonnet-5",
        "reasoning_effort": "low",
        "max_iterations": 6,
    }
    fields.update(overrides)
    return AgentDefinition(**fields)


class BuildTests(SimpleTestCase):
    def setUp(self):
        self.policy = RuntimeCapabilityPolicy(max_model_calls_ceiling=20, max_tool_calls_ceiling=40)
        self.factory = MiddlewareFactory(runtime_policy=self.policy)

    def test_applies_ceiling_to_definition_max_iterations(self):
        middleware = self.factory.build(definition=_definition(max_iterations=999), context=None)

        model_limit = next(m for m in middleware if isinstance(m, ModelCallLimitMiddleware))
        self.assertEqual(model_limit.run_limit, 20)

    def test_passes_through_max_iterations_under_ceiling(self):
        middleware = self.factory.build(definition=_definition(max_iterations=6), context=None)

        model_limit = next(m for m in middleware if isinstance(m, ModelCallLimitMiddleware))
        self.assertEqual(model_limit.run_limit, 6)

    def test_tool_call_limit_uses_ceiling(self):
        middleware = self.factory.build(definition=_definition(), context=None)

        tool_limit = next(m for m in middleware if isinstance(m, ToolCallLimitMiddleware))
        self.assertEqual(tool_limit.run_limit, 40)


class BuildForGeneralPurposeTests(SimpleTestCase):
    def test_uses_policy_general_purpose_defaults(self):
        policy = RuntimeCapabilityPolicy(
            general_purpose_max_model_calls=6,
            general_purpose_max_tool_calls=12,
            max_model_calls_ceiling=20,
            max_tool_calls_ceiling=40,
        )
        factory = MiddlewareFactory(runtime_policy=policy)

        middleware = factory.build_for_general_purpose()

        model_limit = next(m for m in middleware if isinstance(m, ModelCallLimitMiddleware))
        tool_limit = next(m for m in middleware if isinstance(m, ToolCallLimitMiddleware))
        self.assertEqual(model_limit.run_limit, 6)
        self.assertEqual(tool_limit.run_limit, 12)
