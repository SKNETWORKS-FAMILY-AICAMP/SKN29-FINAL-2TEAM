"""Validate explicit Docling media/table-to-caption affiliations.

Caption affiliation is a structural relation, not a plain geometric ordering
problem.  This module only validates existing parent/children references and
never mutates the source document.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

JsonObject = dict[str, Any]
MEDIA_COLLECTIONS = ("pictures", "tables")


def _items_by_ref(document: Mapping[str, Any]) -> dict[str, JsonObject]:
    items: dict[str, JsonObject] = {}
    for collection in ("texts", "pictures", "tables"):
        values = document.get(collection, [])
        if not isinstance(values, list):
            continue
        for item in values:
            if isinstance(item, dict) and isinstance(item.get("self_ref"), str):
                items[item["self_ref"]] = item
    return items


def _child_refs(item: Mapping[str, Any]) -> list[str]:
    children = item.get("children", [])
    if not isinstance(children, list):
        return []
    return [
        child["$ref"]
        for child in children
        if isinstance(child, Mapping) and isinstance(child.get("$ref"), str)
    ]


def _page_numbers(item: Mapping[str, Any]) -> list[int]:
    pages: list[int] = []
    provenances = item.get("prov", [])
    if not isinstance(provenances, list):
        return pages
    for provenance in provenances:
        if not isinstance(provenance, Mapping):
            continue
        page_no = provenance.get("page_no")
        if isinstance(page_no, int) and page_no not in pages:
            pages.append(page_no)
    return pages


def analyze_caption_affiliations(document: Mapping[str, Any]) -> JsonObject:
    """Report caption affiliations using only explicit Docling structure.

    A relation is confirmed only when all of these hold:
    * the media/table lists the caption as a child;
    * the caption points back to that parent;
    * both objects have provenance on at least one common page.
    """

    by_ref = _items_by_ref(document)
    media_refs: set[str] = set()
    relations: list[JsonObject] = []
    linked_caption_refs: set[str] = set()

    for collection in MEDIA_COLLECTIONS:
        values = document.get(collection, [])
        if not isinstance(values, list):
            continue
        for media in values:
            if not isinstance(media, Mapping):
                continue
            media_ref = media.get("self_ref")
            if not isinstance(media_ref, str):
                continue
            media_refs.add(media_ref)
            media_pages = _page_numbers(media)
            for child_ref in _child_refs(media):
                child = by_ref.get(child_ref)
                if not child or child.get("label") != "caption":
                    continue
                linked_caption_refs.add(child_ref)
                parent = child.get("parent")
                parent_ref = parent.get("$ref") if isinstance(parent, Mapping) else None
                caption_pages = _page_numbers(child)
                common_pages = sorted(set(media_pages) & set(caption_pages))
                blockers: list[str] = []
                if parent_ref != media_ref:
                    blockers.append("caption_parent_mismatch")
                if not common_pages:
                    blockers.append("no_common_page_provenance")
                relations.append(
                    {
                        "media_ref": media_ref,
                        "media_label": media.get("label"),
                        "caption_ref": child_ref,
                        "caption_text": child.get("text"),
                        "media_pages": media_pages,
                        "caption_pages": caption_pages,
                        "common_pages": common_pages,
                        "decision": (
                            "AFFILIATION_CONFIRMED"
                            if not blockers
                            else "REVIEW_REQUIRED"
                        ),
                        "blockers": blockers,
                    }
                )

    unlinked: list[JsonObject] = []
    texts = document.get("texts", [])
    if isinstance(texts, list):
        for text in texts:
            if not isinstance(text, Mapping) or text.get("label") != "caption":
                continue
            caption_ref = text.get("self_ref")
            if not isinstance(caption_ref, str) or caption_ref in linked_caption_refs:
                continue
            parent = text.get("parent")
            parent_ref = parent.get("$ref") if isinstance(parent, Mapping) else None
            blockers = ["caption_not_listed_by_media_parent"]
            if parent_ref not in media_refs:
                blockers.append("caption_parent_is_not_picture_or_table")
            unlinked.append(
                {
                    "caption_ref": caption_ref,
                    "caption_text": text.get("text"),
                    "parent_ref": parent_ref,
                    "caption_pages": _page_numbers(text),
                    "decision": "REVIEW_REQUIRED",
                    "blockers": blockers,
                }
            )

    confirmed_count = sum(
        relation["decision"] == "AFFILIATION_CONFIRMED" for relation in relations
    )
    review_count = len(relations) - confirmed_count + len(unlinked)
    return {
        "schema_version": "caption-affiliation-analysis.v1",
        "mode": "ANALYSIS_ONLY",
        "source_mutated": False,
        "relation_count": len(relations),
        "affiliation_confirmed_count": confirmed_count,
        "review_required_count": review_count,
        "unlinked_caption_count": len(unlinked),
        "relations": relations,
        "unlinked_captions": unlinked,
    }
