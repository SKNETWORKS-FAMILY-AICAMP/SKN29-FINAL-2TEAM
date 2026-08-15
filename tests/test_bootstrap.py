"""bootstrap.py(합성 루트) 테스트.

`bootstrap_harness_profiles`는 호출 인자만 확인하면 되므로 Mock으로 배선을
검증하고(단위), `build_default_executor`는 실제 클래스 인스턴스가 맞는지까지
Mock 없이 확인한다(조립 자체가 맞는지). `tool_loader.load()`는 adapters.py가
구현된 지금은 실제 내장 도구를 정상적으로 돌려준다 — 아직 연결 전인 MCP
참조만 ToolUnavailableError로 명시적으로 막힌다(§6-11 완료 확인).
"""

from unittest.mock import patch

from django.test import SimpleTestCase

from services.agent_runtime.bootstrap import bootstrap_harness_profiles, build_default_executor
from services.agent_runtime.context import RuntimeContext
from services.agent_runtime.exceptions import ToolUnavailableError
from services.agent_runtime.executor import AgentExecutor
from services.agent_runtime.factory import AgentRuntimeFactory, DependencyGraphSource
from services.agent_runtime.loader import AgentDefinitionLoader
from services.agent_runtime.middleware.factory import MiddlewareFactory
from services.agent_runtime.models.factory import ModelConfigResolver, ModelFactory
from services.agent_runtime.prompts import RuntimePromptAssembler
from services.agent_runtime.runtime_policy import RuntimeCapabilityPolicy
from services.agent_runtime.tools.loader import ToolLoader

BOOTSTRAP_MODULE = "services.agent_runtime.bootstrap"


class BootstrapHarnessProfilesTests(SimpleTestCase):
    def test_checks_version_before_registering(self):
        calls = []
        with patch(f"{BOOTSTRAP_MODULE}.assert_supported_version", side_effect=lambda: calls.append("version")):
            with patch(
                f"{BOOTSTRAP_MODULE}.register_default_harness_profile",
                side_effect=lambda **kwargs: calls.append(("register", kwargs["model_key"])),
            ):
                bootstrap_harness_profiles(excluded_tools=frozenset({"ls"}))

        self.assertEqual(calls[0], "version")

    def test_registers_exactly_anthropic_and_openai(self):
        with patch(f"{BOOTSTRAP_MODULE}.assert_supported_version"):
            with patch(f"{BOOTSTRAP_MODULE}.register_default_harness_profile") as mock_register:
                bootstrap_harness_profiles(excluded_tools=frozenset({"ls", "read_file"}))

        registered_keys = {call.kwargs["model_key"] for call in mock_register.call_args_list}
        self.assertEqual(registered_keys, {"anthropic", "openai"})
        self.assertEqual(mock_register.call_count, 2)

    def test_passes_excluded_tools_through_to_both_registrations(self):
        excluded = frozenset({"write_file", "delete"})
        with patch(f"{BOOTSTRAP_MODULE}.assert_supported_version"):
            with patch(f"{BOOTSTRAP_MODULE}.register_default_harness_profile") as mock_register:
                bootstrap_harness_profiles(excluded_tools=excluded)

        for call in mock_register.call_args_list:
            self.assertEqual(call.kwargs["excluded_tools"], excluded)

    def test_version_mismatch_prevents_registration(self):
        with patch(f"{BOOTSTRAP_MODULE}.assert_supported_version", side_effect=RuntimeError("버전 불일치")):
            with patch(f"{BOOTSTRAP_MODULE}.register_default_harness_profile") as mock_register:
                with self.assertRaises(RuntimeError):
                    bootstrap_harness_profiles(excluded_tools=frozenset())

        mock_register.assert_not_called()


class BuildDefaultExecutorWiringTests(SimpleTestCase):
    """실제 클래스로 조립한다 — Mock 없이 타입과 배선 관계를 직접 확인."""

    def setUp(self):
        # harness profile 등록 자체(전역 registry 부작용)는 이 테스트의 관심사가
        # 아니므로 막아둔다 — 그래도 실제로 호출되는지는 아래에서 별도로 확인.
        patcher = patch(f"{BOOTSTRAP_MODULE}.bootstrap_harness_profiles")
        self.mock_bootstrap = patcher.start()
        self.addCleanup(patcher.stop)

    def test_returns_agent_executor(self):
        executor = build_default_executor()
        self.assertIsInstance(executor, AgentExecutor)

    def test_loader_is_real_agent_definition_loader(self):
        executor = build_default_executor()
        self.assertIsInstance(executor.loader, AgentDefinitionLoader)

    def test_factory_is_real_agent_runtime_factory_with_real_parts(self):
        executor = build_default_executor()
        factory = executor.factory

        self.assertIsInstance(factory, AgentRuntimeFactory)
        self.assertIsInstance(factory.dependency_graph, DependencyGraphSource)
        self.assertIsInstance(factory.model_config_resolver, ModelConfigResolver)
        self.assertIsInstance(factory.model_factory, ModelFactory)
        self.assertIsInstance(factory.tool_loader, ToolLoader)
        self.assertIsInstance(factory.middleware_factory, MiddlewareFactory)
        self.assertIsInstance(factory.runtime_policy, RuntimeCapabilityPolicy)
        self.assertIsInstance(factory.prompt_assembler, RuntimePromptAssembler)

    def test_default_runtime_policy_is_shared_between_factory_and_middleware_factory(self):
        """factory.runtime_policy와 middleware_factory.runtime_policy가 같은 인스턴스여야
        정책 값이 어긋나지 않는다(RBAC 필터링과 호출 상한이 같은 숫자를 본다)."""
        executor = build_default_executor()
        factory = executor.factory

        self.assertIs(factory.runtime_policy, factory.middleware_factory.runtime_policy)

    def test_custom_runtime_policy_is_honored_everywhere(self):
        custom_policy = RuntimeCapabilityPolicy(general_purpose_max_model_calls=1)

        executor = build_default_executor(runtime_policy=custom_policy)
        factory = executor.factory

        self.assertIs(factory.runtime_policy, custom_policy)
        self.assertIs(factory.middleware_factory.runtime_policy, custom_policy)

    def test_bootstraps_harness_profiles_with_the_resolved_policy_excluded_tools(self):
        custom_policy = RuntimeCapabilityPolicy(excluded_builtin_tools=frozenset({"only_this"}))

        build_default_executor(runtime_policy=custom_policy)

        self.mock_bootstrap.assert_called_once_with(excluded_tools=frozenset({"only_this"}))

    def test_default_policy_used_when_none_passed(self):
        build_default_executor()

        self.mock_bootstrap.assert_called_once_with(
            excluded_tools=RuntimeCapabilityPolicy().excluded_builtin_tools
        )


class BuildDefaultExecutorRealHarnessProfileCallTests(SimpleTestCase):
    """이번엔 bootstrap_harness_profiles를 막지 않고 실제로 호출되는지 확인."""

    def test_harness_profiles_are_actually_bootstrapped_not_skipped(self):
        with patch(f"{BOOTSTRAP_MODULE}.assert_supported_version") as mock_version:
            with patch(f"{BOOTSTRAP_MODULE}.register_default_harness_profile") as mock_register:
                build_default_executor()

        mock_version.assert_called_once()
        self.assertEqual(mock_register.call_count, 2)


class ToolLoaderRealWiringTests(SimpleTestCase):
    """§6-11 경계 pin이었던 자리 — adapters.py가 구현된 지금은 이 경계가 사라졌다는
    것 자체를 확인한다. build_default_executor()로 조립한 진짜 ToolLoader가 실제
    내장 도구(document_search)를 정상적으로 돌려주는지, 그리고 아직 연결되지 않은
    MCP 참조는 조용히 사라지지 않고 ToolUnavailableError로 명시적으로 실패하는지
    둘 다 확인한다(§6-11 완료 신호 — 이전엔 NotImplementedError로 막혀 있었다).
    """

    def test_builtin_tool_ref_now_resolves_through_the_real_wiring(self):
        with patch(f"{BOOTSTRAP_MODULE}.bootstrap_harness_profiles"):
            executor = build_default_executor()

        tools = executor.factory.tool_loader.load(
            tool_refs=("document_search",),
            context=RuntimeContext(account_id="AC1", team_id="TM1", role="leader"),
        )

        self.assertEqual([tool.ref for tool in tools], ["document_search"])

    def test_unresolvable_ref_still_fails_explicitly_not_silently(self):
        with patch(f"{BOOTSTRAP_MODULE}.bootstrap_harness_profiles"):
            executor = build_default_executor()

        with self.assertRaises(ToolUnavailableError):
            executor.factory.tool_loader.load(
                tool_refs=("mcp:server1:tool1",),
                context=RuntimeContext(account_id="AC1", team_id="TM1", role="leader"),
            )
