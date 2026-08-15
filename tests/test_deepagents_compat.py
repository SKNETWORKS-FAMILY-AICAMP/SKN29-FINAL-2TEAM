"""compat/deepagents_v075.py 단위 테스트.

정본: docs/작업기록/Deep_Agents/2026-08-13_04_작업자B_실행코어_세부계획.md §6-2

이 파일은 이 저장소의 다른 모듈과 달리 deepagents를 실제로 import한다(compat
패키지가 정확히 그러라고 있는 경계다 — §4 참고). requirements/base.txt에
deepagents==0.7.5가 pin돼 있으므로, 이 pin이 실제로 설치된 환경에서만 이
테스트가 수집·실행된다.

검증 범위는 "결과가 그럴듯한가"가 아니라 §6-2 완료 조건 두 가지다:
  1. 부트스트랩 등록(register_default_harness_profile)이 중복 호출돼도 안전한가
  2. Root/Child spec 형태가 기대한 dict 구조인가(0-2/0-3의 구조적 보장)

`_spike/runtime_skeleton.py`(§6-1)에서 이미 실제 create_deep_agent 호출로
행동(behavior)은 확인했다 — 여기서는 create_deep_agent를 mock으로 바꿔
"우리가 이걸 어떻게 호출하는가"만 본다(빠르고 API 키가 필요 없다).
"""

from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from deepagents import GeneralPurposeSubagentProfile, HarnessProfile
from deepagents.middleware.subagents import GENERAL_PURPOSE_SUBAGENT

from services.agent_runtime.compat.deepagents_v075 import (
    DELEGATION_TOOL_NAME,
    SUPPORTED_VERSION,
    assert_supported_version,
    build_general_purpose_spec,
    create_child_graph,
    create_root_graph,
    default_general_purpose_prompt,
    register_default_harness_profile,
)

COMPAT_MODULE = "services.agent_runtime.compat.deepagents_v075"


class AssertSupportedVersionTests(SimpleTestCase):
    def test_passes_when_installed_version_matches_supported_version(self):
        with patch(f"{COMPAT_MODULE}.version", return_value=SUPPORTED_VERSION):
            assert_supported_version()  # 예외 없이 통과해야 한다.

    def test_raises_when_installed_version_differs(self):
        with patch(f"{COMPAT_MODULE}.version", return_value="0.8.0"):
            with self.assertRaises(RuntimeError) as ctx:
                assert_supported_version()

        self.assertIn(SUPPORTED_VERSION, str(ctx.exception))
        self.assertIn("0.8.0", str(ctx.exception))

    def test_raises_when_deepagents_not_installed(self):
        from importlib.metadata import PackageNotFoundError

        with patch(f"{COMPAT_MODULE}.version", side_effect=PackageNotFoundError("deepagents")):
            with self.assertRaises(RuntimeError):
                assert_supported_version()


class RegisterDefaultHarnessProfileTests(SimpleTestCase):
    def test_registers_profile_that_disables_auto_general_purpose(self):
        with patch(f"{COMPAT_MODULE}.register_harness_profile") as mock_register:
            register_default_harness_profile(model_key="anthropic")

        mock_register.assert_called_once()
        (model_key, profile), _kwargs = mock_register.call_args
        self.assertEqual(model_key, "anthropic")
        self.assertIsInstance(profile, HarnessProfile)
        self.assertIsInstance(profile.general_purpose_subagent, GeneralPurposeSubagentProfile)
        self.assertIs(profile.general_purpose_subagent.enabled, False)
        self.assertEqual(profile.excluded_tools, frozenset())

    def test_passes_excluded_tools_through_unchanged(self):
        wanted = frozenset({"write_file", "delete"})
        with patch(f"{COMPAT_MODULE}.register_harness_profile") as mock_register:
            register_default_harness_profile(model_key="openai", excluded_tools=wanted)

        _model_key, profile = mock_register.call_args.args
        self.assertEqual(profile.excluded_tools, wanted)

    def test_is_safe_to_call_twice_with_same_model_key(self):
        with patch(f"{COMPAT_MODULE}.register_harness_profile") as mock_register:
            register_default_harness_profile(model_key="anthropic")
            register_default_harness_profile(model_key="anthropic")

        self.assertEqual(mock_register.call_count, 2)
        first_key, _ = mock_register.call_args_list[0].args
        second_key, _ = mock_register.call_args_list[1].args
        self.assertEqual(first_key, second_key)


class BuildGeneralPurposeSpecTests(SimpleTestCase):
    def test_reuses_default_gp_name_and_description(self):
        spec = build_general_purpose_spec()

        self.assertEqual(spec["name"], GENERAL_PURPOSE_SUBAGENT["name"])
        self.assertEqual(spec["description"], GENERAL_PURPOSE_SUBAGENT["description"])
        self.assertNotIn("middleware", spec)

    def test_includes_middleware_when_given(self):
        fake_middleware = Mock(name="fake-middleware")

        spec = build_general_purpose_spec(middleware=[fake_middleware])

        self.assertEqual(spec["middleware"], [fake_middleware])
        # name/description은 middleware를 줘도 그대로 유지돼야 한다.
        self.assertEqual(spec["name"], GENERAL_PURPOSE_SUBAGENT["name"])

    def test_does_not_mutate_original_general_purpose_subagent(self):
        build_general_purpose_spec(middleware=[Mock()])

        self.assertNotIn("middleware", GENERAL_PURPOSE_SUBAGENT)

    def test_no_system_prompt_arg_keeps_deepagents_default(self):
        spec = build_general_purpose_spec()

        self.assertEqual(spec["system_prompt"], GENERAL_PURPOSE_SUBAGENT["system_prompt"])

    def test_system_prompt_arg_overrides_the_default(self):
        spec = build_general_purpose_spec(system_prompt="조립된 프롬프트")

        self.assertEqual(spec["system_prompt"], "조립된 프롬프트")
        # 덮어써도 name/description은 그대로다.
        self.assertEqual(spec["name"], GENERAL_PURPOSE_SUBAGENT["name"])

    def test_overriding_system_prompt_does_not_mutate_the_original(self):
        build_general_purpose_spec(system_prompt="조립된 프롬프트")

        self.assertNotEqual(GENERAL_PURPOSE_SUBAGENT["system_prompt"], "조립된 프롬프트")


class DefaultGeneralPurposePromptTests(SimpleTestCase):
    def test_returns_deepagents_own_default_gp_system_prompt(self):
        self.assertEqual(default_general_purpose_prompt(), GENERAL_PURPOSE_SUBAGENT["system_prompt"])


class CreateRootGraphTests(SimpleTestCase):
    def test_passes_subagents_through_to_create_deep_agent(self):
        fake_model = Mock(name="fake-model")
        fake_gp_spec = {"name": "general-purpose"}
        fake_child = Mock(name="fake-compiled-subagent")

        with patch(f"{COMPAT_MODULE}.create_deep_agent") as mock_create:
            create_root_graph(
                model=fake_model,
                system_prompt="시스템 프롬프트",
                tools=[],
                subagents=[fake_gp_spec, fake_child],
            )

        mock_create.assert_called_once_with(
            model=fake_model,
            system_prompt="시스템 프롬프트",
            tools=[],
            subagents=[fake_gp_spec, fake_child],
            middleware=[],
        )

    def test_defaults_subagents_to_empty_list(self):
        with patch(f"{COMPAT_MODULE}.create_deep_agent") as mock_create:
            create_root_graph(model=Mock(), system_prompt="p")

        _args, kwargs = mock_create.call_args
        self.assertEqual(kwargs["subagents"], [])

    def test_passes_middleware_through(self):
        fake_middleware = [Mock(name="model-call-limit")]
        with patch(f"{COMPAT_MODULE}.create_deep_agent") as mock_create:
            create_root_graph(model=Mock(), system_prompt="p", middleware=fake_middleware)

        _args, kwargs = mock_create.call_args
        self.assertEqual(kwargs["middleware"], fake_middleware)


class CreateChildGraphTests(SimpleTestCase):
    def test_always_forces_subagents_to_empty_list(self):
        with patch(f"{COMPAT_MODULE}.create_deep_agent") as mock_create:
            create_child_graph(model=Mock(), system_prompt="p", tools=[Mock()])

        _args, kwargs = mock_create.call_args
        self.assertEqual(kwargs["subagents"], [])

    def test_passes_middleware_through(self):
        fake_middleware = [Mock(name="tool-call-limit")]
        with patch(f"{COMPAT_MODULE}.create_deep_agent") as mock_create:
            create_child_graph(model=Mock(), system_prompt="p", middleware=fake_middleware)

        _args, kwargs = mock_create.call_args
        self.assertEqual(kwargs["middleware"], fake_middleware)

    def test_rejects_subagents_keyword_argument(self):
        """0-3 — Child가 다시 위임할 경로를 시그니처 단계에서부터 막는다."""

        with self.assertRaises(TypeError):
            create_child_graph(
                model=Mock(),
                system_prompt="p",
                subagents=[{"name": "should-not-be-accepted"}],
            )


class DelegationToolNameTests(SimpleTestCase):
    def test_matches_events_module_constant(self):
        from services.agent_runtime.events import DELEGATION_TOOL_NAME as events_value

        self.assertEqual(DELEGATION_TOOL_NAME, events_value)
