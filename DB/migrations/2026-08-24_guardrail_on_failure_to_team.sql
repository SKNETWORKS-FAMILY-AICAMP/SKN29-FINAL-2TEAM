-- =====================================================================
-- 가드레일 미응답 시 동작을 **팀 속성**으로 옮긴다 (2026-08-24)
--
-- 처음엔 `guardrail_provider.on_failure` 로 등록 한 건에 붙였다. 값이 그 행에
-- 있으니 자연스러워 보였는데, **저장 위치를 보고 정한 것이지 쓰는 사람을 보고
-- 정한 게 아니었다.**
--
-- 실제로는 이런 일이 난다: 개발팀이 Azure 등록에 「막음」을 켜 두고, 키를
-- 교체하려고 새 등록으로 갈아탄다 → **조용히 「그대로 보냄」이 된다.** 갈아타는
-- 것은 우리가 의도한 사용법(키 교체·공급자 비교·시연)이라 더 나쁘다.
--
-- 「이 팀의 대화가 검사를 못 했을 때 어떻게 하나」는 **팀의 정책**이지 등록물의
-- 속성이 아니다. `team` 은 이미 팀별 정책을 담고 있다(capacity_wk_hours ·
-- overload_pct · workload_weeks) — 같은 자리에 둔다.
--
-- 기본값은 OPEN 이다. 옮기면서 정책이 조용히 바뀌면 안 된다 — 지금 CLOSED 인
-- 등록이 있으면 그 팀을 CLOSED 로 올려 준 뒤에 컬럼을 지운다.
-- =====================================================================

BEGIN;

ALTER TABLE team
    ADD COLUMN IF NOT EXISTS guardrail_on_failure VARCHAR(10) NOT NULL DEFAULT 'OPEN';

-- 옮겨 담는다. 한 팀에 CLOSED 인 등록이 하나라도 있으면 그 팀은 CLOSED 다 —
-- 더 안전한 쪽으로 붙인다(막던 팀이 옮기다가 안 막게 되면 안 된다).
UPDATE team AS t
   SET guardrail_on_failure = 'CLOSED'
 WHERE EXISTS (
       SELECT 1 FROM guardrail_provider AS g
        WHERE g.team_id = t.team_id AND g.on_failure = 'CLOSED'
   );

ALTER TABLE guardrail_provider DROP COLUMN IF EXISTS on_failure;

COMMIT;

-- =====================================================================
-- 확인용 — COMMIT 뒤에 따로 실행
-- =====================================================================
-- SELECT team_id, name, guardrail_on_failure FROM team;
