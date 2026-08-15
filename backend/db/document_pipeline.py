from __future__ import annotations

from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from .connection import database_connection
from .errors import PermissionDenied, RecordNotFound
from .repositories import _require_team, _require_team_project


#: 현재 revision 의 원문이 Block·Chunk·Vector 까지 적재됐는가. 세 단계 중 하나라도
#: 비면 검색이 안 되므로 EXISTS 하나로 묶어 묻는다.
_SEARCH_READY = """
    EXISTS (
        SELECT 1 FROM doc_block b
        JOIN chunk c ON c.block_id = b.block_id AND c.is_active = true
        JOIN vec_idx v ON v.chunk_id = c.chunk_id AND v.is_active = true
        WHERE b.doc_id = d.doc_id AND b.revision = d.cur_revision
    ) AS search_ready
"""


class PipelineDocumentRepository:
    """문서 처리는 **팀** 단위다(2026-08-04).

    원래는 전부 `proj_id`로 걸렀는데, 우리 모델에서 문서는 팀의 Drive 폴더에서
    나오고 등록 시점에는 `proj_id`가 NULL이다. 프로젝트에 묶이는 것은 기준 문서로
    **선택될 때**고, 그 선택 화면은 이미 파싱·임베딩이 끝난 문서를 골라야 한다 —
    즉 처리가 선택보다 먼저다. 프로젝트로 걸렀다면 처리할 수 있는 문서가 언제나
    0건이었다.

    소유자(`proj.owner_account_id`) 검사도 팀 검사로 바꿨다. 팀장이 등록한 문서를
    팀원이 못 여는 것은 테넌트 경계가 팀이라는 정의와 어긋난다.
    """

    @staticmethod
    def get_for_processing(*, doc_id: str, account_id: str) -> dict[str, Any]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                cursor.execute(
                    """
                    SELECT doc_id, team_id, proj_id, file_name, mime_type, doc_role,
                           cur_revision, content_hash, storage_key, deleted, access_revoked
                    FROM doc WHERE doc_id = %s
                    """,
                    (doc_id,),
                )
                row = cursor.fetchone()
        if row is None:
            raise RecordNotFound(f"존재하지 않는 문서입니다: {doc_id}")
        if row["team_id"] != team_id:
            raise PermissionDenied("이 문서에 접근할 수 없습니다.")
        if row["deleted"] or row["access_revoked"]:
            raise PermissionDenied("삭제되었거나 접근이 철회된 문서입니다.")
        if not row["storage_key"] or not row["cur_revision"]:
            raise ValueError("문서 원문과 revision이 로컬 저장소에 준비되지 않았습니다.")
        return row

    @staticmethod
    def get_signed_download(*, doc_id: str, revision: str) -> dict[str, Any]:
        """서명 token 으로만 오는 경로다. 로그인 세션이 없어 팀을 물을 수 없고,
        token 이 `doc_id`+`revision`을 함께 서명하므로 그 일치로 갈음한다."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT doc_id, team_id, proj_id, file_name, mime_type, storage_key,
                           cur_revision, deleted, access_revoked
                    FROM doc WHERE doc_id = %s
                    """,
                    (doc_id,),
                )
                row = cursor.fetchone()
        if row is None:
            raise RecordNotFound(f"존재하지 않는 문서입니다: {doc_id}")
        if row["deleted"] or row["access_revoked"]:
            raise PermissionDenied("삭제되었거나 접근이 철회된 문서입니다.")
        if row["cur_revision"] != revision or not row["storage_key"]:
            raise RecordNotFound("서명된 revision의 원문을 찾을 수 없습니다.")
        return row

    @staticmethod
    def list_team_documents(account_id: str) -> list[dict[str, Any]]:
        """기준 문서 선택 화면이 고를 수 있는 후보 — 팀 문서 전부.

        `proj_id`와 `doc_role`을 함께 준다. 이미 이 팀의 다른 프로젝트에 메인 문서로
        잡혀 있는지를 화면이 알아야 같은 문서를 두 번 기준으로 삼지 않는다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                cursor.execute(
                    f"""
                    SELECT d.doc_id, d.proj_id, d.doc_role, d.file_name, d.mime_type,
                           d.storage_key, d.cur_revision, d.src_modified_at,
                           {_SEARCH_READY}
                    FROM doc d
                    WHERE d.team_id = %s AND d.deleted = false AND d.access_revoked = false
                    ORDER BY d.doc_id
                    """,
                    (team_id,),
                )
                return list(cursor.fetchall())

    @staticmethod
    def searchable_doc_ids(team_id: str) -> list[str]:
        """`document_search` 도구가 훑을 범위 — 팀 문서 전부.

        `team_id`를 직접 받는다. 다른 메서드들처럼 `account_id`로 팀을 물을 수
        없어서다 — Harness 의 `run_agent` 는 대화·요청자에 종속되지 않는 순수
        함수라(A2A 대비) 팀만 알고 계정은 모른다.

        `_SEARCH_READY`로 다시 거르지 않는다. 벡터 검색이 이미 활성 chunk·vec_idx
        만 보므로 색인 안 된 문서는 결과에 나올 수 없고, 여기서 한 번 더 판정하면
        같은 규칙이 두 곳에 생긴다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT doc_id FROM doc
                    WHERE team_id = %s AND deleted = false AND access_revoked = false
                    ORDER BY doc_id
                    """,
                    (team_id,),
                )
                return [row["doc_id"] for row in cursor.fetchall()]

    @staticmethod
    def list_ready_for_analysis(*, proj_id: str, account_id: str) -> list[dict[str, Any]]:
        """업무 추출이 검색할 범위 — **팀 문서 전체**.

        사람은 기준 문서 하나만 고른다. 어느 문서가 근거인지는 에이전트가 검색으로
        찾는다(2026-08-04). 예전에는 근거 문서도 사람이 체크해서 넘겼는데, 그러려면
        무엇이 어디 적혀 있는지 미리 알아야 한다 — 그걸 대신 찾아 주는 것이 이
        기능의 목적이라 순서가 거꾸로였다.

        `proj_id`는 권한 확인에만 쓴다. 범위를 프로젝트로 좁히면 방금 만든 DRAFT에
        묶인 문서가 기준 문서 하나뿐이라 1단계와 2~4단계 검색이 같아진다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team_project(cursor, proj_id=proj_id, account_id=account_id)
                cursor.execute(
                    f"""
                    SELECT d.doc_id, d.team_id, d.proj_id, d.doc_role, d.file_name, d.mime_type,
                           d.storage_key, d.cur_revision, {_SEARCH_READY}
                    FROM doc d
                    WHERE d.team_id = %s AND d.deleted = false AND d.access_revoked = false
                    ORDER BY d.doc_id
                    """,
                    (team_id,),
                )
                return list(cursor.fetchall())

    @staticmethod
    def set_primary_document(
        *, proj_id: str, account_id: str, primary_doc_id: str | None
    ) -> dict[str, Any]:
        """기준 문서를 정한다. **이 행위가 프로젝트에 문서를 묶는다.**

        묶이는 문서는 기준 문서 하나뿐이다. 근거 문서는 에이전트가 팀 문서에서
        검색으로 찾으므로 프로젝트에 묶지 않는다 — 같은 회의록이 여러 프로젝트의
        근거가 될 수 있는데 `doc.proj_id`는 하나만 가리킬 수 있다.

        **`None` 이면 해제다.** 잘못 고른 것을 되돌릴 자리가 없으면, 맞는 문서가
        아직 없는 프로젝트는 틀린 기준 문서를 달고 있는 수밖에 없다 — 그 상태로
        업무를 뽑으면 엉뚱한 업무가 등록된다(2026-08-12 실제로 그렇게 됐다).
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team_project(cursor, proj_id=proj_id, account_id=account_id)

                if primary_doc_id is not None:
                    cursor.execute(
                        """
                        SELECT doc_id FROM doc
                        WHERE doc_id = %s AND team_id = %s
                          AND deleted = false AND access_revoked = false
                        """,
                        (primary_doc_id, team_id),
                    )
                    if cursor.fetchone() is None:
                        raise RecordNotFound(f"팀 문서에서 찾을 수 없습니다: {primary_doc_id}")

                # 이 프로젝트에 물려 있던 것을 먼저 풀어 팀 문서 풀로 돌려보낸다.
                # 기준 문서를 바꾸면 이전 것은 다시 아무 프로젝트의 것도 아니다.
                cursor.execute(
                    "UPDATE doc SET proj_id = NULL, doc_role = NULL WHERE proj_id = %s",
                    (proj_id,),
                )
                if primary_doc_id is not None:
                    cursor.execute(
                        "UPDATE doc SET proj_id = %s, doc_role = 'PRIMARY' WHERE doc_id = %s",
                        (proj_id, primary_doc_id),
                    )
        return {"primary_doc_id": primary_doc_id}

    @staticmethod
    def ingest(*, expected_doc: dict[str, Any], result: dict[str, Any]) -> dict[str, int]:
        if result.get("doc_id") != expected_doc["doc_id"]:
            raise ValueError("RunPod 결과의 doc_id가 요청과 다릅니다.")
        if result.get("revision") != expected_doc["cur_revision"]:
            raise ValueError("RunPod 결과의 revision이 현재 문서와 다릅니다.")
        if result.get("embedding_dimension") != 768:
            raise ValueError("RunPod 결과 embedding_dimension은 768이어야 합니다.")
        if result.get("embedding_model") != "google/embeddinggemma-300m":
            raise ValueError("RunPod 결과 임베딩 모델이 프로젝트 설정과 다릅니다.")
        if not (result.get("validation") or {}).get("passed"):
            raise ValueError("RunPod 청킹 검증을 통과하지 못했습니다.")
        blocks, chunks = result.get("blocks"), result.get("chunks")
        if not isinstance(blocks, list) or not blocks or not isinstance(chunks, list) or not chunks:
            raise ValueError("RunPod 결과에 blocks/chunks가 없습니다.")

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT cur_revision, content_hash FROM doc
                    WHERE doc_id = %s AND deleted = false AND access_revoked = false
                    FOR UPDATE
                    """,
                    (expected_doc["doc_id"],),
                )
                current = cursor.fetchone()
                if current is None or current["cur_revision"] != result["revision"]:
                    raise ValueError("처리 중 문서 revision이 변경되었습니다.")
                if current["content_hash"] and result.get("content_hash") != current["content_hash"]:
                    raise ValueError("RunPod가 받은 원문의 content hash가 로컬 원문과 다릅니다.")

                # The browser can repeat the final poll. A completed job must not
                # replace UUIDs every time the same result is observed.
                cursor.execute(
                    """
                    SELECT count(DISTINCT b.block_id) AS blocks,
                           count(DISTINCT c.chunk_id) AS chunks,
                           count(DISTINCT v.chunk_id) AS vectors
                    FROM doc_block b
                    LEFT JOIN chunk c ON c.block_id = b.block_id AND c.is_active = true
                    LEFT JOIN vec_idx v ON v.chunk_id = c.chunk_id AND v.is_active = true
                    WHERE b.doc_id = %s AND b.revision = %s
                      AND v.content_hash = %s AND v.embed_model = %s AND v.embed_dim = 768
                    """,
                    (
                        expected_doc["doc_id"], result["revision"], result.get("content_hash"),
                        result["embedding_model"],
                    ),
                )
                existing = cursor.fetchone()
                if existing and existing["chunks"] == len(chunks) and existing["vectors"] == len(chunks):
                    return {
                        "blocks": existing["blocks"],
                        "chunks": existing["chunks"],
                        "vectors": existing["vectors"],
                    }

                cursor.execute(
                    """DELETE FROM vec_idx WHERE chunk_id IN (
                        SELECT c.chunk_id FROM chunk c JOIN doc_block b ON b.block_id = c.block_id
                        WHERE b.doc_id = %s
                    )""",
                    (expected_doc["doc_id"],),
                )
                cursor.execute(
                    "DELETE FROM chunk WHERE block_id IN (SELECT block_id FROM doc_block WHERE doc_id = %s)",
                    (expected_doc["doc_id"],),
                )
                cursor.execute("DELETE FROM doc_block WHERE doc_id = %s", (expected_doc["doc_id"],))

                block_ids = {}
                for block in blocks:
                    key = block.get("local_block_key")
                    if not key or key in block_ids:
                        raise ValueError("중복되거나 비어 있는 local_block_key입니다.")
                    block_id = uuid4()
                    block_ids[key] = block_id
                    cursor.execute(
                        """
                        INSERT INTO doc_block
                            (block_id, doc_id, block_type, page, heading_path, content,
                             sequence, revision, src_locator, struct_content)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            block_id, expected_doc["doc_id"], block["block_type"], block.get("page"),
                            block.get("heading_path") or [], block["content"], block["sequence"],
                            result["revision"], Jsonb(block.get("src_locator") or {}),
                            Jsonb(block["struct_content"]) if block.get("struct_content") is not None else None,
                        ),
                    )

                for index, chunk in enumerate(chunks):
                    if chunk.get("sequence") != index:
                        raise ValueError("Chunk sequence가 0부터 연속적이지 않습니다.")
                    vector = chunk.get("embedding")
                    if not isinstance(vector, list) or len(vector) != 768:
                        raise ValueError("모든 Chunk embedding은 768차원이어야 합니다.")
                    block_id = block_ids.get(chunk.get("local_block_key"))
                    if block_id is None:
                        raise ValueError("Chunk가 알 수 없는 local_block_key를 참조합니다.")
                    chunk_id = uuid4()
                    cursor.execute(
                        """
                        INSERT INTO chunk
                            (chunk_id, block_id, search_text, chunk_idx, token_cnt,
                             heading_path, chunker_ver)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            chunk_id, block_id, chunk["text"], index, chunk["token_count"],
                            (chunk.get("meta") or {}).get("headings") or [], result["chunker_version"],
                        ),
                    )
                    vector_literal = "[" + ",".join(repr(float(x)) for x in vector) + "]"
                    metadata = {
                        "doc_id": expected_doc["doc_id"],
                        "source_refs": chunk.get("source_refs") or [],
                        "pages": chunk.get("pages") or [],
                        "chunk_type": chunk.get("chunk_type"),
                        "chunk_meta": chunk.get("meta") or {},
                    }
                    cursor.execute(
                        """
                        INSERT INTO vec_idx
                            (chunk_id, embedding, metadata, embed_model, embed_ver,
                             embed_dim, content_hash, revision)
                        VALUES (%s, %s::vector, %s, %s, %s, 768, %s, %s)
                        """,
                        (
                            chunk_id, vector_literal, Jsonb(metadata), result["embedding_model"],
                            result["embedding_model"], result.get("content_hash"), result["revision"],
                        ),
                    )
        return {"blocks": len(blocks), "chunks": len(chunks), "vectors": len(chunks)}


def vector_literal(vector: list[float]) -> str:
    if len(vector) != 768:
        raise ValueError("검색 vector는 768차원이어야 합니다.")
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


class VectorSearchRepository:
    @staticmethod
    def search(*, team_id: str, document_ids: list[str], query_vector: list[float], top_k: int) -> list[dict]:
        """`document_ids`는 호출자가 `list_ready_for_analysis`로 서버에서 확인한
        범위다. `team_id` 조건을 함께 거는 것은 그 목록이 어떤 경로로든 오염됐을 때
        다른 팀 문장이 근거로 섞이지 않게 하는 두 번째 자물쇠다.

        경계는 프로젝트가 아니라 **팀**이다. 근거는 팀 문서 전체에서 찾으므로
        프로젝트로 거는 자물쇠는 잠글 것이 없다."""

        if not document_ids:
            raise ValueError("검색 문서 범위가 비어 있습니다.")
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    -- `v.metadata` 는 안 읽는다(2026-08-05). bbox 좌표·binary_hash·
                    -- 임시 파일명이 들어 있어 평균 927자·최대 7,622자인데, 모델도
                    -- 화면도 쓰지 않으면서 프롬프트와 응답을 그만큼 불린다.
                    SELECT d.doc_id, c.chunk_id::text, c.chunk_idx AS sequence,
                           c.search_text AS text, c.heading_path,
                           1 - (v.embedding <=> %s::vector) AS retrieval_score
                    FROM vec_idx v
                    JOIN chunk c ON c.chunk_id = v.chunk_id
                    JOIN doc_block b ON b.block_id = c.block_id
                    JOIN doc d ON d.doc_id = b.doc_id
                    WHERE d.team_id = %s
                      AND d.doc_id = ANY(%s)
                      AND d.deleted = false AND d.access_revoked = false
                      AND c.is_active = true AND v.is_active = true
                      AND v.embed_model = %s AND v.embed_dim = 768
                    ORDER BY v.embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (
                        vector_literal(query_vector), team_id, document_ids,
                        "google/embeddinggemma-300m", vector_literal(query_vector), top_k,
                    ),
                )
                return list(cursor.fetchall())


#: 질의 앵커로 넘길 첫머리 길이. 개요·사업범위가 들어갈 만큼이면 된다.
OUTLINE_MAX_CHARS = 1500


def document_outline(doc_id: str, *, limit: int = 12) -> str:
    """문서 앞부분 청크를 이어 붙인다. 이 문서가 무엇에 관한 것인지 알려 준다.

    질의 생성 에이전트에 파일명만 주면 주제를 모른 채 「사업 수행 범위에 포함된
    업무 영역」 같은 일반 사업관리 문장을 만든다. 그런 벡터는 실제 과업이 아니라
    관리 보일러플레이트와 가장 가깝고, 실제로 실행 과업이 한 건도 안 잡힌 적이
    있다(2026-08-05). 문서가 무엇에 대한 것인지는 대개 첫머리에 적혀 있다.

    검색이 아니라 순서대로 읽는다 — 앵커는 질의보다 먼저 필요하다.
    """

    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT c.search_text
                FROM chunk c
                JOIN doc_block b ON b.block_id = c.block_id
                JOIN doc d ON d.doc_id = b.doc_id AND b.revision = d.cur_revision
                WHERE b.doc_id = %s AND c.is_active = true
                ORDER BY b.block_id, c.chunk_idx
                LIMIT %s
                """,
                (doc_id, limit),
            )
            rows = cursor.fetchall()

    outline = "\n".join((row["search_text"] or "").strip() for row in rows)
    return outline[:OUTLINE_MAX_CHARS]


class DocMetaRepository:
    """`doc_meta` — 문서 하나당 한 줄. A안의 coarse 단계가 읽는다(8/11 확정 ⑥)."""

    @staticmethod
    def upsert(row: dict[str, Any]) -> None:
        """다시 만들면 덮어쓴다. 문서가 개정되면 요약도 낡기 때문이다.

        추출에 실패한 문서도 행을 남긴다 — 안 남기면 왜 검색에 안 걸리는지
        화면이 말할 수 없고, 매번 다시 시도하게 된다.
        """

        vector = row.get("summary_vec")
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO doc_meta (doc_id, summary, doc_type, keywords, summary_vec,
                                          extracted_text, extract_status, extracted_at)
                    VALUES (%s, %s, %s, %s, %s::vector, %s, %s, now())
                    ON CONFLICT (doc_id) DO UPDATE SET
                        summary = EXCLUDED.summary,
                        doc_type = EXCLUDED.doc_type,
                        keywords = EXCLUDED.keywords,
                        summary_vec = EXCLUDED.summary_vec,
                        extracted_text = EXCLUDED.extracted_text,
                        extract_status = EXCLUDED.extract_status,
                        extracted_at = now()
                    """,
                    (
                        row["doc_id"], row.get("summary"), row.get("doc_type"),
                        row.get("keywords") or [],
                        vector_literal(vector) if vector else None,
                        row.get("extracted_text"), row["extract_status"],
                    ),
                )

    @staticmethod
    def purge(doc_ids: list[str]) -> int:
        """이 문서들의 메타를 지운다. **새 문서를 등록할 때 부른다.**

        `doc_meta` 는 `doc` 을 FK 로 걸지 않아서 `doc` 행이 사라져도 살아남는다.
        그런데 `doc_id` 는 `DC001` 부터 다시 나눠 주므로, 새 문서가 지워진 문서의
        id 를 물려받으면 **남의 요약을 자기 것으로 쓴다** — 요약 임베딩으로
        후보를 좁히는 구조라, 엉뚱한 문서가 근거 후보로 올라온다.

        실제로 겪었다: 8/11 문서를 지우고 `doc_meta` 3건이 남아 있었는데,
        8/15 에 새로 등록한 문서가 그 id 를 받아 「이미 요약된 문서」로 취급됐다.
        """

        if not doc_ids:
            return 0
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM doc_meta WHERE doc_id = ANY(%s)", (doc_ids,))
                return cursor.rowcount

    @staticmethod
    def pending_doc_ids(team_id: str) -> list[str]:
        """아직 메타가 없고 원문은 받아 둔 팀 문서.

        `storage_key` 가 있어야 한다 — 원문이 없으면 CPU 추출을 할 수 없다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT d.doc_id
                    FROM doc d
                    LEFT JOIN doc_meta m ON m.doc_id = d.doc_id
                    WHERE d.team_id = %s AND d.deleted = false AND d.access_revoked = false
                      AND d.storage_key IS NOT NULL AND m.doc_id IS NULL
                    ORDER BY d.doc_id
                    """,
                    (team_id,),
                )
                return [row["doc_id"] for row in cursor.fetchall()]

    @staticmethod
    def coarse_search(*, team_id: str, query_vector: list[float], top_n: int) -> list[dict[str, Any]]:
        """요약 임베딩으로 **문서**를 좁힌다. 청크 검색의 앞단이다.

        `search_ready` 를 함께 준다 — 후보로 뽑혔지만 아직 청크가 없는 문서를
        호출자가 알아야 한다. 그 문서는 요약만 있고 본문 근거를 낼 수 없다.

        추출 실패(FAILED·UNSUPPORTED) 문서는 요약 벡터가 없어 자연히 빠진다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT d.doc_id, d.file_name, m.summary, m.doc_type, m.keywords,
                           1 - (m.summary_vec <=> %s::vector) AS summary_score,
                           {_SEARCH_READY}
                    FROM doc_meta m
                    JOIN doc d ON d.doc_id = m.doc_id
                    WHERE d.team_id = %s AND d.deleted = false AND d.access_revoked = false
                      AND m.summary_vec IS NOT NULL
                    ORDER BY m.summary_vec <=> %s::vector
                    LIMIT %s
                    """,
                    (
                        vector_literal(query_vector), team_id,
                        vector_literal(query_vector), top_n,
                    ),
                )
                return list(cursor.fetchall())


    @staticmethod
    def list_with_meta(account_id: str) -> list[dict[str, Any]]:
        """문서 화면 목록 — `doc` + `doc_meta` + 색인 여부.

        **상태를 하나로 뭉개지 않는다.** 「메타가 없다」·「추출에 실패했다」·
        「형식을 지원하지 않는다」·「본문까지 색인됐다」는 사람이 할 행동이 각각
        다르다 — 순서대로 처리 요청 / 재시도 / 포기 / 없음이다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                cursor.execute(
                    f"""
                    SELECT d.doc_id, d.file_name, d.mime_type, d.proj_id, d.doc_role,
                           d.src_modified_at, d.storage_key,
                           m.summary, m.doc_type, m.keywords, m.extract_status,
                           m.extracted_at, {_SEARCH_READY}
                    FROM doc AS d
                    LEFT JOIN doc_meta AS m ON m.doc_id = d.doc_id
                    WHERE d.team_id = %s AND d.deleted = false AND d.access_revoked = false
                    ORDER BY d.src_modified_at DESC NULLS LAST, d.doc_id
                    """,
                    (team_id,),
                )
                return list(cursor.fetchall())

    @staticmethod
    def list_removed(account_id: str) -> list[dict[str, Any]]:
        """Drive 에서 사라져 내려간 문서. 화면이 「정리된 파일」로 보여준다."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                cursor.execute(
                    """
                    SELECT doc_id, file_name, src_modified_at
                    FROM doc
                    WHERE team_id = %s AND deleted = true
                    ORDER BY doc_id
                    """,
                    (team_id,),
                )
                return list(cursor.fetchall())

    @staticmethod
    def status_counts(team_id: str) -> dict[str, int]:
        """화면이 "몇 건이 왜 검색 대상이 아닌가"를 말할 수 있게."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT m.extract_status, count(*) AS n
                    FROM doc_meta m JOIN doc d ON d.doc_id = m.doc_id
                    WHERE d.team_id = %s AND d.deleted = false
                    GROUP BY m.extract_status
                    """,
                    (team_id,),
                )
                return {row["extract_status"]: row["n"] for row in cursor.fetchall()}
