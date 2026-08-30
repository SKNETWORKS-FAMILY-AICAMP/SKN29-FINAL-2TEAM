"""Run the reading-order postprocess with a fail-closed two-outcome contract.

The default ``shadow`` policy never changes the Docling document.  The
``validated-local-v1`` policy applies only the narrowly validated adjacent
local inversion rule after compiling it into the shared proposal contract and
passing the common validator.  Every other finding remains audit-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Any

PRACTICE_ROOT = Path(__file__).resolve().parent
if str(PRACTICE_ROOT) not in sys.path:
    sys.path.insert(0, str(PRACTICE_ROOT))

from apply_reviewed_structure import apply_review_map  # noqa: E402
from reading_order import (  # noqa: E402
    DetectorConfig,
    build_element_order_map,
    detect_reading_order_candidates,
    load_docling_json,
)
from scan_structure_order_router import route_structure_order_findings  # noqa: E402
from validate_postprocess_proposals import validate_proposals  # noqa: E402
from reading_order.relation_audit import build_relation_audit  # noqa: E402


# Public runtime policy names. POLICY_VERSION below identifies the frozen
# implementation/threshold revision written to audit output; it is not a
# separate CLI policy name.
POLICIES = {"shadow", "validated-local-v1"}
DENSE_ROW_PAIR_BLOCK_THRESHOLD = 20
POLICY_VERSION = "validated-local-v1.1"


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")


def _validate_output_paths(
    source_json: Path, output_json: Path, audit_json: Path
) -> None:
    resolved = [
        source_json.resolve(),
        output_json.resolve(),
        audit_json.resolve(),
    ]
    if len(set(resolved)) != 3:
        raise ValueError(
            "source_json, output_json and audit_json must be distinct paths"
        )


def _compile_validated_local_v1(
    source_hash: str,
    candidates: list[dict[str, Any]],
    blocked_candidate_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Compile only the frozen adjacent local-inversion policy."""

    decisions: list[dict[str, Any]] = []
    blocked_ids = blocked_candidate_ids or set()
    for candidate in candidates:
        metrics = candidate.get("metrics", {})
        observed = candidate.get("observed_order", [])
        proposed = candidate.get("proposed_order", [])
        eligible = (
            candidate.get("type") == "LOCAL_VERTICAL_INVERSION"
            and candidate.get("confidence") == "HIGH"
            and candidate.get("decision") == "AUTO_REORDER_ELIGIBLE"
            and candidate.get("operation") == "SWAP_ADJACENT"
            and isinstance(candidate.get("parent_ref"), str)
            and len(observed) == 2
            and proposed == list(reversed(observed))
            and metrics.get("visual_intervening_sibling_count", 0) == 0
            and metrics.get("complex_geometry") is False
            and not metrics.get("text_quality_flags")
            and candidate.get("candidate_id") not in blocked_ids
        )
        if not eligible:
            continue
        decisions.append(
            {
                "decision_id": f"POLICY-{candidate['candidate_id']}",
                "status": "REVIEW_APPROVED",
                "approval_basis": "validated-local-v1",
                "operation": "REORDER_SUBSET",
                "parent_ref": candidate["parent_ref"],
                "ordered_refs": proposed,
                "reason": candidate["reason"],
                "evidence": {
                    "candidate_id": candidate["candidate_id"],
                    "page_no": candidate["page_no"],
                    "metrics": metrics,
                },
            }
        )
    return {
        "schema_version": "postprocess-proposal.v1",
        "proposal_id": "READING-ORDER-VALIDATED-LOCAL-V1",
        "owner": "reading_order",
        "status": "REVIEW_APPROVED" if decisions else "PRESERVE_CONFIRMED",
        "source": {"json_sha256": source_hash},
        "decisions": decisions,
        "generator": {
            "name": "run_reading_order_postprocess",
            "policy": "validated-local-v1",
            "external_model_calls": 0,
            "source_mutated": False,
        },
    }


def run_postprocess(
    source_path: Path, policy: str = "shadow"
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return output document and a complete, fail-closed audit."""

    if policy not in POLICIES:
        raise ValueError(f"unsupported policy: {policy}")
    source_bytes = source_path.read_bytes()
    source_hash = _sha256_bytes(source_bytes)
    source = load_docling_json(source_path)
    failure_reason: str | None = None
    records: list[dict[str, Any]] = []
    try:
        records = build_element_order_map(source)
        candidates = detect_reading_order_candidates(source, records)
    except (KeyError, TypeError, ValueError) as exc:
        candidates = []
        failure_reason = f"detection_failed: {exc}"
    structure_routes: list[dict[str, Any]] = []
    structure_errors: list[dict[str, Any]] = []
    if failure_reason is None:
        structure_routes, structure_errors = route_structure_order_findings(source)
        if structure_errors:
            failure_reason = "structure_guard_failed"
    parent_by_ref = {
        record["self_ref"]: record.get("parent_ref") for record in records
    }
    text_risk_pages = {
        record["page_numbers"][0]
        for record in records
        if record.get("page_numbers")
        and isinstance(record.get("text"), str)
        and (
            "�" in record["text"]
            or any(
                (ord(char) < 32 and char not in "\t\n\r")
                or 0x7F <= ord(char) <= 0x9F
                for char in record["text"]
            )
        )
    }

    def evidence_refs(value: Any) -> set[str]:
        refs: set[str] = set()
        if isinstance(value, dict):
            for nested in value.values():
                refs.update(evidence_refs(nested))
        elif isinstance(value, list):
            for nested in value:
                refs.update(evidence_refs(nested))
        elif isinstance(value, str) and value.startswith("#/"):
            refs.add(value)
        return refs

    routes_by_page = {route["page_no"]: route for route in structure_routes}
    policy_blockers: dict[str, list[str]] = {}
    for candidate in candidates:
        candidate_id = candidate.get("candidate_id")
        if (
            not isinstance(candidate_id, str)
            or candidate.get("type") != "LOCAL_VERTICAL_INVERSION"
            or candidate.get("decision") != "AUTO_REORDER_ELIGIBLE"
        ):
            continue
        reasons: list[str] = []
        page_no = candidate.get("page_no")
        route = routes_by_page.get(page_no)
        if route is not None:
            dense_pair_count = sum(
                evidence.get("pair_count", 0)
                for evidence in route.get("evidence", [])
                if isinstance(evidence.get("pair_count", 0), int)
            )
            route_parents = {
                parent_by_ref.get(ref) for ref in evidence_refs(route["evidence"])
            }
            if dense_pair_count >= DENSE_ROW_PAIR_BLOCK_THRESHOLD:
                reasons.append("HIGH_DENSITY_ROW_STRUCTURE_RISK")
            elif route.get("review_priority") == "CORROBORATED":
                reasons.append("CORROBORATED_STRUCTURE_ORDER_RISK")
            elif candidate.get("parent_ref") == "#/body":
                reasons.append("BODY_LEVEL_STRUCTURE_ORDER_RISK")
            elif candidate.get("parent_ref") in route_parents:
                reasons.append("SAME_PARENT_STRUCTURE_ORDER_RISK")
        if reasons:
            policy_blockers[candidate_id] = reasons

    proposal = _compile_validated_local_v1(
        source_hash, candidates, set(policy_blockers)
    )
    validation = validate_proposals(source, source_hash, [proposal])

    result = deepcopy(source)
    apply_audit: list[dict[str, Any]] = []
    if (
        failure_reason is None
        and policy == "validated-local-v1"
        and proposal["decisions"]
    ):
        if validation["valid"]:
            try:
                result, apply_audit = apply_review_map(source, proposal)
            except (KeyError, TypeError, ValueError) as exc:
                result = deepcopy(source)
                apply_audit = []
                failure_reason = f"apply_failed: {exc}"
        else:
            failure_reason = "proposal_validation_failed"

    changed = any(item.get("status") == "APPLIED" for item in apply_audit)
    outcome = "CORRECTED" if changed else "PRESERVED"
    review_counts: dict[str, int] = {}
    for candidate in candidates:
        key = str(candidate.get("decision", "UNKNOWN"))
        review_counts[key] = review_counts.get(key, 0) + 1
    blocker_counts = Counter(
        reason
        for reasons in policy_blockers.values()
        for reason in reasons
    )
    detector_config = asdict(DetectorConfig())
    relation_audit = build_relation_audit(candidates, records)
    audit = {
        "schema_version": "reading-order-postprocess.v1",
        "outcome": outcome,
        "policy": policy,
        "policy_version": POLICY_VERSION,
        "policy_config": {
            "local_vertical_inversion": {
                "min_vertical_gap_norm": detector_config["min_vertical_gap"],
                "max_vertical_gap_norm": detector_config["max_vertical_gap"],
                "left_alignment_tolerance_norm": detector_config[
                    "left_alignment_tolerance"
                ],
                "visual_intervening_sibling_max": 0,
                "complex_geometry_allowed": False,
                "text_quality_flags_allowed": False,
            },
            "structure_guard": {
                "dense_row_pair_block_threshold": DENSE_ROW_PAIR_BLOCK_THRESHOLD,
                "corroborated_subtype_block": True,
                "body_level_or_same_parent_block": True,
            },
        },
        "source_mutated": False,
        "source_sha256": source_hash,
        "source_semantic_sha256": _sha256_bytes(_json_bytes(source)),
        "output_semantic_sha256": _sha256_bytes(_json_bytes(result)),
        "candidate_count": len(candidates),
        "candidate_decision_counts": review_counts,
        "policy_blockers": policy_blockers,
        "policy_blocker_counts": dict(sorted(blocker_counts.items())),
        "text_risk_pages": sorted(text_risk_pages),
        "structure_routes": structure_routes,
        "structure_scanner_errors": structure_errors,
        "policy_approved_count": len(proposal["decisions"]),
        "applied_count": sum(
            item.get("status") == "APPLIED" for item in apply_audit
        ),
        "already_applied_count": sum(
            item.get("status") == "ALREADY_APPLIED" for item in apply_audit
        ),
        "failure_reason": failure_reason,
        "validation": validation,
        "proposal": proposal,
        "apply_audit": apply_audit,
        "candidates": candidates,
        "relation_audit": relation_audit,
    }
    return result, audit


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Fail-closed Docling reading-order postprocess. Use shadow for "
            "the first integration run; validated-local-v1 applies only the "
            "frozen same-parent adjacent local-inversion rule."
        )
    )
    parser.add_argument("source_json", type=Path, help="input Docling JSON")
    parser.add_argument(
        "output_json",
        type=Path,
        help="corrected JSON, or an unchanged copy when outcome is PRESERVED",
    )
    parser.add_argument(
        "audit_json", type=Path, help="candidate, guard, apply, and failure audit"
    )
    parser.add_argument(
        "--policy",
        choices=sorted(POLICIES),
        default="shadow",
        help="shadow never mutates; validated-local-v1 enables verified swaps",
    )
    args = parser.parse_args()

    _validate_output_paths(args.source_json, args.output_json, args.audit_json)
    result, audit = run_postprocess(args.source_json, args.policy)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.audit_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_bytes(_json_bytes(result))
    args.audit_json.write_bytes(_json_bytes(audit))
    print(
        json.dumps(
            {
                "outcome": audit["outcome"],
                "policy": audit["policy"],
                "candidate_count": audit["candidate_count"],
                "applied_count": audit["applied_count"],
                "failure_reason": audit["failure_reason"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
