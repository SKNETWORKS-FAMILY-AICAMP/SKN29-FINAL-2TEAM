BEGIN;

CREATE TABLE IF NOT EXISTS skill_catalog_revision (
    account_id VARCHAR(5) PRIMARY KEY,
    revision BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS skill_worker_heartbeat (
    worker_id VARCHAR(128) PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE skill_registration_job
    ADD COLUMN IF NOT EXISTS model_call_count INT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS estimated_cost_usd NUMERIC(12, 6) NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS ix_skill_worker_heartbeat_recent
    ON skill_worker_heartbeat (heartbeat_at DESC);

COMMIT;
