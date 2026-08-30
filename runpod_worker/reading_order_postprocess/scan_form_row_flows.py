"""Analysis-only scanner for form fields read column-first instead of row-first.

This module does not emit corrections. It finds repeated "late returns" to the
same visual row after the body order has already moved downward, then groups
them into compact form-like bands for human review.
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


def _center_y(item: dict[str, Any]) -> float:
    return (item["top_norm"] + item["bottom_norm"]) / 2


def _center_x(item: dict[str, Any]) -> float:
    return (item["left_norm"] + item["right_norm"]) / 2


def find_form_row_return_clusters(
    document: dict[str, Any],
    *,
    min_pair_count: int = 2,
    row_tolerance: float = 0.018,
) -> list[dict[str, Any]]:
    records = add_spatial_features(document, build_element_order_map(document))
    by_page: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for item in records:
        text = (item.get("text") or "").strip()
        if (
            item.get("label") in {"text", "section_header"}
            and 0 < len(text) <= 30
            and item["width_norm"] <= 0.22
        ):
            by_page[item["page_no"]].append(item)

    output = []
    for page_no, items in sorted(by_page.items()):
        items.sort(key=lambda item: item["order_index"])
        pairs = []
        for left_index, anchor in enumerate(items):
            for return_item in items[left_index + 1 :]:
                order_gap = return_item["order_index"] - anchor["order_index"]
                if order_gap < 3:
                    continue
                horizontal_delta = _center_x(return_item) - _center_x(anchor)
                if not 0.04 <= horizontal_delta <= 0.45:
                    continue
                row_delta = abs(_center_y(return_item) - _center_y(anchor))
                if row_delta > row_tolerance:
                    continue
                row_center = (_center_y(anchor) + _center_y(return_item)) / 2
                intervening_below = [
                    item
                    for item in items
                    if anchor["order_index"] < item["order_index"] < return_item["order_index"]
                    and _center_y(item) < row_center - 0.012
                ]
                if len(intervening_below) < 1:
                    continue
                pairs.append(
                    {
                        "anchor_ref": anchor["self_ref"],
                        "return_ref": return_item["self_ref"],
                        "anchor_text": anchor.get("text"),
                        "return_text": return_item.get("text"),
                        "anchor_order": anchor["visual_order"],
                        "return_order": return_item["visual_order"],
                        "row_center_norm": round(row_center, 6),
                        "order_gap": order_gap,
                        "intervening_below_count": len(intervening_below),
                        "half": 0 if (_center_x(anchor) + _center_x(return_item)) / 2 < 0.5 else 1,
                    }
                )

        for half in (0, 1):
            half_pairs = [pair for pair in pairs if pair["half"] == half]
            if len(half_pairs) < min_pair_count:
                continue
            half_pairs.sort(key=lambda pair: -pair["row_center_norm"])
            clusters: list[list[dict[str, Any]]] = []
            for pair in half_pairs:
                if not clusters or abs(
                    clusters[-1][-1]["row_center_norm"] - pair["row_center_norm"]
                ) > 0.10:
                    clusters.append([pair])
                else:
                    clusters[-1].append(pair)
            for cluster in clusters:
                unique_rows = {round(pair["row_center_norm"], 3) for pair in cluster}
                if len(cluster) < min_pair_count or len(unique_rows) < min_pair_count:
                    continue
                output.append(
                    {
                        "page_no": page_no,
                        "page_half": "LEFT" if half == 0 else "RIGHT",
                        "analysis_status": "REVIEW_ONLY",
                        "candidate_kind": "FORM_ROW_MAJOR_RETURN",
                        "pair_count": len(cluster),
                        "pairs": cluster,
                        "auto_reorder_eligible": False,
                        "reason": "같은 행의 오른쪽 필드가 여러 아래 요소 뒤에 기록되는 패턴이 반복됨",
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
            for row in find_form_row_return_clusters(load_docling_json(source)):
                row["corpus_root"] = str(root)
                row["source_json"] = str(source.relative_to(root)).replace("\\", "/")
                rows.append(row)
    result = {
        "schema_version": "reading-order-form-row-scan.v1",
        "mode": "ANALYSIS_ONLY",
        "heading_scope": "READ_ONLY_NOT_MODIFIED",
        "source_mutated": False,
        "scanned_document_count": document_count,
        "review_row_count": len(rows),
        "rows": rows,
        "interpretation": "후보는 양식형 행 복귀 검토 대상이며 자동 보정 승인이 아니다.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"documents": document_count, "review_rows": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
