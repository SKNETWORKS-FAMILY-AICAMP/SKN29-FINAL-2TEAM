import { opsRequest } from './opsClient';

export type NoticeStatus = 'PUBLISHED' | 'SCHEDULED' | 'ENDED';
export type ScheduleMode = 'FROM' | 'UNTIL';

export interface OpsNotice {
  notice_id: string;
  title: string;
  content: string;
  status: NoticeStatus;
  schedule_at: string;
  schedule_mode: ScheduleMode;
  created_by: string | null;
  created_by_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface OpsPolicyChange {
  audit_id: string;
  action: string;
  target_type: string | null;
  target_id: string | null;
  payload: Record<string, unknown>;
  actor_account_id: string | null;
  actor_display_name: string | null;
  actor_email: string | null;
  occurred_at: string;
}

export interface NoticeInput {
  title: string;
  content: string;
  status: NoticeStatus;
  schedule_date: string;
  schedule_time: string;
  schedule_mode: ScheduleMode;
  reason?: string;
}

/** 유해성 카테고리는 서버가 정책 안에 담아 준다 — 화면이 목록을 따로 들지 않는다. */
export type ModerationCategory =
  | 'harassment'
  | 'hate'
  | 'sexual'
  | 'self_harm'
  | 'violence'
  | 'illicit';

export type GuardrailStrategy = 'redact' | 'mask';

export interface GuardrailPolicy {
  pii: { enabled: boolean; strategy: GuardrailStrategy };
  moderation: { enabled: boolean; thresholds: Record<ModerationCategory, number> };
  blocked_words: string[];
}

export function fetchGuardrailPolicy(token: string) {
  return opsRequest<GuardrailPolicy>('/ops/policies/guardrail/', { token });
}

export function saveGuardrailPolicy(token: string, policy: GuardrailPolicy, reason?: string) {
  return opsRequest<GuardrailPolicy>('/ops/policies/guardrail/', {
    method: 'PUT',
    token,
    body: { policy, reason },
  });
}

export function fetchInviteTtl(token: string) {
  return opsRequest<{ days: number }>('/ops/policies/invite-ttl/', { token });
}

export function saveInviteTtl(token: string, days: number, reason?: string) {
  return opsRequest<{ days: number }>('/ops/policies/invite-ttl/', {
    method: 'PUT',
    token,
    body: { days, reason },
  });
}

export function fetchNotices(token: string) {
  return opsRequest<OpsNotice[]>('/ops/policies/notices/', { token });
}

export function createNotice(token: string, input: NoticeInput) {
  return opsRequest<OpsNotice>('/ops/policies/notices/', { method: 'POST', token, body: input });
}

export function updateNotice(token: string, noticeId: string, input: NoticeInput) {
  return opsRequest<OpsNotice>(`/ops/policies/notices/${noticeId}/`, {
    method: 'PUT',
    token,
    body: input,
  });
}

export function deleteNotice(token: string, noticeId: string, reason?: string) {
  return opsRequest<void>(`/ops/policies/notices/${noticeId}/`, {
    method: 'DELETE',
    token,
    body: { reason },
  });
}

export function fetchPolicyChanges(token: string) {
  return opsRequest<OpsPolicyChange[]>('/ops/policies/changes/', { token });
}
