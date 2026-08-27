-- =====================================================================
-- skill_registration_job 평가 컬럼 + skill_eval_regression_case (2026-08-26)
--
-- 정본: docs/설계 및 구현/3_중간발표 이후/작업기록/Juyeon_Agents_Description/
--       03_스킬_검증_등록_설계.md §8.13("재현성과 감사 정보"), §8.8, §9
--
-- 첫 마이그레이션(2026-08-26_skill_registration_job.sql)은 "얇은 종단 경로"
-- 용으로 형식 검사 컬럼만 뒀다. 이제 §8(질문 생성·구조/의미/행동 검토·
-- 트리거 테스트)을 실제로 붙이면서, 그 실행이 남기는 재현성 정보를 담을
-- 컬럼을 추가한다 — "쓰지 않는 컬럼을 미리 깔아 두지 않는다"는 원칙 그대로,
-- 이번에 실제로 쓰기 시작하는 것만 추가한다.
-- =====================================================================

BEGIN;

ALTER TABLE skill_registration_job
    ADD COLUMN IF NOT EXISTS evaluation_agent_id VARCHAR(5),
    ADD COLUMN IF NOT EXISTS evaluation_agent_version_id VARCHAR(5),
    ADD COLUMN IF NOT EXISTS base_catalog_revision BIGINT,
    ADD COLUMN IF NOT EXISTS test_case_set JSONB,
    ADD COLUMN IF NOT EXISTS eval_suite_version VARCHAR(64),
    ADD COLUMN IF NOT EXISTS generator_prompt_version VARCHAR(32),
    ADD COLUMN IF NOT EXISTS semantic_reviewer_prompt_version VARCHAR(32),
    ADD COLUMN IF NOT EXISTS behavior_reviewer_prompt_version VARCHAR(32),
    ADD COLUMN IF NOT EXISTS evaluator_model_snapshot VARCHAR(128),
    ADD COLUMN IF NOT EXISTS platform_probe_version VARCHAR(32),
    ADD COLUMN IF NOT EXISTS regression_case_ids TEXT[],
    ADD COLUMN IF NOT EXISTS candidate_snapshot_hash VARCHAR(64),
    ADD COLUMN IF NOT EXISTS distractor_snapshot_hashes JSONB,
    ADD COLUMN IF NOT EXISTS tool_stub_version VARCHAR(32),
    ADD COLUMN IF NOT EXISTS trace_summary JSONB,
    ADD COLUMN IF NOT EXISTS metrics JSONB;

-- 실제 오발동 회귀 케이스 — 정본 §8.8. 자동 수집 파이프라인은 아직 없다
-- (신고 UI가 없다, 같은 §8.8) — 운영자가 익명화해 수동으로 넣는 걸 전제로
-- 최소한의 저장·승인 구조만 만든다.
CREATE TABLE IF NOT EXISTS skill_eval_regression_case (
    case_id             VARCHAR(40) PRIMARY KEY,
    scope               VARCHAR(10) NOT NULL CHECK (scope IN ('GLOBAL', 'TEAM', 'SKILL')),
    team_id             VARCHAR(5),             -- scope='TEAM'일 때만. team.team_id(FK 없음)
    skill_name          VARCHAR(64),            -- scope='SKILL'일 때만
    capability_tags     TEXT[] NOT NULL DEFAULT '{}',
    polarity            VARCHAR(10) NOT NULL CHECK (polarity IN ('positive', 'negative')),
    case_document       JSONB       NOT NULL,   -- SkillEvalCase 전체(익명화된 messages/fixtures 포함)
    source_trace_hash   VARCHAR(64),            -- 원문을 노출하지 않는 추적용 해시
    review_status       VARCHAR(10) NOT NULL DEFAULT 'DRAFT'
                         CHECK (review_status IN ('DRAFT', 'APPROVED', 'REJECTED')),
    reviewed_by         VARCHAR(5),             -- user_account.account_id(FK 없음), 운영자
    dataset_version     VARCHAR(32) NOT NULL DEFAULT 'v1',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_skill_eval_regression_case_lookup
    ON skill_eval_regression_case (review_status, scope, team_id, skill_name);

COMMIT;

-- =====================================================================
-- 확인용 — COMMIT 뒤에 따로 실행
-- =====================================================================
-- SELECT column_name FROM information_schema.columns
--  WHERE table_name = 'skill_registration_job' AND column_name = 'metrics';
-- SELECT table_name FROM information_schema.tables
--  WHERE table_name = 'skill_eval_regression_case';
