import { opsRequest } from './opsClient';

export type OpsInviteStatus = 'PENDING' | 'ACCEPTED' | 'EXPIRED' | 'REVOKED';

export interface OpsInvite {
  invite_id: string;
  person_id: string;
  person_name: string | null;
  person_email: string | null;
  org_id: string | null;
  org_name: string | null;
  invited_by: string;
  inviter_email: string | null;
  status: OpsInviteStatus;
  expires_at: string;
  accepted_at: string | null;
  created_at: string;
  linked_account_id: string | null;
  linked_account_email: string | null;
  linked_account_duplicate: boolean;
}

export function fetchInvites(token: string) {
  return opsRequest<OpsInvite[]>('/ops/invites/', { token });
}

export function discardInvite(token: string, inviteId: string) {
  return opsRequest<{ invite_id: string; status: string }>(
    `/ops/invites/${inviteId}/discard/`,
    { method: 'POST', token },
  );
}

export function unlinkInvite(token: string, inviteId: string) {
  return opsRequest<{ invite_id: string; account_id: string; revoked_person_ids: string[] }>(
    `/ops/invites/${inviteId}/unlink/`,
    { method: 'POST', token },
  );
}
