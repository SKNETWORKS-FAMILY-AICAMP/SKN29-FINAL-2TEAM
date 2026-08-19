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

from unittest.mock import Mock, NonCallableMock, patch

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


class CreateRootGraphMemorySystemPromptTests(SimpleTestCase):
    """`memory_system_prompt`(2026-08-18, Phase 3, §4-8) 배선.

    `create_deep_agent()`는 MemoryMiddleware의 system_prompt를 바꿀 공개 파라미터가
    없어서(실제 소스로 확인, `services/agent_runtime/compat/deepagents_v075.py`의
    `create_root_graph` docstring 참고) 커스텀 `MemoryMiddleware`를 `middleware=`
    목록에 끼워 넣는 방식으로 우회한다 — 그 배선이 실제로 일어나는지 확인한다.
    """

    _FAKE_PROMPT = "안내문 {agent_memory} 나머지"

    def test_no_memory_system_prompt_does_not_add_memory_middleware(self):
        with patch(f"{COMPAT_MODULE}.create_deep_agent") as mock_create:
            create_root_graph(model=Mock(), system_prompt="p", backend=Mock(name="backend"))

        _args, kwargs = mock_create.call_args
        self.assertEqual(kwargs["middleware"], [])

    def test_memory_system_prompt_without_backend_is_ignored(self):
        """backend가 없으면(=메모리 자체를 안 쓰면) memory_system_prompt만 있어도 무시한다."""

        with patch(f"{COMPAT_MODULE}.create_deep_agent") as mock_create:
            create_root_graph(model=Mock(), system_prompt="p", memory_system_prompt=self._FAKE_PROMPT)

        _args, kwargs = mock_create.call_args
        self.assertEqual(kwargs["middleware"], [])

    def test_memory_system_prompt_with_backend_appends_custom_memory_middleware(self):
        from deepagents import MemoryMiddleware

        fake_backend = Mock(name="backend")
        with patch(f"{COMPAT_MODULE}.create_deep_agent") as mock_create:
            create_root_graph(
                model=Mock(),
                system_prompt="p",
                memory=["/memories/AGENTS.md"],
                backend=fake_backend,
                memory_system_prompt=self._FAKE_PROMPT,
            )

        _args, kwargs = mock_create.call_args
        appended = kwargs["middleware"][-1]
        self.assertIsInstance(appended, MemoryMiddleware)
        self.assertEqual(appended.system_prompt, self._FAKE_PROMPT)
        self.assertEqual(appended.sources, ["/memories/AGENTS.md"])

    def test_custom_memory_middleware_shares_the_same_backend_instance(self):
        """§4-4 — MemoryMiddleware와 FilesystemMiddleware는 같은 backend 인스턴스를
        공유해야 한다. `kwargs["backend"]`(FilesystemMiddleware 쪽으로 감)와 커스텀
        MemoryMiddleware가 든 backend가 identity로 같은 객체인지 확인한다."""

        fake_backend = Mock(name="backend")
        with patch(f"{COMPAT_MODULE}.create_deep_agent") as mock_create:
            create_root_graph(
                model=Mock(),
                system_prompt="p",
                backend=fake_backend,
                memory_system_prompt=self._FAKE_PROMPT,
            )

        _args, kwargs = mock_create.call_args
        appended = kwargs["middleware"][-1]
        self.assertIs(appended._backend, fake_backend)
        self.assertIs(kwargs["backend"], fake_backend)

    def test_appended_after_existing_custom_middleware(self):
        fake_existing = Mock(name="model-call-limit")
        with patch(f"{COMPAT_MODULE}.create_deep_agent") as mock_create:
            create_root_graph(
                model=Mock(),
                system_prompt="p",
                middleware=[fake_existing],
                backend=Mock(name="backend"),
                memory_system_prompt=self._FAKE_PROMPT,
            )

        _args, kwargs = mock_create.call_args
        self.assertEqual(kwargs["middleware"][0], fake_existing)
        self.assertEqual(len(kwargs["middleware"]), 2)


class CreateRootGraphFilesystemExclusionTests(SimpleTestCase):
    """`fs_excluded_tools`(2026-08-18, Phase 6) 배선.

    `create_deep_agent()`는 `FilesystemMiddleware`의 `tools=` allowlist를 바꿀
    공개 파라미터가 없어서(실제 소스로 확인, `create_root_graph` docstring
    참고) `memory_system_prompt`와 같은 이름-치환 방식으로 우회한다.
    """

    def test_no_fs_excluded_tools_does_not_add_filesystem_middleware(self):
        with patch(f"{COMPAT_MODULE}.create_deep_agent") as mock_create:
            create_root_graph(model=Mock(), system_prompt="p")

        _args, kwargs = mock_create.call_args
        self.assertEqual(kwargs["middleware"], [])

    def test_excluded_tools_appends_filesystem_middleware_without_them(self):
        from deepagents.middleware.filesystem import FilesystemMiddleware

        with patch(f"{COMPAT_MODULE}.create_deep_agent") as mock_create:
            create_root_graph(
                model=Mock(),
                system_prompt="p",
                fs_excluded_tools=frozenset({"delete"}),
            )

        _args, kwargs = mock_create.call_args
        appended = kwargs["middleware"][-1]
        self.assertIsInstance(appended, FilesystemMiddleware)
        tool_names = {t.name for t in appended.tools}
        self.assertNotIn("delete", tool_names)
        self.assertIn("read_file", tool_names)
        self.assertIn("ls", tool_names)

    def test_filesystem_middleware_shares_the_same_backend_instance(self):
        """§4-4 — 여러 middleware가 backend 인스턴스를 공유해야 하는 제약이
        `FilesystemMiddleware` 치환에도 그대로 적용되는지 확인한다.

        `FilesystemMiddleware.__init__`은 `callable(backend)`이면서
        `BackendProtocol` 인스턴스가 아닌 값을 "backend factory(0.7에서
        제거됨)"로 보고 `TypeError`를 던진다(실제 소스로 확인) — 그래서
        `Mock()`(callable) 대신 호출 불가능한 `NonCallableMock`을 쓴다.
        """

        fake_backend = NonCallableMock(name="backend")
        with patch(f"{COMPAT_MODULE}.create_deep_agent") as mock_create:
            create_root_graph(
                model=Mock(),
                system_prompt="p",
                backend=fake_backend,
                fs_excluded_tools=frozenset({"delete"}),
            )

        _args, kwargs = mock_create.call_args
        appended = kwargs["middleware"][-1]
        self.assertIs(appended.backend, fake_backend)

    def test_no_backend_falls_back_to_filesystem_middleware_default(self):
        with patch(f"{COMPAT_MODULE}.create_deep_agent") as mock_create:
            create_root_graph(
                model=Mock(),
                system_prompt="p",
                fs_excluded_tools=frozenset({"delete"}),
            )

        _args, kwargs = mock_create.call_args
        appended = kwargs["middleware"][-1]
        from deepagents.backends import StateBackend

        self.assertIsInstance(appended.backend, StateBackend)


class CreateRootGraphInterruptOnTests(SimpleTestCase):
    """`interrupt_on`(2026-08-18, Phase 7) 배선.

    `create_deep_agent()`가 직접 받는 공개 파라미터라(실제 시그니처 확인,
    `create_root_graph` docstring 참고) 그대로 통과시키기만 하면 된다.
    """

    def test_no_interrupt_on_is_not_passed_through(self):
        with patch(f"{COMPAT_MODULE}.create_deep_agent") as mock_create:
            create_root_graph(model=Mock(), system_prompt="p")

        _args, kwargs = mock_create.call_args
        self.assertNotIn("interrupt_on", kwargs)

    def test_empty_interrupt_on_is_not_passed_through(self):
        with patch(f"{COMPAT_MODULE}.create_deep_agent") as mock_create:
            create_root_graph(model=Mock(), system_prompt="p", interrupt_on={})

        _args, kwargs = mock_create.call_args
        self.assertNotIn("interrupt_on", kwargs)

    def test_interrupt_on_passed_through_unchanged(self):
        wanted = {"task_register": True, "task_update": True}
        with patch(f"{COMPAT_MODULE}.create_deep_agent") as mock_create:
            create_root_graph(model=Mock(), system_prompt="p", interrupt_on=wanted)

        _args, kwargs = mock_create.call_args
        self.assertEqual(kwargs["interrupt_on"], wanted)


class CreateRootGraphPermissionsTests(SimpleTestCase):
    """`permissions`(2026-08-19, `middleware/permissions.py`) 배선.

    `create_deep_agent()`가 직접 받는 `permissions` 최상위 kwarg로 통과시키는
    것과 별개로, `fs_excluded_tools`가 켜져 있으면(이 프로젝트는 항상 켜짐)
    이름 치환용 커스텀 `FilesystemMiddleware`에도 `_permissions`로 같이 넘어가야
    한다 — 안 그러면 Root 자신에게는 조용히 적용 안 된다(§5).
    """

    def test_no_permissions_is_not_passed_through(self):
        with patch(f"{COMPAT_MODULE}.create_deep_agent") as mock_create:
            create_root_graph(model=Mock(), system_prompt="p")

        _args, kwargs = mock_create.call_args
        self.assertNotIn("permissions", kwargs)

    def test_empty_permissions_is_not_passed_through(self):
        with patch(f"{COMPAT_MODULE}.create_deep_agent") as mock_create:
            create_root_graph(model=Mock(), system_prompt="p", permissions=[])

        _args, kwargs = mock_create.call_args
        self.assertNotIn("permissions", kwargs)

    def test_permissions_passed_through_top_level_kwarg(self):
        fake_rule = Mock(name="fake-permission")
        with patch(f"{COMPAT_MODULE}.create_deep_agent") as mock_create:
            create_root_graph(model=Mock(), system_prompt="p", permissions=[fake_rule])

        _args, kwargs = mock_create.call_args
        self.assertEqual(kwargs["permissions"], [fake_rule])

    def test_permissions_without_fs_excluded_tools_do_not_add_filesystem_middleware(self):
        """fs_excluded_tools가 비어있으면 이름 치환 자체가 안 일어난다 — 이때는
        deepagents 자동 생성분이 top-level `permissions` kwarg를 그대로 받으므로
        여기서 별도로 middleware를 추가할 필요가 없다."""
        fake_rule = Mock(name="fake-permission")
        with patch(f"{COMPAT_MODULE}.create_deep_agent") as mock_create:
            create_root_graph(model=Mock(), system_prompt="p", permissions=[fake_rule])

        _args, kwargs = mock_create.call_args
        self.assertEqual(kwargs["middleware"], [])

    def test_permissions_with_fs_excluded_tools_reach_the_replacement_filesystem_middleware(self):
        """이 테스트가 §5에서 확인한 실제 버그(치환 시 `_permissions`가 조용히
        사라짐)의 회귀를 잡는다."""
        from deepagents.middleware.filesystem import FilesystemMiddleware

        fake_rule = Mock(name="fake-permission")
        with patch(f"{COMPAT_MODULE}.create_deep_agent") as mock_create:
            create_root_graph(
                model=Mock(),
                system_prompt="p",
                permissions=[fake_rule],
                fs_excluded_tools=frozenset({"delete"}),
            )

        _args, kwargs = mock_create.call_args
        # 최상위 kwarg도 여전히 넘어가야 한다(general-purpose 서브에이전트가
        # spec.get("permissions", permissions)로 상속받는 경로에 필요).
        self.assertEqual(kwargs["permissions"], [fake_rule])
        appended = kwargs["middleware"][-1]
        self.assertIsInstance(appended, FilesystemMiddleware)
        self.assertEqual(appended._permissions, [fake_rule])


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


class CreateChildGraphFilesystemAndInterruptTests(SimpleTestCase):
    """Child에도 Root와 같은 근거로 `fs_excluded_tools`/`interrupt_on`을 받는다."""

    def test_no_fs_excluded_tools_does_not_add_filesystem_middleware(self):
        with patch(f"{COMPAT_MODULE}.create_deep_agent") as mock_create:
            create_child_graph(model=Mock(), system_prompt="p")

        _args, kwargs = mock_create.call_args
        self.assertEqual(kwargs["middleware"], [])

    def test_excluded_tools_appends_filesystem_middleware_without_them(self):
        from deepagents.middleware.filesystem import FilesystemMiddleware

        with patch(f"{COMPAT_MODULE}.create_deep_agent") as mock_create:
            create_child_graph(
                model=Mock(),
                system_prompt="p",
                fs_excluded_tools=frozenset({"delete"}),
            )

        _args, kwargs = mock_create.call_args
        appended = kwargs["middleware"][-1]
        self.assertIsInstance(appended, FilesystemMiddleware)
        tool_names = {t.name for t in appended.tools}
        self.assertNotIn("delete", tool_names)
        self.assertIn("read_file", tool_names)

    def test_child_filesystem_middleware_uses_default_backend_not_a_shared_one(self):
        """Child는 backend를 따로 안 받는다(장기 메모리는 Root 전용) — deepagents
        기본값(StateBackend)으로 떨어지는지 확인한다."""

        from deepagents.backends import StateBackend

        with patch(f"{COMPAT_MODULE}.create_deep_agent") as mock_create:
            create_child_graph(
                model=Mock(),
                system_prompt="p",
                fs_excluded_tools=frozenset({"delete"}),
            )

        _args, kwargs = mock_create.call_args
        appended = kwargs["middleware"][-1]
        self.assertIsInstance(appended.backend, StateBackend)

    def test_no_interrupt_on_is_not_passed_through(self):
        with patch(f"{COMPAT_MODULE}.create_deep_agent") as mock_create:
            create_child_graph(model=Mock(), system_prompt="p")

        _args, kwargs = mock_create.call_args
        self.assertNotIn("interrupt_on", kwargs)

    def test_interrupt_on_passed_through_unchanged(self):
        wanted = {"task_register": True}
        with patch(f"{COMPAT_MODULE}.create_deep_agent") as mock_create:
            create_child_graph(model=Mock(), system_prompt="p", interrupt_on=wanted)

        _args, kwargs = mock_create.call_args
        self.assertEqual(kwargs["interrupt_on"], wanted)


class DelegationToolNameTests(SimpleTestCase):
    def test_matches_events_module_constant(self):
        from services.agent_runtime.events import DELEGATION_TOOL_NAME as events_value

        self.assertEqual(DELEGATION_TOOL_NAME, events_value)
