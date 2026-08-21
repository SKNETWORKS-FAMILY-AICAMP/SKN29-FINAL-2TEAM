-- =====================================================================
-- mcp_call_note 테이블 추가 (2026-08-21, 병렬실행 Phase 3)
--
-- 정본:
--   docs/작업기록/Deep_Agents/2026-08-21_04_MCP_동시_쓰기_경고_설계.md §3
--   docs/작업기록/Deep_Agents/2026-08-21_03_외부_Write_Tool_재시도_안전성.md §4.2
--
-- 승인 카드에 "지금 이걸 승인해도 되나"를 판단할 재료를 붙이려고 둔다. 두
-- 가지를 같은 표에 `kind`로 나눠 담는다:
--
--   ACTIVE     — 지금 실행 중인 MCP 호출. 시작할 때 넣고 끝나면(성공·실패
--                무관) 지운다. 같은 mcp_server_id에 다른 실행이 이미 돌고
--                있으면 승인 카드에 경고를 띄운다.
--   TIMED_OUT  — timeout으로 결과를 확인하지 못한 호출. 지우지 않는다.
--                같은 run에서 같은 tool_ref를 또 부르려 하면(모델의 자발적
--                재시도) 승인 카드에 "이미 실행됐을 수 있다"고 경고한다.
--
-- **왜 직렬화(lock)가 아니라 경고인가**: 원래 설계(2026-08-20_02 §5.2)는 같은
-- MCP 서버 호출을 advisory lock으로 줄 세우는 것이었다. 그런데 그 lock은
-- 즉시 끝나는 로컬 쓰기용이고(memory/write_lock.py — 락을 쥔 채 handler를
-- 부른다), MCP 호출은 최대 480초까지 걸릴 수 있어(runtime_policy.py) 대기하는
-- 호출마다 전용 DB 커넥션을 그만큼 붙잡게 된다. 더 근본적으로는 MCP 서버가
-- 동시 접속을 못 받는 게 아니다 — 우리가 모르는 건 "그 요청이 하는 일이
-- 동시에 일어나도 안전한가"이고, 이건 tools/list로는 애초에 알 수 없다.
-- 정보가 없는 채로 기다리게 하는 대신 아는 사실만 정직하게 보여주고 판단은
-- 승인하는 사람에게 맡긴다(2026-08-21_04 §2).
--
-- **왜 tool_call_idempotency와 별도 표인가**: 그쪽은 "이미 성공한 호출의
-- 결과"만 담아 재실행을 건너뛰는 용도라 성공한 것만 들어간다. 여기는 진행
-- 중이거나(ACTIVE) 결과를 모르는(TIMED_OUT) 호출이 대상이라 담는 시점도
-- 지우는 규칙도 다르다.
--
-- run_id는 agent_run.run_id(FK 없음, 이 저장소의 다른 표와 같은 관례)다.
-- =====================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS mcp_call_note (
    run_id                   UUID         NOT NULL,   -- agent_run.run_id(FK 없음)
    langchain_tool_call_id   VARCHAR(64)  NOT NULL,   -- AIMessage.tool_calls[i]["id"]
    -- ACTIVE = 실행 중, TIMED_OUT = timeout으로 결과 미확인. 위 주석 참고.
    -- 같은 (run_id, tool_call_id)가 두 kind로 다 있을 수 있다 — timeout이 나도
    -- 백그라운드 스레드는 계속 돌기 때문에 ACTIVE 행이 아직 살아 있다.
    kind                     VARCHAR(16)  NOT NULL,
    tool_ref                 VARCHAR(100) NOT NULL,   -- 'mcp:<mcp_tool_id>'
    -- 어느 MCP 서버인지. "같은 서버에 다른 호출이 도는 중"을 판단하는 기준이다.
    mcp_server_id            VARCHAR(5),
    -- 남의 팀 실행을 보고 경고하지 않도록 조회에 함께 건다(McpServerRepository
    -- .credentials_for_tool()이 team_id를 두 번째 자물쇠로 거는 것과 같은 이유).
    team_id                  VARCHAR(5)   NOT NULL,
    started_at               TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, langchain_tool_call_id, kind)
);

-- "이 서버에 지금 도는 다른 호출이 있나"가 주 조회다.
CREATE INDEX IF NOT EXISTS idx_mcp_call_note_server
    ON mcp_call_note (team_id, mcp_server_id, kind, started_at);

-- "이 run에서 이 도구가 timeout난 적 있나"가 두 번째 조회다.
CREATE INDEX IF NOT EXISTS idx_mcp_call_note_run_tool
    ON mcp_call_note (run_id, tool_ref, kind);

COMMIT;

-- =====================================================================
-- 확인용 — COMMIT 뒤에 따로 실행
-- =====================================================================
-- SELECT table_name FROM information_schema.tables
--  WHERE table_name = 'mcp_call_note';
