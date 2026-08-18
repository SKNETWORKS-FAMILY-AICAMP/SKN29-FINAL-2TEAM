# RunPod document worker

Queue-based RunPod Serverless worker for PDF/DOCX parsing, structure-preserving
chunking, and `google/embeddinggemma-300m` CUDA embeddings.

Before chunking, `density_heading_correction.py` promotes `text`/`list_item`
elements that the layout model misclassified back to `section_header` — short,
large-font, well-spaced-above, densely-followed-below items — and rewrites
them in place on the parsed `DoclingDocument` so chunking sees the corrected
structure. `promoted_heading_count` in the result's `validation` block reports
how many were promoted.

Required environment:

```text
HF_TOKEN
EMBEDDING_MODEL=google/embeddinggemma-300m
EMBEDDING_DEVICE=cuda
```

The handler accepts a signed `source_url`; it never receives a local Django
path or database credentials. It returns blocks, chunks, 768-dimensional
embeddings, and diagnostics. Django owns the database transaction.
