# RunPod document worker

Queue-based RunPod Serverless worker for PDF/DOCX parsing, structure-preserving
chunking, and `google/embeddinggemma-300m` CUDA embeddings.

Required environment:

```text
HF_TOKEN
EMBEDDING_MODEL=google/embeddinggemma-300m
EMBEDDING_DEVICE=cuda
```

The handler accepts a signed `source_url`; it never receives a local Django
path or database credentials. It returns blocks, chunks, 768-dimensional
embeddings, and diagnostics. Django owns the database transaction.
