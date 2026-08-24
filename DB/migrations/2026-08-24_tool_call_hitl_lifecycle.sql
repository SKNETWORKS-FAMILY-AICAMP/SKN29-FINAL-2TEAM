-- 2026-08-24 — HITL interrupt/resume 전후의 tool_call 행을 같은 호출로 연결한다.
--
-- 기존 추적기는 `(run_id, langchain_tool_call_id) -> DB UUID` 관계를 스트림의
-- Python dict에만 보관했다. 승인 대기 interrupt로 첫 스트림이 끝나면 그 dict가
-- 사라지고, resume 스트림의 성공 결과가 원래 PENDING 행을 찾지 못했다. 첫
-- 스트림의 finally는 그 행을 FAILED / STREAM_CLOSED로 잘못 닫기도 했다.
--
-- `tool_call_idempotency`는 실행 성공 뒤 result_text를 저장하는 중복 실행 방지
-- 표라 승인 대기·거부 상태를 담을 수 없다. 관측 생명주기의 정본인 tool_call에
-- LangChain 호출 ID를 추가한다.

BEGIN;

ALTER TABLE tool_call
    ADD COLUMN IF NOT EXISTS langchain_tool_call_id VARCHAR(64);

CREATE UNIQUE INDEX IF NOT EXISTS ux_tool_call_run_langchain_id
    ON tool_call (run_id, langchain_tool_call_id)
    WHERE langchain_tool_call_id IS NOT NULL;

COMMENT ON COLUMN tool_call.langchain_tool_call_id IS
    'AIMessage.tool_calls[i]["id"]; HITL interrupt/resume correlation key';

COMMIT;

-- 확인용
-- SELECT tool_call_id, run_id, langchain_tool_call_id, status, error_code
--   FROM tool_call
--  ORDER BY created_at DESC
--  LIMIT 20;
