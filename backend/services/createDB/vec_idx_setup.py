"""
VEC_IDX(pgvector) 예시 저장·검색 스크립트.

VectorDB_저장대상_검증.md 7~8장 설계를 그대로 따른다:
- 별도 Vector DB(ChromaDB 등)를 쓰지 않고, VEC_IDX 테이블 하나로 3-B와
  같은 PostgreSQL 인스턴스에 저장한다(schema.sql 참고, pgvector/pgvector
  이미지가 vector 확장을 지원).
- CHUNK와 VEC_IDX는 1:1이고 vec_idx.chunk_id에 실FK가 걸려 있어서,
  Chroma 때와 달리 참조 대상 chunk가 실제로 존재해야 한다. 아래 데모는
  page3-A 시나리오 문서(CHK-018)와 동일한 예시를 최소 체인
  (proj → doc → doc_block → chunk)까지 만들어서 넣는다.

실행 전: `db` 컨테이너가 떠 있어야 한다(schema.sql이 이미 적용된 상태).
    pip install "psycopg[binary]"   (requirements/base.txt에 이미 포함)
"""

import os

import psycopg

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgres://project_copilot:project_copilot@localhost:5432/project_copilot",
)


def get_conn():
    return psycopg.connect(DATABASE_URL)


def _to_vector_literal(embedding: list[float]) -> str:
    # pgvector 파이썬 패키지 없이 텍스트 리터럴로 캐스팅한다: '[0.1,0.2,...]'::vector
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"


def upsert_vector(
    conn,
    *,
    chunk_id: str,
    embedding: list[float],
    embed_model: str,
    embed_ver: str,
    dist_metric: str = "COSINE",
    content_hash: str | None = None,
    revision: str | None = None,
    metadata: dict | None = None,
):
    """
    chunk_id당 1행(1:1)만 존재해야 하므로 ON CONFLICT로 upsert한다.
    embed_dim은 embedding 길이로 자동 계산 — 별도로 받지 않는다(값이 어긋나면
    그 자체로 버그이기 때문에 입력을 신뢰하지 않고 여기서 다시 계산한다).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO vec_idx
                (chunk_id, embedding, metadata, embed_model, embed_ver,
                 embed_dim, dist_metric, content_hash, revision)
            VALUES
                (%s, %s::vector, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (chunk_id) DO UPDATE SET
                embedding = EXCLUDED.embedding,
                metadata = EXCLUDED.metadata,
                embed_model = EXCLUDED.embed_model,
                embed_ver = EXCLUDED.embed_ver,
                embed_dim = EXCLUDED.embed_dim,
                dist_metric = EXCLUDED.dist_metric,
                content_hash = EXCLUDED.content_hash,
                revision = EXCLUDED.revision,
                indexed_at = now()
            """,
            (
                chunk_id,
                _to_vector_literal(embedding),
                psycopg.types.json.Jsonb(metadata or {}),
                embed_model,
                embed_ver,
                len(embedding),
                dist_metric,
                content_hash,
                revision,
            ),
        )
    conn.commit()


def search(conn, query_embedding: list[float], *, proj_id: str, security: str | None = None, top_k: int = 5):
    """
    1차 필터: proj_id(+선택적으로 security) — 여기까지가 VEC_IDX의 역할.
    업무 관련성(semantic_type) 필터링은 여기서 하지 않고, 반환된 chunk_id들을
    다시 질의해서 CHUNK→KNOW_ITEM_SRC→KNOW_ITEM으로 JOIN한다(7.2 ① 방식).
    거리 연산자 `<=>`는 코사인 거리(pgvector). dist_metric이 다르면 연산자도
    맞춰 바꿔야 한다(L2는 `<->`, inner product는 `<#>`).
    """
    where_security = "AND doc.security = %(security)s" if security else ""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT vec_idx.chunk_id, vec_idx.embedding <=> %(query)s::vector AS distance
            FROM vec_idx
            JOIN chunk ON chunk.chunk_id = vec_idx.chunk_id
            JOIN doc_block ON doc_block.block_id = chunk.block_id
            JOIN doc ON doc.doc_id = doc_block.doc_id
            WHERE doc.proj_id = %(proj_id)s
              AND vec_idx.is_active = true
              {where_security}
            ORDER BY distance
            LIMIT %(top_k)s
            """,
            {
                "query": _to_vector_literal(query_embedding),
                "proj_id": proj_id,
                "security": security,
                "top_k": top_k,
            },
        )
        return cur.fetchall()


if __name__ == "__main__":
    conn = get_conn()

    # 예시: page3-A 시나리오 문서의 CHK-018 청크를 저장한다고 가정.
    # VEC_IDX.chunk_id에 실FK가 걸려 있으므로 proj→doc→doc_block→chunk까지
    # 최소 체인을 먼저 만든다(각 단계 UUID는 데모 재실행 시 그대로 재사용하도록
    # 고정 이름으로 upsert).
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO proj (proj_id, name)
            VALUES ('00000000-0000-0000-0000-0000000000a1', '2026 AI Project')
            ON CONFLICT (proj_id) DO NOTHING
            """
        )
        cur.execute(
            """
            INSERT INTO doc (doc_id, proj_id, file_name, source_type, security)
            VALUES ('00000000-0000-0000-0000-0000000000d1',
                    '00000000-0000-0000-0000-0000000000a1',
                    '2026_AI_Project.pdf', 'DRIVE', 'Internal')
            ON CONFLICT (doc_id) DO NOTHING
            """
        )
        cur.execute(
            """
            INSERT INTO doc_block (block_id, doc_id, block_type, content, sequence, revision)
            VALUES ('00000000-0000-0000-0000-0000000000b1',
                    '00000000-0000-0000-0000-0000000000d1',
                    'PARAGRAPH',
                    '로그인 기능은 2026-08-06까지 완료. 담당자는 백엔드팀 김OO 대리.',
                    1, 'v3')
            ON CONFLICT (block_id) DO NOTHING
            """
        )
        cur.execute(
            """
            INSERT INTO chunk (chunk_id, block_id, search_text, chunk_idx)
            VALUES ('00000000-0000-0000-0000-0000000000c1',
                    '00000000-0000-0000-0000-0000000000b1',
                    '로그인 기능은 2026-08-06까지 완료. 담당자는 백엔드팀 김OO 대리.',
                    0)
            ON CONFLICT (chunk_id) DO NOTHING
            """
        )
    conn.commit()

    dummy_embedding = [0.0] * 1536

    upsert_vector(
        conn,
        chunk_id="00000000-0000-0000-0000-0000000000c1",
        embedding=dummy_embedding,
        embed_model="text-embedding-3-small",
        embed_ver="embed-1.0",
        content_hash="sha256:chunk018...",
        revision="v3",
        metadata={"doc_role": "PROJECT_PLAN", "file_name": "2026_AI_Project.pdf"},
    )

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM vec_idx")
        count = cur.fetchone()[0]

    print(f"VEC_IDX에 저장 완료. 현재 벡터 수: {count}")
    conn.close()
