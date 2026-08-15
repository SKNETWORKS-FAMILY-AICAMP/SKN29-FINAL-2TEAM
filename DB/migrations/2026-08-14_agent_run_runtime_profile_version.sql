-- =====================================================================
-- agent_run.runtime_profile_version 추가 (2026-08-14)
--
-- 배포된 런타임 코드 버전(git commit SHA)을 실행 로그에 같이 남긴다.
-- 미들웨어·정책·프롬프트가 바뀌면 같은 agent_version_id라도 동작이 달라질
-- 수 있어서, 장애·평가 재현에는 "어느 agent_version이 돌았는가"뿐 아니라
-- "그때 배포된 코드가 정확히 무엇이었는가"도 필요하다.
--
-- nullable, 기존 행 영향 없음 — 배포 파이프라인이 GIT_COMMIT_SHA를 넘기기
-- 전까지는(config/settings/base.py RUNTIME_PROFILE_VERSION) 계속 NULL이다.
-- =====================================================================

BEGIN;

ALTER TABLE agent_run ADD COLUMN IF NOT EXISTS runtime_profile_version VARCHAR(64);

COMMIT;

-- =====================================================================
-- 확인용 — COMMIT 뒤에 따로 실행
-- =====================================================================
-- SELECT column_name FROM information_schema.columns
--  WHERE table_name = 'agent_run' AND column_name = 'runtime_profile_version';
