"""prompts.py(RuntimePromptAssembler) 단위 테스트.

2026-08-14 결정 — 레거시 `services/harness/scaffold.py`의 `COMMON_SCAFFOLD`를
새 엔진에 통째로 재사용하지 않는다: 코드가 이미 강제하는 것(호출 상한 등)을
프롬프트에 다시 적으면 두 번째 진실 공급원이 된다. 이 테스트는 그 결정이
지켜지는지와, Root/Child/GP 세 조립 결과가 서로 다른 내용을 담는지를 확인한다.

2026-08-18 뒤집힘 — "확인 카드"는 예외가 됐다. HITL 승인·재개가 이 엔진에도
붙어서(`factory.py`의 `interrupt_on` → `events.py`의 `awaiting_confirmation` →
`api_views.py`의 재개), 이제는 **언급하지 않는 쪽이 거짓**이다.
"""

from django.test import SimpleTestCase

from services.agent_runtime.prompts import RUNTIME_SCAFFOLD, RuntimePromptAssembler


class RuntimeScaffoldContentTests(SimpleTestCase):
    """레거시 COMMON_SCAFFOLD를 그대로 재사용하지 않았는지 확인한다."""

    def test_mentions_the_confirmation_card(self):
        # 2026-08-18에 HITL이 실제로 붙었다 — 이제는 말해야 한다. 게이트를
        # 모르면 모델이 (1) 카드가 이미 묻는 것을 말로 한 번 더 묻고,
        # (2) 승인 전인데 "등록했습니다"라고 끝난 것처럼 말한다.
        self.assertIn("확인 카드", RUNTIME_SCAFFOLD)
        self.assertIn("승인", RUNTIME_SCAFFOLD)

    def test_does_not_restate_limits_already_enforced_by_middleware(self):
        # 호출 횟수 상한은 ModelCallLimitMiddleware/ToolCallLimitMiddleware가
        # 이미 코드로 강제한다 — 프롬프트에 숫자를 다시 적으면 코드 쪽 정책이
        # 바뀌었을 때 프롬프트만 옛 숫자를 계속 말하는 두 번째 진실 공급원이 된다.
        self.assertNotIn("회", RUNTIME_SCAFFOLD)


    def test_injection_guard_lives_only_in_the_memory_prompt(self):
        # 2026-08-20 팀 결정 — 도구 결과 인젝션 방어 문구는 이 Scaffold 에서
        # 뺐다(의도적). 같은 취지가 `_MEMORY_ROUTING_PROMPT` 에는 남아 메모리
        # 채널만 덮는다. 되살릴 때는 이 테스트를 먼저 뒤집을 것.
        from services.agent_runtime.memory.backend import _MEMORY_ROUTING_PROMPT

        self.assertNotIn("지시가 아니라 데이터", RUNTIME_SCAFFOLD)
        self.assertIn("지시가 아니라 데이터", _MEMORY_ROUTING_PROMPT)


class AssembleRootTests(SimpleTestCase):
    def test_includes_both_scaffold_and_agent_prompt(self):
        result = RuntimePromptAssembler().assemble_root(agent_prompt="문서를 요약해라.")

        self.assertIn("문서를 요약해라.", result)
        self.assertIn("근거", result)  # 공통 Scaffold의 일부.

    def test_empty_agent_prompt_still_returns_the_scaffold(self):
        result = RuntimePromptAssembler().assemble_root(agent_prompt="")

        self.assertEqual(result, RUNTIME_SCAFFOLD)

    def test_agent_prompt_is_stripped(self):
        result = RuntimePromptAssembler().assemble_root(agent_prompt="  공백 포함  ")

        self.assertIn("공백 포함", result)
        self.assertNotIn("  공백 포함  ", result)


class AssembleChildTests(SimpleTestCase):
    def test_includes_scaffold_agent_prompt_and_delegation_scope_addendum(self):
        result = RuntimePromptAssembler().assemble_child(agent_prompt="Jira 이슈를 생성해라.")

        self.assertIn("Jira 이슈를 생성해라.", result)
        self.assertIn("근거", result)  # 공통 Scaffold.
        self.assertIn("위임 범위", result)  # Child 전용 추가 지침.

    def test_child_prompt_differs_from_root_prompt_for_the_same_agent_prompt(self):
        assembler = RuntimePromptAssembler()

        root = assembler.assemble_root(agent_prompt="같은 지시")
        child = assembler.assemble_child(agent_prompt="같은 지시")

        self.assertNotEqual(root, child)
        self.assertIn("위임 범위", child)
        self.assertNotIn("위임 범위", root)


class AssembleGeneralPurposeTests(SimpleTestCase):
    def test_includes_scaffold_and_the_given_gp_prompt(self):
        result = RuntimePromptAssembler().assemble_general_purpose(gp_prompt="GP 기본 지시문")

        self.assertIn("GP 기본 지시문", result)
        self.assertIn("근거", result)  # 공통 Scaffold.

    def test_does_not_include_the_child_only_delegation_scope_addendum(self):
        result = RuntimePromptAssembler().assemble_general_purpose(gp_prompt="GP 기본 지시문")

        self.assertNotIn("위임 범위", result)
