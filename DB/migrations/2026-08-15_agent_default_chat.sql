-- =====================================================================
-- agents.is_default_chat 추가 (2026-08-15)
--
-- Chat 재설계: 사용자가 화면 상단 드롭다운에서 대화 상대(빌드된 에이전트)를
-- 직접 고른다(2026-08-15 지훈 확인). 아무것도 안 고르면 팀마다 자동으로
-- 있는 "기본 챗 에이전트"(tool·MCP만 붙고 서브에이전트는 없음)로 떨어진다
-- — 이 컬럼이 그 한 행을 가리킨다.
--
-- **`is_prebuilt`를 재사용하지 않는 이유**: `is_prebuilt`는 이미 "우리가
-- 시드로 넣은 것"이라는 다른 뜻으로 쓰이고 있다 — 정문뿐 아니라 복제용
-- 예시 에이전트도 같은 플래그를 쓴다(backend/db/agent_platform.py:119-121
-- `AgentRepository.PLATFORM_TOOL` 주석, backend/services/createDB/seed_agents.py).
-- 그래서 is_prebuilt만으로는 "이게 Chat 기본값이다"를 못 가른다.
--
-- (참고, 별개 이슈) `DB/migrations/2026-08-13_agent_versioning.sql`의
-- `agents.is_prebuilt` 주석은 "정문 판별용"이라 적었는데, 실제 정문 판별은
-- `agent:*` tool_ref 보유 여부다 — 그 주석은 낡았다. 이 마이그레이션에서
-- 고치진 않지만 발견한 김에 남겨 둔다.
--
-- 팀당 최대 1개만 true — 부분 유니크 인덱스로 강제한다. 삭제·비활성화
-- 금지는 DB 제약이 아니라 애플리케이션(Repository) 레이어에서 막는다.
-- =====================================================================

BEGIN;

ALTER TABLE agents ADD COLUMN IF NOT EXISTS is_default_chat BOOLEAN NOT NULL DEFAULT false;

CREATE UNIQUE INDEX IF NOT EXISTS agents_one_default_chat_per_team
    ON agents (team_id)
    WHERE is_default_chat = true;

COMMIT;

-- =====================================================================
-- 확인용 — COMMIT 뒤에 따로 실행
-- =====================================================================
-- SELECT column_name FROM information_schema.columns
--  WHERE table_name = 'agents' AND column_name = 'is_default_chat';
-- SELECT indexname FROM pg_indexes
--  WHERE tablename = 'agents' AND indexname = 'agents_one_default_chat_per_team';
