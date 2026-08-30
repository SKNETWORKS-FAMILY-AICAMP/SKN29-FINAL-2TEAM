"""Export detector findings into the non-applying postprocess proposal contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_review_proposal(
    source_path: Path, document: dict[str, Any], candidates: list[dict[str, Any]]
) -> dict[str, Any]:
    """Convert supported auto/review candidates to non-applying decisions."""

    decisions = []
    for candidate in candidates:
        decision_status = candidate.get("decision")
        operation = candidate.get("operation")
        if decision_status not in {
            "AUTO_REORDER_ELIGIBLE", "REVIEW_REQUIRED"
        }:
            continue
        decision = {
            "decision_id": f"ORDER-{candidate['candidate_id']}",
            "status": decision_status,
            "reason": candidate["reason"],
            "evidence": {
                "page_no": candidate["page_no"],
                "candidate_type": candidate["type"],
                "confidence": candidate["confidence"],
                "observed_order": candidate["observed_order"],
                "metrics": candidate.get("metrics", {}),
            },
        }
        if operation in {"SWAP_ADJACENT", "SWAP_BLOCKS", "REORDER_SUBSET"}:
            if not isinstance(candidate.get("parent_ref"), str):
                continue
            decision.update(
                operation="REORDER_SUBSET",
                parent_ref=candidate["parent_ref"],
                ordered_refs=candidate["proposed_order"],
            )
        elif operation == "MOVE_AFTER":
            observed = candidate["observed_order"]
            if len(observed) != 2 or not isinstance(candidate.get("parent_ref"), str):
                continue
            decision.update(
                operation="MOVE_AFTER",
                parent_ref=candidate["parent_ref"],
                anchor_ref=observed[0],
                moved_ref=observed[1],
            )
        elif operation == "MOVE_CHILDREN":
            if not (
                isinstance(candidate.get("source_parent_ref"), str)
                and isinstance(candidate.get("target_parent_ref"), str)
                and candidate.get("moved_refs")
            ):
                continue
            decision.update(
                operation="MOVE_CHILDREN",
                source_parent_ref=candidate["source_parent_ref"],
                target_parent_ref=candidate["target_parent_ref"],
                moved_refs=list(candidate["moved_refs"]),
            )
        else:
            continue
        decisions.append(decision)

    statuses = {item["status"] for item in decisions}
    proposal_status = (
        "REVIEW_REQUIRED"
        if "REVIEW_REQUIRED" in statuses
        else "AUTO_REORDER_ELIGIBLE"
        if statuses
        else "PRESERVE_CONFIRMED"
    )
    return {
        "schema_version": "postprocess-proposal.v1",
        "proposal_id": f"ORDER-DETECTOR-{source_path.parent.name}",
        "owner": "reading_order",
        "status": proposal_status,
        "source": {"json_sha256": _sha256(source_path)},
        "decisions": decisions,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "generator": {
            "name": "export_detector_review_proposal",
            "version": "1.0",
            "external_model_calls": 0,
            "source_mutated": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_json", type=Path)
    parser.add_argument("output_json", type=Path)
    args = parser.parse_args()
    document = load_docling_json(args.source_json)
    candidates = detect_reading_order_candidates(
        document, build_element_order_map(document)
    )
    proposal = build_review_proposal(args.source_json, document, candidates)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(proposal, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "decision_count": len(proposal["decisions"]),
                "status": proposal["status"],
                "source_mutated": False,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
