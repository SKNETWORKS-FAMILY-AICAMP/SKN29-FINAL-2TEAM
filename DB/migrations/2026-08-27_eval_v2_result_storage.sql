-- Agent Eval V2 원시 결과의 조회·백업용 사본.
-- LEGACY eval_run/eval_case_result와 의도적으로 분리한다.

BEGIN;

CREATE TABLE IF NOT EXISTS eval_v2_run (
    eval_run_id       VARCHAR(64) PRIMARY KEY,
    schema_version    INT          NOT NULL,
    git_commit        VARCHAR(64)  NOT NULL,
    candidate_id      VARCHAR(64)  NOT NULL,
    candidate_model   VARCHAR(100) NOT NULL,
    runtime_profile   VARCHAR(100) NOT NULL,
    sync_status       VARCHAR(20)  NOT NULL DEFAULT 'SYNCED'
                      CHECK (sync_status = 'SYNCED'),
    started_at        TIMESTAMPTZ  NOT NULL,
    finished_at       TIMESTAMPTZ  NOT NULL,
    manifest          JSONB        NOT NULL,
    summary           JSONB        NOT NULL,
    disposition       JSONB,
    manifest_sha256   CHAR(64)     NOT NULL,
    results_sha256    CHAR(64)     NOT NULL,
    summary_sha256    CHAR(64)     NOT NULL,
    disposition_sha256 CHAR(64),
    synced_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS eval_v2_scenario_result (
    eval_run_id       VARCHAR(64)  NOT NULL,
    scenario_index    INT          NOT NULL CHECK (scenario_index >= 1),
    scenario_id       VARCHAR(100) NOT NULL,
    fixture_id        VARCHAR(100) NOT NULL,
    fixture_version   INT          NOT NULL,
    gold_version      INT          NOT NULL,
    scenario_result   VARCHAR(40)  NOT NULL,
    validity          VARCHAR(40)  NOT NULL,
    record_sha256     CHAR(64)     NOT NULL,
    result            JSONB        NOT NULL,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (eval_run_id, scenario_index)
);

CREATE INDEX IF NOT EXISTS ix_eval_v2_scenario_fixture
    ON eval_v2_scenario_result (fixture_id, scenario_result, created_at DESC);

COMMIT;
