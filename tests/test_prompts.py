"""prompts.py(RuntimePromptAssembler) 단위 테스트.

2026-08-14 결정 — 레거시 `services/harness/scaffold.py`의 `COMMON_SCAFFOLD`를
새 엔진에 그대로 재사용하지 않는다: 그 문구가 언급하는 "확인 카드"(HITL 승인)는
아직 이 엔진에 없다. 이 테스트는 그 결정이 실제로 지켜지는지(없는 기능을
언급하지 않는지)와, Root/Child/GP 세 조립 결과가 서로 다른 내용을 담는지를
확인한다.
"""

from django.test import SimpleTestCase

from services.agent_runtime.prompts import RUNTIME_SCAFFOLD, RuntimePromptAssembler


class RuntimeScaffoldContentTests(SimpleTestCase):
    """레거시 COMMON_SCAFFOLD를 그대로 재사용하지 않았는지 확인한다."""

    def test_does_not_mention_the_not_yet_implemented_confirmation_card(self):
        # 레거시(services/harness/scaffold.py)는 "확인 카드"를 언급한다 — 그
        # HITL 승인·재개 기능은 새 엔진에 아직 없다(⑨ 이후 순번, 계획 문서에
        # 미착수로 기록됨). 없는 기능을 LLM에게 있다고 말하면 안 된다.
        self.assertNotIn("확인 카드", RUNTIME_SCAFFOLD)

    def test_does_not_restate_limits_already_enforced_by_middleware(self):
        # 호출 횟수 상한은 ModelCallLimitMiddleware/ToolCallLimitMiddleware가
        # 이미 코드로 강제한다 — 프롬프트에 숫자를 다시 적으면 코드 쪽 정책이
        # 바뀌었을 때 프롬프트만 옛 숫자를 계속 말하는 두 번째 진실 공급원이 된다.
        self.assertNotIn("회", RUNTIME_SCAFFOLD)


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
