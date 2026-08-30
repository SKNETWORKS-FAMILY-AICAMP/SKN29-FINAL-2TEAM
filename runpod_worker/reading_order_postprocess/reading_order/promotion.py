"""Evidence gates for promoting a reading-order rule.

The detector and correction code must not decide its own production status.
This module turns evaluation evidence into explicit shadow/pilot/automatic
readiness states.  It performs no document mutation.
"""

from __future__ import annotations

from math import sqrt
from typing import Any


DEFAULT_POLICY = {
    "minimum_reviewed_documents": 5,
    "minimum_positive_documents": 3,
    "minimum_positive_cases": 10,
    "minimum_normal_cases": 30,
    "minimum_changed_edge_precision": 0.98,
    "minimum_exact_correction_recall": 0.80,
    "minimum_normal_preservation_rate": 0.99,
    "maximum_boundary_violations": 0,
    "minimum_production_precision_wilson_lower_bound": 0.95,
}


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def wilson_lower_bound(successes: int, total: int, z: float = 1.959963984540054) -> float | None:
    """Return the two-sided 95% Wilson interval lower bound."""

    if total <= 0:
        return None
    proportion = successes / total
    denominator = 1 + z * z / total
    center = proportion + z * z / (2 * total)
    spread = z * sqrt((proportion * (1 - proportion) + z * z / (4 * total)) / total)
    return round((center - spread) / denominator, 4)


def evaluate_rule_promotion(
    evidence: dict[str, Any], policy: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Evaluate one rule without treating DEV or pending labels as proof."""

    effective = dict(DEFAULT_POLICY)
    if policy:
        effective.update(policy)

    required_counts = (
        "reviewed_document_count",
        "positive_document_count",
        "positive_case_count",
        "normal_case_count",
        "corrected_true_positive_count",
        "corrected_false_positive_count",
        "detected_positive_count",
        "normal_preserved_count",
        "boundary_violation_count",
        "unlabeled_auto_candidate_count",
    )
    missing = [name for name in required_counts if name not in evidence]
    if missing:
        raise ValueError(f"missing evidence fields: {', '.join(missing)}")
    if any(not isinstance(evidence[name], int) or evidence[name] < 0 for name in required_counts):
        raise ValueError("evidence counts must be non-negative integers")

    corrected_total = (
        evidence["corrected_true_positive_count"]
        + evidence["corrected_false_positive_count"]
    )
    changed_edge_precision = _ratio(evidence["corrected_true_positive_count"], corrected_total)
    exact_correction_recall = _ratio(
        evidence["corrected_true_positive_count"], evidence["positive_case_count"]
    )
    detection_recall = _ratio(evidence["detected_positive_count"], evidence["positive_case_count"])
    normal_preservation_rate = _ratio(
        evidence["normal_preserved_count"], evidence["normal_case_count"]
    )
    precision_lower_bound = wilson_lower_bound(
        evidence["corrected_true_positive_count"], corrected_total
    )

    blockers: list[str] = []
    if evidence.get("evaluation_role") != "INDEPENDENT_HOLDOUT":
        blockers.append("NOT_INDEPENDENT_HOLDOUT")
    if not evidence.get("frozen_before_evaluation", False):
        blockers.append("RULE_NOT_FROZEN_BEFORE_EVALUATION")
    if evidence.get("threshold_tuned_on_evaluation", False):
        blockers.append("THRESHOLD_TUNED_ON_EVALUATION")
    if not evidence.get("has_exact_correction_executor", False):
        blockers.append("NO_EXACT_CORRECTION_EXECUTOR")
    if evidence["unlabeled_auto_candidate_count"]:
        blockers.append("UNLABELED_AUTO_CANDIDATES")
    if evidence["reviewed_document_count"] < effective["minimum_reviewed_documents"]:
        blockers.append("TOO_FEW_REVIEWED_DOCUMENTS")
    if evidence["positive_document_count"] < effective["minimum_positive_documents"]:
        blockers.append("TOO_FEW_POSITIVE_DOCUMENTS")
    if evidence["positive_case_count"] < effective["minimum_positive_cases"]:
        blockers.append("TOO_FEW_POSITIVE_CASES")
    if evidence["normal_case_count"] < effective["minimum_normal_cases"]:
        blockers.append("TOO_FEW_NORMAL_CASES")
    if changed_edge_precision is None or changed_edge_precision < effective["minimum_changed_edge_precision"]:
        blockers.append("CHANGED_EDGE_PRECISION_BELOW_POLICY")
    if exact_correction_recall is None or exact_correction_recall < effective["minimum_exact_correction_recall"]:
        blockers.append("EXACT_CORRECTION_RECALL_BELOW_POLICY")
    if normal_preservation_rate is None or normal_preservation_rate < effective["minimum_normal_preservation_rate"]:
        blockers.append("NORMAL_PRESERVATION_BELOW_POLICY")
    if evidence["boundary_violation_count"] > effective["maximum_boundary_violations"]:
        blockers.append("STRUCTURAL_BOUNDARY_VIOLATION")

    pilot_ready = not blockers
    production_confidence_ready = (
        pilot_ready
        and precision_lower_bound is not None
        and precision_lower_bound
        >= effective["minimum_production_precision_wilson_lower_bound"]
    )
    if production_confidence_ready:
        status = "UNATTENDED_AUTO_READY"
    elif pilot_ready:
        status = "CONTROLLED_AUTO_PILOT_READY"
    elif evidence.get("detector_implemented", False):
        status = "SHADOW_OR_REVIEW_ONLY"
    else:
        status = "NOT_IMPLEMENTED_OR_UNMEASURED"

    return {
        "rule_id": evidence.get("rule_id"),
        "status": status,
        "controlled_auto_pilot_ready": pilot_ready,
        "unattended_auto_ready": production_confidence_ready,
        "metrics": {
            "changed_edge_precision": changed_edge_precision,
            "changed_edge_precision_wilson_lower_bound_95": precision_lower_bound,
            "exact_correction_recall": exact_correction_recall,
            "detection_recall": detection_recall,
            "normal_preservation_rate": normal_preservation_rate,
        },
        "blockers": blockers,
        "policy": effective,
        "interpretation": (
            "관측 precision이 높아도 작은 표본의 신뢰구간 하한이 낮으면 무인 자동 적용으로 승격하지 않는다."
        ),
    }

