-- =====================================================================
-- 2026-08-18 | 색인이 도는 중인지 실패했는지 (M④ 후속)
--
-- 왜: 「내 파일」을 올리면 요약 뒤에 청크 파싱·임베딩이 뒤에서 돈다. 그런데
--     **그 결과를 아무 데도 안 남겼다** — 실패해도 화면은 「본문 읽는 중」인
--     채로 영원히 있고, 느린 것과 죽은 것이 구분되지 않는다(2026-08-18 PM 지적).
--
-- `doc_meta.extract_status` 와 다르다. 그쪽은 **요약을 만들려고 텍스트를 뽑는**
-- 단계의 결과이고, 이 칸은 그 뒤 **청크·임베딩** 단계의 결과다. 둘은 따로
-- 실패한다 — 요약은 됐는데 색인만 못 하는 경우가 실제로 흔하다.
--
-- 실행 위치: DBeaver 또는 컨테이너에서 직접, 대상 DB 의 public 스키마
-- 전제: 2026-08-18_personal_documents.sql
-- =====================================================================

BEGIN;

-- RUNNING(도는 중) / FAILED(마지막 시도가 실패). NULL 은 둘 중 하나다 —
-- 아직 안 돌렸거나, 끝났거나. 끝난 것은 `search_ready`(청크가 있는지)가
-- 말해 주므로 값을 따로 두지 않는다.
ALTER TABLE doc
    ADD COLUMN IF NOT EXISTS index_status VARCHAR(20);

COMMENT ON COLUMN doc.index_status IS
    '청크 파싱·임베딩 단계의 상태. RUNNING / FAILED / NULL(안 돌렸거나 끝남). '
    'doc_meta.extract_status 와 다르다 — 그쪽은 요약용 텍스트 추출 단계다.';

COMMIT;


-- =====================================================================
-- 확인용 — COMMIT 뒤에 따로 실행
-- =====================================================================
-- SELECT column_name FROM information_schema.columns
--  WHERE table_name = 'doc' AND column_name = 'index_status';
--
-- SELECT index_status, count(*) FROM doc GROUP BY index_status;
--   기존 행은 전부 NULL 이어야 한다 — 커넥터 문서는 검색이 필요할 때 승격하고,
--   그 경로는 이 값을 안 쓴다.
