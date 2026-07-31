import { opsRequest } from './opsClient';

export interface OpsTeam {
  team_id: string;
  name: string;
  owner_account_id: string;
  owner_email: string | null;
  owner_display_name: string | null;
  src_org_id: string | null;
  src_org_name: string | null;
  member_count: number;
  account_count: number;
  unregistered_count: number;
  locked_count: number;
  pending_invite_count: number;
  created_at: string;
}

/**
 * 운영자가 보는 단위는 HR 조직도가 아니라 팀이다 — 우리 플랫폼을 쓰는 것이
 * 팀이고, 조직도는 고객사 내부 사정이라 운영자가 알 필요가 없다.
 */
export function fetchOpsTeams(token: string) {
  return opsRequest<OpsTeam[]>('/ops/teams/', { token });
}
