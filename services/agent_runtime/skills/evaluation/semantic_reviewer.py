"""§8.6 "의미 품질 검토" — 구조 검증이 못 잡는 것(부정 질문이 정말 헷갈리는
근접 질문인지 등)을 생성 모델과 분리된 두 번째 호출로 판단한다.

정본: 03_스킬_검증_등록_설계.md §8.6. "LLM 결과를 곧바로 믿지 않는다"는 말은
LLM을 안 쓴다는 뜻이 아니라, 구조는 코드가 강제하고 의미는 별도 reviewer가
제한된 rubric으로 검토하며 결과와 근거를 job에 남긴다는 뜻이다(같은 절).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from services.agent_runtime.models.factory import ModelConfigResolver, ModelFactory

from .config import SKILL_EVAL_REVIEWER_EFFORT, SKILL_EVAL_REVIEWER_MODEL
from .generator import GeneratedCase
from .prompts import EVAL_CASE_SEMANTIC_REVIEWER_PROMPT, EVAL_CASE_SEMANTIC_REVIEWER_PROMPT_VERSION

Verdict = Literal["PASS", "FAIL", "UNCERTAIN"]


class RubricVerdict(BaseModel):
    verdict: Verdict
    reason: str


class CaseReview(BaseModel):
    case_index: int
    intended_skill_match: RubricVerdict
    hard_negative_quality: RubricVerdict
    fixture_sufficiency: RubricVerdict
    expectation_consistency: RubricVerdict
    naturalness: RubricVerdict

    def overall(self, *, is_positive: bool) -> Verdict:
        """정본 §8.6의 rubric 정의를 그대로 따른다 — `intended_skill_match`는
        "**긍정** 질문이 description의 사용 조건과 실제로 일치하는가"라
        정의돼 있다(설계 md §8.6). 부정 케이스는 애초에 스킬과 안 맞는 게
        맞으므로, 부정 케이스에 이 rubric까지 그대로 적용하면 거의 항상
        FAIL이 나온다 — 부정 케이스가 "인접하지만 쓰면 안 되는가"는 이미
        `hard_negative_quality`가 담당한다.

        2026-08-26 발견 — 이 구분 없이 5개 rubric을 전부 동일하게 봤더니
        부정 케이스 8개가 항상 `intended_skill_match=FAIL`로 걸려서
        `TEST_CASE_REVIEW_FAILED`가 재시도해도 벗어날 수 없었다(실측:
        `korean-to-english-japanese-translation` 재검증에서 재현).
        """

        verdicts = [
            self.expectation_consistency.verdict,
            self.naturalness.verdict,
        ]
        if is_positive:
            verdicts.append(self.fixture_sufficiency.verdict)
            verdicts.append(self.intended_skill_match.verdict)
        else:
            # 부정 라우팅에는 입력·문맥·첨부가 일부러 부족한 hard negative가
            # 포함된다. 이 경우 fixture 부족은 결함이 아니라 비활성 기대의
            # 근거이므로 activation 판정에서 탈락시키지 않는다.
            verdicts.append(self.hard_negative_quality.verdict)
        if "FAIL" in verdicts:
            return "FAIL"
        if "UNCERTAIN" in verdicts:
            return "UNCERTAIN"
        return "PASS"


class SemanticReviewResult(BaseModel):
    reviews: list[CaseReview]


def _build_model():
    resolved = ModelConfigResolver().resolve(
        model=SKILL_EVAL_REVIEWER_MODEL, reasoning_effort=SKILL_EVAL_REVIEWER_EFFORT, team_id=None
    )
    model = ModelFactory().create(resolved)
    return model.with_structured_output(SemanticReviewResult), resolved


def review_cases(
    cases: list[GeneratedCase], *, skill_document: dict
) -> tuple[list[CaseReview], str]:
    """`(케이스 순서와 짝을 맞춘 review 목록, 사용한 model_id)`를 돌려준다."""

    if not cases:
        return [], ""

    structured_model, resolved = _build_model()
    payload = {
        # 설명만 넘기면 본문의 누락 입력 처리·제외 조건·금지 행동을 검토자가
        # 볼 수 없어 정상적인 요청을 hard negative로 승인할 수 있다.
        "skill_candidate": skill_document,
        "cases": [
            {
                "case_index": index,
                "category": case.category,
                "query": case.query,
                "should_activate_candidate": case.should_activate_candidate,
                "context": [m.model_dump() for m in case.context],
                "document_fixtures": [f.model_dump() for f in case.document_fixtures],
                "required_tools": case.required_tools,
                "forbidden_tools": case.forbidden_tools,
                "behavior_assertions": [item.model_dump() for item in case.behavior_assertions],
            }
            for index, case in enumerate(cases)
        ],
    }
    import json

    result = structured_model.invoke(
        [
            {"role": "system", "content": EVAL_CASE_SEMANTIC_REVIEWER_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
    )
    by_index = {r.case_index: r for r in result.reviews}
    ordered = [by_index[i] for i in range(len(cases)) if i in by_index]
    return ordered, resolved.model_id


__all__ = [
    "Verdict",
    "RubricVerdict",
    "CaseReview",
    "SemanticReviewResult",
    "review_cases",
    "EVAL_CASE_SEMANTIC_REVIEWER_PROMPT_VERSION",
]
