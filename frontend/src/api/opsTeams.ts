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

/** 소유자를 넘길 수 있는 후보 — 그 팀의 살아 있는 계정. */
export interface OpsTeamCandidate {
  account_id: string;
  email: string;
  display_name: string;
}

export function fetchTeamOwnerCandidates(token: string, teamId: string) {
  return opsRequest<OpsTeamCandidate[]>(`/ops/teams/${teamId}/owner/`, { token });
}

/**
 * 팀 소유자를 넘긴다. **그 팀에 등록된 모델도 함께 옮겨진다** — 모델이 팀장
 * 계정에 매달려 있어서, 안 옮기면 옛 팀장이 팀을 떠날 때 조용히 사라진다.
 */
export function transferTeamOwner(token: string, teamId: string, accountId: string, reason: string) {
  return opsRequest<{ team_id: string; owner_account_id: string; moved_models: number }>(
    `/ops/teams/${teamId}/owner/`,
    { method: 'POST', token, body: { account_id: accountId, reason } },
  );
}

/** 이 팀이 들고 있는 것과 실제로 있었던 일. **대화 내용·문서 원문은 오지 않는다.** */
export interface OpsTeamAgent {
  agent_id: string;
  name: string;
  description: string | null;
  instruction: string | null;
  model: string | null;
  reasoning_effort: string | null;
  max_iterations: number | null;
  is_prebuilt: boolean;
  status: string;
  tool_refs: string[];
}

export interface OpsTeamRun {
  run_id: string;
  agent_id: string;
  agent_name: string;
  status: string;
  iterations: number;
  token_in: number | null;
  token_out: number | null;
  started_at: string;
  ended_at: string | null;
  tool_calls: number;
  /** 실패한 도구와 그 이유. 실행이 왜 실패했는지는 여기에 있다. */
  failed_tools: string[];
}

export function fetchTeamContent(token: string, teamId: string) {
  return opsRequest<{ agents: OpsTeamAgent[]; runs: OpsTeamRun[] }>(
    `/ops/teams/${teamId}/content/`,
    { token },
  );
}
