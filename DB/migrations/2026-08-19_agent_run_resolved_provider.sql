-- =====================================================================
-- agent_run.resolved_provider / resolved_endpoint_hash 추가 (2026-08-19)
--
-- 정본: docs/설계 및 구현/중간발표 이후/작업기록/Deep_Agents/2026-08-19_01_실행_안정성_설계.md §1
-- (Run Snapshot).
--
-- `agent_version_id`/`runtime_profile_version`은 이미 "이 실행이 어느
-- 정의·어느 배포 코드로 돌았는가"를 남긴다. 남은 구멍은 팀이 등록한
-- 커스텀 엔드포인트(`_team_endpoint`)의 base_url/api_key가 언제든 DB에서
-- 바뀔 수 있다는 것 — 같은 agent_version_id, 같은 runtime_profile_version
-- 으로 실행해도 실제로 어느 서버로 요청이 나갔는지는 지금까지 agent_run에
-- 안 남았다.
--
-- base_url을 원문 그대로 저장하지 않는다 — 사내망 주소가 로그에 그대로
-- 남는 걸 피하려고. sha256(base_url) 정도면 "그때와 지금이 같은
-- 엔드포인트인지" 비교하는 용도로는 충분하다.
--
-- nullable, 기존 행 영향 없음.
-- =====================================================================

BEGIN;

ALTER TABLE agent_run ADD COLUMN IF NOT EXISTS resolved_provider VARCHAR(32);
ALTER TABLE agent_run ADD COLUMN IF NOT EXISTS resolved_endpoint_hash VARCHAR(64);

COMMIT;

-- =====================================================================
-- 확인용 — COMMIT 뒤에 따로 실행
-- =====================================================================
-- SELECT column_name FROM information_schema.columns
--  WHERE table_name = 'agent_run'
--    AND column_name IN ('resolved_provider', 'resolved_endpoint_hash');
