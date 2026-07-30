import { apiRequest } from './client';

/** 팀장/팀원 구분은 서버가 `org.mgr_id`로 판정한다. HR PERSON에 아직 연결되지 않은 계정은 'unlinked'. */
export type AccountRole = 'leader' | 'member' | 'unlinked';

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
  managed_org_ids: string[];
  person: AccountPerson | null;
}

export interface AuthResult {
  token: string;
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
