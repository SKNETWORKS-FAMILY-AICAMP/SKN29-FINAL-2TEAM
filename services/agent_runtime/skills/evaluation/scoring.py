"""§8.12 "점수와 통과 기준".

정본: 03_스킬_검증_등록_설계.md §8.12.

```
recall = 긍정 반복 중 candidate 활성화 성공 / 전체 긍정 반복
false_activation_rate = 부정 반복 중 candidate 활성화 / 전체 부정 반복
precision = TP / (TP + FP)
behavior_pass_rate = 통과한 행동 assertion / 전체 행동 assertion
```

**공식 skill-creator `run_eval.py`와의 차이**는 정본 §8.12에 이미 적혀 있다 —
공식은 질문 단위로 `trigger_rate`를 구해 하나의 threshold(기본 0.5)와
비교하지만, 여기는 반복(36회) 하나하나를 데이터포인트로 삼는다. 이 파일은
그 "반복 단위" 계산을 그대로 구현한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .harness import BehaviorRunResult, CaseRunResult

RECALL_THRESHOLD = 0.80
PRECISION_THRESHOLD = 0.80
FALSE_ACTIVATION_THRESHOLD = 0.20
BEHAVIOR_PASS_THRESHOLD = 0.80
#: §8.12 "인프라 오류로 유효 실행 수가 polarity별 80% 미만이면 EVAL_INFRA_ERROR"
MIN_VALID_RATIO = 0.80


@dataclass
class RoutingMetrics:
    recall: float
    precision: float
    false_activation_rate: float
    positive_total: int
    positive_valid: int
    negative_total: int
    negative_valid: int
    true_positive: int
    false_positive: int


@dataclass
class ScoreResult:
    routing: RoutingMetrics
    behavior_pass_rate: float
    behavior_assertion_total: int
    behavior_assertion_passed: int
    deterministic_failures: list[str]
    passed: bool
    infra_error: bool
    reasons: list[str] = field(default_factory=list)

    def to_metrics_dict(self) -> dict[str, Any]:
        return {
            "recall": self.routing.recall,
            "precision": self.routing.precision,
            "false_activation_rate": self.routing.false_activation_rate,
            "behavior_pass_rate": self.behavior_pass_rate,
            "positive_total": self.routing.positive_total,
            "positive_valid": self.routing.positive_valid,
            "negative_total": self.routing.negative_total,
            "negative_valid": self.routing.negative_valid,
            "deterministic_failures": self.deterministic_failures,
        }


def score_routing(results: list[CaseRunResult], *, case_polarity: dict[str, str]) -> RoutingMetrics:
    positive_valid = [r for r in results if case_polarity.get(r.case_id) == "positive" and r.error is None]
    negative_valid = [r for r in results if case_polarity.get(r.case_id) == "negative" and r.error is None]
    positive_total = sum(1 for r in results if case_polarity.get(r.case_id) == "positive")
    negative_total = sum(1 for r in results if case_polarity.get(r.case_id) == "negative")

    true_positive = sum(1 for r in positive_valid if r.activated_candidate)
    false_negative = len(positive_valid) - true_positive
    false_positive = sum(1 for r in negative_valid if r.activated_candidate)

    recall = true_positive / len(positive_valid) if positive_valid else 0.0
    false_activation_rate = false_positive / len(negative_valid) if negative_valid else 0.0
    precision_denominator = true_positive + false_positive
    precision = true_positive / precision_denominator if precision_denominator else 0.0

    return RoutingMetrics(
        recall=recall,
        precision=precision,
        false_activation_rate=false_activation_rate,
        positive_total=positive_total,
        positive_valid=len(positive_valid),
        negative_total=negative_total,
        negative_valid=len(negative_valid),
        true_positive=true_positive,
        false_positive=false_positive,
    )


def score_behavior(results: list[BehaviorRunResult]) -> tuple[float, int, int, list[str]]:
    """대표 실행별 결정적 규칙과 자연어 assertion 결과를 함께 채점한다.

    자연어 reviewer의 FAIL/UNCERTAIN도 pipeline에서
    ``deterministic_tool_failures``에 정규화되어 들어온다. 이름은 기존 API
    호환을 위해 유지하지만, 도구 규칙만 담는 필드는 아니다. 결정적 도구
    실패는 reviewer가 뒤집을 수 없다.
    """

    total = len(results)
    passed = sum(1 for r in results if not r.deterministic_tool_failures and r.error is None)
    all_failures = [f for r in results for f in r.deterministic_tool_failures]
    rate = passed / total if total else 1.0
    return rate, total, passed, all_failures


def evaluate(
    *,
    routing_results: list[CaseRunResult],
    behavior_results: list[BehaviorRunResult],
    case_polarity: dict[str, str],
) -> ScoreResult:
    routing = score_routing(routing_results, case_polarity=case_polarity)
    behavior_rate, behavior_total, behavior_passed, det_failures = score_behavior(behavior_results)

    reasons: list[str] = []
    infra_error = False
    if routing.positive_total and routing.positive_valid / routing.positive_total < MIN_VALID_RATIO:
        infra_error = True
        reasons.append("긍정 질문 실행 중 유효 결과 비율이 80% 미만입니다(인프라 오류 가능성).")
    if routing.negative_total and routing.negative_valid / routing.negative_total < MIN_VALID_RATIO:
        infra_error = True
        reasons.append("부정 질문 실행 중 유효 결과 비율이 80% 미만입니다(인프라 오류 가능성).")

    if infra_error:
        return ScoreResult(
            routing=routing,
            behavior_pass_rate=behavior_rate,
            behavior_assertion_total=behavior_total,
            behavior_assertion_passed=behavior_passed,
            deterministic_failures=det_failures,
            passed=False,
            infra_error=True,
            reasons=reasons,
        )

    if routing.recall < RECALL_THRESHOLD:
        reasons.append(f"재현율 {routing.recall:.2f} < 기준 {RECALL_THRESHOLD}")
    if routing.precision < PRECISION_THRESHOLD:
        reasons.append(f"정밀도 {routing.precision:.2f} < 기준 {PRECISION_THRESHOLD}")
    if routing.false_activation_rate > FALSE_ACTIVATION_THRESHOLD:
        reasons.append(f"오발동률 {routing.false_activation_rate:.2f} > 기준 {FALSE_ACTIVATION_THRESHOLD}")
    if det_failures:
        reasons.append(f"행동 검증 실패: {det_failures}")
    if behavior_rate < BEHAVIOR_PASS_THRESHOLD:
        reasons.append(f"행동 통과율 {behavior_rate:.2f} < 기준 {BEHAVIOR_PASS_THRESHOLD}")

    return ScoreResult(
        routing=routing,
        behavior_pass_rate=behavior_rate,
        behavior_assertion_total=behavior_total,
        behavior_assertion_passed=behavior_passed,
        deterministic_failures=det_failures,
        passed=not reasons,
        infra_error=False,
        reasons=reasons,
    )


__all__ = [
    "RoutingMetrics",
    "ScoreResult",
    "score_routing",
    "score_behavior",
    "evaluate",
    "RECALL_THRESHOLD",
    "PRECISION_THRESHOLD",
    "FALSE_ACTIVATION_THRESHOLD",
    "BEHAVIOR_PASS_THRESHOLD",
]
