-- =====================================================================
-- agent_favorites 테이블 추가 (2026-08-18)
--
-- 에이전트 카드의 별 토글 — 계정별 개인 즐겨찾기다. **팀 전체에 안
-- 보인다**(지훈 확인) — 내가 즐겨찾기한 건 나만 본다, `agents.owner_
-- account_id`(만든 사람)와는 다른 개념이다. 개인/팀 공유 탭 옆에 새로
-- 생기는 "즐겨찾기" 탭은 이 표를 account_id로 걸러 보여준다.
--
-- 별도 surrogate id 없이 (account_id, agent_id) 복합 PK만 쓴다 —
-- agent_version_tools/agent_version_subagents와 같은 관례(FK 없음,
-- VARCHAR(5) 참조는 주석으로만 문서화).
-- =====================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS agent_favorites (
    account_id  VARCHAR(5)  NOT NULL,   -- user_account.account_id(FK 없음)
    agent_id    VARCHAR(5)  NOT NULL,   -- agents.agent_id(FK 없음)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (account_id, agent_id)
);

COMMIT;

-- =====================================================================
-- 확인용 — COMMIT 뒤에 따로 실행
-- =====================================================================
-- SELECT table_name FROM information_schema.tables
--  WHERE table_name = 'agent_favorites';
