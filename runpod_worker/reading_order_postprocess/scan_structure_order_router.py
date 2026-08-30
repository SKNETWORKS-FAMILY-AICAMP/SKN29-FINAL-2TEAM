"""Merge heterogeneous structure-order signals into page-level review routes.

This module deliberately does not infer a final order.  Form-like late row
returns, comparison grids and stage/detail groupings have different semantics,
but they all indicate that a pair-level local swap is insufficient.  The
router deduplicates those findings by page and preserves each detector's raw
evidence for later labeling.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

PRACTICE_ROOT = Path(__file__).resolve().parent
if str(PRACTICE_ROOT) not in sys.path:
    sys.path.insert(0, str(PRACTICE_ROOT))

from reading_order import load_docling_json  # noqa: E402
from scan_comparison_grid_flows import find_comparison_grid_candidates  # noqa: E402
from scan_form_row_flows import find_form_row_return_clusters  # noqa: E402
from scan_stage_detail_flows import find_stage_detail_candidates  # noqa: E402


Detector = tuple[str, Callable[[dict[str, Any]], list[dict[str, Any]]]]

DETECTORS: tuple[Detector, ...] = (
    ("form_row_return", find_form_row_return_clusters),
    ("comparison_grid", find_comparison_grid_candidates),
    ("stage_detail", find_stage_detail_candidates),
)


def _subtype(detector: str, finding: dict[str, Any]) -> str:
    kind = finding.get("candidate_kind")
    if detector == "form_row_return":
        return "DENSE_ROW_RETURN"
    if detector == "comparison_grid":
        return "GRID_OR_COLUMN_AMBIGUITY"
    if kind == "TWO_AXIS_STAGE_DETAIL_MATRIX":
        return "TWO_AXIS_GROUPING"
    return "PARENT_DETAIL_GROUPING"


def route_structure_order_findings(
    document: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return deduplicated page routes and fail-closed scanner errors."""

    by_page: dict[int, list[dict[str, Any]]] = defaultdict(list)
    errors: list[dict[str, Any]] = []
    for detector_name, detector in DETECTORS:
        try:
            findings = detector(document)
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(
                {
                    "detector": detector_name,
                    "code": "SCANNER_INPUT_ERROR",
                    "message": str(exc),
                    "auto_reorder_eligible": False,
                }
            )
            continue
        for finding in findings:
            page_no = finding.get("page_no")
            if not isinstance(page_no, int):
                errors.append(
                    {
                        "detector": detector_name,
                        "code": "MISSING_PAGE_NUMBER",
                        "message": repr(page_no),
                        "auto_reorder_eligible": False,
                    }
                )
                continue
            evidence = dict(finding)
            evidence["source_detector"] = detector_name
            evidence["router_subtype"] = _subtype(detector_name, finding)
            by_page[page_no].append(evidence)

    routes: list[dict[str, Any]] = []
    for page_no, evidence in sorted(by_page.items()):
        subtypes = sorted({item["router_subtype"] for item in evidence})
        blockers = sorted(
            {
                blocker
                for item in evidence
                for blocker in item.get("review_blockers", [])
            }
        )
        routes.append(
            {
                "page_no": page_no,
                "candidate_kind": "STRUCTURE_ORDER_REVIEW_ROUTE",
                "analysis_status": "REVIEW_REQUIRED",
                "route_subtypes": subtypes,
                "detector_count": len({item["source_detector"] for item in evidence}),
                "evidence_count": len(evidence),
                "review_blockers": blockers,
                "review_priority": (
                    "BLOCKED_LOW"
                    if blockers
                    else "CORROBORATED"
                    if len(subtypes) >= 2
                    else "STANDARD"
                ),
                "auto_reorder_eligible": False,
                "source_mutated": False,
                "evidence": evidence,
                "reason": (
                    "국소 pair swap으로 표현할 수 없는 구조 순서 신호를 "
                    "페이지 단위로 합쳐 검토 대상으로 라우팅"
                ),
            }
        )
    return routes, errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus_roots", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    rows: list[dict[str, Any]] = []
    scanner_errors: list[dict[str, Any]] = []
    document_count = 0
    for root in args.corpus_roots:
        for source in sorted(root.rglob("document.json")):
            document_count += 1
            relative = str(source.relative_to(root)).replace("\\", "/")
            routes, errors = route_structure_order_findings(load_docling_json(source))
            for row in routes:
                row["corpus_root"] = str(root)
                row["source_json"] = relative
                rows.append(row)
            for error in errors:
                error["corpus_root"] = str(root)
                error["source_json"] = relative
                scanner_errors.append(error)

    rows.sort(key=lambda row: (row["corpus_root"], row["source_json"], row["page_no"]))
    for index, row in enumerate(rows, start=1):
        row["route_id"] = f"SOR-{index:06d}"
    result = {
        "schema_version": "reading-order-structure-router.v1",
        "mode": "ANALYSIS_ONLY",
        "source_mutated": False,
        "heading_scope": "READ_ONLY_NOT_MODIFIED",
        "ocr_scope": "READ_ONLY_NOT_MODIFIED",
        "scanned_document_count": document_count,
        "routed_page_count": len(rows),
        "scanner_error_count": len(scanner_errors),
        "subtype_counts": {
            subtype: sum(subtype in row["route_subtypes"] for row in rows)
            for subtype in sorted(
                {subtype for row in rows for subtype in row["route_subtypes"]}
            )
        },
        "rows": rows,
        "scanner_errors": scanner_errors,
        "interpretation": (
            "구조 오류 검토 우선순위이며 자동 보정 승인이 아니다. "
            "동일 페이지의 여러 detector 신호를 중복 후보가 아닌 evidence로 합친다."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "documents": document_count,
                "routed_pages": len(rows),
                "scanner_errors": len(scanner_errors),
                "subtype_counts": result["subtype_counts"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
