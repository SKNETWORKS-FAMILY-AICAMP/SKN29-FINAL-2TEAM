/** 감사 로그(`audit_log.action`) 코드를 화면에 보여줄 한글 라벨로 바꾼다.
 * 새 조치가 추가될 때마다(섹션이 늘어날 때마다) 여기에 항목을 추가한다.
 * 모르는 코드는 원본 값을 그대로 보여준다. */
const ACTION_LABELS: Record<string, string> = {
  OPS_LOGIN: '운영자 로그인',
  OPS_LOGOUT: '운영자 로그아웃',
  ACCOUNT_LOCK: '계정 정지',
  ACCOUNT_UNLOCK: '계정 재활성',
  ACCOUNT_UNLINK_PERSON: '직원 연결 해제',
  INVITE_DISCARD: '초대 폐기',
  POLICY_INVITE_TTL_CHANGE: '초대 정책 변경',
  POLICY_GUARDRAIL_CHANGE: '가드레일 정책 변경',
  NOTICE_CREATE: '공지 생성',
  NOTICE_UPDATE: '공지 수정',
  NOTICE_DELETE: '공지 삭제',
  LOGIN: '로그인',
  SIGNUP: '회원가입',
  PASSWORD_RESET: '비밀번호 재설정',
  CONNECTOR_CONNECT: '커넥터 연결',
  OPS_TEAM_OWNER_TRANSFER: '팀 소유자 이전',
  OPS_ADMIN_GRANT: '운영자 권한 부여',
  OPS_ADMIN_REVOKE: '운영자 권한 회수',
  OPS_MODEL_REGISTER: '모델 등록',
  OPS_MODEL_REMOVE: '모델 삭제',
  OPS_TEAM_MODEL_SET: '팀 기본 모델 변경',
  OPS_MCP_REGISTER: '커스텀 도구 등록',
  OPS_MCP_UPDATE: '커스텀 도구 수정',
  OPS_MCP_REMOVE: '커스텀 도구 삭제',
  OPS_CONNECTOR_REVOKE: '연결 강제 해제',
};

export function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action;
}
