"""의미 reviewer의 polarity별 판정 규칙."""

import json
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from services.agent_runtime.skills.evaluation.generator import GeneratedCase
from services.agent_runtime.skills.evaluation.semantic_reviewer import (
    CaseReview,
    RubricVerdict,
    SemanticReviewResult,
    review_cases,
)


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

    @patch("services.agent_runtime.skills.evaluation.semantic_reviewer._build_model")
    def test_reviewer는_설명뿐_아니라_후보_본문도_받는다(self, build_model):
        model = MagicMock()
        model.invoke.return_value = SemanticReviewResult(reviews=[])
        build_model.return_value = (model, MagicMock(model_id="reviewer"))
        candidate = {
            "name": "neutralize-bug-reports",
            "description": "감정 표현을 중립화합니다.",
            "body": "정보가 없으면 추측하지 말고 확인 필요로 표시합니다.",
        }

        review_cases(
            [
                GeneratedCase(
                    category="direct",
                    query="이 제보를 중립적으로 바꿔줘",
                    should_activate_candidate=True,
                    behavior_assertions=[{"criterion": "사실을 유지한다"}],
                    reason="직접 요청",
                )
            ],
            skill_document=candidate,
        )

        payload = json.loads(model.invoke.call_args.args[0][1]["content"])
        self.assertEqual(payload["skill_candidate"], candidate)
