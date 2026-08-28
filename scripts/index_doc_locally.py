"""문서 하나를 **로컬에서** 청킹·임베딩해 검색 색인에 넣는다.

정상 색인 경로(`promote_to_searchable` → RunPod 문서 처리 잡)는 RunPod 이 문서를
공개 URL 로 되받아 가야 한다. dev 의 그 터널이 죽어 있으면 색인이 안 된다. 이
스크립트는 그 잡을 우회한다 — Markdown 을 헤딩 단위로 쪼개고, 살아 있는
`embed_queries` 엔드포인트로 벡터를 얻어 `doc_block`/`chunk`/`vec_idx` 에 직접 넣는다.

    docker exec skn29-final-2team-web-1 python scripts/index_doc_locally.py DC051

Markdown 전용(간이 청커). 벡터 검색·업무 추출을 dev 에서 굴려 보기 위한 것이다.
"""

from __future__ import annotations

import os
import sys
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from psycopg.types.json import Jsonb  # noqa: E402

from backend.db.connection import database_connection  # noqa: E402
from backend.services import storage  # noqa: E402
from services.document_pipeline.runpod_client import embed_queries  # noqa: E402

_MODEL = "google/embeddinggemma-300m"


def _split_markdown(text: str) -> list[tuple[list[str], str]]:
    """(heading_path, section_text) 목록. `#`~`###` 헤딩마다 한 조각."""
    sections: list[tuple[list[str], str]] = []
    path: list[str | None] = [None, None, None]  # h1, h2, h3
    buf: list[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        if body:
            hp = [h for h in path if h]
            sections.append((hp, (" > ".join(hp) + "\n" + body) if hp else body))

    for line in text.splitlines():
        if line.startswith("### "):
            flush(); buf = []; path[2] = line[4:].strip()
        elif line.startswith("## "):
            flush(); buf = []; path[1] = line[3:].strip(); path[2] = None
        elif line.startswith("# "):
            flush(); buf = []; path[0] = line[2:].strip(); path[1] = path[2] = None
        else:
            buf.append(line)
    flush()
    return sections


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit("usage: index_doc_locally.py <doc_id>")
    doc_id = sys.argv[1]

    with database_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT storage_key, cur_revision, mime_type FROM doc WHERE doc_id = %s", (doc_id,)
        )
        row = cursor.fetchone()
    if row is None or not row["storage_key"]:
        raise SystemExit(f"저장된 원문이 없는 문서: {doc_id}")
    revision = row["cur_revision"]
    raw = storage.load(row["storage_key"]).decode("utf-8")

    sections = _split_markdown(raw)
    if not sections:
        raise SystemExit("쪼갤 내용이 없습니다.")
    texts = [body for _hp, body in sections]
    print(f"{doc_id}: {len(sections)} 조각 임베딩 중…", flush=True)
    vectors = embed_queries(texts)

    with database_connection() as connection, connection.cursor() as cursor:
        # 재실행 대비 — 이 문서의 옛 색인을 지운다.
        cursor.execute(
            """
            DELETE FROM vec_idx WHERE chunk_id IN (
                SELECT c.chunk_id FROM chunk c
                JOIN doc_block b ON b.block_id = c.block_id WHERE b.doc_id = %s
            )
            """,
            (doc_id,),
        )
        cursor.execute(
            "DELETE FROM chunk WHERE block_id IN (SELECT block_id FROM doc_block WHERE doc_id = %s)",
            (doc_id,),
        )
        cursor.execute("DELETE FROM doc_block WHERE doc_id = %s", (doc_id,))

        for idx, ((heading_path, body), vector) in enumerate(zip(sections, vectors, strict=True)):
            block_id = uuid4()
            cursor.execute(
                """
                INSERT INTO doc_block
                    (block_id, doc_id, block_type, heading_path, content, sequence, revision)
                VALUES (%s, %s, 'paragraph', %s, %s, %s, %s)
                """,
                (block_id, doc_id, heading_path, body, idx, revision),
            )
            chunk_id = uuid4()
            cursor.execute(
                """
                INSERT INTO chunk
                    (chunk_id, block_id, search_text, chunk_idx, heading_path, chunker_ver)
                VALUES (%s, %s, %s, %s, %s, 'local-md-1')
                """,
                (chunk_id, block_id, body, idx, heading_path),
            )
            vlit = "[" + ",".join(repr(float(x)) for x in vector) + "]"
            cursor.execute(
                """
                INSERT INTO vec_idx
                    (chunk_id, embedding, metadata, embed_model, embed_ver, embed_dim, revision)
                VALUES (%s, %s::vector, %s, %s, %s, 768, %s)
                """,
                (chunk_id, vlit, Jsonb({"doc_id": doc_id, "local": True}), _MODEL, _MODEL, revision),
            )

        cursor.execute(
            "UPDATE doc SET index_status = 'COMPLETED', index_detail = NULL WHERE doc_id = %s",
            (doc_id,),
        )

    print(f"{doc_id}: {len(sections)} 블록/청크/벡터 색인 완료.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
