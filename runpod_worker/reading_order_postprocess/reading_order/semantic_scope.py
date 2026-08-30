"""Classify which Docling items require strict Reading Order correction.

The goal is semantic document refinement, not pixel-perfect replication of
every visual object. Textual and structural items affect Markdown, chunks, and
RAG context directly. Pictures remain review-only until the downstream
pipeline explicitly consumes their captions, VLM descriptions, or diagram
content. Furniture is outside the body reading flow.
"""

from __future__ import annotations

from typing import Any, Mapping

try:
    from enum import StrEnum
except ImportError:  # Python 3.10 used by the Ubuntu 22.04 Worker image.
    from enum import Enum

    class StrEnum(str, Enum):
        """Minimal Python 3.10-compatible subset used by this module."""

        def __str__(self) -> str:
            return self.value


class OrderingRelevance(StrEnum):
    """How strongly an item participates in semantic Reading Order."""

    REQUIRED = "required"
    REVIEW = "review"
    IGNORE = "ignore"


REQUIRED_LABELS = frozenset(
    {
        "text",
        "paragraph",
        "section_header",
        "title",
        "list_item",
        "caption",
        "table",
        "formula",
        "code",
    }
)

REVIEW_LABELS = frozenset({"picture", "image", "figure", "icon", "diagram"})


def classify_ordering_relevance(record: Mapping[str, Any]) -> OrderingRelevance:
    """Classify one mapped Docling item by downstream semantic impact.

    This conservative default intentionally keeps all pictures in ``REVIEW``.
    A later integration policy may promote a specific picture when its caption,
    VLM description, or diagram content is exported into semantic chunks.
    """

    if record.get("content_layer") == "furniture":
        return OrderingRelevance.IGNORE

    label = record.get("label")
    if label in REQUIRED_LABELS:
        return OrderingRelevance.REQUIRED
    if label in REVIEW_LABELS:
        return OrderingRelevance.REVIEW
    return OrderingRelevance.REVIEW


def filter_ordering_records(
    records: list[dict[str, Any]],
    *,
    include_review: bool = False,
) -> list[dict[str, Any]]:
    """Return records relevant to correction under the selected policy."""

    allowed = {OrderingRelevance.REQUIRED}
    if include_review:
        allowed.add(OrderingRelevance.REVIEW)
    return [
        record
        for record in records
        if classify_ordering_relevance(record) in allowed
    ]
