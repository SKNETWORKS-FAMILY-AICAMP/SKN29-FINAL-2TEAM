"""Export non-executable reading-order relations as a validated shadow audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

PRACTICE_ROOT = Path(__file__).resolve().parent
if str(PRACTICE_ROOT) not in sys.path:
    sys.path.insert(0, str(PRACTICE_ROOT))

from reading_order import (  # noqa: E402
    build_element_order_map,
    detect_reading_order_candidates,
    load_docling_json,
)
from reading_order.relation_audit import build_relation_audit  # noqa: E402


SCHEMA_VERSION = "reading-order-relation-audit.v1"


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def export_relation_audit(
    source_path: Path,
) -> dict[str, Any]:
    """Return validated RELATION_ONLY findings without changing the source."""

    source_bytes = source_path.read_bytes()
    document = load_docling_json(source_path)
    records = build_element_order_map(document)
    candidates = detect_reading_order_candidates(document, records)
    relation_audit = build_relation_audit(candidates, records)

    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "SHADOW_RELATION_ONLY",
        "source_mutated": False,
        "auto_reorder_eligible": False,
        "source": {
            "path": str(source_path),
            "json_sha256": _sha256(source_bytes),
        },
        "relation_candidate_count": relation_audit["candidate_count"],
        "validated_edge_count": (
            len(relation_audit["edges"]) if relation_audit["valid"] else 0
        ),
        "rejected_candidate_count": len(
            relation_audit["rejected_candidates"]
        ),
        "valid": relation_audit["valid"],
        "validation": relation_audit["validation"],
        "validation_error": relation_audit["validation_error"],
        "edges": relation_audit["edges"],
        "rejected_candidates": relation_audit["rejected_candidates"],
        "interpretation": (
            "관계 후보를 보존하는 감사 산출물이며 source JSON을 수정하거나 "
            "자동 보정을 승인하지 않는다."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_json", type=Path)
    parser.add_argument("output_json", type=Path)
    args = parser.parse_args()
    if args.source_json.resolve() == args.output_json.resolve():
        raise ValueError("source_json and output_json must be distinct")
    result = export_relation_audit(args.source_json)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "valid": result["valid"],
        "relation_candidate_count": result["relation_candidate_count"],
        "validated_edge_count": result["validated_edge_count"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
