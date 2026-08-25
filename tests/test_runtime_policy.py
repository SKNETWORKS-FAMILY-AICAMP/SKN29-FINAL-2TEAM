"""runtime_policy.py(RuntimeCapabilityPolicy) 단위 테스트.

정본: docs/설계 및 구현/중간발표 이후/작업기록/Deep_Agents/2026-08-13_04_작업자B_실행코어_세부계획.md §6-4

숫자 자체를 검증하는 게 아니라(그건 정책 값이라 바뀔 수 있다), "방어선(ceiling)이
실제로 적용되는가", "Root/Child는 이 클래스가 새 기본값을 만들지 않는가" 같은
**규칙**을 검증한다. 맨 끝에서 실제 `ModelCallLimitMiddleware`/`ToolCallLimitMiddleware`를
진짜로 만들어서 이 정책 값이 그대로 물려도 되는지 확인한다(langchain을 mock하지 않음).
"""

from django.test import SimpleTestCase
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware

from services.agent_runtime.runtime_policy import (
    DEFAULT_EXCLUDED_BUILTIN_TOOLS,
    DEFAULT_MCP_TOOL_CALL_TIMEOUT_SECONDS,
    DEFAULT_WRITE_TOOL_ALLOWED_ROLES,
    GUNICORN_WORKER_TIMEOUT_SECONDS,
    MAX_MCP_TOOL_CALL_TIMEOUT_SECONDS,
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

    def test_todo_enabled_by_default(self):
        """2026-08-18, §5 Phase 4부터 `middleware/factory.py.build()`가 이 값을
        실제로 읽는다(`tests/test_middleware_factory.py::BuildTodoWiringTests`).

        **2026-08-19에 기본값이 False → True로 바뀌었다**(`17e8c62`, 사용자
        요청 — Root/Child/GP 전부에 `write_todos`가 기본으로 붙는다). 이
        테스트는 그때 같이 안 고쳐져서 옛 기본값(False)을 검증한 채로 남아
        있었다 — 2026-08-21에 실제 정책 값에 맞춘다(`2026-08-21_01` §8이
        정리한 것과 같은 종류의 낡은 테스트)."""
        self.assertTrue(self.policy.enable_todo)

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
    def test_leader_and_member_allowed_by_default(self):
        """2026-08-20부터 팀원도 포함한다(`17e8c62`) — 근거와 그 대가(자기
        승인 HITL)는 `IsToolAllowedForRoleTests.
        test_side_effect_tool_allowed_for_member` docstring 참고."""
        self.assertEqual(DEFAULT_WRITE_TOOL_ALLOWED_ROLES, frozenset({"leader", "member"}))


class IsToolAllowedForRoleTests(SimpleTestCase):
    def setUp(self):
        self.policy = RuntimeCapabilityPolicy()

    def test_non_side_effect_tool_allowed_for_leader(self):
        self.assertTrue(self.policy.is_tool_allowed_for_role(side_effect=False, account_role="leader"))

    def test_non_side_effect_tool_allowed_for_member(self):
        self.assertTrue(self.policy.is_tool_allowed_for_role(side_effect=False, account_role="member"))

    def test_side_effect_tool_allowed_for_leader(self):
        self.assertTrue(self.policy.is_tool_allowed_for_role(side_effect=True, account_role="leader"))

    def test_side_effect_tool_allowed_for_member(self):
        """**2026-08-20부터 팀원도 쓰기(side_effect=True) 도구를 실행할 수
        있다**(`17e8c62`, 사용자 요청 — "팀원이 자기 업무를 직접 등록할 수
        있게 하고 싶다").

        방어선이 없어진 게 아니라 옮겨갔다: 예전엔 "역할이 아니면 즉시 거부"가
        유일한 경계였는데, 이제 `factory.py`의 `build()`가 `interrupt_on`을
        만들 때 **같은 함수**를 다시 부르므로 팀원의 쓰기 호출도 팀장과 똑같이
        HITL 확인 카드(자기 승인)를 거친다. 자세한 배경은
        `docs/설계 및 구현/중간발표 이후/작업기록/Deep_Agents/2026-08-21_02_MCP_승인_범위_변경_반영.md`.

        이 테스트는 그 변경 때 같이 안 고쳐져서 옛 동작(member 차단)을 검증한
        채로 남아 있었다 — 2026-08-21에 실제 정책에 맞춘다."""

        self.assertTrue(self.policy.is_tool_allowed_for_role(side_effect=True, account_role="member"))


class TimeoutForMcpToolTests(SimpleTestCase):
    """2026-08-21, A-1 — `timeout_for_mcp_tool()`.

    2026-08-19의 `timeout_for_tool()`(전역 300초, 모든 도구 대상)을 대체한다.
    그 설계는 `17e8c62`에서 되돌려졌고, 이 테스트도 그때 같이 지워졌어야 했는데
    남아 있어서 import부터 깨져 있었다(`2026-08-21_01` §8).

    숫자 자체는 대부분 계약으로 검증하지 않지만(정책 값이라 바뀔 수 있다),
    **gunicorn 한도와의 관계만은 예외로 고정한다** — 그게 이 값의 유일한
    근거이기 때문이다(`2026-08-21_01` §4).
    """

    def test_default_is_below_gunicorn_worker_timeout(self):
        """이 값의 근거는 "MCP가 보통 이 정도 걸린다"가 아니라 "gunicorn이
        워커를 죽이기 전에 우리가 먼저 끊는다"다 — 그러므로 gunicorn 한도보다
        확실히 작아야 한다는 것 자체가 계약이다."""
        self.assertLess(DEFAULT_MCP_TOOL_CALL_TIMEOUT_SECONDS, GUNICORN_WORKER_TIMEOUT_SECONDS)
        self.assertLess(MAX_MCP_TOOL_CALL_TIMEOUT_SECONDS, GUNICORN_WORKER_TIMEOUT_SECONDS)

    def test_uses_default_when_no_override_registered(self):
        policy = RuntimeCapabilityPolicy()

        self.assertEqual(
            policy.timeout_for_mcp_tool("mcp:MT001"), DEFAULT_MCP_TOOL_CALL_TIMEOUT_SECONDS
        )

    def test_uses_configured_default_when_no_override_registered(self):
        policy = RuntimeCapabilityPolicy(mcp_tool_call_timeout_seconds=42)

        self.assertEqual(policy.timeout_for_mcp_tool("mcp:MT001"), 42)

    def test_override_takes_precedence_over_default(self):
        policy = RuntimeCapabilityPolicy(
            mcp_tool_call_timeout_seconds=300, mcp_tool_call_timeout_overrides={"mcp:MT001": 15}
        )

        self.assertEqual(policy.timeout_for_mcp_tool("mcp:MT001"), 15)
        self.assertEqual(policy.timeout_for_mcp_tool("mcp:MT999"), 300)

    def test_override_cannot_exceed_the_ceiling(self):
        """override로 gunicorn 한도를 넘겨 버리면 이 미들웨어가 끊기 전에 워커가
        먼저 죽어서 있으나 마나가 된다 — 그래서 값 자체를 상한으로 자른다
        (`2026-08-21_01` §5)."""
        policy = RuntimeCapabilityPolicy(
            mcp_tool_call_timeout_overrides={"mcp:MT001": GUNICORN_WORKER_TIMEOUT_SECONDS + 100}
        )

        self.assertEqual(policy.timeout_for_mcp_tool("mcp:MT001"), MAX_MCP_TOOL_CALL_TIMEOUT_SECONDS)

    def test_configured_default_cannot_exceed_the_ceiling(self):
        policy = RuntimeCapabilityPolicy(mcp_tool_call_timeout_seconds=99999)

        self.assertEqual(policy.timeout_for_mcp_tool("mcp:MT001"), MAX_MCP_TOOL_CALL_TIMEOUT_SECONDS)

    def test_default_overrides_dict_is_empty(self):
        """미리 모든 MCP 도구를 "빠름/느림"으로 분류하지 않는다 — 실제로 문제가
        확인된 것만 나중에 넣는다(`2026-08-21_01` §5)."""
        policy = RuntimeCapabilityPolicy()

        self.assertEqual(policy.mcp_tool_call_timeout_overrides, {})
