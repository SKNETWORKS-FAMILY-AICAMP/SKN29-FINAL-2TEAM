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
};

export function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action;
}
