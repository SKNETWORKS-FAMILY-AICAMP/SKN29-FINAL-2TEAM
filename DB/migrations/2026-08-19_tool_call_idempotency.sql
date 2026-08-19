-- =====================================================================
-- 2026-08-19 | Phase 8 — 외부 Write Tool Idempotency
--
-- 왜: HITL 승인 후 재개하거나 checkpoint 저장 실패 후 같은 super-step이
-- 재실행되면 jira_create_issues·task_register 같은 side_effect 도구가 같은
-- 요청으로 두 번 실행될 수 있다. LangGraph의 재시도·재개 메커니즘은 이걸
-- 막아주지 않는다("Tool의 외부 side effect는 checkpoint와 같은 트랜잭션이
-- 아니다" — agent-harness-deepagents-code-benchmark.md §4).
--
-- 설계(2026-08-13_04_작업자B_실행코어_세부계획.md Phase 8, 2026-08-19 구현 시
-- 실측으로 인덱스 방식만 수정 — 아래 "정정" 참고):
--   1. session_id + langchain_tool_call_id 조합으로 이미 성공(OK)한 실행이
--      있는지 handler 호출 "전"에 조회한다(services/agent_runtime/factory.py
--      _to_langchain_tool()._run()).
--   2. 있으면 handler를 다시 안 부르고 저장해 둔 result_text를 그대로
--      돌려준다.
--   3. langchain_tool_call_id는 모델이 낸 AIMessage.tool_calls[i]["id"]다 —
--      checkpoint에 그대로 저장되므로 재개해도 같은 값으로 남는다(모델이
--      재시도 때 새로 짓는 값이 아니다).
--   4. session_id를 쓰는 이유: 재개(HITL resume)는 대화(chat_session.
--      session_id)는 그대로지만 agent_run.run_id는 요청마다 새로 만들어진다
--      (apps/chat/api_views.py._build_runtime_context: run_id=uuid4()) —
--      run_id로 묶으면 재개 시나리오를 놓친다.
--   5. 읽기 전용 도구는 대상에서 뺀다(side_effect=True인 도구만 조회한다) —
--      다시 불러도 부작용이 없어서 이 보호가 필요 없다.
--
-- 정정(2026-08-19, 원래 설계의 "partial UNIQUE index" 대신 일반 인덱스로
-- 구현): tool_call은 이미 "선기록 패턴"(ToolCallRepository.begin() — 실행
-- "전"에 PENDING을 미리 넣는다)을 쓴다. 같은 langchain_tool_call_id로 다시
-- 시도되면(정확히 이 마이그레이션이 막으려는 그 상황) begin()이 또 새
-- PENDING 행을 넣는데, UNIQUE 제약을 걸면 그 재기록 INSERT 자체가 위반으로
-- 막혀 버린다 — 정작 잡아야 할 재시도 케이스에서 오류가 난다. 그래서
-- uniqueness는 DB 제약이 아니라 조회 조건(status='OK')으로 보장한다:
-- 시도마다 새 행이 쌓이는 건 그대로 허용하고(감사 로그로서는 오히려
-- 바람직하다 — 재시도가 있었다는 사실 자체가 남는다), "이미 성공한 행이
-- 있는가"만 조회한다. 인덱스는 그 조회 성능용으로만 둔다.
--
-- 실행 위치: DBeaver 또는 psql, 대상 DB의 public 스키마
-- 전제: 없다. 기존 tool_call 행은 한 줄도 고치지 않는다(컬럼 3개는
-- ADD뿐이라 기존 행에 영향 없음).
-- 멱등: ADD COLUMN IF NOT EXISTS, CREATE INDEX IF NOT EXISTS뿐이라 여러 번
-- 실행해도 안전하다.
-- =====================================================================

BEGIN;

ALTER TABLE tool_call ADD COLUMN IF NOT EXISTS session_id UUID;
ALTER TABLE tool_call ADD COLUMN IF NOT EXISTS langchain_tool_call_id VARCHAR(64);
ALTER TABLE tool_call ADD COLUMN IF NOT EXISTS result_text TEXT;

COMMENT ON COLUMN tool_call.session_id IS
    'chat_session.session_id(FK 없음). 재개(HITL resume) 후에도 안 바뀌는 값으로 '
    'idempotency 조회 범위를 잡는다 — run_id는 재개 때마다 새로 생겨 못 쓴다. '
    'session 없이 돈 실행(평가 스크립트 등)은 NULL.';
COMMENT ON COLUMN tool_call.langchain_tool_call_id IS
    '모델이 낸 AIMessage.tool_calls[i]["id"]. checkpoint에 그대로 저장돼 재개해도 '
    '같은 값이다(모델이 재시도 때 새로 짓는 값이 아니다). side_effect=False 도구는 '
    '이 값을 안 채운다(idempotency 보호가 필요 없어서).';
COMMENT ON COLUMN tool_call.result_text IS
    'status=OK일 때 handler가 반환한 결과 텍스트. 같은 (session_id, '
    'langchain_tool_call_id) 조합으로 다시 오면 handler를 다시 안 부르고 이 값을 '
    '그대로 돌려준다.';

-- UNIQUE가 아니다 — 위 "정정" 문단 참고. 조회(session_id, langchain_tool_call_id,
-- status='OK') 성능용 일반 인덱스.
CREATE INDEX IF NOT EXISTS ix_tool_call_idempotency
    ON tool_call (session_id, langchain_tool_call_id)
    WHERE langchain_tool_call_id IS NOT NULL;

COMMIT;
