"""Validate postprocess proposal contracts without mutating a Docling JSON.

This is deliberately a validation-only boundary. It does not apply order or
heading changes and therefore can run in the local rule-analysis environment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SUPPORTED_ORDER_OPERATIONS = {"MOVE_AFTER", "REORDER_SUBSET", "MOVE_CHILDREN"}
SUPPORTED_HEADING_OPERATIONS = {"SET_HEADING_ATTRIBUTES"}
APPLY_STATUSES = {"REVIEW_APPROVED"}
KNOWN_STATUSES = {
    "AUTO_REORDER_ELIGIBLE",
    "REVIEW_APPROVED",
    "REVIEW_REQUIRED",
    "REJECTED",
    "PRESERVE_CONFIRMED",
}
KNOWN_OWNERS = {"reading_order", "heading"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve(document: dict[str, Any], ref: str) -> Any:
    if not isinstance(ref, str) or not ref.startswith("#/"):
        raise ValueError(f"invalid ref: {ref!r}")
    current: Any = document
    for part in ref.removeprefix("#/").split("/"):
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError) as exc:
                raise ValueError(f"missing ref: {ref}") from exc
        elif isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise ValueError(f"missing ref: {ref}")
    return current


def _decision_refs(decision: dict[str, Any]) -> list[str]:
    operation = decision.get("operation")
    if operation == "MOVE_AFTER":
        return [decision.get("parent_ref"), decision.get("moved_ref"), decision.get("anchor_ref")]
    if operation == "REORDER_SUBSET":
        return [decision.get("parent_ref"), *decision.get("ordered_refs", [])]
    if operation == "MOVE_CHILDREN":
        return [
            decision.get("source_parent_ref"),
            decision.get("target_parent_ref"),
            *decision.get("moved_refs", []),
        ]
    if operation == "SET_HEADING_ATTRIBUTES":
        return [decision.get("target_ref")]
    return []


def _child_refs(parent: Any, parent_ref: str) -> list[str]:
    if not isinstance(parent, dict) or not isinstance(parent.get("children"), list):
        raise ValueError(f"parent has no children list: {parent_ref}")
    refs: list[str] = []
    for child in parent["children"]:
        if not isinstance(child, dict) or not isinstance(child.get("$ref"), str):
            raise ValueError(f"invalid child entry under {parent_ref}")
        refs.append(child["$ref"])
    return refs


def _validate_order_preconditions(
    document: dict[str, Any], decision_id: str, decision: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    operation = decision.get("operation")
    try:
        if operation == "MOVE_AFTER":
            parent_ref = decision["parent_ref"]
            refs = _child_refs(resolve(document, parent_ref), parent_ref)
            moved_ref, anchor_ref = decision["moved_ref"], decision["anchor_ref"]
            if moved_ref == anchor_ref:
                errors.append(f"{decision_id}: moved_ref and anchor_ref must differ")
            for ref in (moved_ref, anchor_ref):
                if ref not in refs:
                    errors.append(f"{decision_id}: {ref} is not a child of {parent_ref}")
        elif operation == "REORDER_SUBSET":
            parent_ref = decision["parent_ref"]
            refs = _child_refs(resolve(document, parent_ref), parent_ref)
            ordered_refs = decision.get("ordered_refs", [])
            if len(ordered_refs) < 2:
                errors.append(f"{decision_id}: REORDER_SUBSET requires at least two refs")
            if len(ordered_refs) != len(set(ordered_refs)):
                errors.append(f"{decision_id}: REORDER_SUBSET refs must be unique")
            missing = sorted(set(ordered_refs) - set(refs))
            if missing:
                errors.append(f"{decision_id}: refs are not children of {parent_ref}: {missing}")
        elif operation == "MOVE_CHILDREN":
            source_ref = decision["source_parent_ref"]
            target_ref = decision["target_parent_ref"]
            if source_ref == target_ref:
                errors.append(f"{decision_id}: source and target parent must differ")
            source_refs = _child_refs(resolve(document, source_ref), source_ref)
            _child_refs(resolve(document, target_ref), target_ref)
            moved_refs = decision.get("moved_refs", [])
            if not moved_refs:
                errors.append(f"{decision_id}: MOVE_CHILDREN requires moved_refs")
            if len(moved_refs) != len(set(moved_refs)):
                errors.append(f"{decision_id}: MOVE_CHILDREN refs must be unique")
            missing = sorted(set(moved_refs) - set(source_refs))
            if missing:
                errors.append(f"{decision_id}: refs are not children of {source_ref}: {missing}")
    except (KeyError, ValueError) as exc:
        errors.append(f"{decision_id}: {exc}")
    return errors


def _approved_order_edges(
    decision_id: str, decision: dict[str, Any]
) -> tuple[str, list[tuple[str, str, str]]] | None:
    """Compile an approved order decision into explicit precedence edges.

    Only proposal relations are included.  The source order is deliberately
    not added because a valid correction is expected to contradict part of
    that order.
    """

    operation = decision.get("operation")
    if operation == "MOVE_AFTER":
        parent_ref = decision.get("parent_ref")
        anchor_ref = decision.get("anchor_ref")
        moved_ref = decision.get("moved_ref")
        if all(isinstance(value, str) for value in (parent_ref, anchor_ref, moved_ref)):
            return parent_ref, [(anchor_ref, moved_ref, decision_id)]
    elif operation == "REORDER_SUBSET":
        parent_ref = decision.get("parent_ref")
        refs = decision.get("ordered_refs", [])
        if isinstance(parent_ref, str) and all(isinstance(ref, str) for ref in refs):
            return parent_ref, [
                (before, after, decision_id)
                for before, after in zip(refs, refs[1:])
            ]
    return None


def _precedence_cycle(
    edges: list[tuple[str, str, str]],
) -> list[str] | None:
    """Return one deterministic precedence cycle, or ``None`` for a DAG."""

    graph: dict[str, set[str]] = {}
    nodes: set[str] = set()
    for before, after, _ in edges:
        graph.setdefault(before, set()).add(after)
        nodes.update((before, after))

    state: dict[str, int] = {}
    stack: list[str] = []
    stack_index: dict[str, int] = {}

    def visit(node: str) -> list[str] | None:
        state[node] = 1
        stack_index[node] = len(stack)
        stack.append(node)
        for target in sorted(graph.get(node, ())):
            if state.get(target, 0) == 0:
                cycle = visit(target)
                if cycle is not None:
                    return cycle
            elif state.get(target) == 1:
                start = stack_index[target]
                return [*stack[start:], target]
        stack.pop()
        stack_index.pop(node, None)
        state[node] = 2
        return None

    for node in sorted(nodes):
        if state.get(node, 0) == 0:
            cycle = visit(node)
            if cycle is not None:
                return cycle
    return None


def validate_proposals(
    document: dict[str, Any],
    source_sha256: str,
    proposals: list[dict[str, Any]],
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    approved: list[tuple[dict[str, Any], dict[str, Any]]] = []
    seen_decisions: set[str] = set()
    order_parent_sequences: dict[str, list[tuple[str, ...]]] = {}
    order_edges_by_parent: dict[str, list[tuple[str, str, str]]] = {}
    order_refs_by_parent: dict[str, set[str]] = {}
    parent_move_claims: dict[str, tuple[str, str, str]] = {}

    for proposal in proposals:
        proposal_id = proposal.get("proposal_id", "<missing-proposal-id>")
        owner = proposal.get("owner")
        if proposal.get("schema_version") != "postprocess-proposal.v1":
            errors.append(f"{proposal_id}: unsupported schema_version")
        if owner not in KNOWN_OWNERS:
            errors.append(f"{proposal_id}: unknown owner {owner!r}")
        declared_hash = proposal.get("source", {}).get("json_sha256")
        if declared_hash != source_sha256:
            errors.append(f"{proposal_id}: source hash mismatch")
        for decision in proposal.get("decisions", []):
            decision_id = decision.get("decision_id", "<missing-decision-id>")
            if decision_id in seen_decisions:
                errors.append(f"{decision_id}: duplicate decision_id")
            seen_decisions.add(decision_id)
            operation = decision.get("operation")
            allowed = (
                SUPPORTED_ORDER_OPERATIONS if owner == "reading_order" else SUPPORTED_HEADING_OPERATIONS
            )
            if operation not in allowed:
                errors.append(f"{decision_id}: unsupported operation {operation!r} for {owner}")
            for ref in _decision_refs(decision):
                if not isinstance(ref, str):
                    errors.append(f"{decision_id}: missing ref")
                    continue
                try:
                    resolve(document, ref)
                except ValueError as exc:
                    errors.append(f"{decision_id}: {exc}")
            status = decision.get("status")
            if status in APPLY_STATUSES:
                approved.append((proposal, decision))
            elif status not in KNOWN_STATUSES:
                warnings.append(f"{decision_id}: unknown status {decision.get('status')!r}")

            if owner == "reading_order" and operation in SUPPORTED_ORDER_OPERATIONS:
                errors.extend(_validate_order_preconditions(document, decision_id, decision))

            if owner == "reading_order" and operation == "REORDER_SUBSET" and status in APPLY_STATUSES:
                parent_ref = decision.get("parent_ref")
                sequence = tuple(decision.get("ordered_refs", []))
                for previous in order_parent_sequences.get(parent_ref, []):
                    shared = set(previous) & set(sequence)
                    if len(shared) >= 2:
                        before = [ref for ref in previous if ref in shared]
                        after = [ref for ref in sequence if ref in shared]
                        if before != after:
                            errors.append(f"{decision_id}: conflicting order proposal for {parent_ref}")
                order_parent_sequences.setdefault(parent_ref, []).append(sequence)

            if owner == "reading_order" and status in APPLY_STATUSES:
                compiled = _approved_order_edges(decision_id, decision)
                if compiled is not None:
                    parent_ref, edges = compiled
                    order_edges_by_parent.setdefault(parent_ref, []).extend(edges)
                    refs = order_refs_by_parent.setdefault(parent_ref, set())
                    for before, after, _ in edges:
                        refs.update((before, after))
                elif operation == "MOVE_CHILDREN":
                    source_ref = decision.get("source_parent_ref")
                    target_ref = decision.get("target_parent_ref")
                    for moved_ref in decision.get("moved_refs", []):
                        if not all(
                            isinstance(value, str)
                            for value in (source_ref, target_ref, moved_ref)
                        ):
                            continue
                        previous = parent_move_claims.get(moved_ref)
                        claim = (source_ref, target_ref, decision_id)
                        if previous is not None and previous[:2] != claim[:2]:
                            errors.append(
                                f"{decision_id}: conflicting parent move for {moved_ref}; "
                                f"{previous[0]}->{previous[1]} vs {source_ref}->{target_ref}"
                            )
                        elif previous is not None:
                            errors.append(
                                f"{decision_id}: duplicate parent move for {moved_ref}"
                            )
                        else:
                            parent_move_claims[moved_ref] = claim

    for parent_ref, edges in sorted(order_edges_by_parent.items()):
        cycle = _precedence_cycle(edges)
        if cycle is not None:
            errors.append(
                f"precedence cycle for {parent_ref}: {' -> '.join(cycle)}"
            )

    for moved_ref, (source_ref, target_ref, decision_id) in sorted(
        parent_move_claims.items()
    ):
        if moved_ref in order_refs_by_parent.get(source_ref, set()):
            errors.append(
                f"{decision_id}: {moved_ref} is reordered under {source_ref} "
                f"and moved to {target_ref}"
            )
        if moved_ref in order_refs_by_parent.get(target_ref, set()):
            errors.append(
                f"{decision_id}: {moved_ref} is reordered under target {target_ref} "
                "before the parent move is applied"
            )

    for proposal in proposals:
        for decision in proposal.get("decisions", []):
            if proposal.get("owner") == "reading_order" and decision.get("status") == "AUTO_REORDER_ELIGIBLE":
                warnings.append(
                    f"{decision.get('decision_id')}: AUTO_REORDER_ELIGIBLE requires explicit approval before apply"
                )

    return {
        "schema_version": "postprocess-validation.v1",
        "mode": "VALIDATION_ONLY",
        "source_mutated": False,
        "source_sha256": source_sha256,
        "proposal_count": len(proposals),
        "approved_decision_count": len(approved),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "approved_precedence_edge_count": sum(
            len(edges) for edges in order_edges_by_parent.values()
        ),
        "approved_parent_move_count": len(parent_move_claims),
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_json", type=Path)
    parser.add_argument("proposal_json", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    source = json.loads(args.source_json.read_text(encoding="utf-8"))
    proposals = [json.loads(path.read_text(encoding="utf-8")) for path in args.proposal_json]
    report = validate_proposals(source, sha256(args.source_json), proposals)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    if not report["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
