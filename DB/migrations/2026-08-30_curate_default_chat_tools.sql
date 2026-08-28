-- 기본 어시스턴트(`is_default_chat`)의 도구 목록을 새로 좁힌 `DEFAULT_CHAT_TOOL_REFS`
-- 에 맞춘다(2026-08-30). 2026-08-29 마이그레이션은 시스템 2개를 뺀 전 도구(30개)를
-- 붙였는데, 전문·관리 성격 도구까지 기본으로 켜져 목록이 길다는 지적이 있었다.
--
-- 아래 여덟은 기본에서 뺀다 — "실제 업무에서 바로 쓸 법한 것 + 검색·조회"라는
-- 기준에서 벗어나거나 자주 안 쓴다. 필요한 팀은 팀장이 Builder 에서 개별로 켠다:
--   document_sync      · 연결 저장소 재색인(관리 작업)
--   file_inspect       · 형식·해시·페이지 수 기술 점검
--   file_sanitize      · 작성자 메타데이터 제거(보안 정책용)
--   archive_manage     · ZIP 묶기/풀기
--   data_quality_check · 빈 값·중복·스키마 감사(데이터 전문 작업)
--   diagram_create / chart_create / graph_create · 시각화(자주 안 씀)
--
-- **`is_default_chat = true` 에이전트에만** 적용한다 — 사용자가 직접 만든
-- 에이전트 버전이 이 도구들을 골랐다면 그 선택을 존중한다.

DELETE FROM agent_version_tools
WHERE tool_ref IN (
        'document_sync', 'file_inspect', 'file_sanitize',
        'archive_manage', 'data_quality_check',
        'diagram_create', 'chart_create', 'graph_create'
    )
  AND agent_version_id IN (
        SELECT current_version_id
        FROM agents
        WHERE is_default_chat = true
          AND current_version_id IS NOT NULL
    );
