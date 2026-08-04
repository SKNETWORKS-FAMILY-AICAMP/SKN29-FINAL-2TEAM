-- =====================================================================
-- 2026-08-04 | proj 에 생성 시각 추가
--
-- 왜: 프로젝트 목록의 "최신순" 정렬과 날짜 열이 근거로 삼을 값이 없었다.
--     proj 는 proj_id · name · status · tz · owner_account_id 뿐이고,
--     audit_log 에도 PROJECT_CREATE 가 없어 되짚을 방법도 없었다.
--     폴더를 고르는 행위가 프로젝트를 만드는 것이라, 그 시점이 곧 생성 시각이다.
--
-- 실행 위치: DBeaver, 대상 DB의 public 스키마
-- 전제: 없다.
--
-- ⚠ 기본값을 나중에 거는 이유:
--     ADD COLUMN 에 DEFAULT 를 함께 주면 Postgres 가 **기존 행까지** 그 값으로
--     채운다. 그러면 예전에 만든 프로젝트가 "오늘 만들어진 것"이 되어, 모르는
--     날짜를 지어내는 꼴이 된다. 컬럼을 먼저 NULL 로 붙이고 기본값을 그 뒤에
--     걸면 기존 행은 NULL 로 남고 새 행만 now() 를 받는다.
-- =====================================================================

BEGIN;

ALTER TABLE proj
    ADD COLUMN created_at TIMESTAMPTZ;

ALTER TABLE proj
    ALTER COLUMN created_at SET DEFAULT now();

COMMIT;


-- =====================================================================
-- 확인용 — COMMIT 뒤에 따로 실행
-- =====================================================================
-- SELECT proj_id, name, status, created_at FROM proj ORDER BY proj_id;
--   기존 행은 created_at 이 NULL 이면 정상이다.
