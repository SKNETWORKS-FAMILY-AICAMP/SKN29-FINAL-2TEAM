"""Prefer an accepted VLM picture description and keep a default fallback.

Text, table, list, and heading serialization keep Docling's defaults.  Only
``PictureItem`` serialization is specialized: an accepted VLM description is
the only embedding text when present; otherwise Docling's default picture and
metadata serializers provide a searchable fallback instead of dropping the
picture from the chunk set.
"""

from __future__ import annotations

from typing import Any

from docling_core.transforms.chunker.doc_chunk import DocChunk
from docling_core.transforms.chunker.hierarchical_chunker import (
    ChunkingDocSerializer,
    ChunkingSerializerProvider,
)
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.serializer.base import (
    BaseDocSerializer,
    SerializationResult,
)
from docling_core.transforms.serializer.common import create_ser_result
from docling_core.transforms.serializer.markdown import (
    MarkdownMetaSerializer,
    MarkdownPictureSerializer,
)
from docling_core.types.doc.document import DoclingDocument, NodeItem, PictureItem
from typing_extensions import override


class DescriptionOnlyPictureSerializer(MarkdownPictureSerializer):
    """Use accepted VLM text first, then Docling's default picture serializer."""

    @override
    def serialize(
        self,
        *,
        item: PictureItem,
        doc_serializer: BaseDocSerializer,
        doc: DoclingDocument,
        **kwargs: Any,
    ) -> SerializationResult:
        description = getattr(getattr(item, "meta", None), "description", None)
        text = str(getattr(description, "text", "") or "").strip()
        if text:
            text = doc_serializer.post_process(text=text)
            return create_ser_result(text=text, span_source=item)
        return super().serialize(
            item=item,
            doc_serializer=doc_serializer,
            doc=doc,
            **kwargs,
        )


class PictureMetaSuppressingSerializer(MarkdownMetaSerializer):
    """Suppress picture metadata only when an accepted description exists.

    ``ChunkingDocSerializer`` serializes an item's meta independently from its
    item serializer. Accepted descriptions must remain description-only, but a
    picture without one intentionally falls back to Docling's default metadata
    serialization.
    """

    @override
    def serialize(
        self,
        *,
        item: NodeItem,
        doc: DoclingDocument,
        **kwargs: Any,
    ) -> SerializationResult:
        if isinstance(item, PictureItem):
            description = getattr(getattr(item, "meta", None), "description", None)
            if str(getattr(description, "text", "") or "").strip():
                return create_ser_result()
        return super().serialize(item=item, doc=doc, **kwargs)


class DescriptionOnlySerializerProvider(ChunkingSerializerProvider):
    """Use description-first Picture serialization with a default fallback."""

    @override
    def get_serializer(self, doc: DoclingDocument) -> ChunkingDocSerializer:
        return ChunkingDocSerializer(
            doc=doc,
            picture_serializer=DescriptionOnlyPictureSerializer(),
            meta_serializer=PictureMetaSuppressingSerializer(),
        )


class DescriptionOnlyHybridChunker(HybridChunker):
    """Preserve description and default-fallback picture chunks as boundaries.

    Docling's ``merge_peers=True`` may otherwise merge a description-only
    picture chunk with adjacent body text that has the same heading metadata.
    Non-picture runs are still merged by Docling's original implementation.
    """

    @override
    def _merge_chunks_with_matching_metadata(
        self,
        chunks: list[DocChunk],
    ) -> list[DocChunk]:
        output: list[DocChunk] = []
        text_run: list[DocChunk] = []

        def flush_text_run() -> None:
            if text_run:
                output.extend(
                    super(
                        DescriptionOnlyHybridChunker, self
                    )._merge_chunks_with_matching_metadata(text_run)
                )
                text_run.clear()

        for chunk in chunks:
            has_picture = any(
                str(getattr(item, "self_ref", "")).startswith("#/pictures/")
                for item in chunk.meta.doc_items
            )
            if has_picture:
                flush_text_run()
                output.append(chunk)
            else:
                text_run.append(chunk)
        flush_text_run()
        return output
