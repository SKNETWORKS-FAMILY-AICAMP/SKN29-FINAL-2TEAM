"""승인된 로컬 청크만 현재 RunPod 문서 모델로 재임베딩해 별도 보관한다."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
import subprocess
from urllib.parse import urlparse

import django
import psycopg
from psycopg.rows import dict_row


SCHEMA = "eval_real"
MODEL = "google/embeddinggemma-300m"
BATCH_SIZE = 20


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(repr(float(value)) for value in vector) + "]"


def main() -> int:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()
    from services.document_pipeline.runpod_client import embed_documents

    database_url = os.environ.get("DATABASE_URL", "").strip()
    if urlparse(database_url).hostname not in {"db", "localhost", "127.0.0.1"}:
        raise RuntimeError("DATABASE_URL은 로컬 Docker DB여야 합니다.")
    code_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, check=True, text=True,
    ).stdout.strip()

    with psycopg.connect(database_url, row_factory=dict_row, connect_timeout=8) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT chunk_id, search_text FROM {SCHEMA}.chunk ORDER BY chunk_id"
            )
            chunks = list(cursor.fetchall())
    if len(chunks) != 294:
        raise RuntimeError(f"승인된 청크가 294개가 아닙니다: {len(chunks)}개")

    generated: list[tuple] = []
    generated_at = datetime.now(timezone.utc)
    for start in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[start:start + BATCH_SIZE]
        output = embed_documents([row["search_text"] for row in batch])
        for row, vector in zip(batch, output["embeddings"], strict=True):
            text_hash = "sha256:" + hashlib.sha256(row["search_text"].encode()).hexdigest()
            generated.append((row["chunk_id"], vector, text_hash))

    if len(generated) != 294 or any(len(vector) != 768 for _, vector, _ in generated):
        raise RuntimeError("재임베딩 완전성 검증에 실패했습니다.")

    with psycopg.connect(database_url, row_factory=dict_row, connect_timeout=8) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {SCHEMA}.verified_vector_run (
                    run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                    generated_at timestamptz NOT NULL,
                    model text NOT NULL,
                    dimension integer NOT NULL,
                    embedding_mode text NOT NULL,
                    normalized boolean NOT NULL,
                    code_commit text NOT NULL,
                    chunk_count integer NOT NULL
                );
                CREATE TABLE IF NOT EXISTS {SCHEMA}.verified_vector (
                    chunk_id uuid PRIMARY KEY REFERENCES {SCHEMA}.chunk(chunk_id),
                    embedding vector(768) NOT NULL,
                    search_text_hash text NOT NULL,
                    generated_at timestamptz NOT NULL,
                    model text NOT NULL,
                    code_commit text NOT NULL
                );
                """
            )
            cursor.execute(f"SELECT count(*) AS count FROM {SCHEMA}.verified_vector")
            if cursor.fetchone()["count"]:
                raise RuntimeError("검증 벡터가 이미 있어 덮어쓰지 않습니다.")
            for chunk_id, vector, text_hash in generated:
                cursor.execute(
                    f"INSERT INTO {SCHEMA}.verified_vector VALUES (%s,%s::vector,%s,%s,%s,%s)",
                    (chunk_id, _vector_literal(vector), text_hash, generated_at, MODEL, code_commit),
                )
            cursor.execute(
                f"""
                INSERT INTO {SCHEMA}.verified_vector_run
                    (generated_at, model, dimension, embedding_mode, normalized, code_commit, chunk_count)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                """,
                (generated_at, MODEL, 768, "document", True, code_commit, len(generated)),
            )
            cursor.execute(
                f"UPDATE {SCHEMA}.dataset_meta SET embedding_model_claim=%s, embedding_provenance_status=%s",
                (MODEL, "verified_reembedded_separate_table"),
            )
    print("실문서 재임베딩 완료: 294/294 · 768차원 · 누락 0 · 별도 테이블 저장")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
