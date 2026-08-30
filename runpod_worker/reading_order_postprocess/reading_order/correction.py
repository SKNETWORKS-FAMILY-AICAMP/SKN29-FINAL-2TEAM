"""Apply a deliberately small, auditable Reading Order correction policy."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any


JsonObject = dict[str, Any]

AUTO_TYPES = frozenset(
    {"LOCAL_VERTICAL_INVERSION", "INTERRUPTED_COLUMN_CONTINUATION"}
)


def build_auto_correction_map(
    candidates: list[JsonObject],
) -> JsonObject:
    """Select only externally validated, high-confidence local inversions."""

    corrections = []
    rejected = []
    for candidate in candidates:
        operation = candidate.get("operation", "SWAP_ADJACENT")
        safe_swap = (
            candidate.get("type") in AUTO_TYPES
            and candidate.get("confidence") == "HIGH"
            and candidate.get("decision") == "AUTO_REORDER_ELIGIBLE"
            and isinstance(candidate.get("parent_ref"), str)
            and len(candidate.get("observed_order", [])) == 2
            and len(candidate.get("proposed_order", [])) == 2
            and operation == "SWAP_ADJACENT"
            and candidate["proposed_order"] == list(reversed(candidate["observed_order"]))
            and candidate.get("metrics", {}).get(
                "visual_intervening_sibling_count", 0
            )
            == 0
        )
        safe_move_after = (
            candidate.get("type") == "INTERRUPTED_COLUMN_CONTINUATION"
            and candidate.get("confidence") == "HIGH"
            and candidate.get("decision") == "AUTO_REORDER_ELIGIBLE"
            and isinstance(candidate.get("parent_ref"), str)
            and operation == "MOVE_AFTER"
            and len(candidate.get("observed_order", [])) == 2
            and candidate.get("metrics", {}).get("downward_alternative_found") is False
        )
        if safe_swap or safe_move_after:
            corrections.append(
                {
                    "candidate_id": candidate.get("candidate_id"),
                    "page_no": candidate.get("page_no"),
                    "type": candidate["type"],
                    "confidence": candidate["confidence"],
                    "parent_ref": candidate["parent_ref"],
                    "operation": operation,
                    "observed_order": candidate["observed_order"],
                    "corrected_order": candidate["proposed_order"],
                    "status": "AUTO_APPROVED",
                }
            )
        else:
            rejected.append(
                {
                    "candidate_id": candidate.get("candidate_id"),
                    "type": candidate.get("type"),
                    "confidence": candidate.get("confidence"),
                    "status": "REVIEW_REQUIRED",
                }
            )
    return {
        "policy": "validated_high_confidence_local_inversion_or_interrupted_continuation",
        "source_mutated": False,
        "correction_count": len(corrections),
        "review_required_count": len(rejected),
        "corrections": corrections,
        "review_required": rejected,
    }


def _resolve_ref(document: Mapping[str, Any], ref: str) -> JsonObject:
    if not ref.startswith("#/"):
        raise ValueError(f"Unsupported reference: {ref!r}")
    current: Any = document
    for part in ref[2:].split("/"):
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, Mapping):
            current = current[part]
        else:
            raise ValueError(f"Reference traverses a scalar: {ref!r}")
    if not isinstance(current, dict):
        raise ValueError(f"Reference is not an object: {ref!r}")
    return current


def apply_correction_map(
    document: JsonObject, correction_map: Mapping[str, Any]
) -> tuple[JsonObject, list[JsonObject]]:
    """Return a corrected deep copy and an application audit log."""

    corrected = copy.deepcopy(document)
    audit = []
    used_refs: set[str] = set()
    for correction in correction_map.get("corrections", []):
        if correction.get("status") != "AUTO_APPROVED":
            continue
        parent_ref = correction["parent_ref"]
        operation = correction.get("operation", "SWAP_ADJACENT")
        observed = correction["observed_order"]
        proposed = correction["corrected_order"]
        if any(ref in used_refs for ref in observed):
            raise ValueError(f"Overlapping correction: {observed!r}")
        parent = _resolve_ref(corrected, parent_ref)
        children = parent.get("children")
        if not isinstance(children, list):
            raise ValueError(f"Parent has no children array: {parent_ref!r}")
        child_refs = [child.get("$ref") for child in children]
        first_index = child_refs.index(observed[0])
        second_index = child_refs.index(observed[1])
        if operation == "SWAP_ADJACENT":
            if (
                second_index + 1 == first_index
                and proposed == [observed[1], observed[0]]
            ):
                used_refs.update(observed)
                audit.append(
                    {
                        "candidate_id": correction.get("candidate_id"),
                        "parent_ref": parent_ref,
                        "operation": operation,
                        "before": proposed,
                        "after": proposed,
                        "status": "ALREADY_APPLIED",
                    }
                )
                continue
            if second_index != first_index + 1:
                raise ValueError(f"Correction refs are not adjacent siblings: {observed!r}")
            if proposed != [observed[1], observed[0]]:
                raise ValueError(f"Only adjacent swaps are supported: {proposed!r}")
            children[first_index], children[second_index] = (
                children[second_index],
                children[first_index],
            )
        elif operation == "MOVE_AFTER":
            if second_index == first_index + 1:
                used_refs.update(observed)
                audit.append(
                    {
                        "candidate_id": correction.get("candidate_id"),
                        "parent_ref": parent_ref,
                        "operation": operation,
                        "before": proposed,
                        "after": proposed,
                        "status": "ALREADY_APPLIED",
                    }
                )
                continue
            if second_index < first_index:
                raise ValueError(f"MOVE_AFTER requires an interrupted order: {observed!r}")
            moved = children.pop(second_index)
            children.insert(first_index + 1, moved)
        else:
            raise ValueError(f"Unsupported correction operation: {operation!r}")
        used_refs.update(observed)
        audit.append(
            {
                "candidate_id": correction.get("candidate_id"),
                "parent_ref": parent_ref,
                "operation": operation,
                "before": observed,
                "after": proposed,
                "status": "APPLIED",
            }
        )
    return corrected, audit
