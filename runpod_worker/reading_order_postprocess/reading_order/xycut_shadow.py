"""Dependency-free XY-cut shadow comparator.

This module is deliberately not a production sorter.  It supplies an
independent, low-cost geometry view for already detected relation edges.
"""

from __future__ import annotations

from typing import Any


def _shrunk_interval(item: dict[str, Any], axis: str, shrink: float) -> tuple[float, float]:
    if axis == "x":
        low, high = item["left_norm"], item["right_norm"]
    elif axis == "y":
        low, high = item["bottom_norm"], item["top_norm"]
    else:
        raise ValueError(f"unsupported axis: {axis}")
    center = (low + high) / 2
    half = (high - low) * shrink / 2
    return center - half, center + half


def _projection_components(
    items: list[dict[str, Any]], axis: str, shrink: float
) -> list[list[dict[str, Any]]]:
    intervals = sorted(
        ((_shrunk_interval(item, axis, shrink), item) for item in items),
        key=lambda pair: (pair[0][0], pair[0][1], pair[1]["self_ref"]),
    )
    components: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_high: float | None = None
    for (low, high), item in intervals:
        if current_high is None or low <= current_high:
            current.append(item)
            current_high = high if current_high is None else max(current_high, high)
        else:
            components.append(current)
            current = [item]
            current_high = high
    if current:
        components.append(current)
    if axis == "y":
        components.reverse()  # visually top to bottom
    return components


def xycut_order(
    items: list[dict[str, Any]], *, primary_axis: str = "y", shrink: float = 0.90
) -> tuple[list[str], list[dict[str, Any]]]:
    """Return deterministic XY-cut order and an auditable split trace."""

    if primary_axis not in {"x", "y"}:
        raise ValueError("primary_axis must be 'x' or 'y'")
    if not 0 < shrink <= 1:
        raise ValueError("shrink must be in (0, 1]")
    refs = [item.get("self_ref") for item in items]
    if any(not isinstance(ref, str) or not ref for ref in refs) or len(set(refs)) != len(refs):
        raise ValueError("items must have unique non-empty self_ref values")
    required = ("left_norm", "right_norm", "top_norm", "bottom_norm")
    for item in items:
        if any(key not in item for key in required):
            raise ValueError(f"missing normalized geometry for {item['self_ref']}")
        if item["right_norm"] <= item["left_norm"] or item["top_norm"] <= item["bottom_norm"]:
            raise ValueError(f"non-positive bbox for {item['self_ref']}")

    trace: list[dict[str, Any]] = []

    def recurse(node_items: list[dict[str, Any]], axis: str, depth: int) -> list[str]:
        if len(node_items) <= 1:
            return [item["self_ref"] for item in node_items]
        secondary = "x" if axis == "y" else "y"
        for candidate_axis in (axis, secondary):
            components = _projection_components(node_items, candidate_axis, shrink)
            if len(components) <= 1:
                continue
            trace.append(
                {
                    "depth": depth,
                    "axis": candidate_axis,
                    "component_count": len(components),
                    "component_refs": [
                        [item["self_ref"] for item in component] for component in components
                    ],
                }
            )
            result: list[str] = []
            next_axis = "x" if candidate_axis == "y" else "y"
            for component in components:
                result.extend(recurse(component, next_axis, depth + 1))
            return result
        # Overlapping boxes have no whitespace cut.  Keep a deterministic
        # visual fallback, but callers must not treat it as cut evidence.
        return [
            item["self_ref"]
            for item in sorted(
                node_items,
                key=lambda item: (
                    -item["top_norm"], item["left_norm"], item.get("order_index", 0), item["self_ref"]
                ),
            )
        ]

    return recurse(items, primary_axis, 0), trace


def compare_relation_edge(
    items: list[dict[str, Any]], from_ref: str, to_ref: str
) -> dict[str, Any]:
    """Compare one proposed order edge across six XY-cut settings."""

    item_by_ref = {item.get("self_ref"): item for item in items}
    if from_ref not in item_by_ref or to_ref not in item_by_ref:
        return {"status": "BLOCKED_MISSING_ENDPOINT", "auto_reorder_eligible": False}
    blockers: list[str] = []
    for item in items:
        flags = set(item.get("geometry_flags") or [])
        if flags & {"bbox_clamped_to_page", "same_page_provenances_aggregated"}:
            blockers.append("UNSTABLE_GEOMETRY")
            break
    labels = {str(item.get("label") or "").lower() for item in items}
    if "table" in labels:
        blockers.append("TABLE_SCOPE")
    if labels & {"picture", "caption"}:
        blockers.append("CARD_MEDIA_SCOPE")

    variants: list[dict[str, Any]] = []
    for axis in ("y", "x"):
        for shrink in (0.85, 0.90, 0.95):
            order, trace = xycut_order(items, primary_axis=axis, shrink=shrink)
            left = order.index(from_ref)
            right = order.index(to_ref)
            variants.append(
                {
                    "primary_axis": axis,
                    "shrink": shrink,
                    "direction_supported": left < right,
                    "reverse_supported": right < left,
                    "adjacency_supported": right == left + 1,
                    "rank_distance": abs(right - left),
                    "cut_count": len(trace),
                }
            )
    direction_count = sum(row["direction_supported"] for row in variants)
    reverse_count = sum(row["reverse_supported"] for row in variants)
    adjacency_count = sum(row["adjacency_supported"] for row in variants)
    if blockers:
        status = "BLOCKED_COMPLEX_OR_UNSTABLE_SCOPE"
    elif direction_count == len(variants):
        status = "STABLE_DIRECTION_SUPPORT"
    elif reverse_count == len(variants):
        status = "STABLE_REVERSE"
    else:
        status = "DIRECTION_SENSITIVE"
    return {
        "status": status,
        "direction_support_count": direction_count,
        "reverse_support_count": reverse_count,
        "adjacency_support_count": adjacency_count,
        "variant_count": len(variants),
        "exact_adjacency_corroborated": adjacency_count == len(variants),
        "blockers": sorted(set(blockers)),
        "variants": variants,
        "auto_reorder_eligible": False,
    }

