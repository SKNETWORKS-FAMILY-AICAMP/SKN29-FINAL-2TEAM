-- =====================================================================
-- 2026-08-11 | Agent Platform 테이블 신설 (개발지시 1차 단계 1)
--
-- 왜: 8/11 팀 회의에서 Chat 기반 Agent Platform으로 확정(아키텍처 §3.1)됐다.
--     Harness·Chat API·MCP가 전부 여기에 행을 남기므로 DB가 먼저 있어야
--     한다. 특히 평가(4_평가_설계.md)는 agent_run·tool_call 로그가 없으면
--     아무것도 측정할 수 없어서, 로그 테이블이 코드보다 앞선다.
--
-- 실행 위치: DBeaver 또는 psql, 대상 DB의 public 스키마
-- 전제: 없다. 전부 신규 테이블이고 기존 테이블은 한 줄도 건드리지 않는다.
-- 멱등: CREATE ... IF NOT EXISTS 뿐이라 여러 번 실행해도 안전하다.
--
-- ---------------------------------------------------------------------
-- PK 종류를 둘로 나눈 이유
--
-- 이 저장소의 `VARCHAR(5)` PK는 접두사 두 글자 + 세 자리 번호라 테이블당
-- 999행이 상한이다(backend/db/codes.py). 사람이 만드는 설정 행(에이전트,
-- MCP 서버·툴)은 그 안에 들어가지만, 대화 한 번에 수십 줄씩 쌓이는 로그
-- (chat_message·agent_run·tool_call)는 데모 도중에도 넘긴다. 그래서
-- 대량 테이블은 doc_block·chunk·vec_idx와 같은 UUID를 쓴다.
--
-- FK 제약은 이 저장소 관례대로 걸지 않는다. 참조는 컬럼 주석으로만 남기고
-- 존재 검증은 Repository가 한다.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 에이전트 정의 — 사람이 만드는 설정
-- ---------------------------------------------------------------------

-- 팀이 소유하는 에이전트 하나. 공통 스캐폴드는 코드 상수라 여기 없고
-- (services/harness/scaffold.py), 이 테이블에는 그 뒤에 붙는 개별
-- instruction만 담는다.
CREATE TABLE IF NOT EXISTS agent (
    agent_id          VARCHAR(5) PRIMARY KEY,   -- 'AG' + 세 자리
    team_id           VARCHAR(5)   NOT NULL,    -- team.team_id(FK 없음). 테넌트 경계
    name              VARCHAR(100) NOT NULL,
    description       VARCHAR(500),
    instruction       TEXT         NOT NULL DEFAULT '',
    model             VARCHAR(100),             -- NULL 이면 코드 기본값
    reasoning_effort  VARCHAR(20),
    -- Loop 하드 상한. 코드가 이 값으로 강제한다 — 모델에게 권고만 하면
    -- 무한 루프를 막을 수단이 없다.
    max_iterations    INT          NOT NULL DEFAULT 10,
    -- 우리가 미리 만들어 넣는 에이전트인가(업무 추출 등). 팀이 지울 수
    -- 없어야 하는 행을 구분한다.
    is_prebuilt       BOOLEAN      NOT NULL DEFAULT false,
    status            VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE / ARCHIVED
    created_by        VARCHAR(5),               -- user_account.account_id(FK 없음)
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- 이 에이전트가 쓸 수 있는 tool 목록(허용 목록). 여기 없는 tool 은
-- Registry 가 거른다.
--
-- 대리키를 두지 않는다 — 순수 조인 테이블이고(model_know_item·task_know_src
-- 와 같은 모양), 복합 PK 가 같은 tool 을 두 번 붙이는 것까지 막아 준다.
CREATE TABLE IF NOT EXISTS agent_tool (
    agent_id  VARCHAR(5)   NOT NULL,   -- agent.agent_id(FK 없음)
    -- 내장 tool 식별자('document_search'·'workload_report') 또는
    -- MCP tool 을 가리키는 'mcp:<mcp_tool.mcp_tool_id>'
    tool_ref  VARCHAR(100) NOT NULL,
    PRIMARY KEY (agent_id, tool_ref)
);

-- ---------------------------------------------------------------------
-- MCP — 외부 tool 서버 등록
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS mcp_server (
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
CREATE TABLE IF NOT EXISTS mcp_tool (
    mcp_tool_id    VARCHAR(5) PRIMARY KEY,   -- 'MT' + 세 자리
    server_id      VARCHAR(5)   NOT NULL,    -- mcp_server.mcp_server_id(FK 없음)
    name           VARCHAR(200) NOT NULL,
    description    TEXT,
    input_schema   JSONB        NOT NULL DEFAULT '{}',
    enabled        BOOLEAN      NOT NULL DEFAULT true,
    discovered_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (server_id, name)
);

-- ---------------------------------------------------------------------
-- 대화 — 사용자에게 보이는 기록
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS chat_session (
    session_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id     VARCHAR(5)   NOT NULL,   -- team.team_id(FK 없음)
    account_id  VARCHAR(5)   NOT NULL,   -- user_account.account_id(FK 없음). 대화 주인
    agent_id    VARCHAR(5)   NOT NULL,   -- agent.agent_id(FK 없음). 수동 선택기로 고른 값
    proj_id     VARCHAR(5),              -- proj.proj_id(FK 없음). 프로젝트 문맥 없이 시작할 수 있어 NULL 허용
    title       VARCHAR(200),
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- 사이드바의 "내 대화 최신순"이 매번 전체를 훑지 않게 한다.
CREATE INDEX IF NOT EXISTS ix_chat_session_account
    ON chat_session (account_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS chat_message (
    message_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  UUID        NOT NULL,   -- chat_session.session_id(FK 없음)
    role        VARCHAR(20) NOT NULL,   -- user / agent / system
    -- 평문이 아니라 JSONB 인 이유: 답변에 근거·확인 요청·결과 카드가 함께
    -- 들어간다. 화면이 다시 그릴 수 있어야 새로고침에 결과가 사라지지 않는다
    -- (8/11 확정 ④). 업무 추출 결과도 이 안에 구조화해서 넣는다.
    content     JSONB       NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_chat_message_session
    ON chat_message (session_id, created_at);

-- ---------------------------------------------------------------------
-- 실행 로그 — 평가의 전제
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS agent_run (
    run_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- **NULL 을 허용한다.** run_agent 는 chat_session 에 종속되지 않는 순수
    -- 함수이고(A2A 대비, 공통구조_비교_회의자료 §3-⑨), 다른 에이전트가
    -- 호출하거나 평가 스크립트가 돌릴 때는 대화가 아예 없다.
    session_id     UUID,                    -- chat_session.session_id(FK 없음)
    agent_id       VARCHAR(5)  NOT NULL,    -- agent.agent_id(FK 없음)
    parent_run_id  UUID,                    -- 에이전트가 에이전트를 부른 경우의 상위 run
    status         VARCHAR(20) NOT NULL DEFAULT 'RUNNING',  -- RUNNING / DONE / FAILED / CANCELLED
    iterations     INT         NOT NULL DEFAULT 0,
    token_in       INT,
    token_out      INT,
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_agent_run_session
    ON agent_run (session_id, started_at);

-- tool 호출 한 건. **선기록 패턴**을 전제로 한다 — 실행 전에 PENDING 으로
-- 넣고 끝난 뒤 status·error_code·duration_ms 를 갱신한다. 끝나고 나서
-- 기록하면 타임아웃·프로세스 종료로 죽은 호출이 로그에서 사라진다.
CREATE TABLE IF NOT EXISTS tool_call (
    tool_call_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id         UUID         NOT NULL,   -- agent_run.run_id(FK 없음)
    tool_ref       VARCHAR(100) NOT NULL,   -- agent_tool.tool_ref 와 같은 형식
    input_summary  TEXT,                    -- 원본 인자가 아니라 요약. 자격증명이 로그에 남지 않게 한다
    status         VARCHAR(20)  NOT NULL DEFAULT 'PENDING',  -- PENDING / OK / FAILED
    error_code     VARCHAR(50),             -- 401 / 429 / validation / timeout 등
    duration_ms    INT,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_tool_call_run
    ON tool_call (run_id, created_at);

-- ---------------------------------------------------------------------
-- 문서 메타 — document_search 의 coarse 단계
-- ---------------------------------------------------------------------

-- 문서 하나당 한 줄(doc 과 1:1). chunk 단위 임베딩을 전부 만들지 않고
-- 요약 임베딩 하나로 후보 문서를 먼저 좁히기 위한 테이블이다(A안, 확정 ⑥).
CREATE TABLE IF NOT EXISTS doc_meta (
    doc_id          VARCHAR(5) PRIMARY KEY,   -- doc.doc_id(FK 없음)
    summary         TEXT,
    doc_type        VARCHAR(50),
    keywords        TEXT[]      NOT NULL DEFAULT '{}',
    -- vec_idx.embedding 과 같은 768 차원(google/embeddinggemma-300m).
    -- 적재와 검색이 같은 모델을 써야 하므로 차원은 한 곳에서만 정해진다.
    summary_vec     VECTOR(768),
    -- CPU 로 뽑아낸 원문 텍스트. **요약을 만든 뒤에도 버리지 않는다.**
    -- 멘토링에서 "요약만으로 coarse 가 부족하다"는 결론이 나오면 A′ 로
    -- 가야 하는데(12_문서처리_방식_비교.md §5), 이 값을 갖고 있으면
    -- tsvector 인덱스만 얹으면 끝나고 없으면 전 문서를 다시 추출해야 한다.
    extracted_text  TEXT,
    -- OK / FAILED(PDF 텍스트 레이어 없음 등) / UNSUPPORTED(hwp).
    -- 기본값을 두지 않는다 — 적재하는 쪽이 결과를 알고 넣는 값이라,
    -- 기본값이 있으면 실패한 문서가 조용히 OK 로 남는다.
    extract_status  VARCHAR(20) NOT NULL,
    extracted_at    TIMESTAMPTZ
);

COMMIT;


-- =====================================================================
-- 확인용 — COMMIT 뒤에 따로 실행
-- =====================================================================
-- SELECT table_name FROM information_schema.tables
--  WHERE table_schema = 'public'
--    AND table_name IN ('agent','agent_tool','mcp_server','mcp_tool',
--                       'chat_session','chat_message','agent_run',
--                       'tool_call','doc_meta')
--  ORDER BY table_name;
--   아홉 줄이 나오면 정상이다.
--
-- SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';
--   49 면 정상이다(기존 40 + 신규 9).
