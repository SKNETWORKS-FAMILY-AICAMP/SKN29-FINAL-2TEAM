-- =====================================================================
-- halil — 전체 PostgreSQL 스키마
-- 생성일: 2026-07-28 (제품명이 「AI 프로젝트 운영 코파일럿」이던 때)
--
-- 사용자·DB 이름의 `project_copilot` 은 그때 이름이 남은 것이다. 일부러 그대로
-- 둔다 — 바꾸면 팀원 전원이 로컬 볼륨을 버리고 DB 를 다시 만들어야 한다.
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
    -- 팀 업무량 기준(2026-08-04 추가). 셋 다 NULL 이면 "설정 안 함"이고 각각
    -- HR 값·100%·4주를 쓴다. 값을 복사해 두지 않는 이유는 HR 이 바뀌면 우리
    -- 사본이 조용히 낡기 때문이다 — 팀장이 명시적으로 정한 것만 담는다.
    --
    -- capacity_wk_hours 는 사람마다 다른 HR 값을 팀 하나로 덮어쓴다. 시간제
    -- 근무자가 있으면 그 사람 값까지 덮으므로 화면이 그 사실을 밝힌다.
    capacity_wk_hours NUMERIC(5,2),        -- 팀 공통 주 근무시간. NULL 이면 HR 의 사람별 값
    overload_pct      INT,                     -- 이 비율을 넘으면 과부하로 본다. NULL 이면 100
    workload_weeks    INT,                     -- 부하 조회 기본 기간(주). NULL 이면 4
    -- 등록된 외부 가드레일을 **못 불렀을 때** 이 팀의 대화를 어떻게 하나
    -- (2026-08-24). 사내 도구면 그대로 보내는 게 맞지만, 규제 고객에게는
    -- 「검사 못 했는데 그냥 보냈다」가 계약 위반이 된다. 등록물이 아니라 팀에
    -- 붙인다 — 등록에 붙이면 공급자를 갈아탈 때 정책이 조용히 바뀐다.
    guardrail_on_failure VARCHAR(10) NOT NULL DEFAULT 'OPEN',  -- OPEN / CLOSED
    -- 팀 기본 채팅 모델(2026-08-22, DB/migrations/2026-08-22_team_default_model.sql).
    -- NULL 이면 "설정 안 함"이고 코드 기본값(services/harness/runner.py 의
    -- DEFAULT_MODEL)을 쓴다. 원래는 레거시 정문 에이전트(agent_tool.tool_ref
    -- ='agent:*')의 agent.model 에 얹혀 있었는데, 레거시 폐기와 함께 팀 설정
    -- 본래 자리로 옮겼다 — 신규 기본 챗(agents.is_default_chat)은 위임하지
    -- 않아 정문과 의미가 다르고, agent_versions 는 불변이라 값을 고칠 자리가
    -- 아니다.
    default_model     VARCHAR(100),
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
    -- 무엇을 하는 프로젝트인가(2026-08-11 추가). 만들 때 이름과 이 문장으로
    -- 팀 문서 풀에서 기준 문서 후보를 찾는다 — 이름만으로는 요약 임베딩
    -- 질의가 너무 짧아 아무 문서나 걸린다.
    description       VARCHAR(500),
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
                                              -- MODEL_API 도 이 표를 쓴다(2026-08-13). 팀에 등록한 모델은
                                              -- 「연결 서비스」가 아니므로 그 화면들은 유형으로 걸러야 한다
    granted_scopes            JSONB NOT NULL DEFAULT '[]',
    auth_status                VARCHAR(20) NOT NULL DEFAULT 'CONNECTED',  -- CONNECTED / EXPIRED / ERROR
                                              -- REVOKED: 운영자가 강제 해제(2026-08-13). 자격증명만 지우고
                                              -- 행은 남긴다 — 재연결이 같은 conn_id 를 다시 쓰기 때문이다
                                              -- (team_folder·proj_source 가 FK 없이 이 값을 가리킨다)
    encrypted_credential_ref  TEXT,           -- 외부 자격증명의 DB 저장용 암호문(기존 ref 명칭 유지). People DB는 자격증명이 없어 NULL
                                              -- VARCHAR(255)로는 부족하다: Fernet 암호문이 Jira 1700자, Drive 632자다(255자는 평문 127바이트까지만 수용)
    -- 증분 동기화의 재개 지점(2026-08-24). Drive 는 changes API 의 pageToken 이
    -- 들어간다. NULL 이면 아직 기준점을 안 잡은 상태다.
    --
    -- `drive_page_token` 이 아니라 중립적인 이름인 이유 — 계획된 저장소 넷 중
    -- 델타 API 가 있는 것은 Drive·SharePoint 뿐이고(Notion·Confluence 는 수정
    -- 시각 폴링밖에 없다), 값의 모양도 저장소마다 다르다.
    sync_cursor               TEXT,
    -- Drive 변경 알림 채널(2026-08-25). `changes.watch` 로 열어 두면 바뀔 때
    -- Google 이 알려 준다 — 대화를 열 때마다 우리가 묻던 것을 대신한다.
    --
    -- 셋 다 NULL 이 정상이다: **채널이 없는 상태는 고장이 아니다.** 아직 안 연
    -- 연결이고, 그때는 대화 시작 시 동기화가 받쳐 준다.
    channel_id                VARCHAR(64),    -- 우리가 만든 채널 id. 알림이 이것만 들고 온다
    channel_resource_id       VARCHAR(255),   -- Google 이 준 값. channels.stop 에 id 와 함께 필요하다
                                              -- 없으면 채널을 못 멈춰 만료까지 알림이 계속 온다
    channel_expires_at        TIMESTAMPTZ,    -- 만료 시각. changes 채널은 최대 1주이고 자동 갱신이 없다
    connected_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 알림은 채널 id 하나만 들고 온다. 그것으로 연결을 찾는 것이 가장 잦은 경로다.
CREATE UNIQUE INDEX ux_connector_conn_channel
    ON connector_conn (channel_id) WHERE channel_id IS NOT NULL;

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
    -- 이 문서를 등록한 팀(2026-08-04 추가) = team.team_id(FK 없음). 커넥터 문서는
    -- 팀의 Drive 폴더에서 나오므로 등록 시점에는 팀에만 속한다.
    --
    -- **사용자가 올린 개인 문서는 여기가 NULL 이다**(2026-08-18 · 「내 파일」).
    -- 그게 핵심이다 — 팀 문서를 읽는 자리가 전부 `WHERE d.team_id = %s` 로 거는데,
    -- NULL 이면 그 자리들이 한 줄도 안 바뀐 채 개인 문서를 걸러낸다. 조건을
    -- 빠뜨렸을 때 새는 것이 아니라 안 보이는 쪽으로 틀린다.
    team_id            VARCHAR(5),
    -- 개인 소유 문서를 올린 계정 = user_account.account_id(FK 없음). 팀 문서는 NULL.
    -- team_id 와 정확히 하나만 채워진다(아래 doc_owner_xor_team).
    owner_account_id   VARCHAR(5),
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
    -- 이 문서가 `proj_id` 프로젝트에서 맡는 역할(2026-08-04 의미 변경).
    --   NULL      아직 어느 프로젝트에도 안 묶인 팀 문서 풀
    --   'PRIMARY' 업무를 뽑아낼 기준 문서. 프로젝트당 하나(아래 유일 인덱스)
    --   'SUB'     근거 검색에 함께 쓰는 문서
    --
    -- 예전에는 문서의 **종류**('PLAN'/'MEETING_NOTE'/'DAILY_REPORT'/'OTHER')였다.
    -- 폴더에 역할을 주고 안의 파일이 물려받는 방식이라 「01_기획」에 든 것은
    -- 요구사항 정의서든 화면설계서든 전부 기획서가 됐고(실측 3건 중 2건이 오분류),
    -- 등록 뒤에 고칠 경로도 없었다. 정작 그 값으로 분기하는 코드는 한 줄도 없었다.
    -- 어느 문서가 근거인지는 사람이 기준 문서 선택 화면에서 고르는 쪽이 정확해서,
    -- 종류 대신 프로젝트와의 관계를 담는다.
    doc_role           VARCHAR(30),
    acl_principals     TEXT[] NOT NULL DEFAULT '{}',
    src_modified_at    TIMESTAMPTZ,
    deleted            BOOLEAN NOT NULL DEFAULT false,
    access_revoked     BOOLEAN NOT NULL DEFAULT false,
    -- 「내 파일」 라이브러리의 toggle(2026-08-18). **`search_ready` 와 다르다** —
    -- 그쪽은 칸이 아니라 계산값이고(청크가 있는지 EXISTS 로 본다) 이 값은 의도다.
    -- 껐는데 청크는 남아 있는 상태가 정상이다. 뭉개면 끌 때 색인을 지워야 하고
    -- 다시 켤 때 또 파싱한다.
    --
    -- 팀 문서에는 뜻이 없다 — 커넥터 문서는 시스템이 필요할 때 승격시키지 사람이
    -- 켜지 않는다(8/15). 그래서 기본값 true 이고 개인 문서에서만 읽는다.
    search_enabled     BOOLEAN NOT NULL DEFAULT true,
    -- 청크 파싱·임베딩 단계의 상태(2026-08-18). RUNNING / FAILED / NULL.
    -- NULL 은 「아직 안 돌렸거나 끝났거나」 둘 다다 — 끝난 것은 청크가 있는지
    -- (`search_ready`)가 말해 주므로 값을 따로 두지 않는다.
    --
    -- ⚠ 이 줄은 **2026-08-24 에 뒤늦게 옮겨 적었다.** 마이그레이션
    -- (`2026-08-18_doc_index_status.sql`)에만 있고 여기엔 없어서, 이 파일로
    -- DB 를 새로 만들면 컬럼이 빠졌다. 같은 날 추가된 `search_enabled` 는
    -- 반영됐는데 이것만 누락된 것이다 — 8/18 배포가 깨진 것과 같은 종류다.
    index_status       VARCHAR(20),
    -- 색인이 **왜** 실패했는지, 사람이 읽을 문구(2026-08-24). FAILED 일 때만
    -- 채우고 성공하면 상태와 함께 NULL 로 되돌린다. 없앤 `doc_meta.extract_detail`
    -- 이 하던 역할을 색인 단계로 옮긴 것이다 — 「실패했다」만 알고 이유를 모르는
    -- 상태를 만들지 않으려는 것이 요점이다.
    index_detail       TEXT,
    -- 이 문서를 데려온 뿌리 폴더 = team_folder.team_folder_id(FK 없음), 2026-08-25.
    -- 「문서」 화면이 좌측 트리를 그리는 근거다. 어느 저장소 연결에서 왔는지는
    -- team_folder.conn_id 를 따라가면 나온다.
    --
    -- 개인 문서(「내 파일」)는 폴더에서 온 것이 아니라 NULL 이다.
    team_folder_id     VARCHAR(5),
    -- 뿌리 폴더 안에서의 상대 경로. clients.list_drive_files 의 folder_path 를
    -- 그대로 받는다 — 빈 문자열이면 뿌리 바로 아래이고 '기획/요구사항' 처럼 이어진다.
    --
    -- **NULL 과 빈 문자열의 뜻이 다르다.** NULL 은 「모른다」(이 칸이 생기기 전에
    -- 등록된 문서)이고 ''는 「뿌리 바로 아래」다. 뭉치면 화면이 옛 문서를 뿌리에
    -- 있는 것처럼 그린다.
    --
    -- 하위 폴더 구조를 담는 표를 따로 두지 않는다. 트리의 뿌리는 team_folder 가,
    -- 그 아래 가지는 이 값들의 서로 다른 조합이 만든다 — Drive 에서 폴더가 바뀌어도
    -- 다음 수집이 문서와 함께 갱신하므로 맞춰 줄 두 번째 표가 없다.
    src_folder_path    TEXT,
    -- 팀 것도 내 것도 아닌 문서, 그리고 둘 다인 문서를 막는다. 둘 다인 행이
    -- 생기면 그 순간 팀 검색에 개인 파일이 섞인다.
    CONSTRAINT doc_owner_xor_team CHECK (
        (team_id IS NOT NULL AND owner_account_id IS NULL)
     OR (team_id IS NULL AND owner_account_id IS NOT NULL)
    )
);

CREATE INDEX ix_doc_owner ON doc (owner_account_id) WHERE owner_account_id IS NOT NULL;

-- 「문서」 화면은 폴더로 묶어 보는 것이 기본 동작이다(2026-08-25).
CREATE INDEX idx_doc_team_folder ON doc (team_id, team_folder_id);

-- 기준 문서는 프로젝트당 하나다. 화면이 라디오라 둘이 될 일이 없어 보여도,
-- 두 건이 되면 어느 것으로 업무를 뽑았는지 알 수 없어 조용히 틀린다.
CREATE UNIQUE INDEX ux_doc_primary_per_proj
    ON doc (proj_id) WHERE doc_role = 'PRIMARY' AND deleted = false;

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
    -- doc.cur_revision과 같은 값을 담는다. Drive의 headRevisionId가 실측 51자라
    -- VARCHAR(50)으로는 한 글자가 모자랐다(2026-08-04 확대). doc 쪽만 2026-07-31에
    -- 넓혀 두는 바람에, 원문은 들어가는데 파싱 결과를 적재할 때 터지는 상태였다.
    revision          VARCHAR(100) NOT NULL,
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
    -- 위 doc_block.revision과 같은 이유로 100자다(2026-08-04). 아직 이 테이블에
    -- 쓰는 코드는 없지만, 담을 값이 같아서 지금 맞춰 두지 않으면 나중에 같은
    -- 사고를 한 번 더 겪는다.
    revision        VARCHAR(100),
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
    -- EmbeddingGemma(google/embeddinggemma-300m)의 출력 차원(2026-08-04 축소).
    -- 1536이던 시절은 OpenAI text-embedding-3-small을 전제한 것인데, 파이프라인이
    -- EmbeddingGemma로 확정되면서 맞지 않게 됐다. 적재와 검색이 같은 모델을 써야
    -- 하므로 차원은 한 곳에서만 정해진다.
    embedding       VECTOR(768) NOT NULL,
    metadata        JSONB NOT NULL DEFAULT '{}',
    indexed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    embed_model     VARCHAR(100),
    embed_ver       VARCHAR(30),
    embed_dim       INT,
    dist_metric     VARCHAR(20) NOT NULL DEFAULT 'COSINE',
    content_hash    VARCHAR(100),
    revision        VARCHAR(100),
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

-- ---------------------------------------------------------------------
-- ⚠ 아래 18개 테이블은 **어떤 애플리케이션 코드도 읽거나 쓰지 않는다**
--   (2026-08-13 전수 확인). `DB/reset_demo.sql` 의 TRUNCATE 에만 등장한다 —
--   초기화는 하지만 아무도 채우지 않는 상태다.
--
--   ① 이름조차 코드에 없는 것 (10)
--      doc_sync · model_know_item · feat_cluster · know_item_src ·
--      feat_cluster_item · task_know_src · person_snap · reco_cand ·
--      reco_evidence · valid_check
--
--   ② 「여기에 저장하지 않는다」는 주석으로만 등장하는 것 (8)
--      cal_event · workload_result · reco_result · valid_result ·
--      decision_rec · assign_run · ana_snapshot · feat_ready_result
--
--   스키마를 먼저 설계하고 구현이 시작되지 않은 자리다. 추천·검증·결정
--   파이프라인은 제품이 업무 배정 추천에서 물러나며 폐기됐고, 그 읽기 쪽
--   (운영자 콘솔 「분석·결정 기록」 탭)과 쓰기 쪽(배정 실행 API)은 같은 날
--   걷었다 — 뒤의 셋(assign_run·ana_snapshot·feat_ready_result)이 그때 이쪽으로
--   넘어왔다.
--
--   **지금 지우지 않는다**(2026-08-13 PM 결정). 이유가 셋이다.
--   1. Agent 런타임 쪽에서 스키마 마이그레이션 작업이 진행 중이라, 같은 파일을
--      양쪽에서 고치면 충돌이 「한쪽이 지운 것을 다른 쪽이 고친」 모양이 된다.
--   2. 문서→지식 체인(doc_sync·know_item_src·task_know_src·model_know_item·
--      feat_cluster*)은 **지금 고도화 중인 파이프라인의 자리**다. 담당자에게
--      쓸 것인지 먼저 물어야 한다.
--   3. 팀원 전원이 로컬 DB 를 다시 만들어야 하고 산출물 ERD 와도 어긋난다.
--
--   **Agent 파트가 정리된 뒤 다시 확인한다.** 그때는 ②의 추천·검증·결정 계열
--   부터 보면 된다 — 폐기가 확정된 것들이다.
-- ---------------------------------------------------------------------

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

-- =====================================================================
-- Agent Platform (2026-08-11 추가)
--
-- 8/11 팀 회의에서 Chat 기반 Agent Platform 으로 확정됐다(아키텍처 §3.1).
-- Harness·Chat API·MCP 가 전부 여기에 행을 남긴다. 특히 평가는 agent_run·
-- tool_call 로그가 없으면 아무것도 측정할 수 없어서, 로그 테이블이 코드보다
-- 앞선다.
--
-- PK 종류가 둘로 나뉜다. 이 스키마의 `VARCHAR(5)` PK 는 접두사 두 글자 +
-- 세 자리 번호라 테이블당 999 행이 상한이다(backend/db/codes.py). 사람이
-- 만드는 설정 행은 그 안에 들어가지만, 대화 한 번에 수십 줄씩 쌓이는 로그는
-- 데모 도중에도 넘긴다 — 그래서 대량 테이블은 doc_block·chunk·vec_idx 와
-- 같은 UUID 를 쓴다.
-- =====================================================================

CREATE TABLE mcp_server (
    mcp_server_id    VARCHAR(5) PRIMARY KEY,   -- 'MS' + 세 자리
    team_id          VARCHAR(5)   NOT NULL,    -- team.team_id(FK 없음)
    name             VARCHAR(100) NOT NULL,
    endpoint_url     VARCHAR(500) NOT NULL,    -- https 만 허용(SSRF 차단은 등록·호출 양쪽에서)
    -- 접속 토큰의 암호문. connector_conn.encrypted_credential_ref 와 같은
    -- 이유로 TEXT 다 — Fernet 암호문은 VARCHAR(255)에 들어가지 않는다.
    auth_token_enc   TEXT,
    -- UNCHECKED = 등록만 하고 아직 연결 테스트를 안 했다. ERROR 와 다르다.
    status           VARCHAR(20)  NOT NULL DEFAULT 'UNCHECKED',  -- CONNECTED / ERROR / UNCHECKED
    last_checked_at  TIMESTAMPTZ,
    created_by       VARCHAR(5)                -- user_account.account_id(FK 없음)
);

-- list_tools 로 발견한 tool. 재조회 때 갱신되므로 서버 안에서 이름이
-- 유일해야 한다 — UNIQUE 가 없으면 같은 tool 이 조회할 때마다 한 줄씩
-- 늘어 Registry 가 중복 등록한다.
CREATE TABLE mcp_tool (
    mcp_tool_id    VARCHAR(5) PRIMARY KEY,   -- 'MT' + 세 자리
    server_id      VARCHAR(5)   NOT NULL,    -- mcp_server.mcp_server_id(FK 없음)
    name           VARCHAR(200) NOT NULL,
    description    TEXT,
    input_schema   JSONB        NOT NULL DEFAULT '{}',
    enabled        BOOLEAN      NOT NULL DEFAULT true,
    discovered_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (server_id, name)
);

CREATE TABLE chat_session (
    session_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id     VARCHAR(5)   NOT NULL,   -- team.team_id(FK 없음)
    account_id  VARCHAR(5)   NOT NULL,   -- user_account.account_id(FK 없음). 대화 주인
    agent_id    VARCHAR(5)   NOT NULL,   -- agent.agent_id(FK 없음). 수동 선택기로 고른 값
    -- agent_versions.agent_version_id(FK 없음). 세션 생성 시 고정하고 이후 바꾸지
    -- 않는다(2026-08-13, 02 §5.5). harness 경로가 이 컬럼을 아직 모르는 동안은
    -- NULL로 쌓인다 — Deep Agent 런타임 전환 전까지는 정상이다.
    agent_version_id  VARCHAR(5),
    proj_id     VARCHAR(5),              -- proj.proj_id(FK 없음). 프로젝트 문맥 없이 시작할 수 있어 NULL 허용
    title       VARCHAR(200),
    -- Chat "+"(도구·MCP 붙이기)가 이 대화에서만 쓸 도구를 여기 저장한다 —
    -- 에이전트 원본 tool_refs는 안 건드린다(2026-08-18,
    -- DB/migrations/2026-08-18_chat_session_tool_override.sql). NULL =
    -- 커스터마이즈 안 함(에이전트 원래 값을 그대로 씀), 빈 배열 = 이 대화만
    -- 도구를 전부 끔 — 그래서 DEFAULT를 안 둔다.
    tool_refs_override  TEXT[],
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- 사이드바의 "내 대화 최신순"이 매번 전체를 훑지 않게 한다.
CREATE INDEX ix_chat_session_account
    ON chat_session (account_id, updated_at DESC);

CREATE TABLE chat_message (
    message_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  UUID        NOT NULL,   -- chat_session.session_id(FK 없음)
    role        VARCHAR(20) NOT NULL,   -- user / agent / system
    -- 평문이 아니라 JSONB 인 이유: 답변에 근거·확인 요청·결과 카드가 함께
    -- 들어간다. 화면이 다시 그릴 수 있어야 새로고침에 결과가 사라지지 않는다
    -- (8/11 확정 ④). 업무 추출 결과도 이 안에 구조화해서 넣는다.
    content     JSONB       NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_chat_message_session
    ON chat_message (session_id, created_at);

CREATE TABLE agent_run (
    run_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- **NULL 을 허용한다.** run_agent 는 chat_session 에 종속되지 않는 순수
    -- 함수이고(A2A 대비, 공통구조_비교_회의자료 §3-⑨), 다른 에이전트가
    -- 호출하거나 평가 스크립트가 돌릴 때는 대화가 아예 없다.
    session_id     UUID,                    -- chat_session.session_id(FK 없음)
    agent_id       VARCHAR(5)  NOT NULL,    -- agent.agent_id(FK 없음)
    -- agent_versions.agent_version_id(FK 없음). 어느 버전이 이 run을 돌렸는지
    -- 기록한다(2026-08-13, 02 §5.6). harness 경로에서는 NULL.
    agent_version_id  VARCHAR(5),
    parent_run_id  UUID,                    -- 에이전트가 에이전트를 부른 경우의 상위 run
    status         VARCHAR(20) NOT NULL DEFAULT 'RUNNING',  -- RUNNING / DONE / FAILED / CANCELLED
    iterations     INT         NOT NULL DEFAULT 0,
    token_in       INT,
    token_out      INT,
    -- 배포된 런타임 코드 버전(git commit SHA). 2026-08-14 추가(DB/migrations/
    -- 2026-08-14_agent_run_runtime_profile_version.sql) — 배포 파이프라인이
    -- GIT_COMMIT_SHA를 안 넘기면(config/settings/base.py RUNTIME_PROFILE_VERSION) NULL.
    runtime_profile_version  VARCHAR(64),
    -- 이 실행이 실제로 사용한 모델 provider와 커스텀 엔드포인트 식별값.
    -- 2026-08-19 추가(DB/migrations/2026-08-19_agent_run_resolved_provider.sql,
    -- 정본: 2026-08-19_01_실행_안정성_설계.md §1) — 같은 agent_version_id/
    -- runtime_profile_version이라도 팀 커스텀 엔드포인트(base_url/api_key)는
    -- 언제든 바뀔 수 있어서, 어느 정의로 돌았는지만으로는 실제로 어느
    -- 서버로 요청이 나갔는지 알 수 없었다. base_url 원문은 저장하지
    -- 않는다(사내망 주소 노출 방지) — sha256(base_url)만 남긴다.
    resolved_provider        VARCHAR(32),
    resolved_endpoint_hash   VARCHAR(64),
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at       TIMESTAMPTZ
);

CREATE INDEX ix_agent_run_session
    ON agent_run (session_id, started_at);

-- tool 호출 한 건. **선기록 패턴**을 전제로 한다 — 실행 전에 PENDING 으로
-- 넣고 끝난 뒤 status·error_code·duration_ms 를 갱신한다. 끝나고 나서
-- 기록하면 타임아웃·프로세스 종료로 죽은 호출이 로그에서 사라진다.
CREATE TABLE tool_call (
    tool_call_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id         UUID         NOT NULL,   -- agent_run.run_id(FK 없음)
    -- AIMessage.tool_calls[i]["id"]. HITL interrupt 전후의 서로 다른 스트림이
    -- 같은 호출 행을 다시 찾는 영속 correlation key다. 이 컬럼이 없던 기존
    -- 행을 보존해야 하므로 nullable이며, 신규 런타임 기록에는 항상 채운다.
    langchain_tool_call_id VARCHAR(64),
    tool_ref       VARCHAR(100) NOT NULL,   -- agent_tool.tool_ref 와 같은 형식
    input_summary  TEXT,                    -- 원본 인자가 아니라 요약. 자격증명이 로그에 남지 않게 한다
    status         VARCHAR(20)  NOT NULL DEFAULT 'PENDING',  -- PENDING / OK / FAILED / REJECTED
    error_code     VARCHAR(50),             -- 401 / 429 / validation / timeout 등
    duration_ms    INT,
    -- 이 호출이 건드린 문서(2026-08-21 추가, DB/migrations/
    -- 2026-08-21_tool_call_retrieved_docs.sql). **본문이 아니라 식별자만 담는다** —
    -- input_summary 가 자격증명을 안 남기는 것과 같은 원칙이다. 검색이 무엇을
    -- 골랐는지는 지금까지 SSE 로 화면에 한 번 흐르고 사라졌다.
    retrieved_doc_ids TEXT[],
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX ix_tool_call_run
    ON tool_call (run_id, created_at);

-- 같은 실행의 같은 LangChain 호출이 HITL resume나 checkpoint 재처리로 다시
-- 관측돼도 tool_call 행은 하나만 유지한다. 옛 NULL 행끼리는 중복을 허용한다.
CREATE UNIQUE INDEX ux_tool_call_run_langchain_id
    ON tool_call (run_id, langchain_tool_call_id)
    WHERE langchain_tool_call_id IS NOT NULL;

-- 「이 문서가 언제 누구에게 조회됐나」로 역추적하는 것이 주된 사용처다.
CREATE INDEX ix_tool_call_retrieved_docs
    ON tool_call USING GIN (retrieved_doc_ids);

-- 가드레일이 실제로 발동한 기록(2026-08-20 추가). `audit_log`를 쓰지 않는다 —
-- 그쪽 `actor_account_id`는 NOT NULL인데 가드레일을 발동시키는 것은 사람이
-- 아니라 런타임이다.
--
-- **원문을 저장하지 않는다.** 가려진 값이 로그에 남으면 가드레일을 두는 의미가
-- 없다(`tool_call.input_summary`와 같은 원칙) — `detail`에는 건수·카테고리·
-- 점수처럼 임계값 튜닝에 필요한 것만 넣는다.
CREATE TABLE guardrail_event (
    event_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id       UUID,                    -- agent_run.run_id(FK 없음). 입력 검사처럼 run 밖에서 나면 NULL
    session_id   UUID,                    -- chat_session.session_id(FK 없음)
    account_id   VARCHAR(5),              -- user_account.account_id(FK 없음)
    team_id      VARCHAR(5),              -- team.team_id(FK 없음)
    stage        VARCHAR(20)  NOT NULL,   -- INPUT / OUTPUT / TOOL_RESULT
    rule         VARCHAR(30)  NOT NULL,   -- PII / MODERATION / BLOCKED_WORD
    action       VARCHAR(20)  NOT NULL,   -- MASKED / BLOCKED
    detail       JSONB,                   -- 원문 없이 요약만(건수·카테고리·점수)
    occurred_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX ix_guardrail_event_occurred
    ON guardrail_event (occurred_at DESC);

-- 외부 가드레일 공급자 등록(2026-08-20). 고객이 이미 가진 가드레일을 등록해서
-- 우리 에이전트가 그걸 거쳐 돌게 한다 — `mcp_server` 와 같은 틀이다(팀 소유,
-- 비밀값 암호화, UNCHECKED 로 시작해 「연결 확인」을 눌러야 CONNECTED).
--
-- `config` 가 JSONB 인 이유는 공급자마다 필요한 값이 달라서다(Azure 는 주소,
-- Bedrock 은 guardrail ID·리전, OpenAI Guardrails 는 설정 JSON). 컬럼으로 다
-- 펴면 대부분 NULL 인 표가 된다. **비밀값은 config 가 아니라 credential_enc 다.**
--
-- 팀당 하나만 둔다(아래 UNIQUE) — 여럿이면 「어느 것이 먼저 도는가」를 정해야
-- 하는데 지금 그 근거가 없다.
CREATE TABLE guardrail_provider (
    provider_id      VARCHAR(5) PRIMARY KEY,   -- 'GP' + 세 자리
    team_id          VARCHAR(5)   NOT NULL,    -- team.team_id(FK 없음)
    name             VARCHAR(100) NOT NULL,
    kind             VARCHAR(40)  NOT NULL,    -- OPENAI_GUARDRAILS / BEDROCK_GUARDRAILS / AZURE_CONTENT_SAFETY
    config           JSONB        NOT NULL DEFAULT '{}'::jsonb,
    credential_enc   TEXT,                     -- 비밀값 암호문(mcp_server.auth_token_enc 와 같은 이유로 TEXT)
    status           VARCHAR(20)  NOT NULL DEFAULT 'UNCHECKED',  -- CONNECTED / ERROR / UNCHECKED
    -- 여러 개 등록해 두고 **그중 하나만** 쓴다(2026-08-20). 합치는 게 아니라
    -- 고르는 것이라 「어느 것이 먼저 도는가」를 정할 필요가 없다.
    is_active        BOOLEAN      NOT NULL DEFAULT FALSE,
    last_checked_at  TIMESTAMPTZ,
    created_by       VARCHAR(5),               -- user_account.account_id(FK 없음)
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- 팀당 활성 하나. **부분 UNIQUE 로 DB 가 강제한다** — 코드에서만 지키면 동시에
-- 두 번 활성화했을 때 둘 다 활성인 상태가 만들어진다.
CREATE UNIQUE INDEX ux_guardrail_provider_active
    ON guardrail_provider (team_id)
    WHERE is_active;

-- 같은 tool_call_id(모델이 낸 AIMessage.tool_calls[i]["id"])가 같은 run 안에서
-- 재실행되지 않게 막는 표. HITL resume·checkpoint 재시도로 super-step이
-- 다시 돌아도 jira_create_issues 같은 외부 side_effect 도구가 두 번
-- 실행되지 않도록, 실행 직전(factory.py의 _to_langchain_tool()._run())에
-- 이 표를 먼저 확인한다. tool_call 의 선기록/갱신 흐름과는 쓰는 시점이
-- 달라 tool_call 을 확장하지 않고 전용 표를 둔다.
CREATE TABLE tool_call_idempotency (
    run_id                   UUID         NOT NULL,   -- agent_run.run_id(FK 없음)
    langchain_tool_call_id   VARCHAR(64)  NOT NULL,    -- AIMessage.tool_calls[i]["id"]
    tool_ref                 VARCHAR(100) NOT NULL,
    result_text              TEXT         NOT NULL,    -- 재실행 대신 그대로 돌려줄 결과(원문)
    created_at               TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, langchain_tool_call_id)
);

-- 승인 카드에 "지금 이걸 승인해도 되나"를 판단할 재료를 붙이려고 둔다
-- (2026-08-21, 병렬실행 Phase 3). 두 가지를 kind 로 나눠 담는다:
--   ACTIVE    = 지금 실행 중인 MCP 호출. 같은 서버에 다른 실행이 이미 돌고
--               있으면 카드에 경고를 띄운다. 끝나면 지운다.
--   TIMED_OUT = timeout 으로 결과를 확인하지 못한 호출. 안 지운다. 같은 run
--               에서 같은 도구를 또 부르면 "이미 실행됐을 수 있다"고 알린다.
-- 같은 MCP 서버 호출을 직렬화(lock)하지 않고 경고만 하는 이유는
-- DB/migrations/2026-08-21_mcp_call_note.sql 주석과
-- docs/설계 및 구현/3_중간발표 이후/작업기록/Deep_Agents/2026-08-21_04_MCP_동시_쓰기_경고_설계.md §2.
-- 성공한 결과만 담는 tool_call_idempotency 와는 담는 시점도 지우는 규칙도
-- 다르므로 전용 표를 둔다.
CREATE TABLE mcp_call_note (
    run_id                   UUID         NOT NULL,   -- agent_run.run_id(FK 없음)
    langchain_tool_call_id   VARCHAR(64)  NOT NULL,   -- AIMessage.tool_calls[i]["id"]
    kind                     VARCHAR(16)  NOT NULL,   -- ACTIVE / TIMED_OUT
    tool_ref                 VARCHAR(100) NOT NULL,   -- 'mcp:<mcp_tool_id>'
    mcp_server_id            VARCHAR(5),              -- mcp_server.mcp_server_id(FK 없음)
    team_id                  VARCHAR(5)   NOT NULL,   -- team.team_id(FK 없음)
    started_at               TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, langchain_tool_call_id, kind)
);

CREATE INDEX idx_mcp_call_note_server
    ON mcp_call_note (team_id, mcp_server_id, kind, started_at);

CREATE INDEX idx_mcp_call_note_run_tool
    ON mcp_call_note (run_id, tool_ref, kind);

-- 문서 하나당 한 줄(doc 과 1:1). chunk 단위 임베딩을 전부 만들지 않고
-- 요약 임베딩 하나로 후보 문서를 먼저 좁히기 위한 테이블이다(A안, 확정 ⑥).
-- `doc_meta`(문서 요약·요약 임베딩·추출 텍스트)는 2026-08-24 에 폐기했다.
-- 폴더의 문서가 전부 본문까지 색인되면서 「어느 문서를 볼지」 요약으로
-- 좁힐 이유가 사라졌고, 요약은 앞 12,000자로만 만들어져 뒤쪽 내용을 못 봤다.
-- 실패 사유는 `doc.index_detail` 이, 후보 추천은 본문 청크 검색이 이어받았다.
-- 폐기 마이그레이션: `DB/migrations/2026-08-24_drop_doc_meta.sql`


-- =====================================================================
-- Deep Agent 런타임 버전 모델 (2026-08-13)
--
-- 지금 살아있는 실행 경로(services/harness/)는 위 agent/agent_tool을 그대로
-- 쓴다. 아래 4테이블은 services/agent_runtime/(신규, 미완성) 전용이고 아직
-- 아무 코드도 읽거나 쓰지 않는다 — 상세 배경은
-- DB/migrations/2026-08-13_agent_versioning.sql 상단 주석과
-- docs/설계 및 구현/3_중간발표 이후/설계/작업목록.md "2026-08-13 착수" 절.
--
-- agent_id 접두사('AG')를 위 agent 테이블과 공유한다 — 의도한 것이다(전환
-- 완료 시 agent를 대체할 전제). 전환 전까지는 테이블명을 꼭 같이 확인할 것.
-- =====================================================================

-- 레거시 `agent`/`agent_tool`은 2026-08-22에 폐기했다
-- (DB/migrations/2026-08-22_drop_legacy_agent.sql). 에이전트 정의는 전부
-- 아래 `agents`/`agent_versions`/`agent_version_tools`/`agent_version_subagents`
-- 네 테이블에 있다.

CREATE TABLE agents (
    agent_id           VARCHAR(5) PRIMARY KEY,   -- 'AG' + 세 자리
    team_id            VARCHAR(5)   NOT NULL,    -- team.team_id(FK 없음)
    name               VARCHAR(100) NOT NULL,
    description        VARCHAR(500),
    owner_account_id   VARCHAR(5),               -- user_account.account_id(FK 없음)
    visibility         VARCHAR(20)  NOT NULL DEFAULT 'TEAM',   -- v1은 항상 TEAM(확정②)
    status             VARCHAR(20)  NOT NULL DEFAULT 'DRAFT',  -- DRAFT/ACTIVE/DISABLED/ARCHIVED
    current_version_id VARCHAR(5),               -- agent_versions.agent_version_id(FK 없음)
    is_prebuilt        BOOLEAN      NOT NULL DEFAULT false,
    -- 팀의 "기본 챗 에이전트"(2026-08-15, DB/migrations/2026-08-15_agent_default_chat.sql).
    -- `is_prebuilt`와는 다른 뜻이다 — 예시 에이전트도 is_prebuilt=true라
    -- 그것만으론 "이게 Chat 기본값이다"를 못 가른다. 팀당 최대 1개 true(아래
    -- 유니크 인덱스). 삭제·비활성화 금지는 Repository 레이어에서 막는다.
    is_default_chat    BOOLEAN      NOT NULL DEFAULT false,
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX agents_one_default_chat_per_team
    ON agents (team_id)
    WHERE is_default_chat = true;

CREATE TABLE agent_versions (
    agent_version_id  VARCHAR(5) PRIMARY KEY,   -- 'AV' + 세 자리
    agent_id          VARCHAR(5)   NOT NULL,    -- agents.agent_id(FK 없음)
    version           INT          NOT NULL,
    system_prompt     TEXT         NOT NULL DEFAULT '',
    model             VARCHAR(100),
    reasoning_effort  VARCHAR(20),
    -- 기본 10 (2026-08-25) — 작업목록.md "함께 정할 것"에서 아키텍처 설계
    -- (§3.1-2 "기본 10")대로 되돌리기로 정리. apps/agents/serializers.py의
    -- default와 맞춘다. 기존 행은 소급 변경하지 않는다(2026-08-25_agent_versions_max_iterations_default_10.sql).
    max_iterations    INT          NOT NULL DEFAULT 10,
    created_by        VARCHAR(5),               -- user_account.account_id(FK 없음)
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (agent_id, version)
);

CREATE INDEX ix_agent_versions_agent
    ON agent_versions (agent_id, version DESC);

CREATE TABLE agent_version_tools (
    agent_version_id  VARCHAR(5)   NOT NULL,   -- agent_versions.agent_version_id(FK 없음)
    tool_ref          VARCHAR(100) NOT NULL,   -- agent_tool.tool_ref 와 같은 형식
    config            JSONB        NOT NULL DEFAULT '{}',
    PRIMARY KEY (agent_version_id, tool_ref)
);

CREATE TABLE agent_version_subagents (
    parent_version_id       VARCHAR(5)   NOT NULL,  -- agent_versions.agent_version_id(FK 없음)
    child_agent_id          VARCHAR(5)   NOT NULL,   -- agents.agent_id(FK 없음)
    -- 발행 시점 자식 버전에 고정. 자식이 새 버전을 내도 이 부모는 그대로 이
    -- 값을 쓴다(02 §5.4).
    child_version_id        VARCHAR(5)   NOT NULL,   -- agent_versions.agent_version_id(FK 없음)
    alias                   VARCHAR(100) NOT NULL,
    delegation_description  TEXT         NOT NULL,
    created_at              TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (parent_version_id, child_agent_id),
    UNIQUE (parent_version_id, alias)
);

-- 에이전트 카드의 별 토글(2026-08-18, DB/migrations/2026-08-18_agent_favorites.sql).
-- 계정별 개인 즐겨찾기 — 팀 전체에 안 보인다. owner_account_id(만든 사람)와는
-- 다른 개념이다.
CREATE TABLE agent_favorites (
    account_id  VARCHAR(5)  NOT NULL,   -- user_account.account_id(FK 없음)
    agent_id    VARCHAR(5)  NOT NULL,   -- agents.agent_id(FK 없음)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (account_id, agent_id)
);

-- =====================================================================
-- Agent 평가 결과 — 로컬 append-only 결과 계약의 DB 조회·집계 사본
-- =====================================================================

-- `run_manifest.json`과 종료 후 `summary.json`을 한 실행 단위로 보존한다.
-- 로컬 파일이 원본이며 DB는 같은 eval_run_id로 멱등 동기화한다. DB 동기화가
-- 실패해도 로컬 평가 결과가 사라지거나 제품 실행이 실패하면 안 된다.
CREATE TABLE eval_run (
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

CREATE INDEX ix_eval_run_dataset
    ON eval_run (dataset_id, dataset_version, started_at DESC);

-- 같은 case_id를 한 실행 안에서 여러 번 반복할 수 있으므로 case_id가 아니라
-- JSONL의 1-based 순서(case_index)를 실행 내 식별자로 사용한다.
CREATE TABLE eval_case_result (
    eval_run_id       VARCHAR(64)  NOT NULL,  -- eval_run.eval_run_id(FK 없음)
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

CREATE INDEX ix_eval_case_result_case
    ON eval_case_result (case_id, status, finished_at DESC);
