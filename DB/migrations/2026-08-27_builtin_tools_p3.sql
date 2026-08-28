-- P3: 이미 존재하는 기본 채팅 에이전트에도 신규 읽기 전용 Tool을 붙인다.
--
-- 새 팀의 기본 에이전트는 `ensure_default_agent()`가 Registry의 side_effect=false
-- Tool을 자동으로 넣는다. 이 데이터 마이그레이션은 그 코드가 배포되기 전에 이미
-- 만들어진 기본 에이전트만 보완한다. 사용자가 직접 만든 에이전트 버전은 불변이며
-- 선택하지 않은 Tool을 임의로 추가하면 안 되므로 대상에서 제외한다.

WITH refs(tool_ref) AS (
    VALUES
        ('document_read'),
        ('file_inspect'),
        ('data_quality_check'),
        ('file_compare'),
        ('calculate')
)
INSERT INTO agent_version_tools (agent_version_id, tool_ref)
SELECT a.current_version_id, refs.tool_ref
FROM agents AS a
CROSS JOIN refs
WHERE a.is_default_chat = true
  AND a.current_version_id IS NOT NULL
ON CONFLICT (agent_version_id, tool_ref) DO NOTHING;
