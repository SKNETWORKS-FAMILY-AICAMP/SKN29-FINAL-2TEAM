const OPS_SESSION_KEY = 'halil.opsSession';

export interface OpsSession {
  email: string;
  signedInAt: string;
}

export function loadOpsSession(): OpsSession | null {
  try {
    const raw = sessionStorage.getItem(OPS_SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as OpsSession;
    return parsed.email ? parsed : null;
  } catch {
    return null;
  }
}

export function saveOpsSession(email: string) {
  const session: OpsSession = {
    email,
    signedInAt: new Date().toISOString(),
  };

  try {
    sessionStorage.setItem(OPS_SESSION_KEY, JSON.stringify(session));
  } catch {
    // 세션 저장소를 사용할 수 없는 환경에서는 현재 탭의 로그인 상태를 유지할 수 없다.
  }
}

export function clearOpsSession() {
  try {
    sessionStorage.removeItem(OPS_SESSION_KEY);
  } catch {
    // 세션 저장소 정리 실패는 로그아웃 화면 이동을 막지 않는다.
  }
}
