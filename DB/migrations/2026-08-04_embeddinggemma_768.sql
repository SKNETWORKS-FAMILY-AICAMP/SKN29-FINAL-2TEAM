-- =====================================================================
-- 2026-08-04 | vec_idx 를 EmbeddingGemma 768 차원으로, revision 컬럼 폭 통일
--
-- 왜(차원): 문서 파싱·임베딩 파이프라인이 google/embeddinggemma-300m 으로
--     확정됐다(768). 기존 1536 은 OpenAI text-embedding-3-small 을 전제한
--     값이라 맞지 않는다. 적재와 검색이 같은 모델을 써야 하므로 차원은 한
--     곳에서만 정해져야 한다.
--
-- 왜(revision): Drive 의 headRevisionId 가 실측 51 자다. doc.cur_revision 만
--     2026-07-31 에 VARCHAR(100) 으로 넓혀 두고 나머지를 안 건드려서, 원문은
--     받아지는데 파싱 결과를 적재할 때 터지는 상태였다. 같은 값을 담는 세
--     컬럼을 여기서 맞춘다.
--
-- 실행 위치: DBeaver, 대상 DB의 public 스키마
-- 전제: vec_idx 가 비어 있어야 한다(아래 설명 참고).
--
-- **기존 벡터를 변환하지 않는다.** 1536 차원 벡터를 768 로 자르거나 0 을
-- 채우면 값은 남지만 의미가 사라진다 — 검색이 조용히 엉뚱한 결과를 내는 쪽이
-- 그냥 실패하는 쪽보다 나쁘다. 행이 있으면 중단하니, 재임베딩할지 지울지를
-- 사람이 먼저 정하고 빈 테이블에서 실행한다.
--
-- 멱등이다. 이미 768 이면 행이 있어도 그냥 넘어간다.
-- =====================================================================

BEGIN;

DO $$
DECLARE current_dim INT;
BEGIN
    -- pgvector 는 차원을 atttypmod 에 그대로 넣는다(varchar 처럼 +4 가 아니다).
    SELECT atttypmod INTO current_dim
      FROM pg_attribute
     WHERE attrelid = 'vec_idx'::regclass AND attname = 'embedding';

    IF current_dim = 768 THEN
        RAISE NOTICE 'vec_idx.embedding 은 이미 768 차원이다. 건너뛴다.';
        RETURN;
    END IF;

    IF EXISTS (SELECT 1 FROM vec_idx) THEN
        RAISE EXCEPTION
            'vec_idx 에 % 행이 있다. 1536 차원 벡터를 768 로 안전하게 바꿀 수 '
            '없으므로 중단한다. 재임베딩하거나 DELETE FROM vec_idx 로 비운 뒤 '
            '다시 실행할 것.', (SELECT count(*) FROM vec_idx);
    END IF;

    ALTER TABLE vec_idx ALTER COLUMN embedding TYPE VECTOR(768);
END $$;

-- 폭을 넓히기만 하므로 데이터 손실이 없고, 이미 100 이면 아무 일도 안 일어난다.
ALTER TABLE doc_block ALTER COLUMN revision TYPE VARCHAR(100);
ALTER TABLE vec_idx   ALTER COLUMN revision TYPE VARCHAR(100);
ALTER TABLE doc_sync  ALTER COLUMN revision TYPE VARCHAR(100);

COMMIT;


-- =====================================================================
-- 확인용 — COMMIT 뒤에 따로 실행
-- =====================================================================
-- SELECT atttypmod AS dim FROM pg_attribute
--  WHERE attrelid = 'vec_idx'::regclass AND attname = 'embedding';
--   768 이면 정상이다.
--
-- SELECT table_name, column_name, character_maximum_length
--   FROM information_schema.columns
--  WHERE column_name IN ('revision', 'cur_revision')
--    AND table_schema = 'public'
--  ORDER BY table_name;
--   doc / doc_block / doc_sync / vec_idx 가 모두 100 이면 정상이다.


-- =====================================================================
-- 뒤따르는 영향
-- =====================================================================
-- backend/services/createDB/vec_idx_setup.py 는 1536 차원 데모 스크립트라 이
-- migration 뒤에는 실패한다. 새 파이프라인과 호환되지 않으니 실행하지 않는다.
-- (DB_시작_가이드 7장에 같은 내용을 적어 뒀다.)
