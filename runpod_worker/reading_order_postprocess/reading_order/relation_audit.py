"""Build fail-closed audit records for non-executable order relations."""

from __future__ import annotations

from typing import Any

from .relations import validate_relation_edges


def build_relation_audit(
    candidates: list[dict[str, Any]], records: list[dict[str, Any]]
) -> dict[str, Any]:
    """Validate endpoint identity, page, parent scope and relation graph."""

    records_by_ref = {record["self_ref"]: record for record in records}
    edges: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for candidate in candidates:
        if candidate.get("operation") != "RELATION_ONLY":
            continue
        source_ref = candidate.get("from_ref")
        target_ref = candidate.get("to_ref")
        source = records_by_ref.get(source_ref)
        target = records_by_ref.get(target_ref)
        page_no = candidate.get("page_no")
        parent_ref = candidate.get("parent_ref")
        reasons: list[str] = []
        if source is None:
            reasons.append("FROM_REF_NOT_FOUND")
        if target is None:
            reasons.append("TO_REF_NOT_FOUND")
        if candidate.get("relation") not in {"BEFORE", "ADJACENT_BEFORE"}:
            reasons.append("UNSUPPORTED_ORDER_RELATION")
        if source is not None and page_no not in source.get("page_numbers", []):
            reasons.append("FROM_PAGE_SCOPE_MISMATCH")
        if target is not None and page_no not in target.get("page_numbers", []):
            reasons.append("TO_PAGE_SCOPE_MISMATCH")
        if source is not None and source.get("parent_ref") != parent_ref:
            reasons.append("FROM_PARENT_SCOPE_MISMATCH")
        if target is not None and target.get("parent_ref") != parent_ref:
            reasons.append("TO_PARENT_SCOPE_MISMATCH")
        if not isinstance(parent_ref, str) or not parent_ref.startswith("#/"):
            reasons.append("INVALID_PARENT_SCOPE")
        if reasons:
            rejected.append({
                "candidate_id": candidate.get("candidate_id"),
                "reasons": reasons,
            })
            continue
        edges.append({
            "edge_id": f"REL-{candidate['candidate_id']}",
            "relation": candidate["relation"],
            "from_ref": source_ref,
            "to_ref": target_ref,
            "page_no": page_no,
            "scope_parent_ref": parent_ref,
            "candidate_id": candidate["candidate_id"],
            "candidate_type": candidate.get("type"),
            "confidence": candidate.get("confidence"),
            "reason": candidate.get("reason"),
            "metrics": candidate.get("metrics", {}),
        })

    validation_error: str | None = None
    try:
        validation = validate_relation_edges(edges)
    except ValueError as exc:
        validation = None
        validation_error = str(exc)
    return {
        "mode": "SHADOW_RELATION_ONLY",
        "source_mutated": False,
        "auto_reorder_eligible": False,
        "candidate_count": len(edges) + len(rejected),
        "valid": validation is not None and not rejected,
        "validation": validation,
        "validation_error": validation_error,
        "edges": edges,
        "rejected_candidates": rejected,
    }
