"""Conservatively triage continuation reviews using semantic boundaries."""

from __future__ import annotations

from typing import Any

from .features import add_spatial_features

JsonObject = dict[str, Any]
HARD_BOUNDARY_LABELS = frozenset({"section_header", "title", "table", "picture"})


def _overlap(start_a: float, end_a: float, start_b: float, end_b: float) -> float:
    return max(0.0, min(end_a, end_b) - max(start_a, start_b))


def _physically_blocks_corridor(
    anchor: JsonObject,
    candidate: JsonObject,
    boundary: JsonObject,
    direction: str | None,
) -> bool:
    if boundary["page_no"] != anchor["page_no"] or boundary["page_no"] != candidate["page_no"]:
        return False
    if direction == "RIGHT":
        gap_left = min(anchor["right_norm"], candidate["left_norm"])
        gap_right = max(anchor["right_norm"], candidate["left_norm"])
        if not gap_right > gap_left:
            return False
        x_overlap = _overlap(
            gap_left, gap_right, boundary["left_norm"], boundary["right_norm"]
        )
        vertical_band_bottom = min(anchor["bottom_norm"], candidate["bottom_norm"])
        vertical_band_top = max(anchor["top_norm"], candidate["top_norm"])
        y_overlap = _overlap(
            vertical_band_bottom,
            vertical_band_top,
            boundary["bottom_norm"],
            boundary["top_norm"],
        )
        return x_overlap > 1e-6 and y_overlap > 1e-6
    if direction == "DOWN":
        gap_bottom = min(candidate["top_norm"], anchor["bottom_norm"])
        gap_top = max(candidate["top_norm"], anchor["bottom_norm"])
        if not gap_top > gap_bottom:
            return False
        y_overlap = _overlap(
            gap_bottom, gap_top, boundary["bottom_norm"], boundary["top_norm"]
        )
        horizontal_band_left = min(anchor["left_norm"], candidate["left_norm"])
        horizontal_band_right = max(anchor["right_norm"], candidate["right_norm"])
        x_overlap = _overlap(
            horizontal_band_left,
            horizontal_band_right,
            boundary["left_norm"],
            boundary["right_norm"],
        )
        return y_overlap > 1e-6 and x_overlap > 1e-6
    return False


def triage_continuation_reviews(
    document: dict[str, Any],
    report: dict[str, Any],
    records: list[dict[str, Any]],
) -> JsonObject:
    """Block review promotion or auto-reorder when a move crosses a hard boundary.

    This is intentionally not a correctness label.  A boundary-blocked item is
    merely unsafe to auto-promote; it is not automatically marked as an error
    or as a confirmed preserve relation.
    """

    enriched = add_spatial_features(document, records)
    index_by_ref = {record["self_ref"]: index for index, record in enumerate(enriched)}
    triaged: list[JsonObject] = []
    counts = {
        "AUTO_BLOCKED_STRUCTURAL_BOUNDARY": 0,
        "AUTO_REORDER_ELIGIBLE": 0,
        "REVIEW_REQUIRED": 0,
    }
    for analysis in report.get("analyses", []):
        source_decision = analysis.get("decision")
        if source_decision not in {"REVIEW_REQUIRED", "AUTO_REORDER_ELIGIBLE"}:
            continue
        anchor_ref = analysis.get("anchor_ref")
        candidate_ref = analysis.get("best_successor_ref")
        if anchor_ref not in index_by_ref or candidate_ref not in index_by_ref:
            decision = source_decision
            boundaries: list[JsonObject] = []
        else:
            first, second = sorted(
                (index_by_ref[anchor_ref], index_by_ref[candidate_ref])
            )
            sequence_boundaries = [
                {
                    "self_ref": record["self_ref"],
                    "label": record.get("label"),
                }
                for record in enriched[first + 1 : second]
                if record.get("label") in HARD_BOUNDARY_LABELS
            ]
            anchor = enriched[index_by_ref[anchor_ref]]
            candidate = enriched[index_by_ref[candidate_ref]]
            by_ref = {record["self_ref"]: record for record in enriched}
            boundaries = [
                boundary
                for boundary in sequence_boundaries
                if _physically_blocks_corridor(
                    anchor,
                    candidate,
                    by_ref[boundary["self_ref"]],
                    analysis.get("best_direction"),
                )
            ]
            decision = (
                "AUTO_BLOCKED_STRUCTURAL_BOUNDARY"
                if boundaries
                else source_decision
            )
        counts[decision] += 1
        triaged.append(
            {
                "page_no": analysis.get("page_no"),
                "anchor_ref": anchor_ref,
                "candidate_ref": candidate_ref,
                "direction": analysis.get("best_direction"),
                "decision": decision,
                "boundaries": boundaries,
                "sequence_boundary_count": len(sequence_boundaries) if anchor_ref in index_by_ref and candidate_ref in index_by_ref else 0,
                "source_decision": source_decision,
            }
        )
    return {
        "schema_version": "continuation-review-triage.v2",
        "mode": "ANALYSIS_ONLY",
        "source_mutated": False,
        "counts": counts,
        "items": triaged,
    }
