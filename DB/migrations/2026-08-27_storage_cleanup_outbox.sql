-- S3/로컬 저장소 삭제가 일시 실패해도 기존 worker가 재시도하도록 남기는 outbox.
BEGIN;

CREATE TABLE IF NOT EXISTS storage_cleanup_outbox (
    cleanup_id       BIGSERIAL    PRIMARY KEY,
    storage_key      TEXT         NOT NULL UNIQUE,
    attempts         INTEGER      NOT NULL DEFAULT 0,
    next_attempt_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_error_code  VARCHAR(100),
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_storage_cleanup_outbox_due
    ON storage_cleanup_outbox (next_attempt_at, cleanup_id);

COMMIT;
