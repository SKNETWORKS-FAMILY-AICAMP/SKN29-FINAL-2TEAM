-- 기본 어시스턴트(`is_default_chat`)의 도구 목록을 `DEFAULT_CHAT_TOOL_REFS` 로 맞춘다
-- (2026-08-29). 예전에는 `side_effect=False` 만 붙어서 Word·Excel 만들기, 파일 변환,
-- PDF 편집, 업무 등록·수정, 시각화(diagram/chart/graph) 도구가 빠져 있었다.
--
-- 누락분만 멱등으로 추가한다. **제거는 하지 않는다** — 팀장이 Builder 에서 뺀
-- 도구가 있으면 그 선택을 존중한다. 사용자가 직접 만든 에이전트 버전
-- (`is_default_chat = false`)은 건드리지 않는다.

WITH refs(tool_ref) AS (
    VALUES
        ('absence_list'), ('archive_manage'), ('calculate'), ('chart_create'),
        ('data_quality_check'), ('diagram_create'), ('document_convert'),
        ('document_create'), ('document_list'), ('document_read'),
        ('document_search'), ('document_sync'), ('file_compare'),
        ('file_inspect'), ('file_sanitize'), ('get_current_datetime'),
        ('graph_create'), ('jira_create_issues'), ('jira_get_issues'),
        ('pdf_edit'), ('people_list'), ('project_list'), ('table_export'),
        ('table_transform'), ('task_extraction'), ('task_list'),
        ('task_register'), ('task_update'), ('web_search'), ('workload_report')
)
INSERT INTO agent_version_tools (agent_version_id, tool_ref)
SELECT a.current_version_id, refs.tool_ref
FROM agents AS a
CROSS JOIN refs
WHERE a.is_default_chat = true
  AND a.current_version_id IS NOT NULL
ON CONFLICT (agent_version_id, tool_ref) DO NOTHING;
