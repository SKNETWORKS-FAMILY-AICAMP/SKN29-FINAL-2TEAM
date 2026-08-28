"""노드·간선 구조를 Mermaid `flowchart` 스펙으로 만들어 SVG로 렌더한다.

모델이 raw Mermaid를 쓰게 두지 않고 `{nodes, edges}` 구조만 받는다 — id 는
우리가 `N0`,`N1`... 로 다시 붙여 스타일·지시문 주입을 막는다.
"""

from __future__ import annotations

from typing import Any

from services.builtin_tools.common.errors import BuiltinToolError
from services.builtin_tools.visualization.renderer import DIAGRAM_PREFIXES, render_mermaid

MAX_NODES = 80
MAX_EDGES = 200
_DIRECTIONS = {"TD", "TB", "LR", "RL", "BT"}


def _label(text: Any) -> str:
    cleaned = " ".join(str(text).replace('"', "'").split())
    return cleaned[:80] or "-"


def build_graph(
    *,
    nodes: list[Any],
    edges: list[dict[str, Any]] | None,
    direction: str | None = "TD",
) -> tuple[bytes, str]:
    """`(svg_bytes, mermaid_source)` 를 돌려준다."""

    layout = (direction or "TD").upper()
    if layout not in _DIRECTIONS:
        layout = "TD"
    if not nodes:
        raise BuiltinToolError("NO_NODES", "노드가 하나 이상 필요합니다.")
    if len(nodes) > MAX_NODES:
        raise BuiltinToolError("TOO_MANY_NODES", f"노드는 {MAX_NODES}개까지입니다.")
    edges = edges or []
    if len(edges) > MAX_EDGES:
        raise BuiltinToolError("TOO_MANY_EDGES", f"간선은 {MAX_EDGES}개까지입니다.")

    id_map: dict[str, str] = {}
    lines = [f"flowchart {layout}"]
    for index, node in enumerate(nodes):
        if isinstance(node, dict):
            raw_id = node.get("id")
            label = node.get("label", raw_id)
        else:
            raw_id = node
            label = node
        if raw_id is None or str(raw_id) == "":
            raise BuiltinToolError("NODE_MISSING_ID", f"{index + 1}번째 노드에 id가 없습니다.")
        key = f"N{index}"
        id_map[str(raw_id)] = key
        lines.append(f'    {key}["{_label(label)}"]')

    for edge in edges:
        if not isinstance(edge, dict):
            raise BuiltinToolError("INVALID_EDGE", "각 간선은 from·to를 담은 객체여야 합니다.")
        source = id_map.get(str(edge.get("from")))
        target = id_map.get(str(edge.get("to")))
        if not source or not target:
            raise BuiltinToolError(
                "UNKNOWN_EDGE_NODE",
                f"간선이 없는 노드를 가리킵니다: {edge.get('from')} → {edge.get('to')}",
            )
        edge_label = edge.get("label")
        if edge_label:
            lines.append(f"    {source} -->|{_label(edge_label)}| {target}")
        else:
            lines.append(f"    {source} --> {target}")

    code = "\n".join(lines)
    return render_mermaid(code, allowed=DIAGRAM_PREFIXES), code
