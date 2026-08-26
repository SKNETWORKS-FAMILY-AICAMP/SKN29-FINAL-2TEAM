-- 2026-08-26 — LLM Judge 판정을 DB에도 저장한다.
--
-- 지금까지 Judge 판정은 로컬 `judge_calibration.jsonl`에만 있었다(DB 저장
-- 자리가 아예 없었다). 로컬 파일이 여전히 원본이고, 이 표는
-- `eval_case_result`와 마찬가지로 조회·집계용 사본이다.
--
-- `(eval_run_id, case_index)`로 `eval_case_result` 한 행과 연결한다(FK 없음 —
-- 기존 `eval_case_result`와 같은 이유, 평가 표는 제품 스키마와 독립적으로
-- 진화한다). 같은 case에 여러 Judge 모델/프롬프트 버전 결과가 쌓일 수 있어
-- 그 둘도 기본키에 넣는다 — `calibration.py`의 append-only 중복 방지 규칙과
-- 동일하다.
--
-- `human_verdict`/`comparison`은 calibration(사람 판정과 비교) 표본일 때만
-- 채운다. 일반 채점만 하고 사람 비교가 없는 실행은 NULL로 둔다 — 값을
-- 지어내지 않는다.
--
-- 실행 위치: DBeaver 또는 `python DB/migrations/_apply.py <이 파일>`

BEGIN;

CREATE TABLE IF NOT EXISTS eval_judge_result (
    eval_run_id      VARCHAR(64)  NOT NULL,  -- eval_case_result.eval_run_id(FK 없음)
    case_index       INT          NOT NULL CHECK (case_index >= 1),
    judge_model      VARCHAR(100) NOT NULL,
    prompt_version   VARCHAR(100) NOT NULL,
    mode             VARCHAR(20)  NOT NULL DEFAULT 'REPORT_ONLY'
                     CHECK (mode = 'REPORT_ONLY'),  -- 결정론적 판정을 덮어쓰지 않는다는 계약을 스키마로도 고정한다
    latency_ms       NUMERIC,
    usage            JSONB,
    verdict          JSONB        NOT NULL,  -- overall_verdict + 5차원 판정·근거
    human_verdict    JSONB,                  -- calibration 표본일 때만
    comparison       JSONB,                  -- calibration 비교 결과, 없으면 NULL
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (eval_run_id, case_index, judge_model, prompt_version)
);

CREATE INDEX IF NOT EXISTS ix_eval_judge_result_case
    ON eval_judge_result (case_index, created_at DESC);

COMMIT;
