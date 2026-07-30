-- =====================================================================
-- AI 프로젝트 운영 코파일럿 — 전체 PostgreSQL 스키마
-- 생성일: 2026-07-28
--
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;


-- =====================================================================
-- PAGE 3-C | 플랫폼 운영·권한 — Tier 0 (의존성 없음)
-- =====================================================================


CREATE TABLE user_account (
    account_id      VARCHAR(5) PRIMARY KEY,
    email           VARCHAR(255) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,           -- 애플리케이션에서 bcrypt/argon2로 해싱 후 저장, 평문 절대 금지
    display_name    VARCHAR(100) NOT NULL,
    account_status  VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE / LOCKED / WITHDRAWN
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- =====================================================================
-- PAGE 3-B | People DB — Tier 0
-- org/level/skill도 전부 VARCHAR(5) 코드 체계(위 설계 방침 참고).
-- =====================================================================

CREATE TABLE org (
    org_id      VARCHAR(5) PRIMARY KEY,
    up_org_id   VARCHAR(5),          -- 상위 조직(자기 참조, FK 없음)
    mgr_id      VARCHAR(5),          -- 조직 관리자 = person_id(FK 없음). ORG↔PERSON이 서로를 가리키는 순환 참조라 애초에 FK를 걸 수 없는 구조이기도 하다
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

-- ⚠ 발견한 이슈: PROJ.owner_account_id는 USER_ACCOUNT를 참조하는데, 원래
-- 세션 초반에 설계했던 tenant_id는 Figma 상에서 이미 빠져있었다(3-C가
-- 독자적으로 만들어지면서 owner_account_id로 대체된 것으로 보임). 그대로 반영.
CREATE TABLE proj (
    proj_id           VARCHAR(5) PRIMARY KEY,
    name              VARCHAR(200) NOT NULL,
    status            VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',
    tz                VARCHAR(50)  NOT NULL DEFAULT 'Asia/Seoul',
    owner_account_id  VARCHAR(5)
);

-- =====================================================================
-- PAGE 3-C | 플랫폼 운영·권한 — Tier 2 (PROJ, USER_ACCOUNT 의존)
-- =====================================================================

CREATE TABLE proj_member (
    proj_member_id  VARCHAR(5) PRIMARY KEY,
    proj_id             VARCHAR(5) NOT NULL,
    account_id          VARCHAR(5) NOT NULL,
    access_role         VARCHAR(20) NOT NULL,   -- OWNER / EDITOR / VIEWER
    joined_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (proj_id, account_id)
);

CREATE TABLE connector_conn (
    conn_id             VARCHAR(5) PRIMARY KEY,
    account_id                VARCHAR(5) NOT NULL,
    connector_type            VARCHAR(30) NOT NULL,   -- PEOPLE_DB / GOOGLE_DRIVE / JIRA
    granted_scopes            JSONB NOT NULL DEFAULT '[]',
    auth_status                VARCHAR(20) NOT NULL DEFAULT 'CONNECTED',  -- CONNECTED / EXPIRED / ERROR
    encrypted_credential_ref  TEXT,           -- 외부 자격증명의 DB 저장용 암호문(기존 ref 명칭 유지). People DB는 자격증명이 없어 NULL
                                              -- VARCHAR(255)로는 부족하다: Fernet 암호문이 Jira 1700자, Drive 632자다(255자는 평문 127바이트까지만 수용)
    connected_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE proj_source (
    proj_source_id   VARCHAR(5) PRIMARY KEY,
    proj_id              VARCHAR(5) NOT NULL,
    conn_id        VARCHAR(5) NOT NULL,
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
    org_id      VARCHAR(5),
    job_role    VARCHAR(100),
    level_id    VARCHAR(5),
    emp_status  VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
);


CREATE TABLE person_skill (
    person_id    VARCHAR(5) NOT NULL,
    skill_id     VARCHAR(5) NOT NULL,
    proficiency  INT NOT NULL CHECK (proficiency BETWEEN 1 AND 5),
    source       VARCHAR(30),
    confidence   NUMERIC(4,3),
    PRIMARY KEY (person_id, skill_id)
);

-- Figma 레이어명은 IDENTITY_LINK, 테이블 표시명은 "link"
CREATE TABLE person_link (
    person_link_id     VARCHAR(5) PRIMARY KEY,
    person_id   VARCHAR(5) NOT NULL,
    sys_type    VARCHAR(30) NOT NULL,   -- 외부 시스템 유형(JIRA 등)
    ext_email   VARCHAR(255) NOT NULL,
    reg_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (sys_type, ext_email),
    UNIQUE (person_id, sys_type)
);

CREATE TABLE sched (
    sched_id       VARCHAR(5) PRIMARY KEY,
    person_id      VARCHAR(5) NOT NULL,
    wk_hours       NUMERIC(5,2),
    def_wk_hours   NUMERIC(5,2),
    fte            NUMERIC(3,2),
    tz             VARCHAR(50) NOT NULL DEFAULT 'Asia/Seoul',
    eff_from       DATE NOT NULL,
    eff_to         DATE
);

CREATE TABLE absence (
    absence_id     VARCHAR(5) PRIMARY KEY,
    person_id      VARCHAR(5) NOT NULL,
    absence_type   VARCHAR(30) NOT NULL,
    start_at       TIMESTAMPTZ NOT NULL,
    end_at         TIMESTAMPTZ NOT NULL,
    status         VARCHAR(20) NOT NULL DEFAULT 'REQUESTED'
);

CREATE TABLE exist_task (
    exist_task_id     VARCHAR(5) PRIMARY KEY,
    assignee_person_id   VARCHAR(5),  -- person_id 참조(FK 없음)
    jira_issue_id        VARCHAR(50) NOT NULL,
    status                VARCHAR(20),
    priority              VARCHAR(20),
    start_at              TIMESTAMPTZ,
    due_at                TIMESTAMPTZ,
    remaining             NUMERIC(6,2),
    spent                 NUMERIC(6,2)
);

CREATE TABLE cal_event (
    cal_event_id    VARCHAR(5) PRIMARY KEY,
    person_id             VARCHAR(5) NOT NULL,
    event_type            VARCHAR(30) NOT NULL,
    start_at              TIMESTAMPTZ NOT NULL,
    end_at                TIMESTAMPTZ NOT NULL,
    availability_impact   NUMERIC(5,2)
);

-- =====================================================================
-- PAGE 3-C | 플랫폼 운영·권한 — Tier 2 (PERSON 의존)
-- 팀장이 HR PERSON을 지정해 초대 코드를 발급하고, 팀원이 로그인 후
-- 코드를 수락하면 USER_ACCOUNT와 PERSON이 매핑된다. 이메일 비교가 아니라
-- 초대 코드가 특정 PERSON에 미리 연결되어 있는 방식(PERSON_LINK의
-- ext_email 매칭과는 다른 신뢰 모델)이라 PERSON_LINK를 재사용하지 않고
-- 별도 테이블로 둔다. FK는 다른 테이블과 동일하게 걸지 않고 Repository의
-- _require_record()로 참조를 검증한다.
-- =====================================================================

CREATE TABLE member_invite (
    invite_id     VARCHAR(5) PRIMARY KEY,
    team_org_id   VARCHAR(5) NOT NULL,   -- 초대 스코프 조직 = org.org_id(FK 없음)
    person_id     VARCHAR(5) NOT NULL,   -- 연결 대상 HR 직원 = person.person_id(FK 없음)
    invited_by    VARCHAR(5) NOT NULL,   -- 초대한 팀장 계정 = user_account.account_id(FK 없음)
    token_hash    VARCHAR(255) NOT NULL UNIQUE,  -- 초대 코드 원문은 저장하지 않고 해시만 저장
    status        VARCHAR(20) NOT NULL DEFAULT 'PENDING',  -- PENDING / ACCEPTED / EXPIRED / REVOKED
    expires_at    TIMESTAMPTZ NOT NULL,
    accepted_at   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 같은 PERSON에게 동시에 유효한(PENDING) 초대가 두 개 이상 발급되는 것을 방지
CREATE UNIQUE INDEX ux_member_invite_pending_person
    ON member_invite (person_id)
    WHERE status = 'PENDING';

CREATE TABLE user_person_link (
    link_id          VARCHAR(5) PRIMARY KEY,
    account_id       VARCHAR(5) NOT NULL,   -- user_account.account_id(FK 없음)
    person_id        VARCHAR(5) NOT NULL,   -- person.person_id(FK 없음)
    invite_id        VARCHAR(5),            -- 근거가 된 member_invite.invite_id(FK 없음)
    mapping_status   VARCHAR(20) NOT NULL DEFAULT 'VERIFIED',  -- VERIFIED / REVOKED
    match_method     VARCHAR(30) NOT NULL DEFAULT 'TEAM_INVITATION',
    linked_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at       TIMESTAMPTZ
);

-- 유효(VERIFIED)한 매핑 기준으로 PERSON 1명은 계정 1개에만 연결
CREATE UNIQUE INDEX ux_user_person_link_active_person
    ON user_person_link (person_id)
    WHERE mapping_status = 'VERIFIED';

-- =====================================================================
-- PAGE 3-A | 문서→지식→Task 파이프라인 — Tier 2 (PROJ 의존)
-- =====================================================================

CREATE TABLE doc (
    doc_id            VARCHAR(5) PRIMARY KEY,
    proj_id            VARCHAR(5) NOT NULL,
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
    know_item_id    VARCHAR(5) PRIMARY KEY,
    proj_id          VARCHAR(5) NOT NULL,
    semantic_type    VARCHAR(40) NOT NULL,
    title            VARCHAR(255) NOT NULL,
    content          TEXT NOT NULL,
    confidence       NUMERIC(4,3)
);

CREATE TABLE proj_know_model (
    model_id           VARCHAR(5) PRIMARY KEY,
    proj_id             VARCHAR(5) NOT NULL,
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
    doc_id            VARCHAR(5) NOT NULL,
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
    sync_id        VARCHAR(5) PRIMARY KEY,
    doc_id          VARCHAR(5) NOT NULL,
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
    model_id       VARCHAR(5) NOT NULL,
    know_item_id   VARCHAR(5) NOT NULL,
    incl_status    VARCHAR(20) NOT NULL DEFAULT 'INCLUDED',
    sort_ord       INT,
    PRIMARY KEY (model_id, know_item_id)
);

CREATE TABLE feat_cluster (
    cluster_id   VARCHAR(5) PRIMARY KEY,
    model_id      VARCHAR(5) NOT NULL,
    name          VARCHAR(200) NOT NULL,
    biz_scope     VARCHAR(200),
    summary       TEXT
);

CREATE TABLE task (
    task_id       VARCHAR(5) PRIMARY KEY,
    model_id       VARCHAR(5) NOT NULL,
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
    block_id        UUID NOT NULL,
    up_chunk_id     UUID,
    search_text     TEXT NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    chunk_idx       INT NOT NULL,
    token_cnt       INT,
    heading_path    TEXT[] NOT NULL DEFAULT '{}',
    chunker_ver     VARCHAR(30)
);

-- CHUNK와 1:1인 pgvector 검색 인덱스.
-- FK 제약은 사용하지 않으며 chunk_id 존재 여부는 적재 코드에서 검증한다.
CREATE TABLE vec_idx (
    chunk_id        UUID PRIMARY KEY,
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
    know_item_id   VARCHAR(5) NOT NULL,
    block_id        UUID NOT NULL,
    rel_type        VARCHAR(20) NOT NULL DEFAULT 'PRIMARY',
    src_ver         VARCHAR(50),
    confidence      NUMERIC(4,3),
    chunk_id        UUID,
    quote_text      TEXT,
    quote_hash      VARCHAR(100),
    src_locator     JSONB,
    PRIMARY KEY (know_item_id, block_id)
);

CREATE TABLE feat_cluster_item (
    cluster_id     VARCHAR(5) NOT NULL,
    know_item_id   VARCHAR(5) NOT NULL,
    sim_score       NUMERIC(4,3),
    merge_status    VARCHAR(20),
    PRIMARY KEY (cluster_id, know_item_id)
);

CREATE TABLE task_know_src (
    task_id        VARCHAR(5) NOT NULL,
    know_item_id   VARCHAR(5) NOT NULL,
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
    snap_id           VARCHAR(5) PRIMARY KEY,
    proj_id            VARCHAR(5) NOT NULL,
    model_id           VARCHAR(5),
    snap_as_of         TIMESTAMPTZ NOT NULL DEFAULT now(),
    policy_ver         VARCHAR(30),
    doc_version_set    JSONB
);

-- =====================================================================
-- PAGE 3-C | 플랫폼 운영·권한 — Tier 3 (PROJECT_SOURCE / AUDIT_LOG)
-- =====================================================================

CREATE TABLE audit_log (
    audit_id            VARCHAR(5) PRIMARY KEY,
    proj_id              VARCHAR(5),     -- nullable: 프로젝트와 무관한 계정 단위 행위도 있음(로그인 등)
    actor_account_id     VARCHAR(5) NOT NULL,
    action                VARCHAR(50) NOT NULL,   -- LOGIN / CONNECT / SYNC / APPROVE / REJECT 등
    target_type           VARCHAR(50),            -- 예: TASK, RECOMMENDATION_RESULT (다형 참조 — 어느 테이블인지는 이 값으로 구분, FK 없음)
    target_id             VARCHAR(5),
    payload               JSONB,
    occurred_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =====================================================================
-- PAGE 3-B | People DB — Tier 2 (ANA_SNAPSHOT / PERSON / EXISTING_TASK 의존)
-- =====================================================================

CREATE TABLE feat_ready_result (
    readiness_id      VARCHAR(5) PRIMARY KEY,
    snapshot_id        VARCHAR(5) NOT NULL,
    feature_type        VARCHAR(50) NOT NULL,
    status               VARCHAR(20) NOT NULL,   -- SUCCESS / PARTIAL / BLOCKED
    missing_data         JSONB,
    limitations          JSONB,
    confidence           NUMERIC(4,3),
    checked_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE person_snap (
    person_snap_id   VARCHAR(5) PRIMARY KEY,
    snapshot_id           VARCHAR(5) NOT NULL,
    person_id             VARCHAR(5) NOT NULL,
    role_json              JSONB,
    skills_json             JSONB,
    fte                    JSONB,
    absence                 JSONB,
    source_version           VARCHAR(30)
);

CREATE TABLE exist_task_snap (
    exist_task_snap_id     VARCHAR(5) PRIMARY KEY,
    snapshot_id            VARCHAR(5) NOT NULL,
    exist_task_id        VARCHAR(5) NOT NULL,
    assignee_person_id      VARCHAR(5),
    estimate                 NUMERIC(6,2),
    remaining                NUMERIC(6,2)
);

-- =====================================================================
-- PAGE 3-B | People DB — Tier 3 (배정 실행)
-- =====================================================================

CREATE TABLE assign_run (
    run_id          VARCHAR(5) PRIMARY KEY,
    snapshot_id      VARCHAR(5) NOT NULL,
    readiness_id     VARCHAR(5),
    model_version     VARCHAR(30),
    policy_version    VARCHAR(30),
    status            VARCHAR(20) NOT NULL DEFAULT 'RUNNING',
    requested_by      VARCHAR(5)
);

-- =====================================================================
-- PAGE 3-B | People DB — Tier 4 (실행 결과)
-- =====================================================================

CREATE TABLE workload_result (
    workload_result_id   VARCHAR(5) PRIMARY KEY,
    run_id                 VARCHAR(5) NOT NULL,
    person_id              VARCHAR(5) NOT NULL,
    effective_capacity      NUMERIC(6,2),
    current_allocation      NUMERIC(6,2),
    remaining_capacity      NUMERIC(6,2),
    load_rate                NUMERIC(5,2)
);

CREATE TABLE reco_result (
    reco_id   VARCHAR(5) PRIMARY KEY,
    run_id                VARCHAR(5) NOT NULL,
    task_id               VARCHAR(5) NOT NULL,
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
    cand_id       VARCHAR(5) PRIMARY KEY,
    reco_id   VARCHAR(5) NOT NULL,
    person_id            VARCHAR(5) NOT NULL,
    rank                  INT,
    fit_score              NUMERIC(5,2),
    expected_load           NUMERIC(5,2),
    is_alternative           BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE valid_result (
    valid_id        VARCHAR(5) PRIMARY KEY,
    reco_id     VARCHAR(5) NOT NULL,
    status                  VARCHAR(20) NOT NULL,
    missing_data             JSONB,
    confidence                NUMERIC(4,3)
);

-- =====================================================================
-- PAGE 3-B | People DB — Tier 6 (근거/체크/결정)
-- =====================================================================

CREATE TABLE reco_evidence (
    evidence_id      VARCHAR(5) PRIMARY KEY,
    cand_id       VARCHAR(5) NOT NULL,
    evidence_type        VARCHAR(30) NOT NULL,
    source_id             VARCHAR(5),   -- 다형 참조(어느 테이블의 근거인지 evidence_type으로 구분, FK 없음)
    reason                 TEXT,
    citation                TEXT,
    verified                BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE valid_check (
    valid_check_id   VARCHAR(5) PRIMARY KEY,
    valid_id           VARCHAR(5) NOT NULL,
    check_type                VARCHAR(50) NOT NULL,
    result                     VARCHAR(20) NOT NULL,
    actual_value                JSONB,
    expected_rule                 JSONB,
    severity                       VARCHAR(20)
);

CREATE TABLE decision_rec (
    decision_id              VARCHAR(5) PRIMARY KEY,
    reco_id          VARCHAR(5) NOT NULL,
    valid_id                VARCHAR(5),
    pm_action                     VARCHAR(20) NOT NULL,  -- APPROVE / MODIFY / REJECT
    reason                          TEXT,
    modified_cand_id            VARCHAR(5),
    decided_by                        VARCHAR(5),
    decided_at                          TIMESTAMPTZ NOT NULL DEFAULT now()
);
