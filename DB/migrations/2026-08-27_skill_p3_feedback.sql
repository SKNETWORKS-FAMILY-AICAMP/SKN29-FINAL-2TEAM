BEGIN;

CREATE TABLE IF NOT EXISTS skill_eval_feedback (
    feedback_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id        UUID NOT NULL,
    session_id        UUID NOT NULL,
    account_id        VARCHAR(5) NOT NULL,
    team_id           VARCHAR(5) NOT NULL,
    feedback_kind     VARCHAR(20) NOT NULL
                      CHECK (feedback_kind IN ('WRONG_USAGE', 'MISSED_USE')),
    observed_skills   TEXT[] NOT NULL DEFAULT '{}',
    expected_skill    VARCHAR(64),
    note              TEXT,
    source_trace_hash VARCHAR(64) NOT NULL,
    review_status     VARCHAR(12) NOT NULL DEFAULT 'PENDING'
                      CHECK (review_status IN ('PENDING', 'CONVERTED', 'DISMISSED')),
    reviewed_by       VARCHAR(5),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (message_id, account_id, feedback_kind)
);

ALTER TABLE skill_eval_regression_case
    ADD COLUMN IF NOT EXISTS source_feedback_id UUID;

ALTER TABLE skill_eval_regression_case
    ALTER COLUMN dataset_version TYPE VARCHAR(64);

ALTER TABLE skill_eval_regression_case
    DROP CONSTRAINT IF EXISTS ck_skill_eval_regression_scope_fields;

ALTER TABLE skill_eval_regression_case
    ADD CONSTRAINT ck_skill_eval_regression_scope_fields CHECK (
        (scope = 'GLOBAL' AND team_id IS NULL AND skill_name IS NULL)
        OR (scope = 'TEAM' AND team_id IS NOT NULL AND skill_name IS NULL)
        OR (scope = 'SKILL' AND skill_name IS NOT NULL)
    );

CREATE INDEX IF NOT EXISTS ix_skill_eval_feedback_review
    ON skill_eval_feedback (review_status, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_skill_eval_regression_source_feedback
    ON skill_eval_regression_case (source_feedback_id)
    WHERE source_feedback_id IS NOT NULL;

COMMIT;
