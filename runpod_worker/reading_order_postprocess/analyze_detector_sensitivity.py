"""Run one-factor sensitivity checks without changing detector defaults."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path
from typing import Any

from evaluate_order_candidates import evaluate
from reading_order import (
    DetectorConfig,
    build_element_order_map,
    detect_reading_order_candidates,
    load_docling_json,
)


SWEEPS = {
    "min_vertical_gap": [0.0, 0.0025, 0.005, 0.0075, 0.01, 0.015, 0.02],
    "max_vertical_gap": [0.04, 0.06, 0.08, 0.1, 0.12],
    "left_alignment_tolerance": [0.01, 0.02, 0.035, 0.05, 0.08],
    "heading_table_min_gap": [-0.03, -0.015, 0.0, 0.01],
    "heading_table_max_gap": [0.03, 0.06, 0.09, 0.12],
    "premature_vertical_margin": [0.0, 0.01, 0.02, 0.025, 0.03, 0.04],
}


def _candidate_artifact(
    document: dict[str, Any], records: list[dict[str, Any]], config: DetectorConfig
) -> dict[str, Any]:
    candidates = detect_reading_order_candidates(document, records, config)
    return {"candidates": candidates}


def analyze(
    hanwha_path: Path, benchmark_path: Path, external_json_dir: Path
) -> dict[str, Any]:
    hanwha = load_docling_json(hanwha_path)
    hanwha_records = build_element_order_map(hanwha)
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    external = []
    for path in sorted(external_json_dir.glob("*.json")):
        document = load_docling_json(path)
        external.append((path.stem, document, build_element_order_map(document)))

    defaults = DetectorConfig()
    runs = []
    for parameter, values in SWEEPS.items():
        for value in values:
            config = replace(defaults, **{parameter: value})
            evaluation = evaluate(
                benchmark, _candidate_artifact(hanwha, hanwha_records, config)
            )
            external_counts = {
                name: len(detect_reading_order_candidates(document, records, config))
                for name, document, records in external
            }
            runs.append(
                {
                    "parameter": parameter,
                    "value": value,
                    "is_default": value == getattr(defaults, parameter),
                    "hanwha_candidate_count": evaluation["candidate_count"],
                    "hanwha_candidate_precision": evaluation["candidate_precision"],
                    "hanwha_issue_detection_recall": evaluation[
                        "issue_detection_recall"
                    ],
                    "hanwha_complete_correction_recall": evaluation[
                        "complete_correction_recall"
                    ],
                    "external_candidate_count": sum(external_counts.values()),
                    "external_counts": external_counts,
                }
            )

    return {
        "analysis_type": "one_factor_at_a_time",
        "default_config": asdict(defaults),
        "hanwha_benchmark_issue_count": len(benchmark["issues"]),
        "external_corpus_role": "negative/false-positive diagnostic only",
        "external_document_count": len(external),
        "runs": runs,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("hanwha", type=Path)
    parser.add_argument("benchmark", type=Path)
    parser.add_argument("external_json_dir", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = analyze(args.hanwha, args.benchmark, args.external_json_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
