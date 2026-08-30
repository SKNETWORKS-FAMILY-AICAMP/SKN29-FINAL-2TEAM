"""Analysis-only scanner for multi-row comparison grids read column-first.

The scanner uses geometry and body/group structure only.  It does not rely on
words such as "current" or "revision", and it never emits a correction.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
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


def _eligible(item: dict[str, Any]) -> bool:
    parent = str(item.get("parent_ref", ""))
    if parent != "#/body" and not parent.startswith("#/groups/"):
        return False
    if item.get("label") not in {"text", "section_header", "list_item", "picture"}:
        return False
    if item.get("label") != "picture" and not (item.get("text") or "").strip():
        return False
    if item.get("label") in {"page_header", "page_footer"}:
        return False
    return item["width_norm"] <= 0.43 and item["height_norm"] <= 0.55


def _column_clusters(items: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    ordered = sorted(items, key=_cx)
    raw: list[list[dict[str, Any]]] = []
    for item in ordered:
        if not raw or _cx(item) - _cx(raw[-1][-1]) >= 0.11:
            raw.append([item])
        else:
            raw[-1].append(item)
    clusters = [cluster for cluster in raw if len(cluster) >= 2]
    if not 3 <= len(clusters) <= 5:
        return []
    return clusters


def _row_starts(cluster: list[dict[str, Any]]) -> list[float]:
    ordered = sorted(cluster, key=lambda item: -item["top_norm"])
    starts = [ordered[0]["top_norm"]]
    previous_bottom = ordered[0]["bottom_norm"]
    for item in ordered[1:]:
        gap = previous_bottom - item["top_norm"]
        if gap >= 0.045:
            starts.append(item["top_norm"])
        previous_bottom = min(previous_bottom, item["bottom_norm"])
    return starts


def _aligned_row_bands(columns: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    points = [
        (start, column_index)
        for column_index, column in enumerate(columns)
        for start in _row_starts(column)
    ]
    bands: list[dict[str, Any]] = []
    for value, column_index in sorted(points, reverse=True):
        target = next(
            (band for band in bands if abs(band["center"] - value) <= 0.025),
            None,
        )
        if target is None:
            bands.append({"values": [value], "columns": {column_index}, "center": value})
        else:
            target["values"].append(value)
            target["columns"].add(column_index)
            target["center"] = sum(target["values"]) / len(target["values"])
    minimum_coverage = max(2, len(columns) - 1)
    return [band for band in bands if len(band["columns"]) >= minimum_coverage]


def _is_column_first(columns: list[list[dict[str, Any]]]) -> bool:
    ordered_columns = sorted(columns, key=lambda cluster: sum(_cx(i) for i in cluster) / len(cluster))
    separated = 0
    for left, right in zip(ordered_columns, ordered_columns[1:]):
        if max(item["order_index"] for item in left) < min(
            item["order_index"] for item in right
        ):
            separated += 1
    return separated == len(ordered_columns) - 1


def _review_blockers(items: list[dict[str, Any]]) -> list[str]:
    texts = [
        (item.get("text") or "").strip()
        for item in items
        if item.get("label") != "picture" and (item.get("text") or "").strip()
    ]
    picture_count = sum(item.get("label") == "picture" for item in items)
    blockers = []
    page_reference_ratio = (
        sum(bool(re.match(r"^\d{1,3}\b", text)) for text in texts) / len(texts)
        if texts
        else 0.0
    )
    if len(texts) >= 10 and page_reference_ratio >= 0.45:
        blockers.append("TOC_LIKE_PAGE_REFERENCE_DENSITY")
    if (
        picture_count >= 3
        and len(texts) >= 6
        and statistics.median(len(text) for text in texts) <= 40
    ):
        blockers.append("REPEATED_CARD_LIKE_PICTURE_SHORT_TEXT")
    return blockers


def find_comparison_grid_candidates(document: dict[str, Any]) -> list[dict[str, Any]]:
    records = add_spatial_features(document, build_element_order_map(document))
    by_page: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for item in records:
        if _eligible(item):
            by_page[item["page_no"]].append(item)

    output = []
    for page_no, items in sorted(by_page.items()):
        columns = _column_clusters(items)
        if not columns or not _is_column_first(columns):
            continue
        bands = _aligned_row_bands(columns)
        if len(bands) < 2:
            continue
        if not any(len(band["columns"]) == len(columns) for band in bands):
            continue
        blockers = _review_blockers(items)
        output.append(
            {
                "page_no": page_no,
                "analysis_status": "REVIEW_ONLY",
                "candidate_kind": "COMPARISON_GRID_COLUMN_FIRST",
                "column_count": len(columns),
                "column_refs": [[item["self_ref"] for item in column] for column in columns],
                "aligned_row_band_count": len(bands),
                "aligned_row_bands": [
                    {
                        "center_norm": round(band["center"], 6),
                        "covered_column_count": len(band["columns"]),
                    }
                    for band in bands
                ],
                "review_blockers": blockers,
                "review_priority": "HIGH" if not blockers else "BLOCKED_LOW",
                "auto_reorder_eligible": False,
                "reason": "3개 이상 열에서 반복 행 시작점이 정렬되지만 body는 각 열을 끝까지 읽은 뒤 다음 열로 이동함",
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
            for row in find_comparison_grid_candidates(load_docling_json(source)):
                row["corpus_root"] = str(root)
                row["source_json"] = str(source.relative_to(root)).replace("\\", "/")
                rows.append(row)
    result = {
        "schema_version": "reading-order-comparison-grid-scan.v1",
        "mode": "ANALYSIS_ONLY",
        "heading_scope": "READ_ONLY_NOT_MODIFIED",
        "ocr_scope": "READ_ONLY_NOT_MODIFIED",
        "source_mutated": False,
        "scanned_document_count": document_count,
        "review_candidate_count": len(rows),
        "high_priority_count": sum(row["review_priority"] == "HIGH" for row in rows),
        "blocked_low_priority_count": sum(
            row["review_priority"] == "BLOCKED_LOW" for row in rows
        ),
        "rows": rows,
        "interpretation": "후보는 비교 그리드 검토 대상이며 자동 보정 승인이 아니다.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"documents": document_count, "review_candidates": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
