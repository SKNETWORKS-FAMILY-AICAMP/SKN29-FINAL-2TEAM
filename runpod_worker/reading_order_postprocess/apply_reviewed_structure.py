"""Apply explicit, audited structural reading-order decisions to Docling JSON.

The engine is document-agnostic. Document-specific references live in a separate
review map so a human decision never becomes a global heuristic by accident.
"""

from __future__ import annotations

import argparse
import copy
import json
from collections import Counter
from pathlib import Path
from typing import Any


def _resolve(document: dict[str, Any], ref: str) -> dict[str, Any]:
    current: Any = document
    try:
        for part in ref.removeprefix("#/").split("/"):
            current = current[int(part)] if isinstance(current, list) else current[part]
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"missing ref: {ref}") from exc
    if not isinstance(current, dict):
        raise ValueError(f"Reference is not an object: {ref}")
    return current


def _child_ref_multiset(document: dict[str, Any]) -> Counter[str]:
    refs: Counter[str] = Counter()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            children = value.get("children")
            if isinstance(children, list):
                for child in children:
                    if not isinstance(child, dict) or not isinstance(child.get("$ref"), str):
                        raise ValueError("Invalid children entry in postprocess document")
                    refs[child["$ref"]] += 1
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(document)
    return refs


def _validate_apply_invariants(
    before_refs: Counter[str], corrected: dict[str, Any]
) -> None:
    after_refs = _child_ref_multiset(corrected)
    if after_refs != before_refs:
        raise ValueError("Postprocess changed the children ref multiset")
    for ref in after_refs:
        _resolve(corrected, ref)


def apply_review_map(
    document: dict[str, Any], review_map: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    corrected = copy.deepcopy(document)
    before_refs = _child_ref_multiset(document)
    audit: list[dict[str, Any]] = []
    for decision in review_map["decisions"]:
        operation = decision["operation"]
        if decision.get("status") != "REVIEW_APPROVED":
            continue
        if operation == "MOVE_AFTER":
            parent = _resolve(corrected, decision["parent_ref"])
            refs = [child["$ref"] for child in parent["children"]]
            moved_ref, anchor_ref = decision["moved_ref"], decision["anchor_ref"]
            moved = parent["children"].pop(refs.index(moved_ref))
            refs = [child["$ref"] for child in parent["children"]]
            parent["children"].insert(refs.index(anchor_ref) + 1, moved)
            after = [anchor_ref, moved_ref]
        elif operation == "REORDER_SUBSET":
            parent = _resolve(corrected, decision["parent_ref"])
            ordered_refs = decision["ordered_refs"]
            wanted = set(ordered_refs)
            existing = [child["$ref"] for child in parent["children"]]
            if not wanted.issubset(existing):
                raise ValueError(f"Missing subset refs: {wanted - set(existing)}")
            positions = [i for i, ref in enumerate(existing) if ref in wanted]
            if len(positions) != len(ordered_refs):
                raise ValueError("REORDER_SUBSET refs must be unique")
            by_ref = {child["$ref"]: child for child in parent["children"]}
            for index, ref in zip(positions, ordered_refs, strict=True):
                parent["children"][index] = by_ref[ref]
            after = ordered_refs
        elif operation == "MOVE_CHILDREN":
            source = _resolve(corrected, decision["source_parent_ref"])
            target = _resolve(corrected, decision["target_parent_ref"])
            moved_refs = decision["moved_refs"]
            source_by_ref = {child["$ref"]: child for child in source["children"]}
            target_refs = [child["$ref"] for child in target["children"]]
            in_source = [ref in source_by_ref for ref in moved_refs]
            in_target = [ref in target_refs for ref in moved_refs]
            if all(in_target) and not any(in_source):
                if not all(
                    _resolve(corrected, ref).get("parent", {}).get("$ref")
                    == decision["target_parent_ref"]
                    for ref in moved_refs
                ):
                    raise ValueError("MOVE_CHILDREN target membership and parent refs disagree")
                audit.append(
                    {
                        "decision_id": decision["decision_id"],
                        "operation": operation,
                        "after": moved_refs,
                        "status": "ALREADY_APPLIED",
                        "reason": decision["reason"],
                    }
                )
                continue
            if not all(in_source) or any(in_target):
                raise ValueError("MOVE_CHILDREN has a partial or conflicting apply state")
            source["children"] = [
                child for child in source["children"] if child["$ref"] not in moved_refs
            ]
            target["children"].extend(source_by_ref[ref] for ref in moved_refs)
            for ref in moved_refs:
                _resolve(corrected, ref)["parent"] = {"$ref": decision["target_parent_ref"]}
            after = moved_refs
        else:
            raise ValueError(f"Unsupported operation: {operation}")
        audit.append(
            {
                "decision_id": decision["decision_id"],
                "operation": operation,
                "after": after,
                "status": "APPLIED",
                "reason": decision["reason"],
            }
        )
    _validate_apply_invariants(before_refs, corrected)
    return corrected, audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("review_map", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument("audit_json", type=Path)
    args = parser.parse_args()
    source = json.loads(args.source.read_text(encoding="utf-8"))
    review_map = json.loads(args.review_map.read_text(encoding="utf-8"))
    corrected, audit = apply_review_map(source, review_map)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(corrected, ensure_ascii=False, indent=2), encoding="utf-8")
    args.audit_json.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"applied": len(audit), "source_mutated": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
