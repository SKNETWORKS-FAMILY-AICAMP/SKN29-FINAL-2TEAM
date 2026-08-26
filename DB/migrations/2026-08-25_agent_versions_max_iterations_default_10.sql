-- =====================================================================
-- agent_versions.max_iterations 기본값 6 → 10 (2026-08-25)
--
-- 작업목록.md "함께 정할 것"에서 미뤄 두었던 불일치다 — 아키텍처 설계(§3.1-2)는
-- 원래 "기본 10"이었는데 `apps/agents/serializers.py`가 `default=6`으로 되어
-- 있어 API로 만드는 에이전트는 전부 6이었다. 여기서는 설계값(10)으로 되돌린다.
--
-- `runtime_policy.py`의 모델 호출 상한은 `min(agent_versions.max_iterations,
-- ceiling=50)`이라, 기본값이 낮으면 새로 만든 에이전트가 몇 번의 도구 호출만
-- 거쳐도 하드 컷에 걸린다(6턴은 흔한 멀티스텝 작업에도 부족하다).
--
-- DEFAULT만 바꾼다 — 이미 저장된 기존 행은 소급 변경하지 않는다. 새 값은
-- 앞으로 이 컬럼을 생략하고 INSERT하는 행에만 적용된다.
-- =====================================================================

ALTER TABLE agent_versions ALTER COLUMN max_iterations SET DEFAULT 10;
