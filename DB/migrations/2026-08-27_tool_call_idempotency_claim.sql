-- 같은 run/tool_call_id가 정확히 동시에 재개돼도 side-effect 도구를 한 번만
-- 실행하기 위한 원자적 claim과 crash 회수 lease.
BEGIN;

ALTER TABLE tool_call_idempotency
    ADD COLUMN IF NOT EXISTS status VARCHAR(16),
    ADD COLUMN IF NOT EXISTS lease_until TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;

UPDATE tool_call_idempotency
   SET status = COALESCE(status, 'SUCCEEDED'),
       updated_at = COALESCE(updated_at, created_at, now());

ALTER TABLE tool_call_idempotency
    ALTER COLUMN status SET DEFAULT 'SUCCEEDED',
    ALTER COLUMN status SET NOT NULL,
    ALTER COLUMN result_text DROP NOT NULL,
    ALTER COLUMN updated_at SET DEFAULT now(),
    ALTER COLUMN updated_at SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'tool_call_idempotency_status_ck'
    ) THEN
        ALTER TABLE tool_call_idempotency
            ADD CONSTRAINT tool_call_idempotency_status_ck
            CHECK (status IN ('RUNNING', 'SUCCEEDED'));
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'tool_call_idempotency_result_ck'
    ) THEN
        ALTER TABLE tool_call_idempotency
            ADD CONSTRAINT tool_call_idempotency_result_ck
            CHECK ((status = 'RUNNING' AND result_text IS NULL) OR
                   (status = 'SUCCEEDED' AND result_text IS NOT NULL));
    END IF;
END $$;

COMMIT;
