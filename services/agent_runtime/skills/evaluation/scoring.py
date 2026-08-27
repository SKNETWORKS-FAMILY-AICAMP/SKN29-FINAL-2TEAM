"""§8.12 "점수와 통과 기준".

정본: 03_스킬_검증_등록_설계.md §8.12.

```
각 질문은 3회 실행 중 2회 이상 나온 결과를 그 질문의 최종 선택으로 확정한다.
recall = 활성화된 긍정 질문 / 유효한 긍정 질문
false_activation_rate = 활성화된 부정 질문 / 유효한 부정 질문
precision = TP / (TP + FP)
behavior_pass_rate = 통과한 행동 assertion / 전체 행동 assertion
```

**공식 skill-creator `run_eval.py`와의 차이**는 정본 §8.12에 이미 적혀 있다 —
공식처럼 같은 질문의 반복 결과를 먼저 질문 단위로 확정한다. 한 번의 확률적
흔들림 때문에 스킬 전체가 실패하지 않게 하되, 2회 이상 같은 결과가 나와야
하므로 일회성 성공도 통과시키지 않는다.
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
    grouped: dict[str, list[CaseRunResult]] = {}
    for result in results:
        if result.case_id in case_polarity:
            grouped.setdefault(result.case_id, []).append(result)

    def majority(group: list[CaseRunResult]) -> bool | None:
        """전체 예정 반복의 과반이 같은 결과일 때만 질문 결과를 확정한다."""

        needed = len(group) // 2 + 1
        valid = [result for result in group if result.error is None]
        activated = sum(1 for result in valid if result.activated_candidate)
        not_activated = sum(1 for result in valid if not result.activated_candidate)
        if activated >= needed:
            return True
        if not_activated >= needed:
            return False
        return None

    resolved = {case_id: majority(group) for case_id, group in grouped.items()}
    positive_ids = [case_id for case_id in grouped if case_polarity[case_id] == "positive"]
    negative_ids = [case_id for case_id in grouped if case_polarity[case_id] == "negative"]
    positive_valid = [resolved[case_id] for case_id in positive_ids if resolved[case_id] is not None]
    negative_valid = [resolved[case_id] for case_id in negative_ids if resolved[case_id] is not None]

    true_positive = sum(1 for activated in positive_valid if activated)
    false_positive = sum(1 for activated in negative_valid if activated)

    recall = true_positive / len(positive_valid) if positive_valid else 0.0
    false_activation_rate = false_positive / len(negative_valid) if negative_valid else 0.0
    precision_denominator = true_positive + false_positive
    precision = true_positive / precision_denominator if precision_denominator else 0.0

    return RoutingMetrics(
        recall=recall,
        precision=precision,
        false_activation_rate=false_activation_rate,
        positive_total=len(positive_ids),
        positive_valid=len(positive_valid),
        negative_total=len(negative_ids),
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

    valid = [result for result in results if result.error is None]
    assertion_total = sum(result.semantic_assertion_total for result in valid)
    if assertion_total:
        total = assertion_total
        passed = sum(result.semantic_assertion_passed for result in valid)
    else:
        # 구조 검증이나 기존 호출자가 assertion 집계를 제공하지 않는 경우의
        # 호환 경로. 실제 pipeline은 각 assertion의 개수를 항상 채운다.
        total = len(valid)
        passed = sum(1 for result in valid if not result.deterministic_tool_failures)
    all_failures = [failure for result in valid for failure in result.deterministic_tool_failures]
    # 실행 오류는 스킬 행동 실패가 아니다. 유효 결과 비율은 evaluate()가 별도로
    # 검사해 인프라 오류로 분류한다.
    rate = passed / total if total else (1.0 if not results else 0.0)
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
    behavior_run_total = len(behavior_results)
    behavior_valid = sum(1 for result in behavior_results if result.error is None)
    if behavior_run_total and behavior_valid / behavior_run_total < MIN_VALID_RATIO:
        infra_error = True
        reasons.append("행동 검증 실행 중 유효 결과 비율이 80% 미만입니다(인프라 오류 가능성).")

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
