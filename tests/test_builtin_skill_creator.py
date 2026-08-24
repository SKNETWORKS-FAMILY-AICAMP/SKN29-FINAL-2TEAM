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
        self.assertIn("스킬을 만들기 위한 설명으로 취급", SKILL_CREATOR_BODY)
        self.assertIn("실제 작업에 쓸 자료는 요구하지 않는다", SKILL_CREATOR_BODY)

    def test_body_caps_followup_questions(self):
        self.assertIn("질문은 전체 과정에서 최대 두 번", SKILL_CREATOR_BODY)

    def test_body_forbids_requesting_runtime_payload(self):
        self.assertIn("번역할 문장, 보낼 메일, 요약할 문서", SKILL_CREATOR_BODY)
        self.assertIn("실제 작업에 쓸 자료는 요구하지 않는다", SKILL_CREATOR_BODY)

    def test_followup_question_uses_plain_short_language(self):
        self.assertIn("어떤 일을 도와주는 스킬을 만들까요?", SKILL_CREATOR_BODY)
        self.assertIn("예: 회의록에서 할 일 정리", SKILL_CREATOR_BODY)
        self.assertIn("이유나 내부 구현은 설명하지 않는다", SKILL_CREATOR_BODY)

    def test_body_omits_internal_design_history(self):
        self.assertNotIn("2026-08-24_02", SKILL_CREATOR_BODY)
        self.assertNotIn("매칭의 성패", SKILL_CREATOR_BODY)
