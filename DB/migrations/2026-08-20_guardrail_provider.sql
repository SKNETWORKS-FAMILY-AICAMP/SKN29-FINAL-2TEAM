-- =====================================================================
-- 외부 가드레일 공급자 등록 (2026-08-20)
--
-- 고객이 이미 가진 가드레일(OpenAI Guardrails·AWS Bedrock·Azure Content
-- Safety)을 등록해서 우리 에이전트가 그걸 거쳐 돌게 한다.
-- 정본: docs/설계 및 구현/중간발표 이후/작업기록/2026-08-20_가드레일_조사와_실측.md §8
--
-- **`mcp_server` 와 같은 틀이다** — 팀 소유, 비밀값은 암호화, status 가
-- UNCHECKED 로 시작하고 「연결 확인」을 눌러야 CONNECTED 가 된다. 등록만 하고
-- 확인 안 한 것(UNCHECKED)과 확인했는데 실패한 것(ERROR)을 구분한다.
--
-- **`config` 를 JSONB 로 두는 이유**: 공급자마다 필요한 값이 다르다. Azure 는
-- 엔드포인트, Bedrock 은 guardrail ID·버전·리전, OpenAI Guardrails 는 설정
-- JSON 이다. 컬럼으로 다 펴면 대부분이 NULL 인 표가 된다.
-- **비밀값은 여기 담지 않는다** — `credential_enc` 로 간다.
--
-- **팀당 하나만 둔다**(UNIQUE). 여럿을 허용하면 「어느 것이 먼저 도는가」와
-- 「하나가 막고 하나가 통과시키면」을 정해야 하는데, 지금 그걸 정할 근거가 없다.
-- 필요해지면 제약을 풀고 순서 컬럼을 더하면 된다.
-- =====================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS guardrail_provider (
    provider_id      VARCHAR(5) PRIMARY KEY,   -- 'GP' + 세 자리
    team_id          VARCHAR(5)   NOT NULL,    -- team.team_id(FK 없음)
    name             VARCHAR(100) NOT NULL,
    -- OPENAI_GUARDRAILS / BEDROCK_GUARDRAILS / AZURE_CONTENT_SAFETY
    kind             VARCHAR(40)  NOT NULL,
    config           JSONB        NOT NULL DEFAULT '{}'::jsonb,
    -- 비밀값 암호문. `mcp_server.auth_token_enc` 와 같은 이유로 TEXT 다
    -- (Fernet 암호문은 VARCHAR(255)에 안 들어간다).
    credential_enc   TEXT,
    status           VARCHAR(20)  NOT NULL DEFAULT 'UNCHECKED',  -- CONNECTED / ERROR / UNCHECKED
    last_checked_at  TIMESTAMPTZ,
    created_by       VARCHAR(5),               -- user_account.account_id(FK 없음)
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_guardrail_provider_team
    ON guardrail_provider (team_id);

COMMIT;

-- =====================================================================
-- 확인용 — COMMIT 뒤에 따로 실행
-- =====================================================================
-- SELECT to_regclass('public.guardrail_provider');
