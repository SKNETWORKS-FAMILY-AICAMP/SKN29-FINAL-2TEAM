from __future__ import annotations

import hashlib
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
    def list_ready_for_analysis(*, proj_id: str, account_id: str) -> list[dict[str, Any]]:
        """업무 추출이 검색할 범위 — 이 프로젝트에 묶인 문서(메인+서브)."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                _require_team_project(cursor, proj_id=proj_id, account_id=account_id)
                cursor.execute(
                    f"""
                    SELECT d.doc_id, d.proj_id, d.doc_role, d.file_name, d.mime_type,
                           d.storage_key, d.cur_revision, {_SEARCH_READY}
                    FROM doc d
                    WHERE d.proj_id = %s AND d.deleted = false AND d.access_revoked = false
                    ORDER BY d.doc_id
                    """,
                    (proj_id,),
                )
                return list(cursor.fetchall())

    @staticmethod
    def set_project_documents(
        *, proj_id: str, account_id: str, primary_doc_id: str, sub_doc_ids: list[str]
    ) -> dict[str, Any]:
        """기준 문서 선택을 저장한다. **이 행위가 프로젝트에 문서를 묶는다.**

        전부 교체한다. 화면은 언제나 전체 선택 상태를 보내므로, 덧붙이면 화면에서
        해제한 문서가 프로젝트에 남는다.
        """

        if primary_doc_id in sub_doc_ids:
            raise ValueError("기준 문서를 서브 문서로 함께 지정할 수 없습니다.")

        wanted = [primary_doc_id, *sub_doc_ids]
        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team_project(cursor, proj_id=proj_id, account_id=account_id)

                cursor.execute(
                    """
                    SELECT doc_id FROM doc
                    WHERE doc_id = ANY(%s) AND team_id = %s
                      AND deleted = false AND access_revoked = false
                    """,
                    (wanted, team_id),
                )
                found = {row["doc_id"] for row in cursor.fetchall()}
                missing = [d for d in wanted if d not in found]
                if missing:
                    raise RecordNotFound(f"팀 문서에서 찾을 수 없습니다: {', '.join(missing)}")

                # 이 프로젝트에 물려 있던 것을 먼저 풀어 팀 문서 풀로 돌려보낸다.
                cursor.execute(
                    "UPDATE doc SET proj_id = NULL, doc_role = NULL WHERE proj_id = %s",
                    (proj_id,),
                )
                cursor.execute(
                    "UPDATE doc SET proj_id = %s, doc_role = 'PRIMARY' WHERE doc_id = %s",
                    (proj_id, primary_doc_id),
                )
                if sub_doc_ids:
                    cursor.execute(
                        "UPDATE doc SET proj_id = %s, doc_role = 'SUB' WHERE doc_id = ANY(%s)",
                        (proj_id, sub_doc_ids),
                    )
        return {"primary_doc_id": primary_doc_id, "sub_doc_ids": sub_doc_ids}

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
    def search(*, proj_id: str, document_ids: list[str], query_vector: list[float], top_k: int) -> list[dict]:
        """`document_ids`는 호출자가 `list_ready_for_analysis`로 서버에서 확인한
        범위다. `proj_id` 조건을 함께 거는 것은 그 목록이 어떤 경로로든 오염됐을 때
        다른 프로젝트 문장이 근거로 섞이지 않게 하는 두 번째 자물쇠다."""

        if not document_ids:
            raise ValueError("검색 문서 범위가 비어 있습니다.")
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT d.doc_id, c.chunk_id::text, c.chunk_idx AS sequence,
                           c.search_text AS text, c.heading_path, v.metadata,
                           1 - (v.embedding <=> %s::vector) AS retrieval_score
                    FROM vec_idx v
                    JOIN chunk c ON c.chunk_id = v.chunk_id
                    JOIN doc_block b ON b.block_id = c.block_id
                    JOIN doc d ON d.doc_id = b.doc_id
                    WHERE d.proj_id = %s
                      AND d.doc_id = ANY(%s)
                      AND d.deleted = false AND d.access_revoked = false
                      AND c.is_active = true AND v.is_active = true
                      AND v.embed_model = %s AND v.embed_dim = 768
                    ORDER BY v.embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (
                        vector_literal(query_vector), proj_id, document_ids,
                        "google/embeddinggemma-300m", vector_literal(query_vector), top_k,
                    ),
                )
                return list(cursor.fetchall())
