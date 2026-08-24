-- =====================================================================
-- 2026-08-24 | 색인이 왜 실패했는지 (요약 단계 제거의 후속)
--
-- 왜: 문서 요약(`doc_meta`)을 없앴다. 전량 색인이 붙으면서 요약으로 문서를
--     좁힐 이유가 사라졌기 때문인데, **실패 사유를 사람 말로 남기던 자리가
--     같이 사라진다.** `doc_meta.extract_detail` 이 「암호가 걸린 PDF 라 열 수
--     없습니다」 같은 문구를 담고 있었고 「내 파일」 화면이 그걸 보여 줬다.
--
--     색인 단계는 `index_status` 로 RUNNING/FAILED 만 남긴다 — 그대로 두면
--     사용자는 「실패했다」만 알고 **왜인지는 영영 모른다.** 그 상태는 이
--     저장소가 반복해서 거부해 온 것이다(「느린 것과 죽은 것이 구분되지
--     않는다」 — 2026-08-18_doc_index_status.sql).
--
-- 실행 위치: DBeaver 또는 컨테이너에서 직접, 대상 DB 의 public 스키마
-- 전제: 2026-08-18_doc_index_status.sql
-- =====================================================================

BEGIN;

-- 사람이 읽을 실패 사유. `index_status = 'FAILED'` 일 때만 채운다.
-- 성공하면 상태와 함께 NULL 로 되돌린다 — 옛 사유가 남아 있으면 다음 실패인지
-- 지난 실패인지 화면이 구분할 수 없다.
ALTER TABLE doc
    ADD COLUMN IF NOT EXISTS index_detail TEXT;

COMMENT ON COLUMN doc.index_detail IS
    '색인 실패 사유(사람이 읽을 문구). index_status = FAILED 일 때만 채운다. '
    '없앤 doc_meta.extract_detail 이 하던 역할을 색인 단계로 옮긴 것이다.';

COMMIT;


-- =====================================================================
-- 확인용 — COMMIT 뒤에 따로 실행
-- =====================================================================
-- SELECT column_name FROM information_schema.columns
--  WHERE table_name = 'doc' AND column_name = 'index_detail';
--
-- SELECT index_status, index_detail, count(*) FROM doc
--  GROUP BY index_status, index_detail;
--   기존 행은 전부 NULL 이어야 한다 — 지난 실패의 사유는 남아 있지 않다.
