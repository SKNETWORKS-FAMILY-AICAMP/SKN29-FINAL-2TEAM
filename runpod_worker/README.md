# RunPod document worker

Queue-based RunPod Serverless worker for PDF/DOCX/Markdown parsing,
structure-preserving chunking, and `google/embeddinggemma-300m` CUDA embeddings.

`SUPPORTED_MIME_TYPES` in `pipeline.py` is the authoritative list. `text/plain`
maps to `.md` on purpose: docling 2.117 has no plain-text `InputFormat`, and
plain text is valid Markdown, so the MD backend reads it as paragraphs. That
list must stay in sync with `_UPLOAD_TYPES` in `backend/services/storage.py` —
otherwise users can upload files the worker cannot index
(`tests/test_document_pipeline.py` checks this).

**Changing `pipeline.py` does nothing until the image is rebuilt and the RunPod
endpoint points at the new tag.**

Before chunking, `density_heading_correction.py` promotes `text`/`list_item`
elements that the layout model misclassified back to `section_header` — short,
large-font, well-spaced-above, densely-followed-below items — and rewrites
them in place on the parsed `DoclingDocument` so chunking sees the corrected
structure. `promoted_heading_count` in the result's `validation` block reports
how many were promoted.

PDF picture description, chart extraction, and picture classification killed
whole documents in two measured ways. `do_chart_extraction` makes
`StandardPdfPipeline.__init__` load Granite Vision V4 onto the GPU, where
EmbeddingGemma, layout, TableFormer and EasyOCR already sit; it runs out of
memory and dies before reading a single page (`NVML_SUCCESS == r INTERNAL
ASSERT FAILED`, 14 jobs on 2026-08-25). Separately, a page that fails
preprocessing is dropped from `conv_res.pages` while enrichment still indexes
that list by the element's original page number, so a PDF with a broken page
died with `IndexError: list index out of range`.

`_convert` retries once with those three options off. docling guards the chart
model's import and construction behind `if do_chart_extraction:`, so the retry
provably avoids the GPU load. It is PDF-only, happens once, and re-raises if it
also fails, so the real reason still reaches the user. Documents rescued this
way carry `validation.enrichment_disabled = true` and have no chart or image
descriptions. The GPU case recurs for every document on that worker, costing a
doomed ~7s first attempt each time — sizing the GPU up, or turning enrichment
off outright, is the real cure.

Required environment:

```text
HF_TOKEN
EMBEDDING_MODEL=google/embeddinggemma-300m
EMBEDDING_DEVICE=cuda
```

The handler accepts a signed `source_url`; it never receives a local Django
path or database credentials. It returns blocks, chunks, 768-dimensional
embeddings, and diagnostics. Django owns the database transaction.

For a frozen evaluation set, the handler also accepts `embed_documents` with
at most 20 already-chunked text strings. It uses SentenceTransformers
`encode_document(..., normalize_embeddings=True)` and returns the model,
dimension, document mode, and normalization provenance. It receives no file
name, document/account identifier, database credential, or unrelated metadata.
