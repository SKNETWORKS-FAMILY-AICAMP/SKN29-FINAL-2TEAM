"""Docling chunk serializer that emits only the VLM picture description.

Text, table, list, and heading serialization keep Docling's defaults.  Only
``PictureItem`` serialization is replaced so captions, image placeholders,
classification results, and other annotations cannot leak into the embedding
text for a picture.
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
    """Serialize a picture as its accepted VLM description and nothing else."""

    @override
    def serialize(
        self,
        *,
        item: PictureItem,
        doc_serializer: BaseDocSerializer,
        doc: DoclingDocument,
        **kwargs: Any,
    ) -> SerializationResult:
        del doc, kwargs
        description = getattr(getattr(item, "meta", None), "description", None)
        text = str(getattr(description, "text", "") or "").strip()
        text = doc_serializer.post_process(text=text)
        return create_ser_result(text=text, span_source=item)


class PictureMetaSuppressingSerializer(MarkdownMetaSerializer):
    """Prevent the document serializer from appending picture meta twice.

    ``ChunkingDocSerializer`` serializes an item's meta independently from its
    item serializer.  The picture serializer above already reads the one
    allowed meta field, so picture meta must be suppressed here.  Non-picture
    item metadata keeps Docling's default behavior.
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
            return create_ser_result()
        return super().serialize(item=item, doc=doc, **kwargs)


class DescriptionOnlySerializerProvider(ChunkingSerializerProvider):
    """Keep Docling defaults except for ``PictureItem`` serialization."""

    @override
    def get_serializer(self, doc: DoclingDocument) -> ChunkingDocSerializer:
        return ChunkingDocSerializer(
            doc=doc,
            picture_serializer=DescriptionOnlyPictureSerializer(),
            meta_serializer=PictureMetaSuppressingSerializer(),
        )


class DescriptionOnlyHybridChunker(HybridChunker):
    """Preserve picture chunks as merge boundaries.

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
