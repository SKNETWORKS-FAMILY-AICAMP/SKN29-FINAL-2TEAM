"""Build context packs for context-aware picture description.

The input must already represent the resolved Docling body order.  This module
does not call a VLM and does not modify picture annotations; it only freezes
the exact text/caption context that a later selective VLM stage may consume.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .mapping import build_element_order_map


TEXT_LABELS = {
    "title",
    "section_header",
    "text",
    "paragraph",
    "list_item",
    "caption",
}
ALLOWED_ORDER_DECISIONS = {"CORRECTED", "PRESERVED"}


def _resolve_ref(document: Mapping[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise ValueError(f"unsupported local reference: {ref!r}")
    current: Any = document
    for part in ref[2:].split("/"):
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, Mapping):
            current = current[part]
        else:
            raise ValueError(f"reference traverses a scalar: {ref!r}")
    if not isinstance(current, dict):
        raise ValueError(f"reference does not resolve to an object: {ref!r}")
    return current


def _page_no(record: Mapping[str, Any]) -> int | None:
    values = record.get("page_numbers") or []
    return int(values[0]) if len(values) == 1 else None


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _caption_context(document: Mapping[str, Any], picture: Mapping[str, Any]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for entry in picture.get("captions") or []:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("$ref"), str):
            raise ValueError("picture captions must be local reference objects")
        ref = str(entry["$ref"])
        item = _resolve_ref(document, ref)
        text = _clean_text(item.get("text"))
        if text:
            output.append({"ref": ref, "text": text})
    return output


def _existing_description_count(picture: Mapping[str, Any]) -> int:
    count = 0
    for annotation in picture.get("annotations") or []:
        if not isinstance(annotation, Mapping):
            continue
        kind = str(annotation.get("kind") or annotation.get("type") or "").lower()
        if "description" in kind or annotation.get("description") or annotation.get("text"):
            count += 1
    return count


def build_picture_context_packs(
    document: dict[str, Any],
    *,
    order_decision: str,
    maximum_before_items: int = 2,
    maximum_after_items: int = 2,
    maximum_context_characters: int = 1200,
) -> list[dict[str, Any]]:
    """Return picture context selected from the final resolved body order.

    Context selection is page-local and parent-local.  If a picture lives at
    the body root, the page itself is the local scope.  Explicit captions are
    carried separately and never inferred from proximity here.
    """

    if order_decision not in ALLOWED_ORDER_DECISIONS:
        raise ValueError(f"order_decision must be one of {sorted(ALLOWED_ORDER_DECISIONS)}")
    if any(
        value < 0
        for value in (
            maximum_before_items,
            maximum_after_items,
            maximum_context_characters,
        )
    ):
        raise ValueError("context limits must not be negative")
    records = build_element_order_map(document)
    by_ref = {record["self_ref"]: record for record in records}
    packs: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if record.get("label") != "picture":
            continue
        page_no = _page_no(record)
        picture = _resolve_ref(document, record["self_ref"])

        def eligible(candidate: Mapping[str, Any]) -> bool:
            if candidate.get("label") not in TEXT_LABELS:
                return False
            if not _clean_text(candidate.get("text")):
                return False
            if _page_no(candidate) != page_no:
                return False
            return candidate.get("parent_ref") == record.get("parent_ref")

        before = [candidate for candidate in records[:index] if eligible(candidate)]
        after = [candidate for candidate in records[index + 1 :] if eligible(candidate)]
        selected_before = before[-maximum_before_items:] if maximum_before_items else []
        selected_after = after[:maximum_after_items] if maximum_after_items else []
        context_items = [
            {
                "ref": candidate["self_ref"],
                "relation": "BEFORE_PICTURE" if candidate in selected_before else "AFTER_PICTURE",
                "text": _clean_text(candidate.get("text")),
            }
            for candidate in [*selected_before, *selected_after]
        ]
        total = 0
        bounded: list[dict[str, str]] = []
        for item in context_items:
            remaining = maximum_context_characters - total
            if remaining <= 0:
                break
            text = item["text"][:remaining]
            bounded.append({**item, "text": text})
            total += len(text)
        captions = _caption_context(document, picture)
        status = "READY" if bounded or captions else "BLOCKED_NO_LOCAL_CONTEXT"
        packs.append(
            {
                "picture_ref": record["self_ref"],
                "page_no": page_no,
                "parent_ref": record.get("parent_ref"),
                "order_decision": order_decision,
                "order_source": "RESOLVED_DOCLING_BODY",
                "context_status": status,
                "context_items": bounded,
                "caption_items": captions,
                "existing_description_count": _existing_description_count(picture),
                "context_aware_description_generated": False,
                "vlm_dispatch_eligible": False,
                "vlm_dispatch_status": "NOT_EVALUATED",
                "quality_flags": [],
            }
        )
    signatures: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for pack in packs:
        signature = (
            pack["page_no"],
            tuple(item["ref"] for item in pack["context_items"]),
            tuple(item["ref"] for item in pack["caption_items"]),
        )
        signatures.setdefault(signature, []).append(pack)
    for matching in signatures.values():
        if len(matching) <= 1:
            continue
        for pack in matching:
            pack["quality_flags"].append("SHARED_CONTEXT_WITH_OTHER_PICTURES")
            if not pack["caption_items"]:
                pack["context_status"] = "REVIEW_SHARED_CONTEXT"
    return packs
