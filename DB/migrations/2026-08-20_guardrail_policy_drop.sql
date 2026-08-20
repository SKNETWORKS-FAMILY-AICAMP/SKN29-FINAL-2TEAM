-- =====================================================================
-- 내장 가드레일 정책(sys_setting.GUARDRAIL_POLICY) 제거 (2026-08-20)
--
-- 방향이 바뀌었다. 우리가 정책 항목을 만들어 주는 게 아니라, **고객이 이미
-- 가진 가드레일(OpenAI Guardrails·Bedrock·Azure)을 등록해서 쓰게** 한다 —
-- 커스텀 도구 서버(`mcp_server`)·커스텀 모델을 등록하는 것과 같은 자리다.
-- 정본: docs/작업기록/2026-08-20_가드레일_조사와_실측.md §8
--
-- `guardrail_event`(발동 기록)는 **지우지 않는다.** 어느 공급자를 쓰든 무엇이
-- 걸렸는지는 남아야 하고, 화면도 그대로 쓴다.
-- =====================================================================

BEGIN;

DELETE FROM sys_setting WHERE setting_key = 'GUARDRAIL_POLICY';

COMMIT;

-- =====================================================================
-- 확인용 — COMMIT 뒤에 따로 실행
-- =====================================================================
-- SELECT count(*) FROM sys_setting WHERE setting_key = 'GUARDRAIL_POLICY';  -- 0
-- SELECT to_regclass('public.guardrail_event');                              -- 남아 있어야 한다
