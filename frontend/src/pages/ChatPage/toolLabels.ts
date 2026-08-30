const APPROVAL_TOOL_LABELS: Record<string, string> = {
  table_export: 'Excel 만들기',
  document_create: 'Word 만들기',
  task_register: '업무 등록',
  task_update: '업무 수정',
  jira_create_issues: 'Jira 이슈 등록',
  document_convert: '파일 변환',
  pdf_edit: 'PDF 편집',
  file_sanitize: '메타데이터 제거',
  archive_manage: '압축·해제',
  table_transform: '표 가공·집계',
  diagram_create: '다이어그램 만들기',
  chart_create: '차트 만들기',
  graph_create: '관계 그래프 만들기',
  skill_register: '스킬 등록',
  skill_creator_ask_followup: '스킬 정보 확인',
  delete: '파일 삭제',
};

/** 실행 식별자는 보존하고, 사용자 화면에서만 사람이 읽는 이름으로 바꾼다. */
export function approvalToolLabel(toolRef: string): string {
  return APPROVAL_TOOL_LABELS[toolRef] ?? toolRef;
}
