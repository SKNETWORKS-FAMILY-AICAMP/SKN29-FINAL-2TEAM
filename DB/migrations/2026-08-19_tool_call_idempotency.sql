-- =====================================================================
-- tool_call_idempotency 테이블 추가 (2026-08-19, §6순위 — Phase 8 외부
-- Write Tool Idempotency)
--
-- HITL 승인 후 재개하거나, checkpoint 저장 실패 후 같은 super-step이
-- 재실행되면 jira_create_issues·task_register 같은 외부 side_effect 도구가
-- 같은 요청으로 두 번 실행될 수 있다(LangGraph의 재시도·재개 메커니즘은
-- 이걸 막아주지 않는다). 모델이 낸 AIMessage.tool_calls[i]["id"]는
-- checkpoint에 그대로 저장돼 재개해도 같은 값으로 남는다 — 이 값과
-- run_id 조합으로 "이미 성공한 호출인지"를 실행 직전에 확인한다.
--
-- **기존 tool_call 테이블을 그대로 확장하지 않는다.** tool_call의
-- 선기록(PENDING insert) → 갱신(UPDATE) 흐름은 executor의 스트림 이벤트
-- (tracing/__init__.py)가 도구를 실제로 실행한 **뒤에** 그 결과를 보고
-- 채운다 — 반면 이 idempotency 확인은 도구를 실행하기 **직전**
-- (services/agent_runtime/factory.py의 _to_langchain_tool()._run())에
-- 필요해서, tool_call의 관측용 생명주기와는 다른 시점에 다른 방식으로
-- 쓰고 읽는다. 같은 표에 두 쓰기 경로를 얹으면 같은 도구 호출이 행
-- 두 개로 이중 기록되므로, 목적이 다른 전용 표를 하나 더 둔다.
--
-- session_id가 아니라 run_id로 스코프를 잡는다 — HITL resume(§0순위)이
-- "멈췄던 실행의 run_id를 그대로 이어받는다"고 이미 정해 뒀고
-- (AgentExecutor.resume() docstring), 같은 super-step 재시도도 같은
-- run_id 안에서 일어난다. 세션 하나에는 여러 run이 있을 수 있어 session_id로
-- 잡으면 서로 무관한 실행끼리 같은 tool_call_id 문자열을 우연히 공유할 때
-- (제공자가 생성하는 고유 ID라 극히 낮은 확률) 불필요하게 더 넓게 걸린다.
--
-- run_id는 agent_run.run_id(FK 없음, 이 저장소의 다른 표와 같은 관례)다.
-- =====================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS tool_call_idempotency (
    run_id                   UUID         NOT NULL,   -- agent_run.run_id(FK 없음)
    langchain_tool_call_id   VARCHAR(64)  NOT NULL,    -- AIMessage.tool_calls[i]["id"]
    tool_ref                 VARCHAR(100) NOT NULL,
    -- 재실행 대신 그대로 돌려줄 결과. 원문 그대로 담는다(화면 요약용
    -- TOOL_OUTPUT_SUMMARY_MAX=500과는 목적이 다르다 — 여기는 "모델이 실제로
    -- 봤던 것과 같은 값을 다시 준다"가 목적이라 자르면 재실행 때와 다른
    -- 입력을 모델에게 주게 된다). 폭주 방지용 상한만 애플리케이션에서 건다
    -- (IDEMPOTENCY_RESULT_MAX_CHARS, backend/db/agent_platform.py).
    result_text              TEXT         NOT NULL,
    created_at                TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, langchain_tool_call_id)
);

COMMIT;

-- =====================================================================
-- 확인용 — COMMIT 뒤에 따로 실행
-- =====================================================================
-- SELECT table_name FROM information_schema.tables
--  WHERE table_name = 'tool_call_idempotency';
