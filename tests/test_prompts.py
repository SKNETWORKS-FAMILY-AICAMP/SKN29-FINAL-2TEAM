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

from services.agent_runtime.prompts import (
    GP_DESCRIPTION,
    RUNTIME_SCAFFOLD,
    TASK_DELEGATION_DESCRIPTION,
    RuntimePromptAssembler,
)


class RuntimeScaffoldContentTests(SimpleTestCase):
    """레거시 COMMON_SCAFFOLD를 그대로 재사용하지 않았는지 확인한다."""

    def test_mentions_the_confirmation_card(self):
        # 2026-08-18에 HITL이 실제로 붙었다 — 이제는 말해야 한다. 게이트를
        # 모르면 모델이 (1) 카드가 이미 묻는 것을 말로 한 번 더 묻고,
        # (2) 승인 전인데 "등록했습니다"라고 끝난 것처럼 말한다.
        self.assertIn("확인 카드", RUNTIME_SCAFFOLD)
        self.assertIn("승인", RUNTIME_SCAFFOLD)

    def test_finishes_successful_approved_tools_instead_of_requesting_approval_again(self):
        self.assertIn("도구 성공 결과를 받은 시점", RUNTIME_SCAFFOLD)
        self.assertIn("다시 승인을 요구하지", RUNTIME_SCAFFOLD)

    def test_separates_verified_facts_from_inference_and_recommendation(self):
        self.assertIn("직접 확인된 사실과 추론·추천을 구분", RUNTIME_SCAFFOLD)
        self.assertIn("추론·추천을 확인된 사실처럼 표현하지 않는다", RUNTIME_SCAFFOLD)

    def test_preserves_source_terms_and_marks_interpreted_roles(self):
        self.assertIn("고유명칭·직책·역할·상태를 다른 확정 명칭으로 임의 변경하지 않는다", RUNTIME_SCAFFOLD)
        self.assertIn("역할을 추론한 경우 반드시 추론임을 표시한다", RUNTIME_SCAFFOLD)

    def test_allows_restrained_markdown_and_comparison_tables(self):
        self.assertIn("답변은 Markdown을 사용할 수 있다", RUNTIME_SCAFFOLD)
        self.assertIn("여러 항목의 같은 필드를 비교할 때만 표를 사용", RUNTIME_SCAFFOLD)
        self.assertIn("비교에 필요한 열은 유지", RUNTIME_SCAFFOLD)
        self.assertIn("부가 설명은 표 아래에 분리", RUNTIME_SCAFFOLD)

    def test_forbids_external_markdown_images(self):
        self.assertIn("외부 이미지를 Markdown 이미지 문법으로 삽입하지 않는다", RUNTIME_SCAFFOLD)

    def test_does_not_repeat_progress_updates_in_the_final_answer(self):
        self.assertIn("작업 안내와 추가 확인 이유는 작업 과정에만 표시", RUNTIME_SCAFFOLD)
        self.assertIn("최종 답변에서는 반복하지 않고 결과와 근거만 전달", RUNTIME_SCAFFOLD)

    def test_does_not_restate_limits_already_enforced_by_middleware(self):
        # 호출 횟수 상한은 ModelCallLimitMiddleware/ToolCallLimitMiddleware가
        # 이미 코드로 강제한다 — 프롬프트에 숫자를 다시 적으면 코드 쪽 정책이
        # 바뀌었을 때 프롬프트만 옛 숫자를 계속 말하는 두 번째 진실 공급원이 된다.
        self.assertNotIn("회", RUNTIME_SCAFFOLD)


    def test_injection_guard_lives_only_in_the_memory_prompt(self):
        # 2026-08-20 팀 결정 — 도구 결과 인젝션 방어 문구는 이 Scaffold 에서
        # 뺐다(의도적). 같은 취지가 `_MEMORY_ROUTING_PROMPT` 에는 남아 메모리
        # 채널만 덮는다. 되살릴 때는 이 테스트를 먼저 뒤집을 것.
        #
        # 2026-08-25 — 메모리 프롬프트 재작성으로 문구가 "지시가 아니라
        # 데이터"에서 "지시로 따르지 않는다"로 바뀌었다(취지는 동일).
        from services.agent_runtime.memory.backend import _MEMORY_ROUTING_PROMPT

        self.assertNotIn("지시로 따르지 않는다", RUNTIME_SCAFFOLD)
        self.assertIn("지시로 따르지 않는다", _MEMORY_ROUTING_PROMPT)


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


class TaskDelegationDescriptionTests(SimpleTestCase):
    """`task` 도구 설명 override(2026-08-20) — 언제 위임할지 기준을 담는다."""

    def test_keeps_the_available_agents_placeholder(self):
        # deepagents가 `.format(available_agents=...)`로 치환하는 자리 —
        # 지우면 Root가 실제 서브 에이전트 목록을 못 본다.
        self.assertIn("{available_agents}", TASK_DELEGATION_DESCRIPTION)

    def test_has_no_other_format_placeholders(self):
        # {available_agents} 말고 다른 중괄호가 있으면 .format() 호출이
        # KeyError로 깨진다.
        import string

        fields = [name for _, name, _, _ in string.Formatter().parse(TASK_DELEGATION_DESCRIPTION) if name is not None]
        self.assertEqual(fields, ["available_agents"])

    def test_covers_when_to_delegate_and_what_to_write(self):
        self.assertIn("언제 위임할지", TASK_DELEGATION_DESCRIPTION)
        self.assertIn("description에 쓸 내용", TASK_DELEGATION_DESCRIPTION)

    def test_five_fields_are_optional_not_mandatory(self):
        # "필요한 경우 포함" — 모든 위임에 5개 필드를 강제하지 않는다.
        self.assertIn("필요한 경우", TASK_DELEGATION_DESCRIPTION)

    def test_forbids_redundant_redelegation_and_repeated_tool_calls(self):
        """2026-08-20, GP 피드백 검토 §3 채택 5 — 같은 목적으로 다시
        위임하거나 같은 도구를 반복 호출하지 않도록 명시한다."""
        self.assertIn("다시 위임", TASK_DELEGATION_DESCRIPTION)
        self.assertIn("반복", TASK_DELEGATION_DESCRIPTION)

    def test_forbids_delegating_side_effect_work_to_general_purpose(self):
        """2026-08-20 — GP가 쓰기 도구를 상속하지 않게 됐으므로(factory.py),
        모델에게도 그런 작업을 GP에 위임하지 말라고 명시한다."""
        self.assertIn("외부를 바꾸거나 데이터를 남기는", TASK_DELEGATION_DESCRIPTION)


class GpDescriptionTests(SimpleTestCase):
    """GP 자신의 description override(2026-08-20) — deepagents 기본값
    (파일/키워드 검색 위주 영어 문구) 대신 쓴다."""

    def test_does_not_mention_specific_tool_names(self):
        # 이 앱의 실제 연결 도구는 바뀔 수 있다 — 특정 도구 이름을
        # 하드코딩하지 않는다.
        for name in ("Jira", "jira", "task_register"):
            self.assertNotIn(name, GP_DESCRIPTION)

    def test_states_read_only_access_not_hitl_parity(self):
        """2026-08-20, GP 피드백 검토 §3 채택 3 — GP는 이제 side_effect 도구를
        상속하지 않는다(factory.py가 읽기 전용만 넘긴다). "Root와 동일한
        도구"라는 옛 문구(HITL parity) 대신 "조회만 가능"을 명시해야 모델이
        GP에게 쓰기 작업을 잘못 기대하지 않는다."""
        self.assertIn("조회", GP_DESCRIPTION)
        self.assertNotIn("Root와 동일한 도구", GP_DESCRIPTION)
