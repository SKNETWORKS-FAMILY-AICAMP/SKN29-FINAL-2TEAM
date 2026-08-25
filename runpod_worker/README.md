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

PDF picture description, chart extraction, and picture classification are
enrichment steps that run *after* page preprocessing. A page that fails
preprocessing is dropped from `conv_res.pages`, but enrichment still indexes
that list by the element's original page number, so any PDF with a broken page
died with `IndexError: list index out of range` inside
`StandardPdfPipeline` — the whole document was lost. `_convert` now retries
once with those three options off, which converts the same file successfully.
The retry is PDF-only, happens once, and re-raises if it also fails, so the
real reason still reaches the user. Documents rescued this way carry
`validation.enrichment_disabled = true` and have no chart or image
descriptions.

Required environment:

```text
HF_TOKEN
EMBEDDING_MODEL=google/embeddinggemma-300m
EMBEDDING_DEVICE=cuda
```

The handler accepts a signed `source_url`; it never receives a local Django
path or database credentials. It returns blocks, chunks, 768-dimensional
embeddings, and diagnostics. Django owns the database transaction.
