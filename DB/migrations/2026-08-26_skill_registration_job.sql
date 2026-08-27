-- =====================================================================
-- skill_registration_job (2026-08-26)
--
-- 정본: docs/설계 및 구현/3_중간발표 이후/작업기록/Juyeon_Agents_Description/
--       03_스킬_검증_등록_설계.md §9
--
-- 개인 스킬 등록/수정은 더 이상 `services.agent_runtime.skills.service`가
-- 즉시 SKILL.md를 쓰지 않는다 — 이 테이블에 검증 job을 만들고, 별도 워커
-- 프로세스(`python manage.py skill_validation_worker`)가 `FOR UPDATE SKIP
-- LOCKED`로 가져가 검증한 뒤에만 SKILL.md를 쓴다.
--
-- 이번 마이그레이션은 "얇은 종단 경로"(형식 검사만 하는 최소 검증) 착수분
-- 이다. §8의 질문 생성·구조/의미/행동 검토가 붙을 때 필요한 컬럼
-- (test_case_set, eval_suite_version, *_prompt_version 등)은 그 기능을
-- 실제로 만들 때 같이 추가한다 — 아직 쓰지 않는 컬럼을 미리 깔아 두지
-- 않는다(써보지 않은 스키마는 그 자체로 검증되지 않은 가정이다).
--
-- Django ORM/migration을 쓰지 않는다(`apps/projects/models.py` 참고) —
-- 이 저장소는 `DB/schema.sql` + `DB/migrations/*.sql`을 직접 관리하고,
-- `backend/db/*.py`가 raw SQL로 접근한다.
-- =====================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS skill_registration_job (
    job_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- 검증 job은 항상 개인 스킬만 대상으로 한다(정본 문서 §2 "TEAM 직접
    -- 등록 경로를 제거한다"). 숨기지 않고 CHECK로 고정한다.
    target_scope        VARCHAR(20) NOT NULL DEFAULT 'PERSONAL'
                         CHECK (target_scope = 'PERSONAL'),

    account_id          VARCHAR(5)  NOT NULL,   -- user_account.account_id(FK 없음)
    team_id             VARCHAR(5),             -- team.team_id(FK 없음). 도구·소속 확인용.

    skill_name          VARCHAR(64) NOT NULL,
    operation           VARCHAR(10) NOT NULL
                         CHECK (operation IN ('CREATE', 'UPDATE', 'RETRY')),

    -- SkillDocument 초안. 검증 중이거나 실패한 동안은 여기가 유일한
    -- 저장소다 — 통과해야만 개인 SKILL.md로 옮겨 쓴다(정본 §3/§4).
    candidate_document  JSONB       NOT NULL,
    candidate_hash       VARCHAR(64) NOT NULL,   -- sha256(candidate_document)
    base_content_hash    VARCHAR(64),            -- UPDATE일 때 수정 전 등록본 해시

    status               VARCHAR(20) NOT NULL DEFAULT 'QUEUED'
                         CHECK (status IN (
                             'QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED',
                             'CANCEL_REQUESTED', 'CANCELED'
                         )),
    stage                VARCHAR(20) NOT NULL DEFAULT 'WAITING'
                         CHECK (stage IN (
                             'WAITING', 'CHECKING', 'PREPARING_TESTS',
                             'TESTING', 'PUBLISHING'
                         )),

    attempt              INT         NOT NULL DEFAULT 1,
    retry_of_job_id       UUID,                  -- skill_registration_job.job_id(FK 없음)

    -- 채팅에서 시작됐을 때의 세션. 설정 화면에서 시작하면 NULL.
    source_session_id    UUID,                   -- chat_session.session_id(FK 없음)

    -- 같은 HITL 재개·네트워크 재시도가 job을 중복 생성하지 않게 막는 키.
    idempotency_key      VARCHAR(128),

    failure_code          VARCHAR(40),
    failure_summary        TEXT,
    failure_details         JSONB,

    -- 실행 중인 워커. `FOR UPDATE SKIP LOCKED`로 가져간 워커가 자기 자신을
    -- 표시하고, lease_expires_at이 지나면 다른 워커가 회수한다.
    lease_owner            VARCHAR(128),
    lease_expires_at        TIMESTAMPTZ,
    heartbeat_at            TIMESTAMPTZ,

    cancel_requested_at     TIMESTAMPTZ,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at              TIMESTAMPTZ,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at            TIMESTAMPTZ
);

-- 워커가 큐를 가져갈 때 쓰는 자리 — status=QUEUED만 스캔한다.
CREATE INDEX IF NOT EXISTS ix_skill_registration_job_queue
    ON skill_registration_job (status, created_at)
    WHERE status = 'QUEUED';

-- 사용자 화면(JobCenter, 스킬 목록)이 "내 열린 job"을 조회하는 자리.
CREATE INDEX IF NOT EXISTS ix_skill_registration_job_account_open
    ON skill_registration_job (account_id, status, created_at DESC);

-- "같은 사용자·스킬 이름에는 열린 job을 하나만 허용한다"(정본 §9) — 부분
-- 유니크 인덱스로 DB 층에서도 고정한다. 애플리케이션(enqueue 이전 조회)이
-- 1차 방어선이고, 이건 경합 상황의 최종 방어선이다.
CREATE UNIQUE INDEX IF NOT EXISTS ux_skill_registration_job_open_per_name
    ON skill_registration_job (account_id, skill_name)
    WHERE status IN ('QUEUED', 'RUNNING', 'CANCEL_REQUESTED');

-- 죽은 워커 회수 — lease_expires_at이 지난 RUNNING job을 찾는 자리.
CREATE INDEX IF NOT EXISTS ix_skill_registration_job_lease
    ON skill_registration_job (status, lease_expires_at)
    WHERE status = 'RUNNING';

COMMIT;

-- =====================================================================
-- 확인용 — COMMIT 뒤에 따로 실행
-- =====================================================================
-- SELECT table_name FROM information_schema.tables
--  WHERE table_name = 'skill_registration_job';
