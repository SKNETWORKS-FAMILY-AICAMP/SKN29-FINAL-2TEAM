import { apiRequest } from './client';

export type InviteStatus = 'PENDING' | 'ACCEPTED' | 'EXPIRED' | 'REVOKED';

export interface Invite {
  invite_id: string;
  person_id: string;
  person_name: string;
  person_email: string;
  org_name: string | null;
  status: InviteStatus;
  expires_at: string;
  accepted_at: string | null;
  created_at: string;
}

/** 발급 응답에만 원문 코드가 담긴다. 서버는 해시만 저장하므로 다시 조회할 수 없다. */
export interface IssuedInvite extends Invite {
  code: string;
}

export interface InviteCandidate {
  person_id: string;
  name: string;
  email: string;
  org_id: string | null;
  org_name: string | null;
  job_role: string | null;
}

export interface InvitePreview {
  person_name: string;
  person_email: string;
  org_name: string | null;
  expires_at: string;
}

export function previewInvite(code: string) {
  return apiRequest<InvitePreview>('/invites/preview/', {
    method: 'POST',
    body: { code },
  });
}

export function listInviteCandidates(token: string) {
  return apiRequest<InviteCandidate[]>('/invites/candidates/', { token });
}

export function createInvite(token: string, personId: string) {
  return apiRequest<IssuedInvite>('/invites/', {
    method: 'POST',
    body: { person_id: personId },
    token,
  });
}

export function revokeInvite(token: string, inviteId: string) {
  return apiRequest<void>(`/invites/${inviteId}/revoke/`, { method: 'POST', token });
}
