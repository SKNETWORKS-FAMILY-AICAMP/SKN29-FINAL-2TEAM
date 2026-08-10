-- 벡터DB 구축 결과서용 측정 스크립트
-- 실행:
--   docker compose -f infra/docker/docker-compose.yml exec -T db \
--     psql -U project_copilot -d project_copilot -f - < vectordb_measure.sql
-- 또는 파일을 컨테이너에 넣고:
--   docker compose -f infra/docker/docker-compose.yml exec db \
--     psql -U project_copilot -d project_copilot -f /tmp/vectordb_measure.sql

\timing on
\pset border 2

\echo '════════════════════════════════════════════════════════'
\echo ' 1. 적재 현황'
\echo '════════════════════════════════════════════════════════'

SELECT
    (SELECT count(*) FROM doc WHERE deleted = false)                       AS "문서(doc)",
    (SELECT count(*) FROM doc_block)                                       AS "블록(doc_block)",
    (SELECT count(*) FROM chunk WHERE is_active)                           AS "청크(chunk)",
    (SELECT count(*) FROM vec_idx WHERE is_active)                         AS "벡터(vec_idx)",
    (SELECT count(*) FROM chunk c
       WHERE c.is_active
         AND NOT EXISTS (SELECT 1 FROM vec_idx v WHERE v.chunk_id = c.chunk_id))
                                                                           AS "벡터_없는_청크";

\echo ''
\echo '-- 문서별 적재 --'
SELECT d.file_name                                   AS "문서명",
       d.mime_type                                   AS "형식",
       count(DISTINCT b.block_id)                    AS "블록",
       count(DISTINCT c.chunk_id)                    AS "청크",
       count(DISTINCT v.chunk_id)                    AS "벡터",
       pg_size_pretty(sum(length(c.search_text))::bigint) AS "본문크기"
FROM doc d
LEFT JOIN doc_block b ON b.doc_id = d.doc_id AND b.revision = d.cur_revision
LEFT JOIN chunk c     ON c.block_id = b.block_id AND c.is_active
LEFT JOIN vec_idx v   ON v.chunk_id = c.chunk_id AND v.is_active
WHERE d.deleted = false
GROUP BY d.doc_id, d.file_name, d.mime_type
ORDER BY 4 DESC NULLS LAST;

\echo ''
\echo '-- 블록 유형별 --'
SELECT block_type AS "블록유형", count(*) AS "건수",
       round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS "비율%"
FROM doc_block GROUP BY block_type ORDER BY 2 DESC;

\echo ''
\echo '════════════════════════════════════════════════════════'
\echo ' 2. 청킹 품질 (상한 512토큰)'
\echo '════════════════════════════════════════════════════════'

SELECT count(*)                                              AS "청크수",
       round(avg(token_cnt))                                 AS "평균토큰",
       min(token_cnt)                                        AS "최소",
       percentile_cont(0.5) WITHIN GROUP (ORDER BY token_cnt)::int AS "중앙값",
       percentile_cont(0.95) WITHIN GROUP (ORDER BY token_cnt)::int AS "p95",
       max(token_cnt)                                        AS "최대",
       count(*) FILTER (WHERE token_cnt > 512)               AS "상한초과",
       count(DISTINCT chunker_ver)                           AS "청커버전수"
FROM chunk WHERE is_active;

\echo ''
\echo '-- 토큰 구간 분포 --'
SELECT CASE WHEN token_cnt <  64 THEN 'a. 0-63'
            WHEN token_cnt < 128 THEN 'b. 64-127'
            WHEN token_cnt < 256 THEN 'c. 128-255'
            WHEN token_cnt < 384 THEN 'd. 256-383'
            WHEN token_cnt <= 512 THEN 'e. 384-512'
            ELSE 'f. 512 초과' END AS "구간",
       count(*) AS "청크수"
FROM chunk WHERE is_active GROUP BY 1 ORDER BY 1;

\echo ''
\echo '════════════════════════════════════════════════════════'
\echo ' 3. 벡터 규격 일관성'
\echo '════════════════════════════════════════════════════════'

SELECT embed_model AS "임베딩모델", embed_dim AS "차원", dist_metric AS "거리척도",
       count(*) AS "건수",
       count(*) FILTER (WHERE vector_dims(embedding) <> 768) AS "차원불일치",
       min(indexed_at)::date AS "최초적재", max(indexed_at)::date AS "최종적재"
FROM vec_idx WHERE is_active
GROUP BY 1,2,3 ORDER BY 4 DESC;

\echo ''
\echo '-- 인덱스 현황 (ANN 인덱스 유무 확인) --'
SELECT indexname AS "인덱스명", indexdef AS "정의"
FROM pg_indexes WHERE tablename IN ('vec_idx','chunk','doc_block');

\echo ''
\echo '-- 저장 용량 --'
SELECT relname AS "테이블", pg_size_pretty(pg_total_relation_size(relid)) AS "총크기"
FROM pg_catalog.pg_statio_user_tables
WHERE relname IN ('doc','doc_block','chunk','vec_idx') ORDER BY pg_total_relation_size(relid) DESC;

\echo ''
\echo '════════════════════════════════════════════════════════'
\echo ' 4. 검색 응답 속도 — 실제 벡터로 10회 반복'
\echo '════════════════════════════════════════════════════════'

-- 적재된 벡터 하나를 질의 벡터로 삼는다. 임베딩 서버를 깨우지 않고도
-- DB 검색 구간만 정확히 잰다(RunPod 임베딩 시간은 아래 5번에서 따로 다룬다).
CREATE TEMP TABLE _probe AS
SELECT embedding AS q FROM vec_idx WHERE is_active ORDER BY chunk_id LIMIT 1;

DO $$
DECLARE
    -- 변수명을 컬럼명(`q`)과 다르게 둔다. 같으면 PL/pgSQL 이
    -- "column reference q is ambiguous" 로 거부해 이 블록이 통째로 실패한다.
    qv vector(768);
    t0 timestamptz; t1 timestamptz;
    ms double precision;
    samples double precision[] := '{}';
    i int;
BEGIN
    SELECT q INTO qv FROM _probe;
    FOR i IN 1..10 LOOP
        t0 := clock_timestamp();
        PERFORM d.doc_id, c.chunk_id, c.search_text,
               1 - (v.embedding <=> qv) AS retrieval_score
        FROM vec_idx v
        JOIN chunk c     ON c.chunk_id = v.chunk_id
        JOIN doc_block b ON b.block_id = c.block_id
        JOIN doc d       ON d.doc_id = b.doc_id
        WHERE d.deleted = false AND d.access_revoked = false
          AND c.is_active AND v.is_active
          AND v.embed_model = 'google/embeddinggemma-300m' AND v.embed_dim = 768
        ORDER BY v.embedding <=> qv
        LIMIT 10;
        t1 := clock_timestamp();
        ms := extract(epoch FROM (t1 - t0)) * 1000;
        samples := samples || ms;
    END LOOP;
    RAISE NOTICE '검색 latency(ms) 10회: %', samples;
    RAISE NOTICE '  평균 %  최소 %  최대 %',
        round((SELECT avg(x) FROM unnest(samples) x)::numeric, 2),
        round((SELECT min(x) FROM unnest(samples) x)::numeric, 2),
        round((SELECT max(x) FROM unnest(samples) x)::numeric, 2);
END $$;

\echo ''
\echo '-- 실행 계획 (Seq Scan 인지 Index Scan 인지) --'
EXPLAIN (ANALYZE, BUFFERS, TIMING)
SELECT d.doc_id, c.chunk_id, 1 - (v.embedding <=> (SELECT q FROM _probe)) AS retrieval_score
FROM vec_idx v
JOIN chunk c     ON c.chunk_id = v.chunk_id
JOIN doc_block b ON b.block_id = c.block_id
JOIN doc d       ON d.doc_id = b.doc_id
WHERE d.deleted = false AND c.is_active AND v.is_active
ORDER BY v.embedding <=> (SELECT q FROM _probe)
LIMIT 10;

\echo ''
\echo '════════════════════════════════════════════════════════'
\echo ' 5. 유사도 점수 분포 — 상위 10건이 얼마나 변별되는가'
\echo '════════════════════════════════════════════════════════'

WITH ranked AS (
    SELECT 1 - (v.embedding <=> (SELECT q FROM _probe)) AS score,
           row_number() OVER (ORDER BY v.embedding <=> (SELECT q FROM _probe)) AS rk,
           left(c.search_text, 60) AS snippet
    FROM vec_idx v JOIN chunk c ON c.chunk_id = v.chunk_id
    WHERE v.is_active AND c.is_active
)
SELECT rk AS "순위", round(score::numeric, 4) AS "유사도", snippet AS "청크 앞부분"
FROM ranked WHERE rk <= 10 ORDER BY rk;

\echo ''
\echo '-- 전체 유사도 분포 (변별력 확인) --'
SELECT round(avg(s)::numeric,4) AS "평균", round(stddev(s)::numeric,4) AS "표준편차",
       round(min(s)::numeric,4) AS "최소", round(max(s)::numeric,4) AS "최대"
FROM (SELECT 1 - (v.embedding <=> (SELECT q FROM _probe)) AS s
      FROM vec_idx v WHERE v.is_active) x;

\echo ''
\echo '════════════════════════════════════════════════════════'
\echo ' 6. 운영 파이프라인 상태'
\echo '════════════════════════════════════════════════════════'

\echo '-- revision 정합성: 현재 revision 이 아닌 잔여 블록 --'
SELECT count(*) AS "스테일_블록"
FROM doc_block b JOIN doc d ON d.doc_id = b.doc_id
WHERE b.revision <> d.cur_revision;

\echo '-- 고아 레코드 (삭제 파이프라인 검증) --'
SELECT
  (SELECT count(*) FROM vec_idx v
     WHERE NOT EXISTS (SELECT 1 FROM chunk c WHERE c.chunk_id = v.chunk_id))     AS "고아_벡터",
  (SELECT count(*) FROM chunk c
     WHERE NOT EXISTS (SELECT 1 FROM doc_block b WHERE b.block_id = c.block_id)) AS "고아_청크",
  (SELECT count(*) FROM doc_block b
     WHERE NOT EXISTS (SELECT 1 FROM doc d WHERE d.doc_id = b.doc_id))           AS "고아_블록";

\echo '-- 검색 가능 상태 문서 (search_ready) --'
SELECT d.file_name AS "문서명",
       EXISTS (SELECT 1 FROM doc_block b
               JOIN chunk c   ON c.block_id = b.block_id AND c.is_active
               JOIN vec_idx v ON v.chunk_id = c.chunk_id AND v.is_active
               WHERE b.doc_id = d.doc_id AND b.revision = d.cur_revision) AS "검색가능"
FROM doc d WHERE d.deleted = false ORDER BY 2 DESC, 1;

\echo ''
\echo '════════════════════════════════════════════════════════'
\echo ' 측정 끝. 위 출력 전체를 그대로 복사해서 전달하면 됩니다.'
\echo '════════════════════════════════════════════════════════'
