# RunPod document worker

Queue-based RunPod Serverless worker for PDF/DOCX/Markdown parsing,
structure-preserving chunking, and `google/embeddinggemma-300m` CUDA embeddings.

`SUPPORTED_MIME_TYPES` in `pipeline.py` is the authoritative list. `text/plain`
maps to `.md` on purpose: Docling has no plain-text `InputFormat`, and
plain text is valid Markdown, so the MD backend reads it as paragraphs. That
list must stay in sync with `_UPLOAD_TYPES` in `backend/services/storage.py` —
otherwise users can upload files the worker cannot index
(`tests/test_document_pipeline.py` checks this).

**Changing `pipeline.py` does nothing until the image is rebuilt and the RunPod
endpoint points at the new tag.**

Before chunking, the worker now applies the final parsing layers in this order:

1. Docling 2.119: Heron, selective EasyOCR, TableFormer ACCURATE/cell matching,
   picture classification, and heading hierarchy.
2. `reading_order_postprocess/`: only validated same-parent adjacent inversions.
3. `density_heading_correction.py`: corrected-order density; only plain `text`
   is auto-promoted. Density-only `list_item` candidates remain shadow-only.
4. `table_gate.py`: remove only the frozen high-precision non-table patterns.
5. `context_picture_description.py`: run Qwen after structural correction so
   captions, section path, and sibling context reflect the final order. Picture
   elements are inferred in batches of 4.
6. `picture_description_serializer.py`: serialize a `PictureItem` as the
   accepted `meta.description.text` only. Caption, classification, other picture
   metadata, placeholders, and adjacent body text are excluded. Picture chunks
   remain merge boundaries even when `merge_peers=true`; non-picture chunks
   retain Docling's normal merge and contextualization behavior.

The complete audit is returned under `validation.final_parse`. Existing
`validation.promoted_heading_count` remains for backward compatibility.

The first Docling pass does not load built-in picture description or Granite
chart extraction. It creates embedded crops and classifications only. The
converter cache is released before Qwen is loaded. If first-stage picture
classification fails, PDF conversion is retried once without classification.
If the optional Qwen stage fails, the corrected structured document is kept
and the exact failure is written to the picture audit; document indexing does
not fail only because an image description failed.

A picture with no accepted description emits no picture text chunk. For a
described picture, the embedding input is the description itself rather than
`HybridChunker.contextualize()`, so headings are not prepended to image text.

Runtime pins are `docling[easyocr,vlm]==2.119.0`, `transformers==5.8.0`, and
`sentence-transformers==6.0.0`.
Rebuild the image; changing this read-only repository copy alone does not update
the separately deployed production Worker.

Required environment:

```text
HF_TOKEN
EMBEDDING_MODEL=google/embeddinggemma-300m
EMBEDDING_DEVICE=cuda
```

The handler accepts a signed `source_url`; it never receives a local Django
path or database credentials. It returns blocks, chunks, 768-dimensional
embeddings, and diagnostics. Django owns the database transaction.
