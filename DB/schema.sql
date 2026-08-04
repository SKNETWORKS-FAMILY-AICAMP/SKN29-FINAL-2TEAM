-- =====================================================================
-- AI 프로젝트 운영 코파일럿 — 전체 PostgreSQL 스키마
-- 생성일: 2026-07-28
--
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

-- =====================================================================
-- 네임스페이스 분리 (2026-07-31)
--
-- `mock_hr`  : 고객사 HR 시스템의 데이터. 우리가 만드는 것이 아니라 **읽기만**
--              하는 남의 시스템이다. Workday API를 붙일 수 없어(결제한 기업
--              고객 전용) 같은 모양의 DB로 대신하고 있을 뿐, 그 역할은 계속된다.
-- `public`   : 우리 플랫폼이 소유하는 데이터. 계정·팀·프로젝트·문서·배정 등.
--
-- 나누는 이유는 "언젠가 진짜 HR로 교체하려고"가 아니다. 교체할 일은 없다.
-- 설계 의도상 남의 시스템인데 코드가 우리 테이블처럼 조인해 쓰던 것을 막기
-- 위해서다. 경계는 이미 코드(`backend/services/hr/`)로 세웠고, 스키마 분리는
-- 그 경계를 DB에서도 눈에 보이게 만든다 — 앞으로 `mock_hr.`를 타이핑하지 않고
-- HR 테이블을 건드리는 일은 없다.
--
-- 애플리케이션은 search_path에 기대지 않고 항상 `mock_hr.`를 명시한다.
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS mock_hr;


-- =====================================================================
-- PAGE 3-C | 플랫폼 운영·권한 — Tier 0 (의존성 없음)
-- =====================================================================


CREATE TABLE user_account (
    account_id      VARCHAR(5) PRIMARY KEY,
    email           VARCHAR(255) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,           -- 애플리케이션에서 bcrypt/argon2로 해싱 후 저장, 평문 절대 금지
    display_name    VARCHAR(100) NOT NULL,
    account_status  VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE / LOCKED / WITHDRAWN
    -- [운영자 콘솔] 관리자 로그인 허용 플래그(2026-07-30 추가). 이메일 패턴 매칭이
    -- 아니라 이 플래그로만 관리자를 판별한다. API로 자기 자신·타인을 승격시키는
    -- 경로는 없고, backend/services/createDB/grant_admin.py로만 켤 수 있다.
    is_admin        BOOLEAN      NOT NULL DEFAULT false,
    -- 이 계정이 속한 팀(2026-07-31 추가) = team.team_id(FK 없음). 팀장은 팀 생성 시,
    -- 팀원은 초대 수락 시 채워진다. 이 값이 곧 테넌트 경계다.
    team_id         VARCHAR(5),
    -- 프로필 사진이 저장소 어디에 있는가(2026-08-04 추가). 파일 경로가 아니라
    -- 저장소 안에서의 키다 — 지금은 로컬 디스크지만 S3로 바뀌어도 이 값은
    -- 그대로 쓴다. 안 올렸으면 NULL 이고 화면이 이름 첫 글자로 대신한다.
    avatar_key      VARCHAR(255),
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- [팀] 우리 플랫폼을 쓰는 단위(2026-07-31 추가).
--
-- HR 조직(`org`)과 다르다. HR에서는 한 회사지만 우리 플랫폼을 쓰는 것은 회사
-- 전체가 아니라 그 안의 그룹이다. 그래서 팀은 조직도에서 유도하지 않고 팀장이
-- 온보딩에서 이름을 붙여 명시적으로 만든다 — 그래야 팀원의 소속을 추론이 아니라
-- 조회로 알 수 있다(조직도만으로는 "어디까지가 우리 그룹인가"에 표시가 없다).
CREATE TABLE team (
    team_id           VARCHAR(5) PRIMARY KEY,
    name              VARCHAR(100) NOT NULL,   -- 팀장이 입력한 팀명
    owner_account_id  VARCHAR(5)  NOT NULL,    -- 만든 팀장 = user_account.account_id(FK 없음)
    src_org_id        VARCHAR(5),              -- 만들 당시 팀장의 HR 소속 = org.org_id. 후보 범위의 근거로 남긴다
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- [팀] 팀에 속한 HR 직원. 계정이 아직 없어도(초대 전·미수락) 팀원이다 —
-- 업무 배정 대상은 계정이 아니라 사람이기 때문이다.
CREATE TABLE team_member (
    team_member_id  VARCHAR(5) PRIMARY KEY,
    team_id         VARCHAR(5)  NOT NULL,   -- team.team_id(FK 없음)
    person_id       VARCHAR(5)  NOT NULL,   -- person.person_id(FK 없음)
    added_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (team_id, person_id)
);

-- [팀] 읽어들일 Google Drive 폴더(2026-08-04 추가). **프로젝트가 아니라 팀에 매단다.**
-- 폴더는 "파일이 어디 있는지"를 알려주는 경로일 뿐이고, 어느 프로젝트의 문서인지는
-- 파일을 열어 봐야 안다. 프로젝트마다 폴더를 다시 고르게 하면 같은 경로를 프로젝트
-- 수만큼 반복해서 등록하게 된다.
CREATE TABLE team_folder (
    team_folder_id      VARCHAR(5) PRIMARY KEY,
    team_id             VARCHAR(5)  NOT NULL,   -- team.team_id(FK 없음)
    conn_id             VARCHAR(5)  NOT NULL,   -- connector_conn.conn_id(FK 없음). 어느 연결로 읽는가
    external_folder_id  VARCHAR(255) NOT NULL,  -- 실제 Drive 폴더 ID
    display_name        VARCHAR(255),           -- 고를 때 Drive가 알려준 이름. 비면 화면이 ID로 대체한다
    default_doc_role    VARCHAR(30),            -- 이 폴더의 기본 문서 역할. doc.doc_role이 상속한다
                                                -- (PLAN / MEETING_NOTE / DAILY_REPORT / OTHER)
    max_depth           INT,                    -- 탐색 깊이. 1이면 선택한 폴더만, NULL이면 제한 없음
    UNIQUE (team_id, external_folder_id)
);

-- =====================================================================
-- PAGE 3-B | People DB — Tier 0   [스키마: mock_hr]
-- org/level/skill도 전부 VARCHAR(5) 코드 체계(위 설계 방침 참고).
--
-- 여기부터 mock_hr 스키마다. 우리가 쓰지 않고 읽기만 하는 고객사 HR 데이터.
-- =====================================================================

CREATE TABLE mock_hr.org (
    org_id      VARCHAR(5) PRIMARY KEY,
    up_org_id   VARCHAR(5),          -- 상위 조직(자기 참조, FK 없음)
    mgr_id      VARCHAR(5),          -- 조직 관리자 = person_id(FK 없음). ORG↔PERSON이 서로를 가리키는 순환 참조라 애초에 FK를 걸 수 없는 구조이기도 하다
    name        VARCHAR(100) NOT NULL,
    org_type    VARCHAR(30),
    status      VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
);

CREATE TABLE mock_hr.level (
    level_id  VARCHAR(5) PRIMARY KEY,
    code      VARCHAR(20) NOT NULL,
    name      VARCHAR(50) NOT NULL,
    rank_ord  INT NOT NULL,
    status    VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
);

CREATE TABLE mock_hr.skill (
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
    owner_account_id  VARCHAR(5),
    -- 이 프로젝트를 하는 팀(2026-08-04 추가) = team.team_id(FK 없음). 소유 계정만으로는
    -- 팀원이 팀의 프로젝트를 볼 수 없다. 테넌트 경계가 팀이므로 프로젝트도 팀에 매단다.
    team_id           VARCHAR(5),
    -- 만든 시각(2026-08-04 추가). 프로젝트 목록의 "최신순" 정렬과 날짜 표시가
    -- 근거로 삼을 값이 없었다. 이 컬럼이 생기기 전에 만들어진 행은 NULL이고
    -- 화면이 '-'로 보여준다 — 모르는 날짜를 지어내지 않는다.
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
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

-- 이 프로젝트가 대응하는 Jira 프로젝트. **프로젝트 하나에 Jira 프로젝트 하나다**
-- (2026-08-04). Jira 프로젝트 하나에는 프로젝트 하나의 업무가 들어 있으므로, 여러 개를
-- 한 프로젝트에 매달면 서로 다른 프로젝트의 업무가 한 진행률로 뭉개진다.
--
-- Drive 폴더는 여기 없다 — 팀에 속하므로 team_folder로 옮겼다(2026-08-04).
CREATE TABLE proj_source (
    proj_source_id   VARCHAR(5) PRIMARY KEY,
    proj_id              VARCHAR(5) NOT NULL UNIQUE,   -- UNIQUE가 곧 1:1 강제다
    conn_id        VARCHAR(5) NOT NULL,
    source_type          VARCHAR(30) NOT NULL,   -- JIRA_PROJECT
    external_source_id   VARCHAR(255) NOT NULL,  -- Jira 프로젝트 키
    -- 고를 때 원본이 알려준 표시 이름(2026-08-03 추가). 'KAN'이 아니라
    -- 'SKN29_Final_2Team'을 화면에 쓰기 위한 것이다. 매번 원본에 물어보면
    -- 화면이 커넥터 생존에 묶이므로 선택 시점에 같이 저장한다. 원본에서
    -- 이름이 바뀌면 다시 고를 때 갱신된다. 비어 있으면 화면이 키로 대체한다.
    display_name          VARCHAR(255),
    sync_status           VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    -- 이 소스를 마지막으로 읽어들인 시각(2026-08-04 추가). 화면이 "지금 보는 숫자가
    -- 언제 것인지"를 말할 수 있어야 갱신 버튼을 누를지 판단할 수 있다. 한 번도
    -- 안 읽었으면 NULL — 0건과 미수집은 다른 상태다
    last_sync_at          TIMESTAMPTZ
);

-- =====================================================================
-- PAGE 3-B | People DB — Tier 1 (org/level 의존)   [스키마: mock_hr]
-- =====================================================================

CREATE TABLE mock_hr.person (
    person_id   VARCHAR(5) PRIMARY KEY,
    emp_id      VARCHAR(30) NOT NULL UNIQUE,
    name        VARCHAR(100) NOT NULL,
    email       VARCHAR(255) NOT NULL UNIQUE,
    org_id      VARCHAR(5),
    job_role    VARCHAR(100),
    level_id    VARCHAR(5),
    emp_status  VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
);


CREATE TABLE mock_hr.person_skill (
    person_id    VARCHAR(5) NOT NULL,
    skill_id     VARCHAR(5) NOT NULL,
    proficiency  INT NOT NULL CHECK (proficiency BETWEEN 1 AND 5),
    source       VARCHAR(30),
    confidence   NUMERIC(4,3),
    PRIMARY KEY (person_id, skill_id)
);

-- Figma 레이어명은 IDENTITY_LINK, 테이블 표시명은 "link"
CREATE TABLE mock_hr.person_link (
    person_link_id     VARCHAR(5) PRIMARY KEY,
    person_id   VARCHAR(5) NOT NULL,
    sys_type    VARCHAR(30) NOT NULL,   -- 외부 시스템 유형(JIRA 등)
    ext_email   VARCHAR(255) NOT NULL,
    reg_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (sys_type, ext_email),
    UNIQUE (person_id, sys_type)
);

CREATE TABLE mock_hr.sched (
    sched_id       VARCHAR(5) PRIMARY KEY,
    person_id      VARCHAR(5) NOT NULL,
    wk_hours       NUMERIC(5,2),
    def_wk_hours   NUMERIC(5,2),
    fte            NUMERIC(3,2),
    tz             VARCHAR(50) NOT NULL DEFAULT 'Asia/Seoul',
    eff_from       DATE NOT NULL,
    eff_to         DATE
);

CREATE TABLE mock_hr.absence (
    absence_id     VARCHAR(5) PRIMARY KEY,
    person_id      VARCHAR(5) NOT NULL,
    absence_type   VARCHAR(30) NOT NULL,
    start_at       TIMESTAMPTZ NOT NULL,
    end_at         TIMESTAMPTZ NOT NULL,
    status         VARCHAR(20) NOT NULL DEFAULT 'REQUESTED'
);

CREATE TABLE exist_task (
    exist_task_id     VARCHAR(5) PRIMARY KEY,
    -- 이 이슈를 어느 소스에서 가져왔는가(2026-08-03 추가). 이 컬럼이 없던 동안은
    -- 재동기화 때 지울 범위를 특정할 수 없어 최초 1회 적재밖에 못 하는 구조였다.
    -- proj_id가 아니라 proj_source_id인 이유: 재동기화의 단위가 소스이기 때문이다.
    -- (2026-08-04부터 proj_source에 UNIQUE (proj_id)가 걸려 Jira는 1:1이지만,
    --  지울 범위를 특정한다는 이 컬럼의 역할은 그대로다.)
    proj_source_id       VARCHAR(5) NOT NULL,   -- proj_source.proj_source_id(FK 없음)
    assignee_person_id   VARCHAR(5),  -- person_id 참조(FK 없음)
                                      -- NULL = 담당자 이메일이 person_link에 없음.
                                      -- 행을 버리지 않는다 — 버리면 부하 총량이 조용히 줄어든다.
                                      -- Readiness에서 "미매핑 담당자"로 올려 PM이 알게 한다.
    jira_issue_id        VARCHAR(50) NOT NULL,
    -- 이슈 제목(2026-08-04 추가). 없으면 업무 목록이 'KAN-34'만 늘어놓게 되어
    -- 무슨 일인지 알 수 없다. Jira에서 바뀌면 재동기화 때 따라 바뀐다.
    summary               VARCHAR(500),
    status                VARCHAR(20),   -- Jira 표시 문자열(프로젝트마다 다름). 로직에 쓰지 말 것
    -- Jira 표준 상태 카테고리(2026-08-03 추가). 로직은 이 값만 본다.
    -- 같은 카테고리인데 KAN은 '해야 할 일', AIP는 '할 일'로 표시된다(실측).
    -- statusCategory.name도 지역화되므로 안전한 값은 key 하나뿐이다.
    -- 'TO_DO' | 'IN_PROGRESS' | 'DONE'  ← 수집 단계에서 key를 변환해 넣는다
    status_category       VARCHAR(20),
    priority              VARCHAR(20),
    start_at              TIMESTAMPTZ,
    due_at                TIMESTAMPTZ,
    -- 최초 추정치(2026-08-03 추가). exist_task_snap.estimate가 이 값을 복사해 간다 —
    -- 기존에는 snap에만 있고 원본에 없어 채울 곳이 없었다.
    estimate              NUMERIC(6,2),
    remaining             NUMERIC(6,2),
    spent                 NUMERIC(6,2)
);

-- 같은 소스에서 같은 이슈를 두 번 넣으면 그 사람 부하가 2배로 잡힌다.
-- 재동기화를 delete-then-insert로 짜든 upsert로 짜든 이 제약이 마지막 방어선이다.
CREATE UNIQUE INDEX ux_exist_task_source_issue
    ON exist_task (proj_source_id, jira_issue_id);

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
    team_id       VARCHAR(5),            -- 어느 팀으로 들어오는 초대인가(2026-07-31 추가) = team.team_id(FK 없음)
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
    -- 이 문서를 등록한 팀(2026-08-04 추가) = team.team_id(FK 없음). 문서는 팀의
    -- Drive 폴더에서 나오므로 등록 시점에는 팀에만 속한다.
    team_id            VARCHAR(5),
    -- 어느 프로젝트의 문서인가. **등록 시점에는 모른다**(2026-08-04 NULL 허용).
    -- 파일을 열어 봐야 알 수 있고, 프로젝트의 메인·서브 문서로 지정될 때 채워진다.
    -- NOT NULL이던 시절에는 폴더를 고르는 것만으로 프로젝트가 만들어져야 했다.
    proj_id            VARCHAR(5),
    src_file_id        VARCHAR(255),
    -- 원천의 리비전 식별자. Drive의 headRevisionId가 실측 51자라 VARCHAR(50)으로는
    -- 한 글자가 모자랐다(2026-07-31 확대). 길이를 보장하는 문서가 없어 여유를 뒀다.
    cur_revision       VARCHAR(100),
    content_hash       VARCHAR(100),
    -- 내려받은 원문이 문서 저장소 어디에 있는가(2026-07-31 추가). 파일 경로 자체가
    -- 아니라 저장소 안에서의 키다 — 지금은 로컬 디스크지만 나중에 S3로 바뀌어도
    -- 이 값은 그대로 쓸 수 있어야 한다. 아직 안 받았으면 NULL.
    storage_key        VARCHAR(255),
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

-- [운영자 콘솔] 플랫폼 전역 설정 키-값 저장소(2026-07-30 추가). 첫 사용처는
-- 초대 코드 만료 기간(기존에는 MemberInviteRepository.INVITE_TTL_DAYS에 14일로
-- 하드코딩돼 있던 값)을 운영자가 화면에서 바꿀 수 있게 하는 것.
CREATE TABLE sys_setting (
    setting_key    VARCHAR(50) PRIMARY KEY,
    setting_value  TEXT NOT NULL,
    updated_by     VARCHAR(5),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO sys_setting (setting_key, setting_value) VALUES ('INVITE_EXPIRE_DAYS', '14');

-- [운영자 콘솔] 플랫폼 시스템 공지(2026-07-30 추가).
CREATE TABLE sys_notice (
    notice_id      VARCHAR(5) PRIMARY KEY,
    title          VARCHAR(200) NOT NULL,
    content        TEXT NOT NULL,
    status         VARCHAR(20) NOT NULL DEFAULT 'SCHEDULED',  -- PUBLISHED / SCHEDULED / ENDED
    schedule_at    TIMESTAMPTZ NOT NULL,
    schedule_mode  VARCHAR(10) NOT NULL,  -- FROM / UNTIL (부터 / 까지)
    created_by     VARCHAR(5),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =====================================================================
-- PAGE 3-B | People DB — Tier 2 (ANA_SNAPSHOT / PERSON / EXISTING_TASK 의존)
-- 아래는 public이다. FigJam에서 같은 페이지에 있을 뿐, HR이 주는 데이터가
-- 아니라 우리가 분석해서 만든 결과다(스냅샷·배정 실행·추천·검증·결정).
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
