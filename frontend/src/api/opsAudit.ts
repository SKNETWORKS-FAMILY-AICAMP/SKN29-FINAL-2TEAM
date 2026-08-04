import { opsRequest } from './opsClient';

export interface OpsOperationLog {
  audit_id: string;
  actor_account_id: string;
  actor_display_name: string | null;
  actor_email: string | null;
  action: string;
  proj_id: string | null;
  target_type: string | null;
  target_id: string | null;
  payload: unknown;
  occurred_at: string;
}

export interface OpsAssignmentRun {
  run_id: string;
  snapshot_id: string;
  proj_id: string | null;
  readiness_id: string | null;
  model_version: string | null;
  policy_version: string | null;
  status: string;
  requested_by: string | null;
  requester_display_name: string | null;
  requester_email: string | null;
  started_at?: string;
  created_at?: string;
}

export interface OpsRecommendation {
  reco_id: string;
  run_id: string;
  task_id: string;
  task_name: string | null;
  status: string;
  confidence: number | null;
  missing_data: unknown;
  limitations: unknown;
  assumptions: unknown;
}

export interface OpsValidation {
  valid_id: string;
  reco_id: string;
  run_id: string | null;
  task_id: string | null;
  task_name?: string | null;
  status: string;
  confidence: number | null;
  missing_data: unknown;
}

export interface OpsDecision {
  decision_id: string;
  reco_id: string;
  valid_id: string | null;
  pm_action: string;
  reason: string | null;
  modified_cand_id: string | null;
  decided_by: string | null;
  decider_display_name: string | null;
  decider_email: string | null;
  decided_at: string;
}

export function fetchOperationLogs(token: string) {
  return opsRequest<OpsOperationLog[]>('/ops/audit/operations/', { token });
}

export function fetchAssignmentRuns(token: string) {
  return opsRequest<OpsAssignmentRun[]>('/ops/audit/assignment-runs/', { token });
}

export function fetchRecommendations(token: string) {
  return opsRequest<OpsRecommendation[]>('/ops/audit/recommendations/', { token });
}

export function fetchValidations(token: string) {
  return opsRequest<OpsValidation[]>('/ops/audit/validations/', { token });
}

export function fetchDecisions(token: string) {
  return opsRequest<OpsDecision[]>('/ops/audit/decisions/', { token });
}
