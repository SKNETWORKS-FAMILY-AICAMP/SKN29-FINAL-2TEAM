-- =====================================================================
-- AI 프로젝트 운영 코파일럿 — 전체 PostgreSQL 스키마
-- Figma "PAGE3-v2" 섹션(PAGE 3-A/3-B/3-C) 현재 상태를 그대로 옮긴 DDL
-- 생성일: 2026-07-28
--
-- VEC_IDX(벡터 검색 인덱스)는 pgvector 기반으로 이 파일에 포함된다(Tier 4,
-- CHUNK 하위). 별도 Vector DB(ChromaDB 등)는 쓰지 않는다 — pgvector/pgvector
-- 이미지가 이미 vector 확장을 지원하므로 3-B와 같은 PostgreSQL 인스턴스에
-- 그대로 저장한다.
--
-- 실행 순서: 이 파일 하나만 위에서 아래로 실행하면 된다(의존성 순서로 정렬됨).
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_uuid() 사용
CREATE EXTENSION IF NOT EXISTS vector;    -- VEC_IDX.embedding용 vector 타입

-- =====================================================================
-- PAGE 3-C | 플랫폼 운영·권한 — Tier 0 (의존성 없음)
-- =====================================================================

CREATE TABLE user_account (
    account_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,           -- 애플리케이션에서 bcrypt/argon2로 해싱 후 저장, 평문 절대 금지
    display_name    VARCHAR(100) NOT NULL,
    account_status  VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE / LOCKED / WITHDRAWN
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- =====================================================================
-- PAGE 3-B | People DB — Tier 0 (의존성 없음)
-- Figma 표기가 VARCHAR(5) 짧은 코드(person_id="P0001" 형태)를 쓰고 있어서
-- 그대로 따랐다. org/level/skill도 전부 VARCHAR(5) 코드 체계.
-- =====================================================================

CREATE TABLE org (
    org_id      VARCHAR(5) PRIMARY KEY,
    up_org_id   VARCHAR(5) REFERENCES org(org_id),          -- 상위 조직(자기 참조)
    mgr_id      VARCHAR(5),                                  -- 조직 관리자 = person_id, PERSON 생성 후 아래서 FK 추가(순환 참조)
    name        VARCHAR(100) NOT NULL,
    org_type    VARCHAR(30),
    status      VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
);

CREATE TABLE level (
    level_id  VARCHAR(5) PRIMARY KEY,
    code      VARCHAR(20) NOT NULL,
    name      VARCHAR(50) NOT NULL,
    rank_ord  INT NOT NULL,
    status    VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
);

CREATE TABLE skill (
    skill_id  VARCHAR(5) PRIMARY KEY,
    name      VARCHAR(100) NOT NULL,
    category  VARCHAR(50),
    status    VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
);

-- =====================================================================
-- PAGE 3-A | 문서→지식→Task 파이프라인 — Tier 1
-- =====================================================================

CREATE TABLE proj (
    proj_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name              VARCHAR(200) NOT NULL,
    status            VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',
    tz                VARCHAR(50)  NOT NULL DEFAULT 'Asia/Seoul',
    owner_account_id  UUID REFERENCES user_account(account_id)
);

-- =====================================================================
-- PAGE 3-C | 플랫폼 운영·권한 — Tier 2 (PROJ, USER_ACCOUNT 의존)
-- =====================================================================

CREATE TABLE proj_member (
    proj_member_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proj_id             UUID NOT NULL REFERENCES proj(proj_id) ON DELETE CASCADE,
    account_id          UUID NOT NULL REFERENCES user_account(account_id) ON DELETE CASCADE,
    access_role         VARCHAR(20) NOT NULL,   -- OWNER / EDITOR / VIEWER
    joined_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (proj_id, account_id)
);

CREATE TABLE connector_conn (
    conn_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id                UUID NOT NULL REFERENCES user_account(account_id) ON DELETE CASCADE,
    connector_type            VARCHAR(30) NOT NULL,   -- GOOGLE_DRIVE / JIRA
    granted_scopes            JSONB NOT NULL DEFAULT '[]',
    auth_status                VARCHAR(20) NOT NULL DEFAULT 'CONNECTED',  -- CONNECTED / EXPIRED / ERROR
    encrypted_credential_ref  VARCHAR(255),   -- 실제 토큰이 아니라 Secret Manager 참조 키
    connected_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE proj_source (
    proj_source_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proj_id              UUID NOT NULL REFERENCES proj(proj_id) ON DELETE CASCADE,
    conn_id        UUID NOT NULL REFERENCES connector_conn(conn_id) ON DELETE CASCADE,
    source_type          VARCHAR(30) NOT NULL,   -- DRIVE_FOLDER / JIRA_PROJECT
    external_source_id   VARCHAR(255) NOT NULL,  -- 실제 Drive 폴더 ID / Jira 프로젝트 키
    sync_status           VARCHAR(20) NOT NULL DEFAULT 'PENDING'
);

-- =====================================================================
-- PAGE 3-B | People DB — Tier 1 (org/level 의존)
-- =====================================================================

CREATE TABLE person (
    person_id   VARCHAR(5) PRIMARY KEY,
    emp_id      VARCHAR(30) NOT NULL UNIQUE,
    name        VARCHAR(100) NOT NULL,
    email       VARCHAR(255) NOT NULL UNIQUE,
    org_id      VARCHAR(5) REFERENCES org(org_id),
    job_role    VARCHAR(100),
    level_id    VARCHAR(5) REFERENCES level(level_id),
    emp_status  VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
);

-- ORG.mgr_id ↔ PERSON 순환 참조 해결: PERSON 생성 후 FK 추가
ALTER TABLE org
    ADD CONSTRAINT fk_org_mgr FOREIGN KEY (mgr_id) REFERENCES person(person_id);

CREATE TABLE person_skill (
    person_id    VARCHAR(5) NOT NULL REFERENCES person(person_id) ON DELETE CASCADE,
    skill_id     VARCHAR(5) NOT NULL REFERENCES skill(skill_id) ON DELETE CASCADE,
    proficiency  INT NOT NULL CHECK (proficiency BETWEEN 1 AND 5),
    source       VARCHAR(30),
    confidence   NUMERIC(4,3),
    PRIMARY KEY (person_id, skill_id)
);

-- Figma 레이어명은 IDENTITY_LINK, 테이블 표시명은 "link"
CREATE TABLE person_link (
    person_link_id     VARCHAR(5) PRIMARY KEY,
    person_id   VARCHAR(5) NOT NULL REFERENCES person(person_id) ON DELETE CASCADE,
    sys_type    VARCHAR(30) NOT NULL,   -- 외부 시스템 유형(JIRA 등)
    ext_email   VARCHAR(255) NOT NULL,
    reg_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (sys_type, ext_email),
    UNIQUE (person_id, sys_type)
);

CREATE TABLE sched (
    sched_id       VARCHAR(5) PRIMARY KEY,
    person_id      VARCHAR(5) NOT NULL REFERENCES person(person_id) ON DELETE CASCADE,
    wk_hours       NUMERIC(5,2),
    def_wk_hours   NUMERIC(5,2),
    fte            NUMERIC(3,2),
    tz             VARCHAR(50) NOT NULL DEFAULT 'Asia/Seoul',
    eff_from       DATE NOT NULL,
    eff_to         DATE
);

CREATE TABLE absence (
    absence_id     VARCHAR(5) PRIMARY KEY,
    person_id      VARCHAR(5) NOT NULL REFERENCES person(person_id) ON DELETE CASCADE,
    absence_type   VARCHAR(30) NOT NULL,
    start_at       TIMESTAMPTZ NOT NULL,
    end_at         TIMESTAMPTZ NOT NULL,
    status         VARCHAR(20) NOT NULL DEFAULT 'REQUESTED'
);

CREATE TABLE exist_task (
    exist_task_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assignee_person_id   VARCHAR(5) REFERENCES person(person_id), 
    jira_issue_id        VARCHAR(50) NOT NULL,
    status                VARCHAR(20),
    priority              VARCHAR(20),
    start_at              TIMESTAMPTZ,
    due_at                TIMESTAMPTZ,
    remaining             NUMERIC(6,2),
    spent                 NUMERIC(6,2)
);

CREATE TABLE cal_event (
    cal_event_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id             VARCHAR(5) NOT NULL REFERENCES person(person_id) ON DELETE CASCADE,
    event_type            VARCHAR(30) NOT NULL,
    start_at              TIMESTAMPTZ NOT NULL,
    end_at                TIMESTAMPTZ NOT NULL,
    availability_impact   NUMERIC(5,2)
);

-- =====================================================================
-- PAGE 3-A | 문서→지식→Task 파이프라인 — Tier 2 (PROJ 의존)
-- =====================================================================

CREATE TABLE doc (
    doc_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proj_id            UUID NOT NULL REFERENCES proj(proj_id) ON DELETE CASCADE,
    src_file_id        VARCHAR(255),
    cur_revision       VARCHAR(50),
    content_hash       VARCHAR(100),
    security           VARCHAR(20) NOT NULL DEFAULT 'Internal',
    source_type        VARCHAR(20) NOT NULL,   -- DRIVE / JIRA
    file_name          VARCHAR(255),
    mime_type          VARCHAR(100),
    doc_role           VARCHAR(30),
    acl_principals     TEXT[] NOT NULL DEFAULT '{}',
    src_modified_at    TIMESTAMPTZ,
    deleted            BOOLEAN NOT NULL DEFAULT false,
    access_revoked     BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE know_item (
    know_item_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proj_id          UUID NOT NULL REFERENCES proj(proj_id) ON DELETE CASCADE,
    semantic_type    VARCHAR(40) NOT NULL,
    title            VARCHAR(255) NOT NULL,
    content          TEXT NOT NULL,
    confidence       NUMERIC(4,3)
);

CREATE TABLE proj_know_model (
    model_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proj_id             UUID NOT NULL REFERENCES proj(proj_id) ON DELETE CASCADE,
    model_ver           VARCHAR(20) NOT NULL,
    status               VARCHAR(20) NOT NULL DEFAULT 'GENERATING',  -- GENERATING / READY
    generated_at         TIMESTAMPTZ,
    conflict_summary     JSONB
);

-- =====================================================================
-- PAGE 3-A — Tier 3 (DOC / PROJ_KNOW_MODEL 의존)
-- =====================================================================

CREATE TABLE doc_block (
    block_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id            UUID NOT NULL REFERENCES doc(doc_id) ON DELETE CASCADE,
    block_type        VARCHAR(20) NOT NULL,   -- HEADING / PARAGRAPH / TABLE / LIST
    page              INT,
    heading_path      TEXT[] NOT NULL DEFAULT '{}',
    content           TEXT NOT NULL,
    sequence          INT NOT NULL,
    revision          VARCHAR(50) NOT NULL,
    src_locator       JSONB,
    struct_content    JSONB
);

CREATE TABLE doc_sync (
    sync_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id          UUID NOT NULL REFERENCES doc(doc_id) ON DELETE CASCADE,
    chg_type        VARCHAR(20) NOT NULL,   -- CREATED / UPDATED / DELETED
    sync_status     VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    ckpt_token      TEXT,
    retry_cnt       INT NOT NULL DEFAULT 0,
    revision        VARCHAR(50),
    parse_status    VARCHAR(20),   -- SUCCESS / PARTIAL_RESULT / BLOCKED
    content_hash    VARCHAR(100),
    parser_ver      VARCHAR(30),
    embed_ver       VARCHAR(30),
    last_proc_at    TIMESTAMPTZ,
    warnings        JSONB NOT NULL DEFAULT '[]',
    errors          JSONB NOT NULL DEFAULT '[]'
);

CREATE TABLE model_know_item (
    model_id       UUID NOT NULL REFERENCES proj_know_model(model_id) ON DELETE CASCADE,
    know_item_id   UUID NOT NULL REFERENCES know_item(know_item_id) ON DELETE CASCADE,
    incl_status    VARCHAR(20) NOT NULL DEFAULT 'INCLUDED',
    sort_ord       INT,
    PRIMARY KEY (model_id, know_item_id)
);

CREATE TABLE feat_cluster (
    cluster_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_id      UUID NOT NULL REFERENCES proj_know_model(model_id) ON DELETE CASCADE,
    name          VARCHAR(200) NOT NULL,
    biz_scope     VARCHAR(200),
    summary       TEXT
);

CREATE TABLE task (
    task_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_id       UUID NOT NULL REFERENCES proj_know_model(model_id) ON DELETE CASCADE,
    task_name      VARCHAR(255) NOT NULL,
    req_role       VARCHAR(100),
    effort         NUMERIC(6,2),
    start_at       TIMESTAMPTZ,
    due_at         TIMESTAMPTZ,
    priority       VARCHAR(20),
    src_type       VARCHAR(30) NOT NULL,   -- EXTRACTED / GENERATED / AI_SUGGESTED_MISSING_TASK / USER_ADDED
    confidence     NUMERIC(4,3),
    status         VARCHAR(20) NOT NULL DEFAULT 'PROPOSED'  -- PROPOSED / CONFIRMED / REJECTED
);

-- =====================================================================
-- PAGE 3-A — Tier 4 (BLOCK/MODEL/CLUSTER/TASK 하위)
-- =====================================================================

CREATE TABLE chunk (
    chunk_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    block_id        UUID NOT NULL REFERENCES doc_block(block_id) ON DELETE CASCADE,
    up_chunk_id     UUID REFERENCES chunk(chunk_id),
    search_text     TEXT NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    chunk_idx       INT NOT NULL,
    token_cnt       INT,
    heading_path    TEXT[] NOT NULL DEFAULT '{}',
    chunker_ver     VARCHAR(30)
);

-- CHUNK와 1:1. embed_dim은 embedding vector(N)의 N과 항상 같아야 하며,
-- 임베딩 모델 교체로 차원이 달라지면 새 embed_ver로 재임베딩해서 별도 행을
-- 쌓는다(기존 행을 고치지 않음 — is_active로 최신 여부만 표시).
CREATE TABLE vec_idx (
    vec_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id        UUID NOT NULL UNIQUE REFERENCES chunk(chunk_id) ON DELETE CASCADE,
    embedding       VECTOR(1536) NOT NULL,
    metadata        JSONB NOT NULL DEFAULT '{}',
    indexed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    embed_model     VARCHAR(100),
    embed_ver       VARCHAR(30),
    embed_dim       INT,
    dist_metric     VARCHAR(20) NOT NULL DEFAULT 'COSINE',
    content_hash    VARCHAR(100),
    revision        VARCHAR(50),
    is_active       BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE know_item_src (
    know_item_id   UUID NOT NULL REFERENCES know_item(know_item_id) ON DELETE CASCADE,
    block_id        UUID NOT NULL REFERENCES doc_block(block_id) ON DELETE CASCADE,
    rel_type        VARCHAR(20) NOT NULL DEFAULT 'PRIMARY',
    src_ver         VARCHAR(50),
    confidence      NUMERIC(4,3),
    chunk_id        UUID REFERENCES chunk(chunk_id),
    quote_text      TEXT,
    quote_hash      VARCHAR(100),
    src_locator     JSONB,
    PRIMARY KEY (know_item_id, block_id)
);

CREATE TABLE feat_cluster_item (
    cluster_id     UUID NOT NULL REFERENCES feat_cluster(cluster_id) ON DELETE CASCADE,
    know_item_id   UUID NOT NULL REFERENCES know_item(know_item_id) ON DELETE CASCADE,
    sim_score       NUMERIC(4,3),
    merge_status    VARCHAR(20),
    PRIMARY KEY (cluster_id, know_item_id)
);

CREATE TABLE task_know_src (
    task_id        UUID NOT NULL REFERENCES task(task_id) ON DELETE CASCADE,
    know_item_id   UUID NOT NULL REFERENCES know_item(know_item_id) ON DELETE CASCADE,
    rel_type        VARCHAR(20) NOT NULL DEFAULT 'PRIMARY',
    rationale       TEXT,
    PRIMARY KEY (task_id, know_item_id)
);

-- =====================================================================
-- 공유 스냅샷 — page3-A와 page3-B가 함께 참조
-- (ANA_SNAPSHOT은 page3-A ERD에 정의돼 있지만, page3-B의 PERSON_SNAPSHOT/
--  EXISTING_TASK_SNAPSHOT/ASSIGNMENT_RUN/FEATURE_READINESS_RESULT가 전부
--  같은 snapshot_id로 이 테이블을 가리킨다 — "이 시점 기준 데이터"라는
--  개념을 두 도메인이 공유하는 구조. 아래 사용처 표 참고)
-- =====================================================================

CREATE TABLE ana_snapshot (
    snap_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proj_id            UUID NOT NULL REFERENCES proj(proj_id) ON DELETE CASCADE,
    model_id           UUID REFERENCES proj_know_model(model_id),
    snap_as_of         TIMESTAMPTZ NOT NULL DEFAULT now(),
    policy_ver         VARCHAR(30),
    doc_version_set    JSONB
);

-- =====================================================================
-- PAGE 3-C | 플랫폼 운영·권한 — Tier 3 (PROJECT_SOURCE / AUDIT_LOG)
-- =====================================================================

CREATE TABLE audit_log (
    audit_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proj_id              UUID REFERENCES proj(proj_id),     -- nullable: 프로젝트와 무관한 계정 단위 행위도 있음(로그인 등)
    actor_account_id     UUID NOT NULL REFERENCES user_account(account_id),
    action                VARCHAR(50) NOT NULL,   -- LOGIN / CONNECT / SYNC / APPROVE / REJECT 등
    target_type           VARCHAR(50),            -- 예: TASK, RECOMMENDATION_RESULT (다형 참조라 FK 강제 안 함)
    target_id             UUID,
    payload               JSONB,
    occurred_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =====================================================================
-- PAGE 3-B | People DB — Tier 2 (ANA_SNAPSHOT / PERSON / EXISTING_TASK 의존)
-- =====================================================================

CREATE TABLE feat_ready_result (
    readiness_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id        UUID NOT NULL REFERENCES ana_snapshot(snap_id) ON DELETE CASCADE,
    feature_type        VARCHAR(50) NOT NULL,
    status               VARCHAR(20) NOT NULL,   -- SUCCESS / PARTIAL / BLOCKED
    missing_data         JSONB,
    limitations          JSONB,
    confidence           NUMERIC(4,3),
    checked_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE person_snap (
    person_snap_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id           UUID NOT NULL REFERENCES ana_snapshot(snap_id) ON DELETE CASCADE,
    person_id             VARCHAR(5) NOT NULL REFERENCES person(person_id),
    role_json              JSONB,
    skills_json             JSONB,
    fte                    JSONB,
    absence                 JSONB,
    source_version           VARCHAR(30)
);

CREATE TABLE exist_task_snap (
    exist_task_snap_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id            UUID NOT NULL REFERENCES ana_snapshot(snap_id) ON DELETE CASCADE,
    exist_task_id        UUID NOT NULL REFERENCES exist_task(exist_task_id),
    assignee_person_id      VARCHAR(5) REFERENCES person(person_id),
    estimate                 NUMERIC(6,2),
    remaining                NUMERIC(6,2)
);

-- =====================================================================
-- PAGE 3-B | People DB — Tier 3 (배정 실행)
-- =====================================================================

CREATE TABLE assign_run (
    run_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id      UUID NOT NULL REFERENCES ana_snapshot(snap_id),
    readiness_id     UUID REFERENCES feat_ready_result(readiness_id),
    model_version     VARCHAR(30),
    policy_version    VARCHAR(30),
    status            VARCHAR(20) NOT NULL DEFAULT 'RUNNING',
    requested_by      UUID REFERENCES user_account(account_id)
);

-- =====================================================================
-- PAGE 3-B | People DB — Tier 4 (실행 결과)
-- =====================================================================

CREATE TABLE workload_result (
    workload_result_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id                 UUID NOT NULL REFERENCES assign_run(run_id) ON DELETE CASCADE,
    person_id              VARCHAR(5) NOT NULL REFERENCES person(person_id),
    effective_capacity      NUMERIC(6,2),
    current_allocation      NUMERIC(6,2),
    remaining_capacity      NUMERIC(6,2),
    load_rate                NUMERIC(5,2)
);

CREATE TABLE reco_result (
    reco_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id                UUID NOT NULL REFERENCES assign_run(run_id) ON DELETE CASCADE,
    task_id               UUID NOT NULL REFERENCES task(task_id),
    status                 VARCHAR(20) NOT NULL,   -- PASS / CONDITIONAL_PASS / REJECT
    confidence              NUMERIC(4,3),
    missing_data             JSONB,
    limitations               JSONB,
    assumptions                JSONB
);

-- =====================================================================
-- PAGE 3-B | People DB — Tier 5 (후보/검증)
-- =====================================================================

CREATE TABLE reco_cand (
    cand_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reco_id   UUID NOT NULL REFERENCES reco_result(reco_id) ON DELETE CASCADE,
    person_id            VARCHAR(5) NOT NULL REFERENCES person(person_id),
    rank                  INT,
    fit_score              NUMERIC(5,2),
    expected_load           NUMERIC(5,2),
    is_alternative           BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE valid_result (
    valid_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reco_id     UUID NOT NULL REFERENCES reco_result(reco_id) ON DELETE CASCADE,
    status                  VARCHAR(20) NOT NULL,
    missing_data             JSONB,
    confidence                NUMERIC(4,3)
);

-- =====================================================================
-- PAGE 3-B | People DB — Tier 6 (근거/체크/결정)
-- =====================================================================

CREATE TABLE reco_evidence (
    evidence_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cand_id       UUID NOT NULL REFERENCES reco_cand(cand_id) ON DELETE CASCADE,
    evidence_type        VARCHAR(30) NOT NULL,
    source_id             UUID,   -- 다형 참조(어느 테이블의 근거인지 evidence_type으로 구분) — FK 강제 안 함
    reason                 TEXT,
    citation                TEXT,
    verified                BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE valid_check (
    valid_check_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    valid_id           UUID NOT NULL REFERENCES valid_result(valid_id) ON DELETE CASCADE,
    check_type                VARCHAR(50) NOT NULL,
    result                     VARCHAR(20) NOT NULL,
    actual_value                JSONB,
    expected_rule                 JSONB,
    severity                       VARCHAR(20)
);

CREATE TABLE decision_rec (
    decision_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reco_id          UUID NOT NULL REFERENCES reco_result(reco_id),
    valid_id                UUID REFERENCES valid_result(valid_id),
    pm_action                     VARCHAR(20) NOT NULL,  -- APPROVE / MODIFY / REJECT
    reason                          TEXT,
    modified_cand_id            UUID REFERENCES reco_cand(cand_id),
    decided_by                        UUID REFERENCES user_account(account_id),
    decided_at                          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =====================================================================
-- 끝. 총 41개 테이블 (VEC_IDX 포함, pgvector 기반)
-- =====================================================================