-- =====================================================================
-- 2026-08-03 | exist_task 에 소스 연결과 추정치 추가
--
-- 왜: exist_task 에 소유 관계를 나타내는 컬럼이 하나도 없었다. 어느 프로젝트
--     것인지도, 어느 계정 것인지도 모르는 채로 쌓이는 구조라
--       - 재동기화 때 지울 범위를 특정할 수 없고
--       - "임준의 부하 196h = KAN 144h + AIP 52h" 분해가 안 나온다
--     최초 1회 INSERT 는 되지만 두 번째부터 깨지는 상태였다.
--
-- 실행 위치: DBeaver, 대상 DB의 public 스키마
-- 전제: exist_task 가 비어 있어야 한다 (2026-08-03 기준 0행).
--       행이 있으면 1번의 NOT NULL 에서 실패한다 — 그때는 아래 주석 참고.
-- =====================================================================

BEGIN;

-- 0. 전제 확인. 0 이 아니면 여기서 멈추고 아래 대안을 쓴다.
SELECT count(*) AS exist_task_rows FROM exist_task;


-- 1. 어느 소스에서 온 이슈인가
--    proj_id 가 아니라 proj_source_id 다 — 프로젝트 하나가 Jira 프로젝트를
--    여러 개 읽을 수 있어서(N:M), 재동기화 범위의 실제 단위는 proj_source 다.
ALTER TABLE exist_task
    ADD COLUMN proj_source_id VARCHAR(5) NOT NULL;

--    [행이 이미 있는 경우의 대안]
--    ALTER TABLE exist_task ADD COLUMN proj_source_id VARCHAR(5);
--    UPDATE exist_task SET proj_source_id = '<채울 값>' WHERE proj_source_id IS NULL;
--    ALTER TABLE exist_task ALTER COLUMN proj_source_id SET NOT NULL;


-- 2. 최초 추정치. exist_task_snap.estimate 가 복사해 갈 원본이 없었다.
ALTER TABLE exist_task
    ADD COLUMN estimate NUMERIC(6,2);


-- 3. 중복 방지. 같은 소스의 같은 이슈가 두 줄이 되면 부하가 2배로 잡힌다.
CREATE UNIQUE INDEX ux_exist_task_source_issue
    ON exist_task (proj_source_id, jira_issue_id);


COMMIT;


-- =====================================================================
-- 확인용 — COMMIT 뒤에 따로 실행
-- =====================================================================
-- 컬럼이 붙었는지
-- SELECT column_name, data_type, is_nullable
-- FROM information_schema.columns
-- WHERE table_name = 'exist_task'
-- ORDER BY ordinal_position;
--
-- 인덱스가 생겼는지
-- SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'exist_task';
