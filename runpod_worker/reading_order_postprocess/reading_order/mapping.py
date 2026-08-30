"""Build a stable semantic body-order mapping to Docling JSON references.

The traversal mirrors the behavior used by the baseline visualization:

* start from ``body.children``;
* recurse through group nodes;
* yield document items but treat picture/table and their captions as one
  affiliated semantic unit;
* exclude furniture-layer items such as page headers and footers.

This intentionally differs from overlays made with an unrestricted
``DoclingDocument.iterate_items()`` call, which can number caption children
separately.  Stable ``$ref`` values, not overlay numbers, are the comparison
contract.  No document-specific coordinates, text, references, or order
numbers are used.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

JsonObject = dict[str, Any]


def load_docling_json(path: str | Path) -> JsonObject:
    """Load and minimally validate a DoclingDocument JSON file."""

    source_path = Path(path)
    document = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("Docling JSON root must be an object")
    if not isinstance(document.get("body"), dict):
        raise ValueError("Docling JSON must contain a body object")
    return document


def _resolve_ref(document: Mapping[str, Any], ref: str) -> JsonObject:
    """Resolve a local Docling JSON reference such as ``#/texts/51``."""

    if not ref.startswith("#/"):
        raise ValueError(f"Unsupported reference: {ref!r}")

    current: Any = document
    for part in ref[2:].split("/"):
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError) as exc:
                raise ValueError(f"Invalid list reference: {ref!r}") from exc
        elif isinstance(current, Mapping):
            if part not in current:
                raise ValueError(f"Missing reference component {part!r}: {ref!r}")
            current = current[part]
        else:
            raise ValueError(f"Reference traverses a scalar value: {ref!r}")

    if not isinstance(current, dict):
        raise ValueError(f"Reference does not resolve to an object: {ref!r}")
    return current


def _child_refs(node: Mapping[str, Any]) -> Iterator[str]:
    children = node.get("children", [])
    if not isinstance(children, list):
        raise ValueError("children must be an array")

    for child in children:
        if not isinstance(child, Mapping):
            raise ValueError("Each child must be a reference object")
        ref = child.get("$ref")
        if not isinstance(ref, str):
            raise ValueError("Each child must contain a string $ref")
        yield ref


def iter_reading_order_items(
    document: Mapping[str, Any],
) -> Iterator[tuple[str, JsonObject]]:
    """Yield baseline Reading Order items as ``(self_ref, item)`` pairs.

    Groups are structural containers and are recursively expanded. Picture and
    table children are intentionally not expanded because correction analysis
    treats an explicitly affiliated caption as part of its media/table unit.
    Caption integrity is validated separately by ``affiliation.py``.
    Furniture-layer items are not part of the body reading flow.
    """

    body = document.get("body")
    if not isinstance(body, Mapping):
        raise ValueError("Docling JSON must contain a body object")

    active_groups: set[str] = set()

    def walk(node: Mapping[str, Any]) -> Iterator[tuple[str, JsonObject]]:
        for ref in _child_refs(node):
            item = _resolve_ref(document, ref)

            if ref.startswith("#/groups/"):
                if ref in active_groups:
                    raise ValueError(f"Group cycle detected at {ref!r}")
                active_groups.add(ref)
                yield from walk(item)
                active_groups.remove(ref)
                continue

            if item.get("content_layer") == "furniture":
                continue
            if item.get("prov"):
                yield ref, item

    yield from walk(body)


def build_element_order_map(document: Mapping[str, Any]) -> list[JsonObject]:
    """Return JSON-serializable visual-order records."""

    records: list[JsonObject] = []
    for visual_order, (ref, item) in enumerate(
        iter_reading_order_items(document), start=1
    ):
        provenances = item.get("prov", [])
        if not isinstance(provenances, list):
            raise ValueError(f"prov must be an array for {ref!r}")

        page_numbers = []
        for provenance in provenances:
            if not isinstance(provenance, Mapping):
                raise ValueError(f"Invalid provenance for {ref!r}")
            page_no = provenance.get("page_no")
            if page_no is not None and page_no not in page_numbers:
                page_numbers.append(page_no)

        parent = item.get("parent")
        parent_ref = parent.get("$ref") if isinstance(parent, Mapping) else None

        records.append(
            {
                "visual_order": visual_order,
                "self_ref": ref,
                "parent_ref": parent_ref,
                "page_numbers": page_numbers,
                "label": item.get("label"),
                "text": item.get("text"),
                "enumerated": item.get("enumerated"),
                "marker": item.get("marker"),
                "content_layer": item.get("content_layer"),
                "provenances": provenances,
            }
        )
    return records


def write_element_order_json(records: list[JsonObject], path: str | Path) -> None:
    """Write the complete mapping as UTF-8 JSON."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_element_order_csv(records: list[JsonObject], path: str | Path) -> None:
    """Write a compact human-review mapping as UTF-8 BOM CSV."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "visual_order",
                "self_ref",
                "parent_ref",
                "page_numbers",
                "label",
                "text",
            ],
        )
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "visual_order": record["visual_order"],
                    "self_ref": record["self_ref"],
                    "parent_ref": record["parent_ref"],
                    "page_numbers": ",".join(
                        str(value) for value in record["page_numbers"]
                    ),
                    "label": record["label"],
                    "text": record["text"],
                }
            )
