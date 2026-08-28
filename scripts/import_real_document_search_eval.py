"""공용 RDS의 승인된 팀 PDF 검색 데이터만 로컬 격리 스키마로 복사한다.

소스 연결은 항상 read-only와 짧은 timeout을 강제한다. 대상은 로컬 DATABASE_URL의
새 ``eval_real`` 스키마이며, 이미 존재하면 덮어쓰지 않고 중단한다.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import os
from urllib.parse import urlparse

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


SCHEMA = "eval_real"
SOURCE_OPTIONS = "-c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=1000"


def _connection_identity(url: str) -> tuple[str | None, int | None, str]:
    parsed = urlparse(url)
    return parsed.hostname, parsed.port, parsed.path.lstrip("/")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--approval-note", required=True)
    parser.add_argument("--retention-days", type=int, default=7)
    args = parser.parse_args()
    if args.retention_days < 1 or args.retention_days > 30:
        raise ValueError("보관 기간은 1~30일이어야 합니다.")

    source_url = os.environ.get("EVAL_SOURCE_DATABASE_URL", "").strip()
    destination_url = os.environ.get("DATABASE_URL", "").strip()
    if not source_url or not destination_url:
        raise RuntimeError("EVAL_SOURCE_DATABASE_URL과 DATABASE_URL이 모두 필요합니다.")
    if _connection_identity(source_url) == _connection_identity(destination_url):
        raise RuntimeError("공용 소스 DB와 로컬 대상 DB가 같습니다.")
    if _connection_identity(destination_url)[0] not in {"db", "localhost", "127.0.0.1"}:
        raise RuntimeError("대상 DATABASE_URL은 로컬 Docker DB여야 합니다.")

    imported_at = datetime.now(timezone.utc)
    expires_at = imported_at + timedelta(days=args.retention_days)
    with (
        psycopg.connect(
            source_url, row_factory=dict_row, options=SOURCE_OPTIONS, connect_timeout=8,
        ) as source,
        psycopg.connect(destination_url, row_factory=dict_row, connect_timeout=8) as destination,
    ):
        with source.cursor() as source_cursor, destination.cursor() as destination_cursor:
            source_cursor.execute(
                """
                SELECT current_setting('transaction_read_only') AS read_only,
                       current_setting('server_version') AS postgres_version,
                       COALESCE((SELECT extversion FROM pg_extension WHERE extname = 'pg_trgm'),
                                'missing') AS pg_trgm_version
                """
            )
            environment = source_cursor.fetchone()
            if environment["read_only"] != "on":
                raise RuntimeError("소스 DB 연결이 read-only가 아닙니다.")
            destination_cursor.execute(
                """
                SELECT current_setting('server_version') AS postgres_version,
                       COALESCE((SELECT extversion FROM pg_extension WHERE extname = 'pg_trgm'),
                                'missing') AS pg_trgm_version,
                       COALESCE((SELECT extversion FROM pg_extension WHERE extname = 'vector'),
                                'missing') AS vector_version
                """
            )
            runtime_environment = destination_cursor.fetchone()

            source_cursor.execute(
                """
                SELECT d.doc_id, d.cur_revision AS revision, d.content_hash, d.mime_type
                  FROM doc d
                 WHERE d.team_id IS NOT NULL
                   AND d.owner_account_id IS NULL
                   AND d.mime_type = 'application/pdf'
                   AND d.deleted = false
                   AND d.access_revoked = false
                   AND EXISTS (
                       SELECT 1
                         FROM doc_block b
                         JOIN chunk c ON c.block_id = b.block_id AND c.is_active = true
                         JOIN vec_idx v ON v.chunk_id = c.chunk_id
                        WHERE b.doc_id = d.doc_id AND b.revision = d.cur_revision
                   )
                 ORDER BY d.doc_id
                """
            )
            documents = list(source_cursor.fetchall())
            if len(documents) != 8:
                raise RuntimeError(f"승인 후보 팀 PDF가 예상한 8개가 아닙니다: {len(documents)}개")
            doc_ids = [row["doc_id"] for row in documents]

            destination_cursor.execute("SELECT to_regnamespace(%s) AS existing", (SCHEMA,))
            if destination_cursor.fetchone()["existing"] is not None:
                raise RuntimeError(f"로컬 {SCHEMA} 스키마가 이미 있어 덮어쓰지 않습니다.")
            destination_cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(SCHEMA)))
            destination_cursor.execute(
                f"""
                CREATE TABLE {SCHEMA}.dataset_meta (
                    imported_at timestamptz NOT NULL,
                    expires_at timestamptz NOT NULL,
                    approved_by text NOT NULL,
                    approval_note text NOT NULL,
                    source_postgres_version text NOT NULL,
                    source_pg_trgm_version text NOT NULL,
                    runtime_postgres_version text NOT NULL,
                    runtime_pg_trgm_version text NOT NULL,
                    runtime_vector_version text NOT NULL,
                    fts_config text NOT NULL,
                    revision_scope text NOT NULL,
                    contains_raw_pdf boolean NOT NULL
                );
                CREATE TABLE {SCHEMA}.document (
                    doc_id text PRIMARY KEY,
                    display_alias text NOT NULL UNIQUE,
                    revision text NOT NULL,
                    content_hash text NOT NULL,
                    mime_type text NOT NULL,
                    approved_for_evaluation boolean NOT NULL,
                    approved_by text NOT NULL,
                    approved_at timestamptz NOT NULL
                );
                CREATE TABLE {SCHEMA}.block (
                    block_id uuid PRIMARY KEY,
                    doc_id text NOT NULL REFERENCES {SCHEMA}.document(doc_id),
                    block_type text NOT NULL,
                    page integer,
                    heading_path text[] NOT NULL,
                    content text NOT NULL,
                    sequence integer NOT NULL,
                    revision text NOT NULL,
                    src_locator jsonb,
                    struct_content jsonb
                );
                CREATE TABLE {SCHEMA}.chunk (
                    chunk_id uuid PRIMARY KEY,
                    block_id uuid NOT NULL REFERENCES {SCHEMA}.block(block_id),
                    search_text text NOT NULL,
                    chunk_idx integer NOT NULL,
                    token_cnt integer,
                    heading_path text[] NOT NULL,
                    chunker_ver text
                );
                CREATE TABLE {SCHEMA}.vector (
                    chunk_id uuid PRIMARY KEY REFERENCES {SCHEMA}.chunk(chunk_id),
                    embedding vector(768) NOT NULL,
                    metadata jsonb NOT NULL
                );
                """
            )
            destination_cursor.execute(
                f"""
                INSERT INTO {SCHEMA}.dataset_meta
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    imported_at, expires_at, args.approved_by, args.approval_note,
                    environment["postgres_version"], environment["pg_trgm_version"],
                    runtime_environment["postgres_version"],
                    runtime_environment["pg_trgm_version"],
                    runtime_environment["vector_version"],
                    "simple", "current_only", False,
                ),
            )
            for index, row in enumerate(documents, start=1):
                destination_cursor.execute(
                    f"INSERT INTO {SCHEMA}.document VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        row["doc_id"], f"TEAM-PDF-{index:02d}", row["revision"],
                        row["content_hash"], row["mime_type"], True,
                        args.approved_by, imported_at,
                    ),
                )

            source_cursor.execute(
                """
                SELECT b.block_id, b.doc_id, b.block_type, b.page, b.heading_path,
                       b.content, b.sequence, b.revision, b.src_locator, b.struct_content
                  FROM doc_block b
                  JOIN doc d ON d.doc_id = b.doc_id AND d.cur_revision = b.revision
                 WHERE b.doc_id = ANY(%s)
                 ORDER BY b.doc_id, b.sequence
                """,
                (doc_ids,),
            )
            blocks = list(source_cursor.fetchall())
            for row in blocks:
                destination_cursor.execute(
                    f"INSERT INTO {SCHEMA}.block VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        row["block_id"], row["doc_id"], row["block_type"], row["page"],
                        row["heading_path"], row["content"], row["sequence"],
                        row["revision"],
                        Jsonb(row["src_locator"]) if row["src_locator"] is not None else None,
                        Jsonb(row["struct_content"]) if row["struct_content"] is not None else None,
                    ),
                )

            source_cursor.execute(
                """
                SELECT c.chunk_id, c.block_id, c.search_text, c.chunk_idx, c.token_cnt,
                       c.heading_path, c.chunker_ver, v.embedding::text AS embedding,
                       v.metadata
                  FROM chunk c
                  JOIN doc_block b ON b.block_id = c.block_id
                  JOIN doc d ON d.doc_id = b.doc_id AND d.cur_revision = b.revision
                  JOIN vec_idx v ON v.chunk_id = c.chunk_id
                 WHERE b.doc_id = ANY(%s) AND c.is_active = true
                 ORDER BY b.doc_id, c.chunk_idx
                """,
                (doc_ids,),
            )
            chunks = list(source_cursor.fetchall())
            for row in chunks:
                destination_cursor.execute(
                    f"INSERT INTO {SCHEMA}.chunk VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (
                        row["chunk_id"], row["block_id"], row["search_text"],
                        row["chunk_idx"], row["token_cnt"], row["heading_path"],
                        row["chunker_ver"],
                    ),
                )
                destination_cursor.execute(
                    f"INSERT INTO {SCHEMA}.vector VALUES (%s,%s::vector,%s)",
                    (row["chunk_id"], row["embedding"], Jsonb(row["metadata"])),
                )

            destination_cursor.execute(
                f"""
                SELECT (SELECT count(*) FROM {SCHEMA}.document) AS documents,
                       (SELECT count(*) FROM {SCHEMA}.block) AS blocks,
                       (SELECT count(*) FROM {SCHEMA}.chunk) AS chunks,
                       (SELECT count(*) FROM {SCHEMA}.vector) AS vectors,
                       (SELECT count(*) FROM {SCHEMA}.chunk c
                         LEFT JOIN {SCHEMA}.vector v USING (chunk_id)
                        WHERE v.chunk_id IS NULL) AS missing_vectors
                """
            )
            counts = destination_cursor.fetchone()
            if counts["documents"] != 8 or counts["chunks"] != counts["vectors"]:
                raise RuntimeError(f"복사 완전성 검증 실패: {dict(counts)}")
            if counts["missing_vectors"]:
                raise RuntimeError(f"벡터 누락: {counts['missing_vectors']}개")

    print(
        f"실문서 평가 데이터 준비 완료: 문서 {counts['documents']} · "
        f"블록 {counts['blocks']} · 청크/벡터 {counts['chunks']} · "
        f"보관 기한 {expires_at.date().isoformat()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
