-- 스킬 검증 job의 사용자용 세부 진행 정보.
-- 5단계 stage는 화면 구조로 유지하고, 그 안에서 워커가 실제로 수행 중인
-- 작업과 반복 실행 개수를 별도 필드로 전달한다. 모델의 내부 사고과정은
-- 저장하지 않고 관찰 가능한 작업 시작·완료 사실만 기록한다.

BEGIN;

ALTER TABLE skill_registration_job
    ADD COLUMN IF NOT EXISTS progress_message TEXT
        NOT NULL DEFAULT '검증을 시작할 차례를 기다리고 있어요.',
    ADD COLUMN IF NOT EXISTS progress_current INT,
    ADD COLUMN IF NOT EXISTS progress_total INT,
    ADD COLUMN IF NOT EXISTS progress_events JSONB
        NOT NULL DEFAULT '[]'::jsonb;

COMMIT;
