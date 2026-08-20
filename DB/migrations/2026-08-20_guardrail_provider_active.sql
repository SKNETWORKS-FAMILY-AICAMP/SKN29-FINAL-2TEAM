-- =====================================================================
-- 가드레일을 여러 개 등록하고 그중 하나만 쓴다 (2026-08-20)
--
-- 처음엔 팀당 하나만 두게 막았다(`ux_guardrail_provider_team`). 여럿을 허용하면
-- 「어느 것이 먼저 도는가」와 「하나가 막고 하나가 통과시키면」을 정해야 하는데
-- 그 근거가 없어서였다.
--
-- **PM 지적으로 바꾼다.** 「여러 개 등록해 두고 그중 하나만 사용」은 그 문제를
-- 아예 만들지 않는다 — 합치는 게 아니라 **고르는** 것이다. 그리고 실제로 쓸모가
-- 있다: 키를 교체할 때 새 것을 등록해 확인한 뒤 옮겨 타고, 공급자를 비교해 보고,
-- 시연에서 갈아 끼운다.
--
-- **부분 UNIQUE 로 「팀당 활성 하나」를 DB 가 강제한다.** 코드에서만 지키면
-- 동시에 두 번 활성화했을 때 둘 다 활성인 상태가 만들어진다.
--
-- 기존 행은 전부 활성으로 둔다 — 지금까지 팀당 하나뿐이었으므로 그대로가 맞고,
-- 안 그러면 이미 등록해 쓰던 팀의 대화가 조용히 검사를 건너뛴다.
-- =====================================================================

BEGIN;

ALTER TABLE guardrail_provider
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT FALSE;

-- 기존 등록분을 활성으로 (지금까지 팀당 하나였다)
UPDATE guardrail_provider SET is_active = TRUE WHERE is_active = FALSE;

DROP INDEX IF EXISTS ux_guardrail_provider_team;

CREATE UNIQUE INDEX IF NOT EXISTS ux_guardrail_provider_active
    ON guardrail_provider (team_id)
    WHERE is_active;

COMMIT;

-- =====================================================================
-- 확인용 — COMMIT 뒤에 따로 실행
-- =====================================================================
-- SELECT team_id, count(*) FILTER (WHERE is_active) AS 활성
--   FROM guardrail_provider GROUP BY team_id;   -- 활성은 팀당 0 또는 1
