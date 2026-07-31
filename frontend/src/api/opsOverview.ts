import { opsRequest } from './opsClient';

export interface OpsAccountStats {
  total: number;
  locked: number;
  duplicate_mapping: number;
  needs_review: number;
}

export interface OpsConnectorStats {
  total: number;
  connected: number;
  expired: number;
  error: number;
}

export interface OpsInviteStats {
  pending: number;
  expiring_today: number;
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
  recent_activity: OpsActivity[];
}

export function fetchOverview(token: string) {
  return opsRequest<OpsOverview>('/ops/overview/', { token });
}
