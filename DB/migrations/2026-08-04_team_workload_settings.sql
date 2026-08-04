-- =====================================================================
-- 2026-08-04 | team 에 업무량 기준 3개 추가
--
-- 왜: 설정의 「팀 업무량 기준」이 화면에만 있고 저장되지 않았다. 주 근무시간
--     40·과부하 110%·기본 8시간이 로컬 상태였고 「저장」은 토스트만 띄웠다.
--     계산은 그 값들을 보지도 않았다.
--
-- 셋 다 NULL 이 기본이고 "설정 안 함"을 뜻한다.
--   capacity_wk_hours NULL → HR 의 사람별 주 근무시간을 그대로 쓴다
--   overload_pct      NULL → 100%
--   workload_weeks    NULL → 4주
--
-- HR 값을 복사해 두지 않는다. 복사하면 HR 이 바뀌었을 때 우리 사본이 조용히
-- 낡고, 화면은 낡은 값을 "현재 기준"이라고 말하게 된다.
--
-- 실행 위치: DBeaver, 대상 DB의 public 스키마
-- 전제: team 테이블이 있어야 한다(2026-07-31 추가분).
-- =====================================================================

BEGIN;

ALTER TABLE team ADD COLUMN capacity_wk_hours NUMERIC(5,2);
ALTER TABLE team ADD COLUMN overload_pct      INT;
ALTER TABLE team ADD COLUMN workload_weeks    INT;

COMMIT;


-- =====================================================================
-- 확인용 — COMMIT 뒤에 따로 실행
-- =====================================================================
-- SELECT team_id, name, capacity_wk_hours, overload_pct, workload_weeks FROM team;
--   전부 NULL 이면 정상이다. 설정 화면에서 정하면 채워진다.
