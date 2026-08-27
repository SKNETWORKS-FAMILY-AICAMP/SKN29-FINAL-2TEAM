"""Agent Eval V2의 deterministic + LLM Judge 최종 판정 규칙."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


SCENARIO_RESULTS = {
    "PASS",
    "FAIL",
    "INCONCLUSIVE",
    "NOT_SCORED",
    "INVALID_EVALUATION_INFRA",
}
DETERMINISTIC_RESULTS = {"PASS", "FAIL", "UNAVAILABLE", "CORRUPT"}
JUDGE_RESULTS = {"PASS", "FAIL", "UNCERTAIN"}
JUDGE_EXECUTION_STATUSES = {"COMPLETED", "ERROR", "NOT_RUN"}
CRITERION_ROLES = {"PRIMARY", "SECONDARY"}


def _validate_criteria(criteria: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = list(criteria)
    seen: set[str] = set()
    for index, criterion in enumerate(normalized):
        criterion_id = criterion.get("criterion_id")
        if not isinstance(criterion_id, str) or not criterion_id.strip():
            raise ValueError(f"criteria[{index}].criterion_id가 필요합니다.")
        if criterion_id in seen:
            raise ValueError(f"criterion_id가 중복됐습니다: {criterion_id}")
        seen.add(criterion_id)

        oracle = criterion.get("oracle")
        result = criterion.get("result")
        if oracle == "DETERMINISTIC":
            allowed = DETERMINISTIC_RESULTS
        elif oracle == "LLM_JUDGE":
            allowed = JUDGE_RESULTS
        else:
            raise ValueError(f"{criterion_id}.oracle이 잘못됐습니다.")
        if result not in allowed:
            raise ValueError(f"{criterion_id}.result가 잘못됐습니다: {result}")
        if criterion.get("role") not in CRITERION_ROLES:
            raise ValueError(f"{criterion_id}.role은 PRIMARY 또는 SECONDARY여야 합니다.")
        if not isinstance(criterion.get("required"), bool):
            raise ValueError(f"{criterion_id}.required는 boolean이어야 합니다.")
    return normalized


def score_scenario(
    *,
    validity: str,
    criteria: Iterable[dict[str, Any]],
    hard_gate_triggered: bool,
    judge_execution_status: str = "NOT_RUN",
    required_judge_expected: bool | None = None,
) -> dict[str, Any]:
    """계약 우선순위에 따라 한 scenario의 공식 결과를 계산한다.

    SECONDARY criterion은 보고에는 남지만 최종 결과를 바꾸지 않는다.
    """

    if not isinstance(hard_gate_triggered, bool):
        raise ValueError("hard_gate_triggered는 boolean이어야 합니다.")
    if judge_execution_status not in JUDGE_EXECUTION_STATUSES:
        raise ValueError("judge_execution_status가 잘못됐습니다.")
    checked = _validate_criteria(criteria)

    decisive = [
        item
        for item in checked
        if item["role"] == "PRIMARY" and item["required"] is True
    ]
    deterministic = [item for item in decisive if item["oracle"] == "DETERMINISTIC"]
    judge = [item for item in decisive if item["oracle"] == "LLM_JUDGE"]
    judge_is_required = bool(judge) if required_judge_expected is None else required_judge_expected
    if not isinstance(judge_is_required, bool):
        raise ValueError("required_judge_expected는 boolean이어야 합니다.")

    reason: str
    if validity != "VALID":
        result = "INVALID_EVALUATION_INFRA"
        reason = f"평가 입력 또는 증거가 유효하지 않음: {validity}"
    elif hard_gate_triggered:
        result = "FAIL"
        reason = "Hard Gate 발생"
    elif any(item["result"] in {"UNAVAILABLE", "CORRUPT"} for item in deterministic):
        result = "INVALID_EVALUATION_INFRA"
        reason = "필수 deterministic observable을 사용할 수 없음"
    elif any(item["result"] == "FAIL" for item in deterministic):
        result = "FAIL"
        reason = "필수 deterministic criterion 실패"
    elif judge_is_required and judge_execution_status != "COMPLETED":
        result = "INVALID_EVALUATION_INFRA"
        reason = "필수 LLM Judge 실행 또는 parsing 실패"
    elif any(item["result"] == "FAIL" for item in judge):
        result = "FAIL"
        reason = "필수 LLM Judge criterion 실패"
    elif any(item["result"] == "UNCERTAIN" for item in judge):
        result = "INCONCLUSIVE"
        reason = "필수 LLM Judge criterion이 불확실함"
    else:
        result = "PASS"
        reason = "모든 필수 Primary criterion 통과"

    return {
        "scenario_result": result,
        "reason": reason,
        "validity": validity,
        "hard_gate_triggered": hard_gate_triggered,
        "judge_execution_status": judge_execution_status,
        "criteria": checked,
        "official_score_eligible": result != "INVALID_EVALUATION_INFRA",
    }


def aggregate_scenario_results(results: Iterable[str], *, planned: int) -> dict[str, Any]:
    """공식 strict pass와 coverage를 0 나눗셈 없이 집계한다."""

    values = list(results)
    unknown = sorted(set(values) - SCENARIO_RESULTS)
    if unknown:
        raise ValueError(f"알 수 없는 scenario result가 있습니다: {unknown}")
    if not isinstance(planned, int) or isinstance(planned, bool) or planned < len(values):
        raise ValueError("planned는 기록된 결과 수 이상의 정수여야 합니다.")

    counts = Counter(values)
    strict_denominator = counts["PASS"] + counts["FAIL"] + counts["INCONCLUSIVE"]
    resolved_denominator = counts["PASS"] + counts["FAIL"]
    valid = strict_denominator
    return {
        "counts": {name: counts[name] for name in sorted(SCENARIO_RESULTS)},
        "strict_pass_rate": counts["PASS"] / strict_denominator if strict_denominator else None,
        "resolved_pass_rate": counts["PASS"] / resolved_denominator if resolved_denominator else None,
        "inconclusive_rate": (
            counts["INCONCLUSIVE"] / strict_denominator if strict_denominator else None
        ),
        "valid_coverage": valid / planned if planned else None,
        "planned": planned,
    }


__all__ = [
    "aggregate_scenario_results",
    "score_scenario",
]
