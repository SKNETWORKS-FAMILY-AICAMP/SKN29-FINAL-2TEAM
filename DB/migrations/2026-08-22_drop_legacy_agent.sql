-- =====================================================================
-- 2026-08-22 | 레거시 `agent`/`agent_tool` 폐기
--
-- 왜: 2026-08-13에 만든 버전 스키마(`agents`/`agent_versions`/
--     `agent_version_tools`/`agent_version_subagents`)가 빌더·챗·실행까지
--     전부 대체했다. 같은 날 마이그레이션 헤더가 "전환 완료 시 `agent`가
--     폐기되면 이 우려는 사라진다"고 예고한 그 시점이다.
--
--     두 테이블이 'AG' 접두어를 공유해 같은 id가 양쪽에 존재할 수 있었고,
--     `_resolve_session_agent()`가 레거시를 먼저 봐서 신규 에이전트가 **조용히**
--     가려지는 사고가 두 번 있었다(2026-08-15·08-19). 이 마이그레이션으로
--     그 위험이 근본적으로 없어진다.
--
-- ⚠ **되돌릴 수 없다.** 이 스크립트는 데이터를 지운다. 먼저 백업할 것:
--     pg_dump -t agent -t agent_tool -t chat_session -t chat_message \
--             -t agent_run -t tool_call <DB> > backup_2026-08-22.sql
--
-- 전제(코드가 먼저 배포돼 있어야 한다):
--   - 2026-08-22_team_default_model.sql 을 **먼저** 돌렸을 것. 팀 기본 모델이
--     레거시 정문 에이전트의 `agent.model`에 있어서, 이 스크립트가 그 행을
--     지우면 값이 사라진다.
--   - 레거시 빌더 화면·API·harness 실행기를 지운 배포가 올라가 있을 것.
--     안 그러면 살아 있는 코드가 없는 테이블을 조회한다.
--
-- 실행 위치: DBeaver 또는 psql, 대상 DB의 public 스키마
-- 멱등: DROP ... IF EXISTS. 1~2단계 삭제는 대상이 없으면 0건이라 다시 돌려도
--       안전하다.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1단계. 레거시 에이전트를 가리키던 대화를 지운다.
--
-- 이 대화들은 살릴 수 없다 — `chat_session.agent_version_id`가 NULL이고,
-- 그 정의가 있던 `agent` 행이 곧 없어진다. 남겨 두면 목록에는 뜨는데 열면
-- "존재하지 않는 에이전트"로 죽는, 사용자가 이유를 알 수 없는 상태가 된다.
--
-- 메시지를 먼저 지운다(FK가 없어서 순서를 우리가 지켜야 한다 — 반대로 하면
-- 부모가 사라진 뒤 자식을 못 찾는다).
-- ---------------------------------------------------------------------
DELETE FROM chat_message
WHERE  session_id IN (
    SELECT s.session_id FROM chat_session AS s
    WHERE  NOT EXISTS (SELECT 1 FROM agents AS a WHERE a.agent_id = s.agent_id)
);

DELETE FROM chat_session AS s
WHERE  NOT EXISTS (SELECT 1 FROM agents AS a WHERE a.agent_id = s.agent_id);

-- ---------------------------------------------------------------------
-- 2단계. 레거시 실행 로그를 지운다.
--
-- `agent_run`/`tool_call`은 평가의 재료지만, 가리키는 에이전트 정의가 없으면
-- "무엇을 돌린 기록인지"를 복원할 수 없어 재료가 못 된다. 평가를 이제 시작
-- 하는 시점이라 깨끗한 상태에서 다시 쌓는 편이 낫다는 판단이다.
--
-- 남기고 싶으면 이 두 DELETE만 주석 처리하면 된다 — 나머지 단계와 무관하다.
-- 그때는 `agent_run.agent_id`가 아무 데도 안 걸리는 값으로 남는다(FK 없음).
-- ---------------------------------------------------------------------
DELETE FROM tool_call
WHERE  run_id IN (
    SELECT r.run_id FROM agent_run AS r
    WHERE  NOT EXISTS (SELECT 1 FROM agents AS a WHERE a.agent_id = r.agent_id)
);

DELETE FROM agent_run AS r
WHERE  NOT EXISTS (SELECT 1 FROM agents AS a WHERE a.agent_id = r.agent_id);

-- ---------------------------------------------------------------------
-- 3단계. 테이블을 내린다. `agent_tool`이 `agent`를 참조하므로 먼저 지운다
-- (FK는 없지만 읽는 순서를 문서와 맞춘다).
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS agent_tool;
DROP TABLE IF EXISTS agent;

COMMIT;


-- =====================================================================
-- 확인용 — COMMIT 뒤에 따로 실행
-- =====================================================================
-- 1) 테이블이 없어졌는가 (두 줄 다 0이어야 한다)
-- SELECT count(*) FROM information_schema.tables
--  WHERE table_schema='public' AND table_name IN ('agent','agent_tool');
--
-- 2) 가리키는 곳 없는 대화가 남았는가 (0이어야 한다)
-- SELECT count(*) FROM chat_session AS s
--  WHERE NOT EXISTS (SELECT 1 FROM agents AS a WHERE a.agent_id = s.agent_id);
--
-- 3) 팀 기본 모델이 잘 옮겨졌는가 (team_default_model 마이그레이션 결과)
-- SELECT team_id, name, default_model FROM team ORDER BY team_id;
