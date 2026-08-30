"""Compare non-mutating detector candidates with explicit Golden issues."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _is_ordered_subsequence(values: list[str], expected: list[str]) -> bool:
    positions = {value: index for index, value in enumerate(expected)}
    if not values or any(value not in positions for value in values):
        return False
    indices = [positions[value] for value in values]
    return indices == sorted(indices)


def evaluate(
    benchmark: dict[str, Any], artifact: dict[str, Any]
) -> dict[str, Any]:
    issues = benchmark["issues"]
    candidates = artifact["candidates"]
    issue_results = []
    matched_candidate_ids: set[str] = set()

    for issue in issues:
        expected = issue["expected_order"]
        matches = []
        for candidate in candidates:
            proposed = candidate["proposed_order"]
            if (
                candidate["page_no"] == issue["page_no"]
                and len(proposed) >= 2
                and _is_ordered_subsequence(proposed, expected)
            ):
                matches.append(candidate)
                matched_candidate_ids.add(candidate["candidate_id"])

        covered_refs = {
            ref for candidate in matches for ref in candidate["proposed_order"]
        }
        missing_refs = [ref for ref in expected if ref not in covered_refs]
        detected = bool(matches)
        complete = detected and not missing_refs
        issue_results.append(
            {
                "issue_id": issue["issue_id"],
                "page_no": issue["page_no"],
                "category": issue["category"],
                "status": "COMPLETE" if complete else "PARTIAL" if detected else "MISSED",
                "matched_candidate_ids": [item["candidate_id"] for item in matches],
                "missing_refs": missing_refs,
            }
        )

    candidate_count = len(candidates)
    issue_count = len(issues)
    detected_count = sum(item["status"] != "MISSED" for item in issue_results)
    complete_count = sum(item["status"] == "COMPLETE" for item in issue_results)
    return {
        "benchmark_id": benchmark["benchmark_id"],
        "candidate_count": candidate_count,
        "matched_candidate_count": len(matched_candidate_ids),
        "unmatched_candidate_ids": [
            item["candidate_id"]
            for item in candidates
            if item["candidate_id"] not in matched_candidate_ids
        ],
        "issue_count": issue_count,
        "detected_issue_count": detected_count,
        "complete_issue_count": complete_count,
        "candidate_precision": round(
            len(matched_candidate_ids) / candidate_count, 4
        ) if candidate_count else None,
        "issue_detection_recall": round(detected_count / issue_count, 4),
        "complete_correction_recall": round(complete_count / issue_count, 4),
        "issue_results": issue_results,
        "interpretation": {
            "candidate_precision": "후보가 Golden issue의 올바른 상대 순서와 일치한 비율",
            "issue_detection_recall": "오류 위치를 하나 이상의 후보가 찾은 비율",
            "complete_correction_recall": "필요한 모든 ref를 빠짐없이 제안한 오류 비율"
        }
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("benchmark", type=Path)
    parser.add_argument("candidates", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    benchmark = json.loads(args.benchmark.read_text(encoding="utf-8"))
    candidates = json.loads(args.candidates.read_text(encoding="utf-8"))
    report = evaluate(benchmark, candidates)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
