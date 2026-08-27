-- 시연용 초기화 — 앱 데이터만 비우고 People DB 목업은 남긴다.
--
-- 언제 쓰나: 시연 영상을 회원가입부터 다시 찍을 때. 팀·계정·커넥터·문서·
-- 프로젝트가 전부 없는 상태가 되어 온보딩을 처음부터 태울 수 있다.
--
-- **`mock_hr` 는 건드리지 않는다.** 그쪽은 고객사 HR 시스템에서 읽어오는
-- 데이터라는 경계이고, 팀이 새로 온보딩한다고 회사 인사 정보가 지워지지는
-- 않는다. person 57 · org 9 · skill 14 · sched · absence 그대로 남는다.
--
-- 실행:
--   docker compose -f infra/docker/docker-compose.yml exec -T db \
--     psql -U project_copilot -d project_copilot < DB/reset_demo.sql
--
-- 실행 후 반드시 할 것 3가지는 파일 맨 아래에 적어 뒀다.

BEGIN;

-- 지우는 순서는 의미가 없다(이 스키마에 FK 제약이 없다). 읽는 사람이
-- 계층을 알아볼 수 있게 묶어서 적는다.

-- 추천·검증·스냅샷 계열 (지금은 전부 0행이지만, 붙고 나서 이 스크립트를
-- 고치는 것을 잊으면 옛 실행 결과가 시연에 섞인다)
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

-- 커넥터 연결. 여기를 비우면 Google·Jira OAuth 를 다시 해야 한다.
-- 그것이 이 초기화의 목적 중 하나다 — 시연 영상에 연결 장면이 들어가고,
-- 테스트 모드 refresh_token(7일) 도 새로 받는다.
TRUNCATE TABLE connector_conn;

-- Agent Platform. **여기가 통째로 빠져 있었다 (2026-08-12 확인).**
--
-- 짧은 코드는 행이 없으면 001 부터 다시 나가므로 새 팀도 TE001 이 된다.
-- 그런데 `agent`·`chat_session`·`mcp_server` 가 team_id 로 옛 TE001 을
-- 가리킨 채 남아 있으면 **새 팀이 그대로 물려받는다** — 위에서 문서 저장소에
-- 대해 경고한 것과 같은 사고가 DB 안에서 난다. 실제로 초기화 전 상태에서
-- 에이전트 9건·대화가 남아 있었다.
--
-- `agent_run`·`tool_call` 은 실행 로그다. 평가의 모수라 평소에는 지우지
-- 않지만(ChatSessionRepository.delete 도 남긴다), 여기서는 테넌트를 통째로
-- 새로 만드는 것이라 같이 비운다 — 옛 팀의 실행이 새 팀 것으로 보인다.
--
-- 레거시 `agent`/`agent_tool`은 2026-08-22에 폐기했다
-- (DB/migrations/2026-08-22_drop_legacy_agent.sql) — 에이전트 정의는 전부
-- 아래 버전 스키마 네 테이블에 있다.
--
-- **2026-08-25 에 같은 구멍이 또 뚫려 있었다.** 8/12 에 채워 넣은 뒤로 테이블이
-- 넷 늘었는데 여기가 따라가지 않았다. `guardrail_provider.team_id` 는 NOT NULL
-- 이라 8/12 과 정확히 같은 사고를 낸다 — 새 팀이 옛 팀의 가드레일 공급자를
-- 그대로 물려받는다. `mcp_call_note` 도 team_id 를 든다.
--
-- ⚠ **테이블을 더하면 손으로 줄을 더해야 하는 곳이 ~~셋~~ 다섯이다** — 여기,
-- `backend/db/repositories.py` 의 `_TEAM_PURGE_STEPS`, `_ACCOUNT_PURGE_STEPS`,
-- 그리고 `DB/reset_eval.sql` 과 `tests/test_ops_purge.py` 의
-- `RESET_KEEP`·`EVAL_KEEP`(2026-08-27 정정 — 스킬 표를 더하다 드러났다).
-- 이 스키마엔 FK 가 하나도 없어 CASCADE 가 없다.
-- 그 테스트가 다섯을 서로 대조하므로 표를 더하면 먼저 깨진다 — 고칠 때는
-- `python manage.py test tests.test_ops_purge` 부터 돌린다.
TRUNCATE TABLE
    tool_call_idempotency, mcp_call_note,
    tool_call, agent_run,
    eval_case_result, eval_run,
    chat_message, chat_session,
    agent_version_tools, agent_version_subagents, agent_favorites,
    agent_versions, agents,
    mcp_tool, mcp_server;

-- `eval_case_result`·`eval_run`도 시연 초기화에서는 비운다. 이 결과는 특정
-- 런타임·데이터셋으로 실행한 성적표라, 회원가입부터 다시 시작하는 새 시연에
-- 이전 성적이 섞이면 안 된다. 평가 입력만 교체하는 `reset_eval.sql`은 반대로
-- 이 두 테이블을 보존한다.

-- 가드레일. `guardrail_provider` 는 팀이 등록한 외부 공급자(team_id NOT NULL),
-- `guardrail_event` 는 걸린 사건 기록이다. 둘 다 테넌트에 매달린다.
TRUNCATE TABLE guardrail_event, guardrail_provider;

-- 스킬 검증·등록 (2026-08-27 에 채웠다 — 8/26~8/27 마이그레이션이 나갈 때
-- 여기가 또 따라오지 않았다. 8/12 · 8/25 에 이어 세 번째다).
--   skill_registration_job      account_id·team_id 를 든 검증 job
--   skill_catalog_revision      사람마다의 카탈로그 리비전
--   skill_eval_regression_case  team_id 를 든 회귀 사례
--   skill_eval_feedback         account_id·team_id 를 든 오발동 신고
-- 넷 다 옛 테넌트를 가리킨 채 남으면 새 팀이 그대로 물려받는다.
TRUNCATE TABLE
    skill_eval_feedback, skill_eval_regression_case,
    skill_catalog_revision, skill_registration_job;

-- 팀·계정·초대. 캘린더는 아직 연동 전이지만 같이 비운다.
TRUNCATE TABLE
    cal_event,
    user_person_link, member_invite,
    team_folder, team_member, team, user_account;

-- 감사 로그. 남겨 두면 운영자 콘솔 화면에 지난 실행 기록이 섞인다.
TRUNCATE TABLE audit_log;

-- 일부러 남기는 것:
--   sys_setting  INVITE_EXPIRE_DAYS=14. schema.sql 의 유일한 INSERT(594줄)라
--                TRUNCATE 하면 되살아나지 않는다. 플랫폼 설정이지 테넌트
--                데이터가 아니다.
--   sys_notice   운영자가 등록하는 공지. 같은 이유.
--   mock_hr.*    고객사 HR 시스템 몫.
--   skill_worker_heartbeat
--                워커 프로세스의 생존 신호다. 테넌트 데이터가 아니고, 비우면
--                「워커가 떠 있나」를 다음 하트비트까지 알 수 없다.

COMMIT;

-- 남은 행 확인 — 아래 셋만 나와야 한다.
SELECT 'sys_setting'   AS t, count(*) FROM sys_setting
UNION ALL SELECT 'sys_notice',  count(*) FROM sys_notice
UNION ALL SELECT 'mock_hr.person', count(*) FROM mock_hr.person;


-- =====================================================================
-- 실행 후 반드시 할 것
-- =====================================================================
--
-- 1. 문서 저장소를 비운다. 이 스크립트는 DB 만 지운다.
--    짧은 코드는 행이 없으면 001 부터 다시 나가므로 새 팀도 TE001 이 되고,
--    옛 TE001/DC001.pdf 가 그대로 남아 있으면 새 문서와 뒤섞인다.
--    아바타도 마찬가지다(새 UA001 이 옛 사람 사진을 물려받는다).
--
--      docker compose -f infra/docker/docker-compose.yml exec web \
--        sh -c 'rm -rf /var/lib/halil/documents/*'
--
-- 2. 운영자 계정을 다시 만든다. `user_account` 를 비우면 `is_admin=true` 인
--    계정이 사라져 `/ops/login` 으로 들어갈 수 없다. 화면에서 승격하는 경로는
--    없다(API 에 없다). 새로 가입한 뒤 이 스크립트로만 켤 수 있다.
--
--      docker compose -f infra/docker/docker-compose.yml exec web \
--        python backend/services/createDB/grant_admin.py <이메일>
--
-- 2-1. **따로 시드할 것 없다(2026-08-22부터).** 팀을 새로 만들면
--      `TeamRepository.create()`가 같은 트랜잭션에서 "기본 어시스턴트"
--      (`agents.is_default_chat=true`)를 자동으로 만든다 — 온보딩 화면에서
--      팀을 만드는 순간 Chat이 바로 된다. 손댈 것이 없다.
--
--      옛 「코파일럿」(전체 도구 + 팀의 아무 에이전트나 위임)은 레거시
--      스키마 전용 개념이라 폐기와 함께 없어졌다. 기본 어시스턴트는 읽기
--      도구만 쓰고 위임하지 않는다 — 쓰기 도구가 필요하면 Builder에서
--      직접 에이전트를 만든다.
--
-- 3. **로컬에서만** 해당한다 — Cloudflare 터널을 새로 띄우고 `.env` 를 고친 뒤
--    **컨테이너를 재생성**한다. Quick Tunnel 은 재실행할 때마다 주소가 바뀐다.
--    빼먹으면 RunPod 이 원문을 받아 갈 주소가 없어 파싱이 전부 실패한다.
--
--      cloudflared tunnel --url http://localhost:8000
--      → 나온 주소를 .env 의 PUBLIC_BACKEND_BASE_URL 과 ALLOWED_HOSTS 에
--      docker compose -f infra/docker/docker-compose.yml up -d --force-recreate web
--
--    `restart` 로는 안 된다 — env_file 을 다시 읽지 않는다.
--
--    **AWS 는 이 단계가 없다**(2026-08-14~). PUBLIC_BACKEND_BASE_URL 이
--    `https://api.halil-ai.site` 로 고정이라 초기화와 무관하다.
--
-- 그리고 촬영 전에 문서 하나를 미리 처리해 RunPod 워커를 깨워 둔다.
-- 모델이 이미지에 구워져 있지 않아 콜드 스타트에 수 GB 를 다시 받는다.
