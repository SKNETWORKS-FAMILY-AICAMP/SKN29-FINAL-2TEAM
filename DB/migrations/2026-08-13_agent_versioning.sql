-- =====================================================================
-- 2026-08-13 | Deep Agent 런타임을 위한 버전 모델 4테이블 + 컬럼 2개
--
-- 왜: Deep Agent형 에이전트 빌더 개편
--     (docs/설계 및 구현/3_중간발표 이후/작업기록/Deep_Agents/2026-08-13_01_*.md,
--      구현 계약 정본 2026-08-13_02_Deep-Agent_런타임_공통_계약_v1.md)이
--     "저장·발행된 agent_versions는 불변, 세션은 생성 시 agent_version_id에
--     고정, 부모는 자식의 특정 child_version_id를 참조"를 MVP 전제로 확정
--     했다(02 §2 원칙 1~3). 지금의 `agent`/`agent_tool`은 비버전 모델이라
--     이 전제를 못 담는다.
--
-- ⚠ 이건 2026-08-11 팀 확정("Harness 구현 방식: 직접 구현 + 구조 차용")을
--    뒤집는 방향 전환이다. 이 마이그레이션 자체는 그 전환의 찬반과 무관하게
--    "적용해도 지금 화면이 안 깨지는 형태"로만 짰다 — docs/설계 및 구현/3_중간발표 이후/설계/작업목록.md
--    "2026-08-13 착수" 절 참고.
--
-- 실행 위치: DBeaver 또는 psql, 대상 DB의 public 스키마
-- 전제: 없다. 기존 `agent`·`agent_tool`·`chat_session`·`agent_run`은 한 줄도
--       고치지 않는다(컬럼 2개는 ADD뿐이라 기존 행에 영향 없음) — 2026-08-11
--       agent_platform 마이그레이션과 같은 원칙이다. **안 돌려도 지금 화면은
--       멀쩡하고, 새 Deep Agent 런타임(services/agent_runtime/)이 참조를
--       못 찾을 뿐이다.**
-- 멱등: CREATE ... IF NOT EXISTS, ADD COLUMN IF NOT EXISTS 뿐이라 여러 번
--       실행해도 안전하다.
--
-- ---------------------------------------------------------------------
-- 왜 `agent`가 아니라 `agents`인가 (읽을 때 반드시 알아야 할 것)
--
-- 지금 살아있는 Chat/Agent 실행 경로(services/harness/, apps/chat,
-- apps/agents)는 여전히 비버전 `agent`/`agent_tool`을 그대로 쓴다. 이
-- 마이그레이션이 만드는 `agents`/`agent_versions`/`agent_version_tools`/
-- `agent_version_subagents`는 **완전히 별개의 새 테이블**이고, 지금은
-- services/agent_runtime/ 스텁만 이걸 참조 대상으로 코드에 적어 뒀을 뿐
-- 아직 아무 것도 실제로 읽거나 쓰지 않는다(loader.py가 NotImplementedError).
--
-- ⚠ ID 접두사 충돌 주의: `agents.agent_id`도 `agent.agent_id`와 같은 'AG'
-- 접두사를 쓴다(02 문서의 예시가 그렇게 돼 있어 그대로 따랐다). `next_short_code`
-- (backend/db/codes.py)는 테이블별로 번호를 매기므로 DB 제약 충돌은 없지만,
-- **"AG011"이 `agent` 테이블 것인지 `agents` 테이블 것인지는 테이블명을 같이
-- 봐야 구분된다.** 로그·디버깅 시 반드시 테이블명과 같이 기록할 것 — 이건
-- 설계 결정이지 실수가 아니다: 새 테이블이 결국 `agent`를 대체하는 것을
-- 전제로 같은 코드 체계를 물려받았다(전환 완료 시 `agent`가 폐기되면 이
-- 우려는 사라진다). 전환 전까지 둘이 같이 사는 동안은 헷갈릴 수 있다는
-- 점을 팀에 공유해 둘 것.
--
-- `agents`의 필드 중 `is_prebuilt`는 02 §5.1 원문 스케치에는 없다 — 기존
-- `agent.is_prebuilt`(정문 에이전트 판별에 실제로 쓰이는 컬럼,
-- 작업목록.md 확정④ 정정 참고)를 대체하려면 반드시 필요해서 추가했다.
-- 마찬가지로 02는 `owner_user_id`라고 썼지만, 이 저장소는 사람을 가리킬
-- 때 항상 `*_account_id`를 쓰므로(예: `agent.created_by` 주석) 이름을
-- `owner_account_id`로 맞췄다 — 의미는 같다.
--
-- `agent_versions.max_iterations` 기본값은 10이 아니라 6이다. 작업목록.md
-- "함께 정할 것 — 기본값이 설계와 다르다"에 적힌 대로, 지금 살아있는
-- `apps/agents/serializers.py`가 6을 쓰고 있어(설계 문서 §3.1-2는 10) 그
-- 확정 전까지는 **실제로 도는 값**을 기본값으로 맞춘다. 확정되면 이 컬럼
-- 기본값도 같이 바꿀 것.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 논리적 에이전트 — 이름·소유·현재 버전 포인터
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS agents (
    agent_id           VARCHAR(5) PRIMARY KEY,   -- 'AG' + 세 자리. 위 주석의 접두사 공유 참고
    team_id            VARCHAR(5)   NOT NULL,    -- team.team_id(FK 없음). 테넌트 경계
    name               VARCHAR(100) NOT NULL,
    description        VARCHAR(500),
    owner_account_id   VARCHAR(5),               -- user_account.account_id(FK 없음)
    -- v1은 팀 공유 고정이다(작업목록.md 확정②) — 이 컬럼은 그 원칙이
    -- 바뀔 때를 위한 자리만 만들어 둔다. 지금은 항상 'TEAM'.
    visibility         VARCHAR(20)  NOT NULL DEFAULT 'TEAM',
    -- DRAFT / ACTIVE / DISABLED / ARCHIVED — 기존 agent.status와 같은 생명주기.
    status             VARCHAR(20)  NOT NULL DEFAULT 'DRAFT',
    -- agent_versions.agent_version_id(FK 없음). 아직 한 번도 발행 안 했으면 NULL.
    current_version_id VARCHAR(5),
    -- 정문 에이전트 판별용(기존 agent.is_prebuilt와 같은 목적).
    is_prebuilt        BOOLEAN      NOT NULL DEFAULT false,
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- 불변 실행 버전 — 발행되면 고치지 않는다
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS agent_versions (
    agent_version_id  VARCHAR(5) PRIMARY KEY,   -- 'AV' + 세 자리
    agent_id          VARCHAR(5)   NOT NULL,    -- agents.agent_id(FK 없음)
    version           INT          NOT NULL,    -- 그 agent_id 안에서 1부터 증가
    system_prompt     TEXT         NOT NULL DEFAULT '',
    model             VARCHAR(100),             -- NULL 이면 코드 기본값
    reasoning_effort  VARCHAR(20),
    -- 기본 6 — 위 주석 참고("실제로 도는 값"에 맞춤, 10 확정 시 갱신).
    max_iterations    INT          NOT NULL DEFAULT 6,
    created_by        VARCHAR(5),               -- user_account.account_id(FK 없음)
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (agent_id, version)
);

CREATE INDEX IF NOT EXISTS ix_agent_versions_agent
    ON agent_versions (agent_id, version DESC);

-- ---------------------------------------------------------------------
-- 버전별 허용 도구 — 기존 agent_tool과 같은 모양의 조인 테이블
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS agent_version_tools (
    agent_version_id  VARCHAR(5)   NOT NULL,   -- agent_versions.agent_version_id(FK 없음)
    -- 내장 tool 식별자 또는 MCP tool 참조('mcp:<mcp_tool.mcp_tool_id>') —
    -- 기존 agent_tool.tool_ref와 같은 형식을 그대로 쓴다.
    tool_ref          VARCHAR(100) NOT NULL,
    -- 도구별 세부 설정 자리(02 §5.3). 지금 당장 쓰는 곳은 없다 — 빈 객체 기본값.
    config            JSONB        NOT NULL DEFAULT '{}',
    PRIMARY KEY (agent_version_id, tool_ref)
);

-- ---------------------------------------------------------------------
-- 버전별 서브 에이전트 관계 — 부모 버전이 자식의 특정 버전을 고정 참조
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS agent_version_subagents (
    parent_version_id       VARCHAR(5)   NOT NULL,  -- agent_versions.agent_version_id(FK 없음)
    child_agent_id          VARCHAR(5)   NOT NULL,   -- agents.agent_id(FK 없음)
    -- 발행 시점의 자식 버전에 고정한다. 자식이 나중에 새 버전을 내도 이
    -- 부모는 이 값을 계속 쓴다(02 §5.4) — "자식을 고치면 모든 부모에 즉시
    -- 반영"이 이 모델에서는 일어나지 않는다.
    child_version_id        VARCHAR(5)   NOT NULL,   -- agent_versions.agent_version_id(FK 없음)
    alias                   VARCHAR(100) NOT NULL,   -- 부모가 호출할 때 쓰는 이름
    delegation_description  TEXT         NOT NULL,   -- 부모가 위임 판단에 쓰는 설명. 필수
    created_at              TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (parent_version_id, child_agent_id),
    -- 같은 부모 버전 안에서 alias가 겹치면 부모 모델이 어느 자식을 부르는지
    -- 구분 못 한다 — subagents/validation.py의 DuplicateSubagentAliasError와
    -- 같은 규칙을 DB 레벨에서도 강제한다(방어적 이중화).
    UNIQUE (parent_version_id, alias)
);

-- ---------------------------------------------------------------------
-- 기존 실행 테이블에 버전 참조 컬럼 추가 — nullable, 기존 행 영향 없음
-- ---------------------------------------------------------------------

-- 세션 생성 시 고정하고 이후 바꾸지 않는다(02 §5.5). 지금은 harness 경로가
-- 이 컬럼을 모르므로 NULL로 계속 쌓인다 — Chat이 agent_runtime으로
-- 전환되기 전까지는 정상이다.
ALTER TABLE chat_session ADD COLUMN IF NOT EXISTS agent_version_id VARCHAR(5);

-- 실행 로그에도 어느 버전이 돌았는지 남긴다(02 §5.6). 마찬가지로 harness
-- 경로가 채우기 전까지는 NULL.
ALTER TABLE agent_run ADD COLUMN IF NOT EXISTS agent_version_id VARCHAR(5);

COMMIT;


-- =====================================================================
-- 확인용 — COMMIT 뒤에 따로 실행
-- =====================================================================
-- SELECT table_name FROM information_schema.tables
--  WHERE table_schema = 'public'
--    AND table_name IN ('agents','agent_versions','agent_version_tools',
--                       'agent_version_subagents')
--  ORDER BY table_name;
--   네 줄이 나오면 정상이다.
--
-- SELECT column_name FROM information_schema.columns
--  WHERE table_name = 'chat_session' AND column_name = 'agent_version_id';
-- SELECT column_name FROM information_schema.columns
--  WHERE table_name = 'agent_run' AND column_name = 'agent_version_id';
--   각각 한 줄씩 나오면 정상이다.
--
-- SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';
--   53 이면 정상이다(2026-08-11 시점 49 + 신규 4).
