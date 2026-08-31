from typing import Any

import pytest

pytest.importorskip("docling_core")

from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer
from docling_core.types.doc.document import (
    DescriptionMetaField,
    DoclingDocument,
    PictureClassificationMetaField,
    PictureClassificationPrediction,
    PictureMeta,
)
from docling_core.types.doc.labels import DocItemLabel
from picture_description_serializer import (
    DescriptionOnlyHybridChunker,
    DescriptionOnlySerializerProvider,
)


class WordTokenizer(BaseTokenizer):
    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def get_max_tokens(self) -> int:
        return 512

    def get_tokenizer(self) -> Any:
        return None


def _document_with_picture() -> tuple[DoclingDocument, object]:
    doc = DoclingDocument(name="description-only-test")
    caption = doc.add_text(
        label=DocItemLabel.CAPTION,
        text="caption must not leak",
    )
    picture = doc.add_picture(caption=caption)
    picture.meta = PictureMeta(
        description=DescriptionMetaField(
            text="VLM description only",
            created_by="test",
        ),
        classification=PictureClassificationMetaField(
            predictions=[
                PictureClassificationPrediction(
                    class_name="diagram",
                    confidence=0.99,
                )
            ]
        ),
    )
    return doc, picture


def test_picture_serialization_contains_description_only():
    doc, picture = _document_with_picture()
    serializer = DescriptionOnlySerializerProvider().get_serializer(doc)

    assert serializer.serialize(item=picture).text == "VLM description only"


def test_non_picture_serialization_keeps_docling_default():
    doc, _ = _document_with_picture()
    text = doc.add_text(label=DocItemLabel.TEXT, text="plain text preserved")
    serializer = DescriptionOnlySerializerProvider().get_serializer(doc)

    assert serializer.serialize(item=text).text == "plain text preserved"


def test_picture_without_description_uses_docling_default_serializer():
    doc = DoclingDocument(name="fallback-description-test")
    caption = doc.add_text(
        label=DocItemLabel.CAPTION,
        text="fallback caption",
    )
    picture = doc.add_picture(caption=caption)
    serializer = DescriptionOnlySerializerProvider().get_serializer(doc)

    assert "fallback caption" in serializer.serialize(item=picture).text


def test_hybrid_chunker_uses_description_only_picture_serializer():
    doc, _ = _document_with_picture()
    chunker = HybridChunker(
        tokenizer=WordTokenizer(),
        max_tokens=512,
        merge_peers=False,
        serializer_provider=DescriptionOnlySerializerProvider(),
    )

    chunks = list(chunker.chunk(dl_doc=doc))

    assert len(chunks) == 1
    assert chunks[0].text == "VLM description only"


def test_hybrid_chunker_keeps_default_picture_fallback_searchable():
    doc = DoclingDocument(name="fallback-chunk-test")
    caption = doc.add_text(
        label=DocItemLabel.CAPTION,
        text="fallback pump diagram",
    )
    doc.add_picture(caption=caption)
    chunker = HybridChunker(
        tokenizer=WordTokenizer(),
        max_tokens=512,
        merge_peers=False,
        serializer_provider=DescriptionOnlySerializerProvider(),
    )

    chunks = list(chunker.chunk(dl_doc=doc))

    assert any("fallback pump diagram" in chunk.text for chunk in chunks)


def test_merge_peers_keeps_picture_description_separate_from_body_text():
    doc, _ = _document_with_picture()
    doc.add_text(label=DocItemLabel.TEXT, text="adjacent body")
    chunker = DescriptionOnlyHybridChunker(
        tokenizer=WordTokenizer(),
        max_tokens=512,
        merge_peers=True,
        serializer_provider=DescriptionOnlySerializerProvider(),
    )

    chunks = list(chunker.chunk(dl_doc=doc))

    assert [chunk.text for chunk in chunks] == [
        "VLM description only",
        "adjacent body",
    ]
