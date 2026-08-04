-- =====================================================================
-- 2026-08-04 | doc.doc_role 을 문서 「종류」에서 프로젝트와의 「관계」로
--
-- 왜: doc_role 은 폴더에 준 역할을 안의 파일이 물려받는 값이었다. 그래서
--     「01_기획」 폴더에 든 것은 요구사항 정의서든 화면설계서든 전부 'PLAN' 이
--     됐다(실측 3건 중 2건 오분류). 등록 뒤에 고칠 API 도 화면도 없었다.
--     그런데 이 값으로 분기하는 코드는 백엔드·프론트·파이프라인 어디에도
--     한 줄이 없었다 — 아무도 안 쓰는 값을 부정확하게 채우고 있었던 셈이다.
--
--     어느 문서가 업무의 근거인지는 기준 문서 선택 화면에서 사람이 고른다.
--     그 결정을 담을 자리가 필요했고, 마침 비는 이 컬럼을 쓴다. 새 컬럼을
--     만들지 않는다.
--
--       NULL      아직 어느 프로젝트에도 안 묶인 팀 문서 풀
--       'PRIMARY' 업무를 뽑아낼 기준 문서. 프로젝트당 하나
--       'SUB'     근거 검색에 함께 쓰는 문서
--
-- 실행 위치: DBeaver, 대상 DB의 public 스키마
-- 전제: 없다.
--
-- 옛 값('PLAN'/'MEETING_NOTE'/'DAILY_REPORT'/'OTHER')은 지운다. 새 의미에서
-- 읽으면 거짓말이 되고, 어차피 전부 proj_id 가 NULL 이라 「팀 문서 풀」이
-- 맞다. 컬럼 자체는 남기므로 되돌릴 일이 있으면 역할을 다시 지정하면 된다.
-- =====================================================================

BEGIN;

UPDATE doc
   SET doc_role = NULL
 WHERE doc_role IN ('PLAN', 'MEETING_NOTE', 'DAILY_REPORT', 'OTHER');

-- 폴더에 물려줄 종류가 없어졌다. 폴더는 이제 파일이 어디 있는지만 알려준다.
UPDATE team_folder SET default_doc_role = NULL WHERE default_doc_role IS NOT NULL;

-- 기준 문서는 프로젝트당 하나. 화면이 라디오라 둘이 될 일이 없어 보여도, 두 건이
-- 되면 어느 것으로 업무를 뽑았는지 알 수 없어 조용히 틀린다.
CREATE UNIQUE INDEX IF NOT EXISTS ux_doc_primary_per_proj
    ON doc (proj_id) WHERE doc_role = 'PRIMARY' AND deleted = false;

COMMIT;


-- =====================================================================
-- 확인용 — COMMIT 뒤에 따로 실행
-- =====================================================================
-- SELECT doc_role, count(*) FROM doc WHERE deleted = false GROUP BY doc_role;
--   전부 NULL 이면 정상이다. 기준 문서를 고르면 PRIMARY/SUB 가 생긴다.
--
-- SELECT indexname FROM pg_indexes WHERE indexname = 'ux_doc_primary_per_proj';
--   한 줄 나오면 정상이다.
