import { apiRequest } from './client';

/**
 * 가입 경로로 정해지는 역할. 초대 코드로 들어온 계정만 팀원이고 직접 가입은
 * 팀장이다 — HR 시스템 연결 권한이 회사에서 팀장에게만 주어진다는 전제.
 */
export type AccountRole = 'leader' | 'member';

export interface AccountPerson {
  person_id: string;
  name: string;
  email: string;
  org_id: string | null;
  org_name: string | null;
  job_role: string | null;
}

export interface Account {
  account_id: string;
  email: string;
  display_name: string;
  account_status: string;
  role: AccountRole;
  /** 본인 조직 + 하위 조직. 팀원 초대 범위와 같은 기준. HR 미연결이면 빈 배열. */
  scope_org_ids: string[];
  person: AccountPerson | null;
}

export interface AuthResult {
  token: string;
  /** 토큰 만료 시각(ISO8601). 프론트엔드가 만료된 세션을 스스로 버리는 데 쓴다. */
  expires_at: string;
  account: Account;
}

export function login(email: string, password: string) {
  return apiRequest<AuthResult>('/auth/login/', {
    method: 'POST',
    body: { email, password },
  });
}

export function signup(params: {
  email: string;
  password: string;
  displayName: string;
  inviteCode?: string;
}) {
  return apiRequest<AuthResult>('/auth/signup/', {
    method: 'POST',
    body: {
      email: params.email,
      password: params.password,
      display_name: params.displayName,
      invite_code: params.inviteCode ?? '',
    },
  });
}

export function fetchCurrentAccount(token: string) {
  return apiRequest<Account>('/auth/me/', { token });
}

/** 계정 존재 여부를 노출하지 않으려고 서버가 항상 같은 응답을 준다. */
export function requestPasswordReset(email: string) {
  return apiRequest<{ detail: string }>('/auth/password-reset/', {
    method: 'POST',
    body: { email },
  });
}

export function confirmPasswordReset(token: string, password: string) {
  return apiRequest<{ detail: string }>('/auth/password-reset/confirm/', {
    method: 'POST',
    body: { token, password },
  });
}
