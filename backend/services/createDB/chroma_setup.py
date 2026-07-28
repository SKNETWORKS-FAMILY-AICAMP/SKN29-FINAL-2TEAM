"""
ChromaDB 컬렉션 생성

실행 전: `docker compose -f infra/docker/docker-compose.yml up -d chroma` 로 Chroma 서버를 먼저 띄워둘 것.
    pip install chromadb --break-system-packages
"""

import chromadb

CHROMA_HOST = "localhost"
CHROMA_PORT = 8001

client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)


def collection_name(embed_ver: str) -> str:
    # 컬렉션 = "이 임베딩 버전으로 만든 청크들의 모음"
    return f"chunks_{embed_ver}"


def get_or_create_collection(embed_ver: str, dist_metric: str = "cosine"):
    """
    dist_metric은 Chroma에서 컬렉션 생성 시 한 번만 정할 수 있는 값이다
    (VEC_IDX.dist_metric은 행마다 저장하지만 실제로는 이 컬렉션 설정의
    스냅샷일 뿐이라는 점을 VectorDB_저장대상_검증.md 7.4에서 이미 정리했다).
    """
    return client.get_or_create_collection(
        name=collection_name(embed_ver),
        metadata={"hnsw:space": dist_metric},
    )


def upsert_chunk(collection, *, vec_id, chunk_id, doc_id, proj_id,
                  search_text, embedding, doc_role, security, file_name,
                  revision, content_hash, is_active=True):
    """
    page3-A_시나리오_기획서1건처리흐름.md 4단계에서 만든 예시 청크(CHK-018)를
    그대로 넣는다고 가정한 함수. metadata에는 acl_principals를 넣지 않는다
    (Chroma metadata는 배열을 지원하지 않음 — 7.3 참고, ACL 최종 검증은
    Postgres DOC.acl_principals JOIN으로 애플리케이션 레이어에서 처리).
    """
    collection.upsert(
        ids=[vec_id],
        embeddings=[embedding],
        documents=[search_text],  # Chroma는 검색 결과에 원문을 바로 돌려주기 위해 document를 따로 요구한다
        metadatas=[{
            "chunk_id": chunk_id,
            "doc_id": doc_id,
            "proj_id": proj_id,
            "doc_role": doc_role,
            "security": security,
            "file_name": file_name,
            "revision": revision,
            "content_hash": content_hash,
            "is_active": is_active,
        }],
    )


def search(collection, query_embedding, *, proj_id: str, security: str | None = None, top_k: int = 5):
    """
    1차 필터: proj_id(+선택적으로 security) — 여기까지가 Chroma의 역할.
    업무 관련성(semantic_type) 필터링은 여기서 하지 않고, 반환된 chunk_id들을
    Postgres에 다시 질의해서 CHUNK→KNOW_ITEM_SRC→KNOW_ITEM으로 JOIN한다
    (7.2 ① 방식 — 검색 후 필터).
    """
    where = {"proj_id": proj_id}
    if security:
        where["security"] = security
    return collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where,
    )


if __name__ == "__main__":
    col = get_or_create_collection(embed_ver="embed-1.0", dist_metric="cosine")

    # 예시: page3-A 시나리오 문서의 CHK-018 청크를 저장한다고 가정
    # (실제로는 embedding 모델 호출 결과를 넣는다 — 아래는 자리 표시용 더미 벡터)
    dummy_embedding = [0.0] * 1536

    upsert_chunk(
        col,
        vec_id="V-018",
        chunk_id="CHK-018",
        doc_id="D-001",
        proj_id="P-001",
        search_text="로그인 기능은 2026-08-06까지 완료. 담당자는 백엔드팀 김OO 대리.",
        embedding=dummy_embedding,
        doc_role="PROJECT_PLAN",
        security="Internal",
        file_name="2026_AI_Project.pdf",
        revision="v3",
        content_hash="sha256:chunk018...",
    )

    print(f"컬렉션 '{col.name}'에 저장 완료. 현재 문서 수: {col.count()}")