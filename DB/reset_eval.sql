-- 평가용 초기화 — 프로젝트·문서·파싱 산출물만 비우고 테넌트는 남긴다.
--
-- 언제 쓰나: 에이전트 평가 세트(`tests/eval/`)를 올리기 전에 실서버의 옛
-- 프로젝트와 문서를 걷어낼 때. 팀·계정·커넥터·에이전트 정의는 남으므로
-- **재로그인도 Google/Jira 재연결도 필요 없다.** 회원가입부터 다시 찍는
-- 시연용 초기화는 이 파일이 아니라 `reset_demo.sql` 이다.
--
-- 실행 (RDS):
--   psql "$DATABASE_URL" -f DB/reset_eval.sql
--
-- 실행 (로컬 컨테이너):
--   docker compose -f infra/docker/docker-compose.yml exec -T db \
--     psql -U project_copilot -d project_copilot < DB/reset_eval.sql
--
-- ⚠ **먼저 백업한다.** 되돌릴 수 없다.
--   pg_dump "$DATABASE_URL" > backup_$(date +%Y%m%d_%H%M).sql
--
-- ⚠ **「내 파일」도 같이 사라진다.** 개인 파일은 별도 테이블이 아니라 `doc`
--   에 `owner_account_id` 로 들어간다. 문서를 비운다는 것은 그것까지 비운다는
--   뜻이다.
--
-- 실행 후 반드시 할 것 3가지는 파일 맨 아래에 적어 뒀다.

BEGIN;

-- 지우는 순서는 의미가 없다(이 스키마에 FK 제약이 없다). 읽는 사람이 계층을
-- 알아볼 수 있게 묶어서 적는다. 묶음은 `reset_demo.sql` 과 같은 순서다 —
-- 두 파일을 나란히 놓고 무엇이 빠졌는지 볼 수 있어야 한다.

-- 추천·검증·스냅샷 계열
TRUNCATE TABLE
    valid_check, valid_result,
    reco_cand, reco_evidence, reco_result,
    decision_rec, assign_run, workload_result,
    feat_ready_result, ana_snapshot, person_snap, exist_task_snap;

-- 지식 모델·업무 계열
TRUNCATE TABLE
    task_know_src, task,
    model_know_item, proj_know_model,
    feat_cluster_item, feat_cluster,
    know_item_src, know_item;

-- 문서 파싱 산출물. vec_idx → chunk → doc_block 순으로 적는다.
-- chunk.search_text 에 원문이 그대로 들어 있어 doc 만 지우면 본문이 남는다.
TRUNCATE TABLE vec_idx, chunk, doc_block, doc_sync, doc;

-- Jira 수집분과 프로젝트
TRUNCATE TABLE exist_task, proj_member, proj_source, proj;

-- 대화와 실행 로그. **프로젝트를 지우면 여기도 지워야 한다** — `chat_session`
-- 이 `proj_id` 를 들고 있어서, 남겨 두면 없는 프로젝트를 가리키는 대화가
-- 사이드바에 남는다. 실행 로그(`agent_run`·`tool_call`)는 그 대화에 매달려
-- 있으므로 같이 간다. 평가의 모수를 새로 쌓는 것이 이 초기화의 목적이기도 하다.
TRUNCATE TABLE
    tool_call_idempotency, mcp_call_note,
    tool_call, agent_run,
    guardrail_event,
    chat_message, chat_session;

-- 일부러 남기는 것 (`tests/test_ops_purge.py` 의 EVAL_KEEP 과 같은 목록이다):
--   user_account · team · team_member · team_folder · member_invite ·
--   user_person_link   테넌트 그 자체. 이 초기화가 남기려는 것.
--   connector_conn     Google/Jira 재연결을 피하려는 것이 이 파일의 존재 이유다.
--   agents · agent_versions · agent_version_tools · agent_version_subagents ·
--   agent_favorites    에이전트 정의. 평가 대상이지 평가 데이터가 아니다.
--   mcp_server · mcp_tool · guardrail_provider   팀이 등록한 설정.
--   audit_log          감사 기록은 어느 삭제도 지우지 않는다(`_TEAM_PURGE_STEPS`
--                      와 같은 원칙). 지워진 프로젝트를 가리키는 행이 남지만
--                      로그는 그 시점의 사실이다.
--   cal_event          아직 연동 전이라 프로젝트와 무관하다.
--   sys_setting · sys_notice · mock_hr.*   플랫폼 설정과 고객사 HR 몫.

COMMIT;


-- =====================================================================
-- 확인용 — COMMIT 뒤에 따로 실행
-- =====================================================================
-- SELECT 'proj' AS t, count(*) FROM proj
-- UNION ALL SELECT 'doc',          count(*) FROM doc
-- UNION ALL SELECT 'chunk',        count(*) FROM chunk
-- UNION ALL SELECT 'vec_idx',      count(*) FROM vec_idx
-- UNION ALL SELECT 'chat_session', count(*) FROM chat_session
-- UNION ALL SELECT 'team',         count(*) FROM team
-- UNION ALL SELECT 'user_account', count(*) FROM user_account
-- UNION ALL SELECT 'connector_conn', count(*) FROM connector_conn;
--   앞의 다섯은 0, 뒤의 셋은 그대로여야 한다.


-- =====================================================================
-- 실행 후 반드시 할 것
-- =====================================================================
--
-- 1. **Drive 폴더에서 옛 파일을 치운다.** 이 스크립트는 DB 만 지운다.
--    아래 3번에서 폴더를 다시 저장하면 전체를 훑으므로(`intake_connector_documents`)
--    폴더에 남아 있는 옛 파일이 **그대로 다시 들어온다.** 지운 의미가 없어진다.
--    (대화 시작 시의 Changes 동기화는 변경분만 보므로 이때는 안 들어온다.
--     그래서 「안 지웠는데 조용히 되살아나는」 형태로 나타난다.)
--
-- 2. 문서 저장소(S3)의 원문을 치운다. `doc` 행이 사라져 가리키는 것이 없는
--    객체만 남는다. 새 문서와 뒤섞이지는 않지만(키가 doc_id 기반) 용량만 쓴다.
--
--      aws s3 rm s3://$AWS_STORAGE_BUCKET_NAME/documents/ --recursive
--
-- 3. 팀 폴더 지정을 다시 저장한다. `team_folder` 는 남겼으므로 폴더 설정
--    자체는 그대로지만, 저장을 다시 눌러야 전체 수집(`intake_connector_documents`)
--    이 돈다. 대화 시작 시의 Changes 동기화는 **변경분만** 따라가므로
--    이미 폴더에 있던 파일을 새로 등록해 주지 않는다.
