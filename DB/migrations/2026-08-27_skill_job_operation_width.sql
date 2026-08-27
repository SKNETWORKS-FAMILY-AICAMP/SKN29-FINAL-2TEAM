-- 기존 DB의 skill_registration_job.operation이 VARCHAR(5)로 남아 있으면
-- CREATE/UPDATE는 저장되지만 RETRY(5자를 초과)가 실패한다. 새 테이블 정의만
-- 고쳐서는 이미 생성된 컬럼이 바뀌지 않으므로 명시적으로 넓힌다.

BEGIN;

ALTER TABLE skill_registration_job
    ALTER COLUMN operation TYPE VARCHAR(10);

COMMIT;
