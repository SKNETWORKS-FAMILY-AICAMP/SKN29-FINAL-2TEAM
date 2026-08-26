"""skills/invocation.py 단위 테스트 — 명시적 스킬 호출("/스킬이름 ...") 파싱·해석·조립.

정본: `services/agent_runtime/skills/invocation.py` 모듈 docstring
(2026-08-22, 사용자 요청 — "명시적 호출도 추가해줘... 클로드의 스킬 기능 그대로
가져오고 싶어").
"""

from unittest.mock import patch

from django.test import SimpleTestCase

from services.agent_runtime.skills.invocation import (
    build_invocation_input,
    parse_invocation,
    resolve_invocable_skill,
)
from services.agent_runtime.skills.service import SkillNotFound


class ParseInvocationTests(SimpleTestCase):
    def test_slash_and_name_and_rest(self):
        self.assertEqual(
            parse_invocation("/humanizer 이 문장을 자연스럽게 바꿔줘"),
            ("humanizer", "이 문장을 자연스럽게 바꿔줘"),
        )

    def test_slash_and_name_only_rest_is_empty_string(self):
        self.assertEqual(parse_invocation("/humanizer"), ("humanizer", ""))

    def test_hyphenated_name(self):
        self.assertEqual(
            parse_invocation("/jira-issue-registration 등록해줘"),
            ("jira-issue-registration", "등록해줘"),
        )

    def test_leading_whitespace_before_slash_is_tolerated(self):
        self.assertEqual(parse_invocation("  /humanizer 다듬어줘"), ("humanizer", "다듬어줘"))

    def test_no_leading_slash_is_not_an_invocation(self):
        self.assertIsNone(parse_invocation("이거 그냥 평범한 질문이야"))

    def test_slash_not_at_the_very_start_is_not_an_invocation(self):
        self.assertIsNone(parse_invocation("경로는 /skills/personal/ 이야"))

    def test_uppercase_name_does_not_match_skill_naming_rules(self):
        """스킬 이름 규칙(`validate_skill_name`)과 같은 정규식 — 대문자가 섞이면
        애초에 스킬 이름일 수 없으므로 평범한 채팅으로 흘려보낸다."""
        self.assertIsNone(parse_invocation("/Humanizer 이거 바꿔줘"))

    def test_leading_or_trailing_hyphen_does_not_match(self):
        self.assertIsNone(parse_invocation("/-humanizer 바꿔줘"))

    def test_multiline_rest_is_captured_in_full(self):
        text = "/humanizer 첫 줄\n둘째 줄"
        self.assertEqual(parse_invocation(text), ("humanizer", "첫 줄\n둘째 줄"))

    def test_just_a_slash_alone_does_not_match(self):
        """스킬 이름 없이 "/" 하나만 온 메시지는 호출로 보지 않는다."""
        self.assertIsNone(parse_invocation("/"))


class ResolveInvocableSkillTests(SimpleTestCase):
    """팀 스킬은 공유 카탈로그이며, 가져온 개인 스킬만 명시적으로 실행된다."""

    @patch("services.agent_runtime.skills.service.ensure_builtin_skill_creator")
    @patch("services.agent_runtime.skills.service.get_builtin_skill")
    def test_reserved_builtin_skill_is_resolved_explicitly(self, get_builtin, ensure_builtin):
        get_builtin.return_value = {
            "skill_id": "skill-creator",
            "name": "skill-creator",
            "body": "BUILTIN_BODY",
        }

        result = resolve_invocable_skill(
            account_id="AC001", team_id="TM001", name="skill-creator"
        )

        self.assertEqual(result["body"], "BUILTIN_BODY")
        self.assertEqual(result["scope"], "builtin")
        ensure_builtin.assert_called_once_with()

    @patch("services.agent_runtime.skills.service.get_personal_skill")
    def test_resolves_personal_skill(self, get_personal):
        get_personal.return_value = {"skill_id": "humanizer", "name": "humanizer", "body": "PERSONAL_BODY"}

        result = resolve_invocable_skill(account_id="AC001", team_id="TM001", name="humanizer")

        self.assertEqual(result["body"], "PERSONAL_BODY")
        self.assertEqual(result["scope"], "personal")

    @patch("services.agent_runtime.skills.service.get_personal_skill", side_effect=SkillNotFound("없음"))
    def test_returns_none_when_personal_scope_does_not_have_it(self, _get_personal):
        self.assertIsNone(resolve_invocable_skill(account_id="AC001", team_id="TM001", name="nope"))

    @patch("services.agent_runtime.skills.service.get_personal_skill")
    def test_disabled_personal_skill_is_not_invocable(self, get_personal):
        get_personal.return_value = {
            "skill_id": "humanizer",
            "name": "humanizer",
            "body": "PERSONAL_BODY",
            "enabled": False,
        }

        self.assertIsNone(
            resolve_invocable_skill(account_id="AC001", team_id="TM001", name="humanizer")
        )


class BuildInvocationInputTests(SimpleTestCase):
    def test_wraps_body_and_request_with_explicit_marker(self):
        result = build_invocation_input(name="humanizer", body="스킬 본문", request="이 문장을 다듬어줘")

        self.assertIn("humanizer", result)
        self.assertIn("스킬 본문", result)
        self.assertIn("이 문장을 다듬어줘", result)
        self.assertIn("explicit_skill_invocation", result)

    def test_empty_request_gets_a_fallback_instruction_instead_of_blank(self):
        result = build_invocation_input(name="humanizer", body="스킬 본문", request="")

        self.assertNotIn("사용자 요청: \n", result)
        self.assertIn("바로 앞 대화 맥락", result)
