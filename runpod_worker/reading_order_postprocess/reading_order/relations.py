"""Validation primitives for typed document-structure relations."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


ORDER_RELATIONS = {"BEFORE", "ADJACENT_BEFORE"}
SUPPORTED_RELATIONS = ORDER_RELATIONS | {"CAPTION_OF", "CONTAINS"}


def _cycle(nodes: set[str], edges: list[tuple[str, str]]) -> list[str] | None:
    adjacency: dict[str, list[str]] = defaultdict(list)
    for source, target in edges:
        adjacency[source].append(target)
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        state[node] = 1
        stack.append(node)
        for target in adjacency.get(node, []):
            if state.get(target, 0) == 0:
                found = visit(target)
                if found:
                    return found
            elif state.get(target) == 1:
                return stack[stack.index(target) :] + [target]
        stack.pop()
        state[node] = 2
        return None

    for node in sorted(nodes):
        if state.get(node, 0) == 0:
            found = visit(node)
            if found:
                return found
    return None


def validate_relation_edges(edges: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate typed edges without inferring any missing relation."""

    seen: set[tuple[Any, ...]] = set()
    order_by_scope: dict[tuple[Any, Any], list[tuple[str, str]]] = defaultdict(list)
    adjacent_out: dict[tuple[Any, Any, str], str] = {}
    adjacent_in: dict[tuple[Any, Any, str], str] = {}
    captions_from: dict[str, str] = {}
    captions_to: dict[str, str] = {}
    contains_parent: dict[str, str] = {}

    for index, edge in enumerate(edges):
        relation = edge.get("relation")
        source = edge.get("from_ref")
        target = edge.get("to_ref")
        if relation not in SUPPORTED_RELATIONS:
            raise ValueError(f"edge {index}: unsupported relation {relation!r}")
        if not isinstance(source, str) or not source.startswith("#/"):
            raise ValueError(f"edge {index}: invalid from_ref")
        if not isinstance(target, str) or not target.startswith("#/"):
            raise ValueError(f"edge {index}: invalid to_ref")
        if source == target:
            raise ValueError(f"edge {index}: self relation is not allowed")
        scope = (edge.get("page_no"), edge.get("scope_parent_ref"))
        identity = (relation, source, target, *scope)
        if identity in seen:
            raise ValueError(f"edge {index}: duplicate relation")
        seen.add(identity)

        if relation in ORDER_RELATIONS:
            order_by_scope[scope].append((source, target))
        if relation == "ADJACENT_BEFORE":
            out_key = (*scope, source)
            in_key = (*scope, target)
            if out_key in adjacent_out and adjacent_out[out_key] != target:
                raise ValueError(f"edge {index}: adjacency successor degree exceeds one")
            if in_key in adjacent_in and adjacent_in[in_key] != source:
                raise ValueError(f"edge {index}: adjacency predecessor degree exceeds one")
            adjacent_out[out_key] = target
            adjacent_in[in_key] = source
        elif relation == "CAPTION_OF":
            if source in captions_from and captions_from[source] != target:
                raise ValueError(f"edge {index}: media has multiple captions")
            if target in captions_to and captions_to[target] != source:
                raise ValueError(f"edge {index}: caption is claimed by multiple media")
            captions_from[source] = target
            captions_to[target] = source
        elif relation == "CONTAINS":
            if target in contains_parent and contains_parent[target] != source:
                raise ValueError(f"edge {index}: child has multiple containers")
            contains_parent[target] = source

    for scope, scope_edges in order_by_scope.items():
        nodes = {ref for edge in scope_edges for ref in edge}
        found = _cycle(nodes, scope_edges)
        if found:
            raise ValueError(f"ordering cycle in scope {scope}: {' -> '.join(found)}")

    return {
        "edge_count": len(edges),
        "order_edge_count": sum(edge["relation"] in ORDER_RELATIONS for edge in edges),
        "caption_edge_count": sum(edge["relation"] == "CAPTION_OF" for edge in edges),
        "contains_edge_count": sum(edge["relation"] == "CONTAINS" for edge in edges),
        "cycle_count": 0,
        "conflict_count": 0,
    }

