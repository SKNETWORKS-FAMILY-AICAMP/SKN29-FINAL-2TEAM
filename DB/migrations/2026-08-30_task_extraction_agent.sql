-- 「업무 추출 에이전트」를 기존 팀에 심는다(2026-08-30).
--
-- 배경: `task_extraction` 은 채팅 도구였다. 이제 사용자 화면(채팅 「+」·빌더 도구
-- 목록)에서는 안 보이고(`AGENT_ONLY_TOOL_REFS`), 이 prebuilt 에이전트만 그
-- 파이프라인(`services/task_extraction/service.py`)을 부른다. 에이전트 드롭다운에서
-- 직접 골라야 쓰는 **독립 에이전트**다 — 기본 어시스턴트에 위임으로 붙이지 않는다.
--
-- 신규 팀은 `backend/db/repositories.py::TeamRepository.create()` 가
-- `provision_task_extraction_agent` 로 같은 결과를 만든다. 이 스크립트는 그 함수를
-- **기존 팀에** 재현한다. 멱등 — 이미 있으면 건너뛴다.
--
-- 적용: docker exec -i <db> psql -U project_copilot -d project_copilot < 이 파일

DO $$
DECLARE
    t            RECORD;
    v_ext_agent  VARCHAR(5);
    v_ext_ver    VARCHAR(5);
BEGIN
FOR t IN
    SELECT team_id, owner_account_id
    FROM agents
    WHERE is_default_chat = true
LOOP
    SELECT agent_id INTO v_ext_agent
    FROM agents
    WHERE team_id = t.team_id AND is_prebuilt = true AND name = '업무 추출 에이전트'
    LIMIT 1;

    IF v_ext_agent IS NOT NULL THEN
        CONTINUE;
    END IF;

    SELECT 'AG' || lpad((COALESCE(MAX(CAST(SUBSTRING(agent_id FROM 3) AS INT)), 0) + 1)::text, 3, '0')
      INTO v_ext_agent FROM agents;
    SELECT 'AV' || lpad((COALESCE(MAX(CAST(SUBSTRING(agent_version_id FROM 3) AS INT)), 0) + 1)::text, 3, '0')
      INTO v_ext_ver FROM agent_versions;

    INSERT INTO agents
        (agent_id, team_id, name, description, owner_account_id, status, is_prebuilt, is_default_chat)
    VALUES
        (v_ext_agent, t.team_id, '업무 추출 에이전트',
         '프로젝트 기준 문서에서 업무 후보를 뽑아 근거와 함께 정리하고, 원하면 플랫폼 업무로 등록합니다.',
         t.owner_account_id, 'ACTIVE', true, false);

    INSERT INTO agent_versions
        (agent_version_id, agent_id, version, system_prompt, model, reasoning_effort, created_by)
    VALUES
        (v_ext_ver, v_ext_agent, 1,
         '너는 프로젝트 문서에서 해야 할 업무를 뽑아 정리하는 전담 에이전트다.' || E'\n\n' ||
         '사용자가 「이 프로젝트 문서에서 업무를 뽑아 줘」·「할 일 정리해 줘」처럼 요청하면 ' ||
         '`task_extraction` 을 인자 없이 부른다. 기준 문서는 사람이 프로젝트 화면에서 ' ||
         '미리 골라 둔 것을 쓰므로 네가 문서를 고르거나 id 를 넘기지 않는다. ' ||
         '몇 분 걸리는 작업이니 시작 전에 그 사실을 한 줄로 알린다.' || E'\n\n' ||
         '추출이 끝나면 결과를 제목·담당 역할·예상 공수·근거 요약이 보이는 표로 정리해 ' ||
         '보여 준다. 사용자가 등록을 원하면 `task_register` 로 넘긴다(실행 전 승인 카드가 ' ||
         '뜬다). 같은 제목이 이미 있는지 궁금하면 먼저 `task_list` 로 확인한다.' || E'\n\n' ||
         '추출 결과에 `model_fallback_from` 값이 있으면, 답변에 「요청하신 모델(<그 값>)로는 ' ||
         '이 추출을 돌릴 수 없어 gpt-5.6-sol 로 대체했습니다」를 반드시 명시한다.' || E'\n\n' ||
         '「기준 문서가 지정되지 않았다」는 오류가 나면, 프로젝트 화면의 「기준 문서 선택」에서 ' ||
         '문서를 정한 뒤 다시 요청하라고 안내한다.',
         'gpt-5.6-sol', 'medium', t.owner_account_id);

    INSERT INTO agent_version_tools (agent_version_id, tool_ref)
    VALUES (v_ext_ver, 'task_extraction'),
           (v_ext_ver, 'task_register'),
           (v_ext_ver, 'task_list'),
           (v_ext_ver, 'document_list');

    UPDATE agents SET current_version_id = v_ext_ver WHERE agent_id = v_ext_agent;
    RAISE NOTICE '팀 % : 업무 추출 에이전트 % 생성', t.team_id, v_ext_agent;
END LOOP;
END $$;
