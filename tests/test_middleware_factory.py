"""middleware/factory.py(MiddlewareFactory) 단위 테스트.

실제 ModelCallLimitMiddleware/ToolCallLimitMiddleware(langchain)를 만들어서
runtime_policy.py 값이 그대로 반영되는지 확인한다(mock 아님).
"""

from django.test import SimpleTestCase
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    PIIMiddleware,
    TodoListMiddleware,
    ToolCallLimitMiddleware,
)
from langchain_core.messages import AIMessage, HumanMessage

from services.agent_runtime.context import RuntimeContext
from services.agent_runtime.definitions import AgentDefinition
from services.agent_runtime.middleware.factory import MiddlewareFactory
from services.agent_runtime.middleware.sensitive_input import SensitiveInputMaskMiddleware
from services.agent_runtime.runtime_policy import RuntimeCapabilityPolicy


def _context(**overrides) -> RuntimeContext:
    fields = {"account_id": "UA001", "team_id": "TM001", "role": "leader"}
    fields.update(overrides)
    return RuntimeContext(**fields)


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

    def test_accepts_real_context_without_changing_result_yet(self):
        """2026-08-18, Phase 2: `context`(→ `account_role`)를 넘겨도 아직 실제
        역할별 값 분기가 없으므로 `context=None`일 때와 결과가 같아야 한다 —
        `runtime_policy.py`의 `resolve_*_limit` docstring 참고."""

        middleware = self.factory.build(
            definition=_definition(max_iterations=6), context=_context(role="leader")
        )

        model_limit = next(m for m in middleware if isinstance(m, ModelCallLimitMiddleware))
        tool_limit = next(m for m in middleware if isinstance(m, ToolCallLimitMiddleware))
        self.assertEqual(model_limit.run_limit, 6)
        self.assertEqual(tool_limit.run_limit, 40)

    def test_member_context_does_not_change_result_yet(self):
        middleware = self.factory.build(
            definition=_definition(max_iterations=6), context=_context(role="member")
        )

        model_limit = next(m for m in middleware if isinstance(m, ModelCallLimitMiddleware))
        self.assertEqual(model_limit.run_limit, 6)


class BuildTodoWiringTests(SimpleTestCase):
    """2026-08-18, §5 Phase 4 — `runtime_policy.enable_todo`가 실제로 읽히는지.

    **2026-08-19에 기본값이 False → True로 바뀌었다**(`17e8c62`, 사용자 요청).
    그래서 "기본값에서는 안 붙는다"가 아니라 "기본값에서 붙고, 명시적으로 끄면
    안 붙는다"를 검증한다 — 아래 두 테스트가 양쪽 방향을 다 덮는다."""

    def test_enabled_by_default_adds_todo_middleware(self):
        policy = RuntimeCapabilityPolicy()
        factory = MiddlewareFactory(runtime_policy=policy)

        middleware = factory.build(definition=_definition(), context=None)

        self.assertTrue(any(isinstance(m, TodoListMiddleware) for m in middleware))

    def test_explicitly_disabled_omits_todo_middleware(self):
        """정책 값이 실제로 읽히는지(=하드코딩이 아닌지) 확인하는 반대 방향."""
        policy = RuntimeCapabilityPolicy(enable_todo=False)
        factory = MiddlewareFactory(runtime_policy=policy)

        middleware = factory.build(definition=_definition(), context=None)

        self.assertFalse(any(isinstance(m, TodoListMiddleware) for m in middleware))

    def test_enabled_adds_todo_middleware(self):
        policy = RuntimeCapabilityPolicy(enable_todo=True)
        factory = MiddlewareFactory(runtime_policy=policy)

        middleware = factory.build(definition=_definition(), context=None)

        todo = next(m for m in middleware if isinstance(m, TodoListMiddleware))
        self.assertIsInstance(todo, TodoListMiddleware)

    def test_enabled_keeps_default_langchain_system_prompt(self):
        """2026-08-18 정정 — 예전엔 `system_prompt=""`로 껐었다("중복 방지"라고
        적었지만, `RUNTIME_SCAFFOLD`를 실제로 읽어보니 겹치는 내용이 없었다 —
        §5 Phase 4 계획 문서 참고). 근거 없이 실제 검증된 LangChain 기본
        안내문을 지웠던 것이므로, 이제 인자를 안 넘겨 기본값 그대로 쓰인다."""

        from langchain.agents.middleware.todo import WRITE_TODOS_SYSTEM_PROMPT

        policy = RuntimeCapabilityPolicy(enable_todo=True)
        factory = MiddlewareFactory(runtime_policy=policy)

        middleware = factory.build(definition=_definition(), context=None)

        todo = next(m for m in middleware if isinstance(m, TodoListMiddleware))
        self.assertEqual(todo.system_prompt, WRITE_TODOS_SYSTEM_PROMPT)

    def test_enabled_tool_description_extends_default_with_distinguishing_paragraph(self):
        from langchain.agents.middleware.todo import WRITE_TODOS_TOOL_DESCRIPTION

        policy = RuntimeCapabilityPolicy(enable_todo=True)
        factory = MiddlewareFactory(runtime_policy=policy)

        middleware = factory.build(definition=_definition(), context=None)

        todo = next(m for m in middleware if isinstance(m, TodoListMiddleware))
        self.assertTrue(todo.tool_description.startswith(WRITE_TODOS_TOOL_DESCRIPTION))
        self.assertIn("task_register", todo.tool_description)
        self.assertIn("task_update", todo.tool_description)

    def test_enabled_does_not_remove_existing_call_limit_middleware(self):
        policy = RuntimeCapabilityPolicy(enable_todo=True, max_model_calls_ceiling=20, max_tool_calls_ceiling=40)
        factory = MiddlewareFactory(runtime_policy=policy)

        middleware = factory.build(definition=_definition(), context=None)

        self.assertTrue(any(isinstance(m, ModelCallLimitMiddleware) for m in middleware))
        self.assertTrue(any(isinstance(m, ToolCallLimitMiddleware) for m in middleware))


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

    def test_never_includes_todo_middleware_even_when_enabled(self):
        """2026-08-18, §5 Phase 4 — 계획서가 명시한 배선 지점은 `build()`뿐이다
        (`middleware/factory.py.build()에서 ... 배선`) — GP에는 안 붙는다."""

        policy = RuntimeCapabilityPolicy(enable_todo=True)
        factory = MiddlewareFactory(runtime_policy=policy)

        middleware = factory.build_for_general_purpose()

        self.assertFalse(any(isinstance(m, TodoListMiddleware) for m in middleware))


class McpToolCallTimeoutWiringTests(SimpleTestCase):
    """2026-08-21, A-1 — `build()`가 `McpToolCallTimeoutMiddleware`를 붙이는지,
    그 인스턴스가 같은 `runtime_policy`를 참조하는지 확인한다.

    2026-08-19의 같은 이름 테스트는 전역 timeout(모든 도구 대상, GP 포함)을
    검증했는데, 그 설계가 `17e8c62`에서 되돌려지면서 import부터 깨져 있었다
    (`2026-08-21_01` §8). 새 설계에 맞춰 다시 썼다.
    """

    def test_build_includes_mcp_tool_call_timeout_middleware(self):
        from services.agent_runtime.middleware.tool_timeout import McpToolCallTimeoutMiddleware

        policy = RuntimeCapabilityPolicy()
        factory = MiddlewareFactory(runtime_policy=policy)

        middleware = factory.build(definition=_definition(), context=None)

        timeout_mw = next(m for m in middleware if isinstance(m, McpToolCallTimeoutMiddleware))
        self.assertIs(timeout_mw._runtime_policy, policy)

    def test_build_for_general_purpose_does_not_include_it(self):
        """GP는 `side_effect=False` 도구만 물려받고(2026-08-20, `factory.py`의
        `gp_read_only_tools`) MCP 도구는 전부 `side_effect=True`라, GP에는 MCP
        도구가 아예 안 들어간다 — 여기 붙이면 영원히 아무것도 안 하는 죽은
        미들웨어가 된다(`middleware/factory.py`의
        `build_for_general_purpose()` docstring)."""
        from services.agent_runtime.middleware.tool_timeout import McpToolCallTimeoutMiddleware

        factory = MiddlewareFactory(runtime_policy=RuntimeCapabilityPolicy())

        middleware = factory.build_for_general_purpose()

        self.assertFalse(any(isinstance(m, McpToolCallTimeoutMiddleware) for m in middleware))


class PiiMiddlewareWiringTests(SimpleTestCase):
    """2026-08-24, PIIMiddleware 도입 — `_build_pii_middleware()`/`build()`가
    실제로 credit_card/ip/mac_address 3종을 redact 전략·apply_to_input=True로
    붙이는지, GP에는 안 붙는지 확인한다(`middleware/factory.py` 23-43번째 줄
    주석, `_build_pii_middleware` 참고). 지금까지 이 부분에 대한 단위 테스트가
    없었다."""

    def setUp(self):
        self.factory = MiddlewareFactory(runtime_policy=RuntimeCapabilityPolicy())

    def test_build_adds_exactly_three_pii_middlewares(self):
        middleware = self.factory.build(definition=_definition(), context=None)

        pii_middlewares = [m for m in middleware if isinstance(m, PIIMiddleware)]
        self.assertEqual(len(pii_middlewares), 3)

    def test_build_covers_credit_card_ip_mac_address_only(self):
        middleware = self.factory.build(definition=_definition(), context=None)

        pii_types = {m.pii_type for m in middleware if isinstance(m, PIIMiddleware)}
        self.assertEqual(pii_types, {"credit_card", "ip", "mac_address"})

    def test_build_does_not_cover_email_or_url(self):
        """이메일·URL은 업무 대화에 정상적으로 섞여 있어 오탐이 잦다는 이유로
        의도적으로 뺐다(`middleware/factory.py` 23-30번째 줄 주석) — 그 결정이
        실제로 지켜지는지 반대 방향에서 확인한다."""
        middleware = self.factory.build(definition=_definition(), context=None)

        pii_types = {m.pii_type for m in middleware if isinstance(m, PIIMiddleware)}
        self.assertNotIn("email", pii_types)
        self.assertNotIn("url", pii_types)

    def test_build_uses_redact_strategy_and_covers_input_output_tool_results(self):
        """2026-08-25 — 사용자 입력뿐 아니라 모델 답변(`apply_to_output`)·도구
        실행 결과(`apply_to_tool_results`)도 검사 범위에 들어간다."""
        middleware = self.factory.build(definition=_definition(), context=None)

        pii_middlewares = [m for m in middleware if isinstance(m, PIIMiddleware)]
        for pii_middleware in pii_middlewares:
            self.assertEqual(pii_middleware.strategy, "redact")
            self.assertTrue(pii_middleware.apply_to_input)
            self.assertTrue(pii_middleware.apply_to_output)
            self.assertTrue(pii_middleware.apply_to_tool_results)

    def test_build_for_general_purpose_does_not_include_pii_middleware(self):
        """GP는 별도 `build_for_general_purpose()`를 쓰므로 PII 미들웨어가 아직
        안 붙는다(`build()` 107-111번째 줄 주석: "GP가 사용자 원문을 직접 보는
        경로가 생기면 그때 같은 줄을 추가한다") — 상위 에이전트가 이미 걸러줘서
        생략한 게 아니라, 아직 GP 경로가 그 위험에 노출되지 않았다는 판단이다."""
        middleware = self.factory.build_for_general_purpose()

        self.assertFalse(any(isinstance(m, PIIMiddleware) for m in middleware))

    def test_credit_card_in_user_message_is_redacted_before_model(self):
        """실제 `before_model` 훅을 돌려서 카드번호가 진짜로 가려지는지 확인한다
        (와이어링만 보고 "붙어 있으니 될 것"이라 가정하지 않는다)."""
        middleware = self.factory.build(definition=_definition(), context=None)
        credit_card_middleware = next(
            m for m in middleware if isinstance(m, PIIMiddleware) and m.pii_type == "credit_card"
        )

        state = {"messages": [HumanMessage(content="내 카드번호는 4111111111111111 이야")]}
        result = credit_card_middleware.before_model(state, runtime=None)

        self.assertIsNotNone(result)
        redacted_content = result["messages"][0].content
        self.assertNotIn("4111111111111111", redacted_content)
        self.assertIn("REDACTED", redacted_content)

    def test_ip_and_mac_address_in_user_message_are_each_redacted(self):
        ip_middleware = next(
            m
            for m in self.factory.build(definition=_definition(), context=None)
            if isinstance(m, PIIMiddleware) and m.pii_type == "ip"
        )
        mac_middleware = next(
            m
            for m in self.factory.build(definition=_definition(), context=None)
            if isinstance(m, PIIMiddleware) and m.pii_type == "mac_address"
        )

        ip_state = {"messages": [HumanMessage(content="서버 주소는 192.168.1.1 이야")]}
        ip_result = ip_middleware.before_model(ip_state, runtime=None)
        self.assertNotIn("192.168.1.1", ip_result["messages"][0].content)

        mac_state = {"messages": [HumanMessage(content="맥주소는 00:1A:2B:3C:4D:5E 야")]}
        mac_result = mac_middleware.before_model(mac_state, runtime=None)
        self.assertNotIn("00:1A:2B:3C:4D:5E", mac_result["messages"][0].content)

    def test_before_model_only_ever_inspects_the_last_human_message(self):
        """`before_model`은 항상 "가장 마지막 HumanMessage"만 본다 — 그 뒤에
        온 AIMessage의 카드번호는 이 훅의 검사 대상이 아니다(그건
        `after_model`의 몫, 아래 별도 테스트)."""
        middleware = self.factory.build(definition=_definition(), context=None)
        credit_card_middleware = next(
            m for m in middleware if isinstance(m, PIIMiddleware) and m.pii_type == "credit_card"
        )

        state = {
            "messages": [
                HumanMessage(content="안녕"),
                AIMessage(content="카드번호 4111111111111111 확인했습니다"),
            ]
        }
        result = credit_card_middleware.before_model(state, runtime=None)

        self.assertIsNone(result)

    def test_credit_card_in_ai_answer_is_redacted_after_model(self):
        """2026-08-25 — `apply_to_output=True`이므로 모델이 되풀이한 카드번호도
        `after_model` 훅에서 가려지는지 확인한다."""
        middleware = self.factory.build(definition=_definition(), context=None)
        credit_card_middleware = next(
            m for m in middleware if isinstance(m, PIIMiddleware) and m.pii_type == "credit_card"
        )

        state = {
            "messages": [
                HumanMessage(content="내 카드번호가 뭐였지?"),
                AIMessage(content="카드번호 4111111111111111 확인했습니다"),
            ]
        }
        result = credit_card_middleware.after_model(state, runtime=None)

        self.assertIsNotNone(result)
        redacted_content = result["messages"][-1].content
        self.assertNotIn("4111111111111111", redacted_content)
        self.assertIn("REDACTED", redacted_content)


class SensitiveInputMaskMiddlewareWiringTests(SimpleTestCase):
    """2026-08-26 — 상시 정규식 필터(§2-①)가 `MiddlewareFactory.build()`에서
    실제로 붙는지, GP에는 아직 안 붙는지 확인한다(`sensitive_input.py` 모듈
    docstring). PII 배선 테스트와 같은 구조다."""

    def setUp(self):
        self.factory = MiddlewareFactory(runtime_policy=RuntimeCapabilityPolicy())

    def test_build_adds_exactly_one_sensitive_input_mask(self):
        middleware = self.factory.build(definition=_definition(), context=None)

        matches = [m for m in middleware if isinstance(m, SensitiveInputMaskMiddleware)]
        self.assertEqual(len(matches), 1)

    def test_build_for_general_purpose_does_not_include_it(self):
        """GP는 사용자 원문을 직접 보는 경로가 아직 없다 — PII와 같은 판단
        (`_build_pii_middleware` 주석)."""
        middleware = self.factory.build_for_general_purpose()

        self.assertFalse(any(isinstance(m, SensitiveInputMaskMiddleware) for m in middleware))

    def test_credential_in_human_message_is_masked_before_model(self):
        """와이어링만 보고 "붙어 있으니 될 것"이라 가정하지 않는다 — 실제
        `before_model` 훅을 돌려서 확인한다."""
        middleware = self.factory.build(definition=_definition(), context=None)
        mask_middleware = next(m for m in middleware if isinstance(m, SensitiveInputMaskMiddleware))

        state = {"messages": [HumanMessage(content="내 API 키는 sk-abcdefghijklmnopqrstuvwx1234 입니다")]}
        result = mask_middleware.before_model(state, runtime=None)

        self.assertIsNotNone(result)
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwx1234", result["messages"][0].content)
