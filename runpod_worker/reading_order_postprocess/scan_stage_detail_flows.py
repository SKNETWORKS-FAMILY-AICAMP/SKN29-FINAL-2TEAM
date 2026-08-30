"""Analysis-only scanner for stage labels separated from their detail groups.

It detects two orthogonal layouts without relying on stage-specific words:

* VERTICAL_PARENTS: stage labels stacked vertically, details to the right.
* HORIZONTAL_PARENTS: stage labels in a top row, details below each column.

The scanner only creates review candidates.  It never mutates Docling order.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

PRACTICE_ROOT = Path(__file__).resolve().parent
if str(PRACTICE_ROOT) not in sys.path:
    sys.path.insert(0, str(PRACTICE_ROOT))

from reading_order import build_element_order_map, load_docling_json  # noqa: E402
from reading_order.features import add_spatial_features  # noqa: E402


def _cx(item: dict[str, Any]) -> float:
    return (item["left_norm"] + item["right_norm"]) / 2


def _cy(item: dict[str, Any]) -> float:
    return (item["top_norm"] + item["bottom_norm"]) / 2


def _is_parent_label(item: dict[str, Any]) -> bool:
    text = (item.get("text") or "").strip()
    return (
        item.get("parent_ref") == "#/body"
        and item.get("label") in {"text", "section_header"}
        and 0 < len(text) <= 40
        and item["width_norm"] <= 0.16
    )


def _is_group_child(item: dict[str, Any]) -> bool:
    return (
        str(item.get("parent_ref", "")).startswith("#/groups/")
        and item.get("label") in {"text", "list_item"}
        and bool((item.get("text") or "").strip())
    )


def _aligned_parent_sets(
    parents: list[dict[str, Any]], *, orientation: str
) -> list[list[dict[str, Any]]]:
    axis = _cx if orientation == "VERTICAL_PARENTS" else _cy
    cross = _cy if orientation == "VERTICAL_PARENTS" else _cx
    tolerance = 0.04 if orientation == "VERTICAL_PARENTS" else 0.025
    minimum_span = 0.15
    ordered = sorted(parents, key=lambda item: item["order_index"])
    candidates: list[list[dict[str, Any]]] = []
    # Use compact sliding runs instead of taking every label in the same axis
    # band.  Real pages often contain a title and another diagram on the same
    # x coordinate; swallowing all of them hid the actual four-stage run.
    for start in range(len(ordered)):
        for size in range(3, 7):
            aligned = ordered[start : start + size]
            if len(aligned) != size:
                continue
            if len({item.get("label") for item in aligned}) != 1:
                continue
            if max(axis(item) for item in aligned) - min(axis(item) for item in aligned) > tolerance * 2:
                continue
            if max(cross(item) for item in aligned) - min(cross(item) for item in aligned) < minimum_span:
                continue
            # Stage labels should be one compact body-order run.  Small gaps
            # allow arrows/pictures between vertical labels.
            if aligned[-1]["order_index"] - aligned[0]["order_index"] > len(aligned) * 3:
                continue
            candidates.append(aligned)

    # Prefer maximal runs and suppress their three-label subsets.
    output: list[list[dict[str, Any]]] = []
    for candidate in sorted(candidates, key=len, reverse=True):
        refs = {item["self_ref"] for item in candidate}
        if any(refs < {item["self_ref"] for item in existing} for existing in output):
            continue
        output.append(candidate)
    return output


def _match_children(
    parents: list[dict[str, Any]],
    children: list[dict[str, Any]],
    *,
    orientation: str,
) -> dict[str, list[dict[str, Any]]] | None:
    latest_parent_order = max(parent["order_index"] for parent in parents)
    matches: dict[str, list[dict[str, Any]]] = {parent["self_ref"]: [] for parent in parents}
    if orientation == "VERTICAL_PARENTS":
        candidate_children = [
            child
            for child in children
            if child["order_index"] > latest_parent_order
            and child["left_norm"] > max(parent["right_norm"] for parent in parents) + 0.005
            and min(_cy(parent) for parent in parents) - 0.06
            <= _cy(child)
            <= max(_cy(parent) for parent in parents) + 0.06
        ]
        for child in candidate_children:
            parent = min(parents, key=lambda item: abs(_cy(item) - _cy(child)))
            if abs(_cy(parent) - _cy(child)) <= 0.085:
                matches[parent["self_ref"]].append(child)
        # One or two flattened groups are expected in this orientation.  A
        # large number of unrelated groups usually indicates ordinary columns.
        group_refs = {child["parent_ref"] for values in matches.values() for child in values}
        if len(group_refs) > 2:
            return None
    else:
        candidate_children = [
            child
            for child in children
            if child["order_index"] > latest_parent_order
            and child["top_norm"] < min(parent["bottom_norm"] for parent in parents) - 0.005
            and min(_cx(parent) for parent in parents) - 0.06
            <= _cx(child)
            <= max(_cx(parent) for parent in parents) + 0.06
        ]
        parent_centers = sorted(_cx(parent) for parent in parents)
        spacing = min(
            right - left for left, right in zip(parent_centers, parent_centers[1:])
        )
        max_distance = min(0.08, spacing * 0.60)
        for child in candidate_children:
            parent = min(parents, key=lambda item: abs(_cx(item) - _cx(child)))
            if abs(_cx(parent) - _cx(child)) <= max_distance:
                matches[parent["self_ref"]].append(child)

    if any(not values for values in matches.values()):
        return None
    if sum(len(values) for values in matches.values()) < len(parents) + 2:
        return None
    return matches


def _match_two_axis_matrix(
    parents: list[dict[str, Any]], items: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Match a guarded two-column hierarchy flattened column-first.

    Two ordinary article columns are intentionally excluded by requiring many
    short descendants and at least three aligned descendant rows.  This is a
    review signal only; it does not infer a corrected order.
    """
    if len(parents) != 2:
        return None
    left_parent, right_parent = sorted(parents, key=_cx)
    parent_gap = _cx(right_parent) - _cx(left_parent)
    if not 0.10 <= parent_gap <= 0.32:
        return None
    if abs(_cy(left_parent) - _cy(right_parent)) > 0.025:
        return None
    if abs(left_parent["order_index"] - right_parent["order_index"]) > 2:
        return None

    latest_parent_order = max(item["order_index"] for item in parents)
    midpoint = (_cx(left_parent) + _cx(right_parent)) / 2
    descendants = [
        item
        for item in items
        if item["order_index"] > latest_parent_order
        and item.get("label") in {"text", "section_header", "list_item"}
        and bool((item.get("text") or "").strip())
        and len((item.get("text") or "").strip()) <= 80
        and item["height_norm"] <= 0.09
        and item["width_norm"] <= 0.20
        and item["top_norm"] < min(p["bottom_norm"] for p in parents) + 0.01
        and _cx(left_parent) - 0.09 <= _cx(item) <= _cx(right_parent) + 0.09
    ]
    left = [item for item in descendants if _cx(item) < midpoint]
    right = [item for item in descendants if _cx(item) >= midpoint]
    if len(left) < 4 or len(right) < 4:
        return None

    # Require a dense leading column before the other column begins.  Ignore
    # later footer/process rows that span the matrix and can legitimately
    # return to the first column.
    left_leading = [
        item for item in left
        if item["order_index"] < min(other["order_index"] for other in right)
    ]
    right_leading = [
        item for item in right
        if item["order_index"] < min(other["order_index"] for other in left)
    ]
    if len(left_leading) >= 4:
        first_side, first_items, second_items = "LEFT", left_leading, right
    elif len(right_leading) >= 4:
        first_side, first_items, second_items = "RIGHT", right_leading, left
    else:
        return None

    unmatched_second = list(second_items)
    aligned_pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for first_item in sorted(first_items, key=_cy, reverse=True):
        if not unmatched_second:
            break
        second_item = min(
            unmatched_second, key=lambda item: abs(_cy(item) - _cy(first_item))
        )
        if abs(_cy(second_item) - _cy(first_item)) <= 0.025:
            aligned_pairs.append((first_item, second_item))
            unmatched_second.remove(second_item)
    if len(aligned_pairs) < 3:
        return None

    return {
        "left_descendants": left,
        "right_descendants": right,
        "aligned_pairs": aligned_pairs,
        "column_first_side": first_side,
    }


def find_stage_detail_candidates(document: dict[str, Any]) -> list[dict[str, Any]]:
    records = add_spatial_features(document, build_element_order_map(document))
    by_page: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for item in records:
        by_page[item["page_no"]].append(item)

    output = []
    for page_no, items in sorted(by_page.items()):
        parents = [item for item in items if _is_parent_label(item)]
        children = [item for item in items if _is_group_child(item)]
        for orientation in ("VERTICAL_PARENTS", "HORIZONTAL_PARENTS"):
            for parent_set in _aligned_parent_sets(parents, orientation=orientation):
                matches = _match_children(
                    parent_set, children, orientation=orientation
                )
                if matches is None:
                    continue
                output.append(
                    {
                        "page_no": page_no,
                        "analysis_status": "REVIEW_ONLY",
                        "candidate_kind": "STAGE_DETAIL_GROUPING",
                        "orientation": orientation,
                        "parent_refs": [item["self_ref"] for item in parent_set],
                        "parent_texts": [item.get("text") for item in parent_set],
                        "child_refs_by_parent": {
                            ref: [item["self_ref"] for item in values]
                            for ref, values in matches.items()
                        },
                        "child_count": sum(len(values) for values in matches.values()),
                        "auto_reorder_eligible": False,
                        "reason": "정렬된 단계 라벨이 모두 먼저 나오고 각 단계와 공간적으로 대응하는 group 자식이 나중에 몰려 있음",
                    }
                )

        # A two-axis strategy matrix needs stronger evidence than the generic
        # 3-6 stage case: consecutive peer headers, dense short descendants,
        # repeated aligned rows, and a fully column-first body order.
        ordered_parents = sorted(parents, key=lambda item: item["order_index"])
        for first, second in zip(ordered_parents, ordered_parents[1:]):
            if first.get("label") != second.get("label"):
                continue
            match = _match_two_axis_matrix([first, second], items)
            if match is None:
                continue
            output.append(
                {
                    "page_no": page_no,
                    "analysis_status": "REVIEW_ONLY",
                    "candidate_kind": "TWO_AXIS_STAGE_DETAIL_MATRIX",
                    "orientation": "HORIZONTAL_PARENTS",
                    "parent_refs": [first["self_ref"], second["self_ref"]],
                    "parent_texts": [first.get("text"), second.get("text")],
                    "descendant_refs_by_parent": {
                        first["self_ref"]: [
                            item["self_ref"] for item in match["left_descendants"]
                        ],
                        second["self_ref"]: [
                            item["self_ref"] for item in match["right_descendants"]
                        ],
                    },
                    "aligned_descendant_row_count": len(match["aligned_pairs"]),
                    "column_first_side": match["column_first_side"],
                    "auto_reorder_eligible": False,
                    "reason": "2개 상위 축과 짧은 하위 요소의 반복 행이 공간적으로 대응하지만 body는 한 열을 끝까지 읽은 뒤 다음 열로 이동함",
                }
            )
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus_roots", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    rows = []
    document_count = 0
    for root in args.corpus_roots:
        for source in sorted(root.rglob("document.json")):
            document_count += 1
            for row in find_stage_detail_candidates(load_docling_json(source)):
                row["corpus_root"] = str(root)
                row["source_json"] = str(source.relative_to(root)).replace("\\", "/")
                rows.append(row)
    result = {
        "schema_version": "reading-order-stage-detail-scan.v2",
        "mode": "ANALYSIS_ONLY",
        "heading_scope": "READ_ONLY_NOT_MODIFIED",
        "ocr_scope": "READ_ONLY_NOT_MODIFIED",
        "source_mutated": False,
        "scanned_document_count": document_count,
        "review_candidate_count": len(rows),
        "rows": rows,
        "interpretation": "후보는 단계-설명 분리 검토 대상이며 자동 보정 승인이 아니다.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"documents": document_count, "review_candidates": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
