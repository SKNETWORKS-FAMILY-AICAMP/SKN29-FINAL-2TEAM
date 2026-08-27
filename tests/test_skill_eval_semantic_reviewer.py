"""의미 reviewer의 polarity별 판정 규칙."""

from django.test import SimpleTestCase

from services.agent_runtime.skills.evaluation.semantic_reviewer import CaseReview, RubricVerdict


def _verdict(value: str) -> RubricVerdict:
    return RubricVerdict(verdict=value, reason="test")


def _review(**overrides) -> CaseReview:
    values = {
        "case_index": 0,
        "intended_skill_match": _verdict("PASS"),
        "hard_negative_quality": _verdict("PASS"),
        "fixture_sufficiency": _verdict("PASS"),
        "expectation_consistency": _verdict("PASS"),
        "naturalness": _verdict("PASS"),
    }
    values.update(overrides)
    return CaseReview(**values)


class OverallTests(SimpleTestCase):
    def test_긍정은_hard_negative_quality를_판정에_쓰지_않는다(self):
        review = _review(hard_negative_quality=_verdict("FAIL"))
        self.assertEqual(review.overall(is_positive=True), "PASS")

    def test_부정은_intended_skill_match를_판정에_쓰지_않는다(self):
        review = _review(intended_skill_match=_verdict("FAIL"))
        self.assertEqual(review.overall(is_positive=False), "PASS")

    def test_부정은_의도적인_fixture_부족을_판정에_쓰지_않는다(self):
        review = _review(fixture_sufficiency=_verdict("FAIL"))
        self.assertEqual(review.overall(is_positive=False), "PASS")

    def test_긍정은_intended_skill_match_실패를_거부한다(self):
        review = _review(intended_skill_match=_verdict("FAIL"))
        self.assertEqual(review.overall(is_positive=True), "FAIL")

    def test_부정은_hard_negative_quality_실패를_거부한다(self):
        review = _review(hard_negative_quality=_verdict("FAIL"))
        self.assertEqual(review.overall(is_positive=False), "FAIL")
