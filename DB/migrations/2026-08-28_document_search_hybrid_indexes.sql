-- document_search 하이브리드 검색용 확장과 lexical 인덱스.
-- raw_text 컬럼은 추가하지 않는다. 청킹 문맥이 붙은 search_text가 검색 대상이고,
-- 실제 근거 본문은 이미 보관 중인 doc_block.content를 사용한다.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_chunk_search_text_fts
    ON chunk USING GIN (to_tsvector('simple', search_text));

CREATE INDEX IF NOT EXISTS idx_chunk_search_text_trgm
    ON chunk USING GIN (search_text gin_trgm_ops);
