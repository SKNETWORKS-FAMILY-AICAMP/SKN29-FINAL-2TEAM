"""runtime_policy.py(RuntimeCapabilityPolicy) 단위 테스트.

정본: docs/작업기록/Deep_Agents/2026-08-13_04_작업자B_실행코어_세부계획.md §6-4

숫자 자체를 검증하는 게 아니라(그건 정책 값이라 바뀔 수 있다), "방어선(ceiling)이
실제로 적용되는가", "Root/Child는 이 클래스가 새 기본값을 만들지 않는가" 같은
**규칙**을 검증한다. 맨 끝에서 실제 `ModelCallLimitMiddleware`/`ToolCallLimitMiddleware`를
진짜로 만들어서 이 정책 값이 그대로 물려도 되는지 확인한다(langchain을 mock하지 않음).
"""

from django.test import SimpleTestCase
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware

from services.agent_runtime.runtime_policy import (
    DEFAULT_EXCLUDED_BUILTIN_TOOLS,
    DEFAULT_WRITE_TOOL_ALLOWED_ROLES,
    RuntimeCapabilityPolicy,
)


class DefaultExcludedBuiltinToolsTests(SimpleTestCase):
    def test_excludes_only_delete(self):
        """가상 파일 도구 중 **`delete` 만** 막는다.

        전에는 일곱 개를 전부 제외한다고 단언했는데 코드는 `delete` 하나만
        막고 있었다 — 병합해 보고서야 어긋난 것이 드러났다(2026-08-15).
        **코드 쪽이 의도한 것이 맞다고 확인받았다**(지훈). 읽기·쓰기 도구를
        열어 두는 것이 Deep Agent 런타임의 전제라, 테스트를 코드에 맞춘다.

        같은 파일의 `EXTERNAL_WRITE_TOOLS_POLICY_NOTE` 는 **외부 시스템**에
        쓰는 도구 이야기다. 여기서 여는 것은 런타임의 가상 파일이라 다른 층이다.
        """

        self.assertEqual(DEFAULT_EXCLUDED_BUILTIN_TOOLS, frozenset({"delete"}))

    def test_does_not_exclude_execute(self):
        """execute는 SandboxBackend를 안 붙이면 애초에 안 생기는 도구라 제외 목록에 안 둔다."""

        self.assertNotIn("execute", DEFAULT_EXCLUDED_BUILTIN_TOOLS)


class RuntimeCapabilityPolicyDefaultsTests(SimpleTestCase):
    def setUp(self):
        self.policy = RuntimeCapabilityPolicy()

    def test_todo_disabled_by_default(self):
        """2026-08-18, §5 Phase 4부터 `middleware/factory.py.build()`가 이 값을
        실제로 읽는다(`tests/test_middleware_factory.py::BuildTodoWiringTests`) —
        여기서는 "명시적으로 켜지 않으면 꺼져 있다"는 기본값 계약만 확인한다."""
        self.assertFalse(self.policy.enable_todo)

    def test_uses_default_excluded_builtin_tools(self):
        self.assertEqual(self.policy.excluded_builtin_tools, DEFAULT_EXCLUDED_BUILTIN_TOOLS)

    def test_is_immutable(self):
        with self.assertRaises(Exception):
            self.policy.enable_todo = True  # frozen dataclass


class GeneralPurposeLimitsTests(SimpleTestCase):
    def test_returns_configured_defaults_when_under_ceiling(self):
        policy = RuntimeCapabilityPolicy(
            general_purpose_max_model_calls=6,
            general_purpose_max_tool_calls=12,
            max_model_calls_ceiling=20,
            max_tool_calls_ceiling=40,
        )

        limits = policy.limits_for_general_purpose()

        self.assertEqual(limits.max_model_calls, 6)
        self.assertEqual(limits.max_tool_calls, 12)

    def test_ceiling_caps_general_purpose_defaults_when_configured_higher(self):
        """설정 실수로 GP 기본값이 방어선보다 크게 잡혀도 방어선을 넘지 않는다."""

        policy = RuntimeCapabilityPolicy(
            general_purpose_max_model_calls=999,
            general_purpose_max_tool_calls=999,
            max_model_calls_ceiling=20,
            max_tool_calls_ceiling=40,
        )

        limits = policy.limits_for_general_purpose()

        self.assertEqual(limits.max_model_calls, 20)
        self.assertEqual(limits.max_tool_calls, 40)


class ResolveModelCallLimitTests(SimpleTestCase):
    def test_passes_through_when_under_ceiling(self):
        policy = RuntimeCapabilityPolicy(max_model_calls_ceiling=20)

        self.assertEqual(policy.resolve_model_call_limit(requested=6), 6)

    def test_applies_ceiling_when_requested_exceeds_it(self):
        """사용자가 max_iterations를 500처럼 비정상적으로 크게 넣어도 방어선을 넘지 않는다."""

        policy = RuntimeCapabilityPolicy(max_model_calls_ceiling=20)

        self.assertEqual(policy.resolve_model_call_limit(requested=500), 20)

    def test_account_role_is_optional_and_does_not_change_result_yet(self):
        """2026-08-18, Phase 2: `account_role`은 구조만 열어둔 파라미터다 — 아직
        역할별로 실제 값을 분기하지 않으므로 어떤 역할을 넘겨도(안 넘겨도) 결과가
        같아야 한다. 역할별 실제 차등 값이 확정되면 이 테스트가 갈라져야 한다."""

        policy = RuntimeCapabilityPolicy(max_model_calls_ceiling=20)

        self.assertEqual(policy.resolve_model_call_limit(requested=6), 6)
        self.assertEqual(policy.resolve_model_call_limit(requested=6, account_role="leader"), 6)
        self.assertEqual(policy.resolve_model_call_limit(requested=6, account_role="member"), 6)


class ResolveToolCallLimitTests(SimpleTestCase):
    def test_defaults_to_ceiling_when_no_request(self):
        """Root/Child에는 tool-call 전용 사용자 설정 필드가 없으므로 방어선 값을 그대로 쓴다."""

        policy = RuntimeCapabilityPolicy(max_tool_calls_ceiling=40)

        self.assertEqual(policy.resolve_tool_call_limit(), 40)

    def test_applies_ceiling_when_requested_exceeds_it(self):
        policy = RuntimeCapabilityPolicy(max_tool_calls_ceiling=40)

        self.assertEqual(policy.resolve_tool_call_limit(requested=999), 40)

    def test_account_role_is_optional_and_does_not_change_result_yet(self):
        """`resolve_model_call_limit`과 같은 이유 — 구조만 확장, 아직 값 분기 없음."""

        policy = RuntimeCapabilityPolicy(max_tool_calls_ceiling=40)

        self.assertEqual(policy.resolve_tool_call_limit(), 40)
        self.assertEqual(policy.resolve_tool_call_limit(account_role="leader"), 40)
        self.assertEqual(policy.resolve_tool_call_limit(account_role="member"), 40)


class MiddlewareIntegrationTests(SimpleTestCase):
    """이 정책 값이 실제 LangChain 미들웨어 생성자에 그대로 물려도 되는지 확인한다."""

    def test_builds_real_model_call_limit_middleware_from_policy_values(self):
        policy = RuntimeCapabilityPolicy()
        limits = policy.limits_for_general_purpose()

        middleware = ModelCallLimitMiddleware(run_limit=limits.max_model_calls, exit_behavior="error")

        self.assertEqual(middleware.run_limit, limits.max_model_calls)
        self.assertIsNone(middleware.thread_limit)  # 체크포인터가 아직 없어(스텁) thread_limit은 안 씀

    def test_builds_real_tool_call_limit_middleware_from_policy_values(self):
        policy = RuntimeCapabilityPolicy()
        limits = policy.limits_for_general_purpose()

        middleware = ToolCallLimitMiddleware(run_limit=limits.max_tool_calls, exit_behavior="error")

        self.assertEqual(middleware.run_limit, limits.max_tool_calls)


class DefaultWriteToolAllowedRolesTests(SimpleTestCase):
    def test_only_leader_allowed_by_default(self):
        self.assertEqual(DEFAULT_WRITE_TOOL_ALLOWED_ROLES, frozenset({"leader"}))


class IsToolAllowedForRoleTests(SimpleTestCase):
    def setUp(self):
        self.policy = RuntimeCapabilityPolicy()

    def test_non_side_effect_tool_allowed_for_leader(self):
        self.assertTrue(self.policy.is_tool_allowed_for_role(side_effect=False, account_role="leader"))

    def test_non_side_effect_tool_allowed_for_member(self):
        self.assertTrue(self.policy.is_tool_allowed_for_role(side_effect=False, account_role="member"))

    def test_side_effect_tool_allowed_for_leader(self):
        self.assertTrue(self.policy.is_tool_allowed_for_role(side_effect=True, account_role="leader"))

    def test_side_effect_tool_blocked_for_member(self):
        """팀원은 쓰기(side_effect=True) 도구를 **실행**할 수 없다 — 사용자 명시
        요구사항. 노출(모델에게 보여주는 것)은 더는 이 판단을 안 탄다
        (2026-08-19 정책 변경 — `factory.py`의 `build()`가 역할과 무관하게
        전부 보여주고, 이 함수는 `_run()`의 실행 시점 확인에만 쓰인다)."""

        self.assertFalse(self.policy.is_tool_allowed_for_role(side_effect=True, account_role="member"))
