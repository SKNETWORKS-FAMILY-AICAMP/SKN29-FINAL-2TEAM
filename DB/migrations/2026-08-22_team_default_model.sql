-- =====================================================================
-- 2026-08-22 | team 에 기본 채팅 모델 1개 추가 + 레거시에서 값 옮기기
--
-- 왜: 「팀 기본 채팅 모델」이 지금까지 **레거시 정문 에이전트의 컬럼**에
--     얹혀 있었다 — `agent_tool.tool_ref='agent:*'`(A2A 위임 와일드카드)인
--     ACTIVE `agent` 행의 `model` 이 곧 그 팀의 기본 모델이었다
--     (backend/db/agent_platform.py 의 `AgentRepository.main_model_for_team`).
--     레거시 `agent`/`agent_tool` 을 폐기하기로 하면서 이 값이 갈 곳이
--     없어졌다.
--
--     에이전트 쪽에 그대로 두지 않는 이유는 두 가지다.
--     ① **의미가 이미 어긋났다.** 레거시 정문은 다른 에이전트로 위임하는
--        오케스트레이터였는데, 신규 스키마의 기본 챗(`agents.is_default_chat`)
--        은 "도구·MCP만 붙일 수 있고 다른 에이전트로 위임하지 않는다"
--        (2026-08-15 시드 description). 같은 자리가 아니다.
--     ② **`agent_versions` 는 불변이다**(02 §5.2). 모델을 바꿀 때마다 새
--        버전을 발행해야 하는데, 운영자가 남의 팀 모델을 바꾸는 일이
--        그 팀의 에이전트 버전 이력을 늘리는 건 이상하다.
--
--     팀 기본 모델은 원래 **팀 설정**이지 에이전트 속성이 아니다. 그래서
--     `team` 의 기존 설정 컬럼들(capacity_wk_hours/overload_pct/
--     workload_weeks, 2026-08-04)과 같은 자리·같은 규칙으로 둔다.
--
-- NULL 이 기본이고 "설정 안 함"을 뜻한다 — 그때는 코드 기본값
-- (`services/harness/runner.py` 의 `DEFAULT_MODEL`)이 쓰인다. 화면은 NULL 을
-- 「아직 없다」로 말해야 하고 임의의 기본값을 저장된 것처럼 보이면 안 된다
-- (그게 원래 Model 탭의 문제였다 — `main_model()` docstring).
--
-- 실행 위치: DBeaver 또는 psql, 대상 DB의 public 스키마
-- 전제: team 테이블(2026-07-31), agent/agent_tool(2026-08-11). 레거시 두
--       테이블은 이 스크립트가 **읽기만** 한다 — 폐기는 별도 단계다.
-- 멱등: ADD COLUMN IF NOT EXISTS + 백필이 이미 채워진 행을 건너뛴다
--       (WHERE t.default_model IS NULL). 여러 번 돌려도 안전하다.
-- =====================================================================

BEGIN;

ALTER TABLE team ADD COLUMN IF NOT EXISTS default_model VARCHAR(100);

-- 레거시 정문 에이전트의 모델을 그 팀의 설정으로 옮긴다.
--
-- 팀에 정문이 여러 개일 수 있는가: 지금 스키마는 막지 않는다(유니크 제약
-- 없음). 그래서 `MIN(a.model)` 로 하나를 고정해 뽑는다 — 임의로 하나를
-- 집는 것은 기존 조회(`LIMIT 1`, 정렬 없음)와 같은 수준의 보장이고,
-- 집계로 감싸야 팀당 한 행이 되어 UPDATE ... FROM 이 결정적으로 돈다.
--
-- `model IS NOT NULL` 인 것만 옮긴다 — 레거시에서도 NULL 은 "코드 기본값을
-- 쓴다"는 뜻이었으므로 그대로 NULL 로 두는 것이 같은 의미다.
UPDATE team AS t
SET    default_model = src.model
FROM (
    SELECT a.team_id, MIN(a.model) AS model
    FROM   agent AS a
    JOIN   agent_tool AS tl ON tl.agent_id = a.agent_id
    WHERE  tl.tool_ref = 'agent:*'
      AND  a.status = 'ACTIVE'
      AND  a.model IS NOT NULL
    GROUP BY a.team_id
) AS src
WHERE t.team_id = src.team_id
  AND t.default_model IS NULL;

COMMIT;


-- =====================================================================
-- 확인용 — COMMIT 뒤에 따로 실행
-- =====================================================================
-- 1) 옮겨진 값
-- SELECT team_id, name, default_model FROM team ORDER BY team_id;
--
-- 2) 레거시와 대조 — 두 열이 같아야 한다(레거시 쪽이 NULL 인 팀은 team 도 NULL).
-- SELECT t.team_id, t.default_model AS moved, src.model AS legacy
-- FROM   team AS t
-- LEFT JOIN (
--     SELECT a.team_id, MIN(a.model) AS model
--     FROM agent AS a JOIN agent_tool AS tl ON tl.agent_id = a.agent_id
--     WHERE tl.tool_ref = 'agent:*' AND a.status = 'ACTIVE' AND a.model IS NOT NULL
--     GROUP BY a.team_id
-- ) AS src ON src.team_id = t.team_id
-- ORDER BY t.team_id;
