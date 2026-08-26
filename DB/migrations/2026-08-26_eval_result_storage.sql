-- 2026-08-26 — Agent 평가의 로컬 결과 계약을 DB에서도 조회·집계한다.
--
-- 로컬 `run_manifest.json`/`case_results.jsonl`/`summary.json`이 원본이다.
-- DB 동기화는 같은 eval_run_id와 case_index에 대해 멱등이며, 내용이 다른 중복은
-- 덮어쓰지 않고 코드에서 충돌로 거부한다.
--
-- 실행 위치: DBeaver 또는 `python DB/migrations/_apply.py <이 파일>`

BEGIN;

CREATE TABLE IF NOT EXISTS eval_run (
    eval_run_id      VARCHAR(64) PRIMARY KEY,
    schema_version   INT          NOT NULL,
    git_commit       VARCHAR(64)  NOT NULL,
    dataset_id       VARCHAR(100) NOT NULL,
    dataset_version  VARCHAR(50)  NOT NULL,
    runtime          VARCHAR(100) NOT NULL,
    environment      VARCHAR(100) NOT NULL,
    repetitions      INT          NOT NULL CHECK (repetitions >= 1),
    run_status       VARCHAR(30),
    sync_status      VARCHAR(20)  NOT NULL DEFAULT 'SYNC_PENDING'
                     CHECK (sync_status IN ('SYNC_PENDING', 'SYNCED')),
    started_at       TIMESTAMPTZ  NOT NULL,
    finished_at      TIMESTAMPTZ,
    manifest         JSONB        NOT NULL,
    summary          JSONB,
    synced_at        TIMESTAMPTZ,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_eval_run_dataset
    ON eval_run (dataset_id, dataset_version, started_at DESC);

CREATE TABLE IF NOT EXISTS eval_case_result (
    eval_run_id       VARCHAR(64)  NOT NULL,
    case_index        INT          NOT NULL CHECK (case_index >= 1),
    case_id           VARCHAR(100) NOT NULL,
    agent_id          VARCHAR(20)  NOT NULL,
    agent_version_id  VARCHAR(20)  NOT NULL,
    model             VARCHAR(100) NOT NULL,
    runtime           VARCHAR(100) NOT NULL,
    status            VARCHAR(30)  NOT NULL,
    started_at        TIMESTAMPTZ  NOT NULL,
    finished_at       TIMESTAMPTZ  NOT NULL,
    agent_run_id      VARCHAR(64),
    langfuse_trace_id VARCHAR(128),
    metrics            JSONB        NOT NULL,
    result             JSONB        NOT NULL,
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (eval_run_id, case_index)
);

CREATE INDEX IF NOT EXISTS ix_eval_case_result_case
    ON eval_case_result (case_id, status, finished_at DESC);

COMMIT;
