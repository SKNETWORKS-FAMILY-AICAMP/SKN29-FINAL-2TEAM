"""Page-level pilot metrics for fully reviewed reading-order pages.

This evaluates detector proposals only.  Heading labels and source Docling JSON
are read-only and never modified.
"""

from __future__ import annotations

from collections import Counter
from typing import Any


def _ordered_subsequence(values: list[str], expected: list[str]) -> bool:
    positions = {value: index for index, value in enumerate(expected)}
    if not values or any(value not in positions for value in values):
        return False
    indices = [positions[value] for value in values]
    return indices == sorted(indices)


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def evaluate_full_page_pilot(
    benchmark: dict[str, Any], detector: dict[str, Any]
) -> dict[str, Any]:
    if benchmark.get("schema_version") != "reading-order-full-page-benchmark.v1":
        raise ValueError("unsupported full-page benchmark schema")

    audit_documents = {
        (item["corpus_root"], item["source_json"]): item
        for item in detector.get("documents", [])
    }
    issue_results = []
    page_candidate_outcomes: Counter[str] = Counter()
    total_auto_candidates = 0
    correct_auto_candidates: set[tuple[str, str, str]] = set()
    normal_page_count = 0
    normal_page_auto_preserved_count = 0

    for page in benchmark["pages"]:
        if page["review_status"] != "SINGLE_REVIEW_CONFIRMED":
            continue
        key = (page["corpus_root"], page["source_json"])
        audit_document = audit_documents.get(key)
        if audit_document is None:
            raise ValueError(f"page source missing from detector audit: {key}")
        candidates = [
            item for item in audit_document.get("candidates", [])
            if int(item["page_no"]) == int(page["page_no"])
        ]
        total_auto_candidates += sum(
            item.get("decision") == "AUTO_REORDER_ELIGIBLE" for item in candidates
        )
        if not page.get("issues"):
            normal_page_count += 1
            if not any(
                item.get("decision") == "AUTO_REORDER_ELIGIBLE"
                for item in candidates
            ):
                normal_page_auto_preserved_count += 1

        for outcome in page.get("candidate_outcomes", []):
            page_candidate_outcomes[outcome["outcome"]] += 1

        for issue in page.get("issues", []):
            expected = issue["expected_order"]
            matches = [
                candidate for candidate in candidates
                if _ordered_subsequence(candidate["proposed_order"], expected)
            ]
            exact = [
                candidate for candidate in matches
                if candidate["proposed_order"] == expected
            ]
            for candidate in exact:
                if candidate.get("decision") == "AUTO_REORDER_ELIGIBLE":
                    correct_auto_candidates.add(
                        (page["source_json"], candidate["candidate_id"], issue["issue_id"])
                    )
            issue_results.append(
                {
                    "issue_id": issue["issue_id"],
                    "page_id": page["page_id"],
                    "category": issue["category"],
                    "status": "COMPLETE" if exact else "PARTIAL" if matches else "MISSED",
                    "matched_candidate_ids": [item["candidate_id"] for item in matches],
                    "exact_candidate_ids": [item["candidate_id"] for item in exact],
                }
            )

    issue_count = len(issue_results)
    detected_count = sum(item["status"] != "MISSED" for item in issue_results)
    complete_count = sum(item["status"] == "COMPLETE" for item in issue_results)
    auto_true_count = len(correct_auto_candidates)
    scorable_review = (
        page_candidate_outcomes["TRUE_POSITIVE"]
        + page_candidate_outcomes["FALSE_POSITIVE"]
    )
    return {
        "schema_version": "reading-order-full-page-metrics.v1",
        "evaluation_scope": benchmark.get(
            "evaluation_scope", "DEV_SINGLE_REVIEW_FULL_PAGE_PILOT"
        ),
        "heading_scope": "READ_ONLY_NOT_MODIFIED",
        "reviewed_page_count": sum(
            page["review_status"] == "SINGLE_REVIEW_CONFIRMED"
            for page in benchmark["pages"]
        ),
        "issue_count": issue_count,
        "detected_issue_count": detected_count,
        "complete_issue_count": complete_count,
        "issue_detection_recall": _ratio(detected_count, issue_count),
        "exact_correction_recall": _ratio(complete_count, issue_count),
        "auto_correct_issue_count": auto_true_count,
        "auto_coverage": _ratio(auto_true_count, issue_count),
        "auto_candidate_count_on_reviewed_pages": total_auto_candidates,
        "auto_precision_on_reviewed_pages": _ratio(
            auto_true_count, total_auto_candidates
        ),
        "normal_page_count": normal_page_count,
        "normal_page_auto_preserved_count": normal_page_auto_preserved_count,
        "normal_page_auto_preservation_rate": _ratio(
            normal_page_auto_preserved_count, normal_page_count
        ),
        "review_candidate_outcomes": dict(page_candidate_outcomes),
        "review_scorable_candidate_count": scorable_review,
        "review_yield_observed": _ratio(
            page_candidate_outcomes["TRUE_POSITIVE"], scorable_review
        ),
        "review_yield_reportable": (
            _ratio(page_candidate_outcomes["TRUE_POSITIVE"], scorable_review)
            if scorable_review >= 3 else None
        ),
        "review_yield_minimum_support": 3,
        "issue_results": issue_results,
        "limitations": benchmark.get(
            "limitations",
            [
                "DEV pages already seen during rule development",
                "single visual reviewer",
                "four-page pilot; not HOLDOUT or production accuracy",
                "block segmentation and decorative-image ambiguity excluded",
            ],
        ),
    }
