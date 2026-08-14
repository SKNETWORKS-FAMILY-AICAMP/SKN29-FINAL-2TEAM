import { opsRequest } from './opsClient';

export interface OpsAdmin {
  account_id: string;
  email: string;
  display_name: string;
}

export interface OpsAuthResult {
  token: string;
  admin: OpsAdmin;
}

export function opsLogin(email: string, password: string) {
  return opsRequest<OpsAuthResult>('/ops/auth/login/', {
    method: 'POST',
    body: { email, password },
  });
}

export function opsLogout(token: string) {
  return opsRequest<void>('/ops/auth/logout/', { method: 'POST', token });
}
