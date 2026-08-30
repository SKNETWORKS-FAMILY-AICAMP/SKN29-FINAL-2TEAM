import { opsRequest } from './opsClient';

export interface OpsAccountStats {
  total: number;
  active: number;
  locked: number;
  withdrawn: number;
  duplicate_mapping: number;
  needs_review: number;
}

export interface OpsConnectorStats {
  total: number;
  connected: number;
  expired: number;
  error: number;
  revoked: number;
}

export interface OpsInviteStats {
  pending: number;
  expiring_today: number;
}

export interface OpsRuntimeStats {
  window_days: number;
  runs: number;
  runs_failed: number;
  token_in: number;
  token_out: number;
  runs_without_tokens: number;
  tool_calls_completed: number;
  tool_calls_failed: number;
}

export interface OpsActivity {
  audit_id: string;
  action: string;
  target_type: string | null;
  target_id: string | null;
  occurred_at: string;
  actor_display_name: string | null;
  actor_email: string | null;
}

export interface OpsOverview {
  team_count: number;
  org_count: number;
  accounts: OpsAccountStats;
  connectors: OpsConnectorStats;
  invites: OpsInviteStats;
  runtime: OpsRuntimeStats;
  recent_activity: OpsActivity[];
}

export function fetchOverview(token: string) {
  return opsRequest<OpsOverview>('/ops/overview/', { token });
}
