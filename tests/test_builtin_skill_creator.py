"""내장 skill-creator의 생성 전용 경계 회귀 테스트."""

from unittest import TestCase

from services.agent_runtime.skills.builtin_content import (
    SKILL_CREATOR_BODY,
    SKILL_CREATOR_DESCRIPTION,
)


class BuiltinSkillCreatorPromptTests(TestCase):
    def test_description_separates_creation_from_execution(self):
        self.assertIn("업무를 실제로 수행하지 않는다", SKILL_CREATOR_DESCRIPTION)

    def test_body_treats_settings_answers_as_specification_only(self):
        self.assertIn("스킬의 명세만 작성", SKILL_CREATOR_BODY)
        self.assertIn("정보로만 취급", SKILL_CREATOR_BODY)

    def test_body_caps_followup_questions(self):
        self.assertIn("질문은 전체 과정에서 최대 세 번", SKILL_CREATOR_BODY)

    def test_body_requires_scope_and_output_before_registration(self):
        self.assertIn("완성도 확인", SKILL_CREATOR_BODY)
        self.assertIn("서로 다른 작업들이 같은 스킬 대상으로 해석", SKILL_CREATOR_BODY)
        self.assertIn("결과 조건이 빠져", SKILL_CREATOR_BODY)

    def test_followup_is_derived_from_user_request_instead_of_hardcoded_domain(self):
        self.assertIn("사용자의 표현에", SKILL_CREATOR_BODY)
        self.assertIn("맞춘 짧은 질문", SKILL_CREATOR_BODY)
        self.assertIn("특정 업무·언어·도구·문구를 고정 예시로 사용하지 않는다", SKILL_CREATOR_BODY)
        for hardcoded_example in ("한국어", "영어", "일본어", "메일", "회의록"):
            self.assertNotIn(hardcoded_example, SKILL_CREATOR_BODY)

    def test_single_sentence_new_skill_requires_at_least_one_dynamic_clarification(self):
        self.assertIn("한 문장으로 처음 요청한 경우", SKILL_CREATOR_BODY)
        self.assertIn("적어도 한 번 확인한다", SKILL_CREATOR_BODY)
        self.assertIn("사용자의 요청에서 매번 새로 만든다", SKILL_CREATOR_BODY)

    def test_body_forbids_requesting_runtime_payload(self):
        self.assertIn("실제 업무에 사용할 입력값을 요구하지 않는다", SKILL_CREATOR_BODY)

    def test_followup_question_uses_plain_short_language(self):
        self.assertIn("한 번에 한 가지만 묻는다", SKILL_CREATOR_BODY)
        self.assertIn("일상 표현", SKILL_CREATOR_BODY)
        self.assertIn("이유나 내부 구현은 설명하지 않는다", SKILL_CREATOR_BODY)

    def test_body_omits_internal_design_history(self):
        self.assertNotIn("2026-08-24_02", SKILL_CREATOR_BODY)
        self.assertNotIn("매칭의 성패", SKILL_CREATOR_BODY)
