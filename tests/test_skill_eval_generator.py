"""§8.5 "구조 검증" — `validate_structural()`. LLM 호출 없이 순수 로직만 검사한다."""

from django.test import SimpleTestCase

from services.agent_runtime.skills.evaluation.generator import GeneratedCase, validate_structural


def _case(**overrides) -> GeneratedCase:
    base = {"category": "direct", "query": "회의록에서 할 일 정리해줘", "should_activate_candidate": True, "reason": "r"}
    base.update(overrides)
    base.setdefault("behavior_assertions", [{"criterion": "업무가 포함된다"}] if base["should_activate_candidate"] else [])
    return GeneratedCase(**base)


class ValidateStructuralTests(SimpleTestCase):
    def test_긍정_질문이_비활성으로_표시되면_거부한다(self):
        case = _case(should_activate_candidate=False)
        failures = validate_structural(
            [case], polarity="positive", skill_name="meeting-action-items",
            available_tool_refs={"task_extraction"}, other_skill_names=set(),
        )
        self.assertIn("polarity_mismatch", {failure.rule for failure in failures})

    def test_부정_질문이_활성으로_표시되면_거부한다(self):
        case = _case(should_activate_candidate=True)
        failures = validate_structural(
            [case], polarity="negative", skill_name="meeting-action-items",
            available_tool_refs={"task_extraction"}, other_skill_names=set(),
        )
        self.assertIn("polarity_mismatch", {failure.rule for failure in failures})

    def test_정상_케이스는_실패가_없다(self):
        failures = validate_structural(
            [_case()], polarity="positive", skill_name="meeting-action-items",
            available_tool_refs=set(), other_skill_names=set(),
        )
        self.assertEqual(failures, [])

    def test_빈_질문은_거부한다(self):
        failures = validate_structural(
            [_case(query="")], polarity="positive", skill_name="s",
            available_tool_refs=set(), other_skill_names=set(),
        )
        self.assertEqual([f.rule for f in failures], ["empty_query"])

    def test_긴_질문은_거부한다(self):
        failures = validate_structural(
            [_case(query="가" * 400)], polarity="positive", skill_name="s",
            available_tool_refs=set(), other_skill_names=set(),
        )
        self.assertIn("query_too_long", [f.rule for f in failures])

    def test_거의_같은_질문은_근접중복으로_거부한다(self):
        failures = validate_structural(
            [_case(query="회의록에서 할 일 정리해줘"), _case(query="회의록에서 할 일 좀 정리해줘")],
            polarity="positive", skill_name="s", available_tool_refs=set(), other_skill_names=set(),
        )
        self.assertIn("near_duplicate", [f.rule for f in failures])

    def test_스킬_이름이_질문에_노출되면_거부한다(self):
        failures = validate_structural(
            [_case(query="meeting-action-items 스킬로 정리해줘")],
            polarity="positive", skill_name="meeting-action-items",
            available_tool_refs=set(), other_skill_names=set(),
        )
        self.assertIn("name_leak", [f.rule for f in failures])

    def test_존재하지_않는_도구는_거부한다(self):
        failures = validate_structural(
            [_case(required_tools=["nonexistent_tool"])],
            polarity="positive", skill_name="s",
            available_tool_refs={"task_register"}, other_skill_names=set(),
        )
        self.assertIn("unknown_tool", [f.rule for f in failures])

    def test_제공되지_않은_다른_스킬_이름은_거부한다(self):
        failures = validate_structural(
            [_case(should_activate_candidate=False, allowed_other_skill_names=["unknown-skill"])],
            polarity="negative", skill_name="s",
            available_tool_refs=set(), other_skill_names={"known-skill"},
        )
        self.assertIn("unknown_other_skill", [f.rule for f in failures])

    def test_참조한_문서_fixture가_없으면_거부한다(self):
        failures = validate_structural(
            [_case(query="doc-abc123 문서 요약해줘")],
            polarity="positive", skill_name="s",
            available_tool_refs=set(), other_skill_names=set(),
        )
        self.assertIn("missing_fixture", [f.rule for f in failures])
