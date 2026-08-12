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
TRUNCATE TABLE
    tool_call, agent_run,
    chat_message, chat_session,
    agent_tool, agent,
    mcp_tool, mcp_server;

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
-- 2-1. **에이전트를 다시 시드한다.** 위에서 `agent` 를 비웠으므로 기본 제공
--      에이전트(「코파일럿」)가 없다. 없으면 Chat 이 아무것도 못 한다 —
--      화면에는 「아직 우리 팀 에이전트가 없습니다」만 뜬다.
--      **팀을 먼저 만든 뒤**(People DB 연결) 돌려야 한다. 팀이 없으면 붙일
--      곳이 없다.
--
--        docker compose -f infra/docker/docker-compose.yml exec web \
--          python backend/services/createDB/seed_agents.py --all-teams
--
--      `--team TE001` 로 하나만 할 수도 있다. 인자를 빼면 실행되지 않는다.
--
-- 3. Cloudflare 터널을 새로 띄우고 `.env` 를 고친 뒤 **컨테이너를 재생성**한다.
--    Quick Tunnel 은 재실행할 때마다 주소가 바뀐다. 이걸 빼먹으면 RunPod 이
--    원문을 받아 갈 주소가 없어 등록한 문서의 파싱이 전부 실패한다.
--
--      cloudflared tunnel --url http://localhost:8000
--      → 나온 주소를 .env 의 PUBLIC_BACKEND_BASE_URL 과 ALLOWED_HOSTS 에
--      docker compose -f infra/docker/docker-compose.yml up -d --force-recreate web
--
--    `restart` 로는 안 된다 — env_file 을 다시 읽지 않는다.
--
-- 그리고 촬영 전에 문서 하나를 미리 처리해 RunPod 워커를 깨워 둔다.
-- 모델이 이미지에 구워져 있지 않아 콜드 스타트에 수 GB 를 다시 받는다.
