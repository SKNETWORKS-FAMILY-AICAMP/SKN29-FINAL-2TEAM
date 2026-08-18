import { apiRequest } from './client';

/**
 * 새 버전 스키마(`agents`/`agent_versions`) API 클라이언트.
 *
 * `api/agents.ts`(옛 비버전 스키마)와 나란히 존재한다. 2026-08-15부터 Chat이
 * 이 스키마의 에이전트도 직접 선택해서 대화할 수 있다(`ChatPage.tsx` 상단
 * 드롭다운) — 팀마다 자동으로 있는 `is_default_chat` 에이전트가 기본
 * 선택값이다. 옛 "정문"(`agent:*` A2A) 경로와는 별개로 나란히 존재한다.
 */

/** DRAFT(작성 중) / ACTIVE(활성) / DISABLED(팀이 내림). 옛 스키마와 값은 같다. */
export type AgentVersionStatus = 'DRAFT' | 'ACTIVE' | 'DISABLED';

/** 목록에 보이는 한 줄 — 논리적 에이전트 + 현재 버전 스냅샷. */
export interface AgentVersionSummary {
  agent_id: string;
  name: string;
  description: string;
  status: AgentVersionStatus;
  /** Chat이 아무것도 안 고르면 떨어지는 팀의 기본 상대. 팀당 최대 1개. */
  is_default_chat: boolean;
  /** 만든 사람. 삭제 버튼 노출 판단(본인 또는 팀장)에 쓴다. */
  owner_account_id: string | null;
  current_version_id: string | null;
  version: number | null;
  model: string | null;
  reasoning_effort: string | null;
  max_iterations: number | null;
  /** 지금 버전이 위임하는 서브 에이전트 이름. 목록 카드가 버전 번호 대신 보여준다. */
  subagent_names: string[];
  updated_at: string | null;
}

/** 부모 버전이 고정 참조하는 자식 하나. */
export interface SubagentRef {
  child_agent_id: string;
  child_version_id: string;
  alias: string;
  delegation_description: string;
}

/** 상세 조회 — 편집 화면 프리필용. */
export interface AgentVersionDetail extends AgentVersionSummary {
  system_prompt: string;
  tool_refs: string[];
  subagents: SubagentRef[];
}

/** 저장·발행 요청 바디. "저장"과 "발행"은 한 동작이다(버전이 불변이라 중간
 * 상태가 없음) — 이 바디를 보내는 순간 새 불변 버전이 생긴다. */
export interface AgentVersionWrite {
  name: string;
  description: string;
  system_prompt: string;
  model: string | null;
  reasoning_effort: string | null;
  max_iterations: number;
  tool_refs: string[];
  subagents: SubagentRef[];
}

export function listAgentVersions(token: string) {
  return apiRequest<AgentVersionSummary[]>('/agents/versions/', { token });
}

export function getAgentVersion(token: string, agentId: string) {
  return apiRequest<AgentVersionDetail>(`/agents/versions/${agentId}/`, { token });
}

/** 새 논리적 에이전트 + 첫 버전을 함께 발행한다. */
export function createAgentVersion(token: string, body: AgentVersionWrite) {
  return apiRequest<AgentVersionDetail>('/agents/versions/', { method: 'POST', body, token });
}

/**
 * 기존 에이전트에 새 버전을 발행한다. **멱등하지 않다** — 같은 바디로 두 번
 * 부르면 버전이 두 개 생긴다(서버가 그렇게 설계돼 있다, 02 §5.2).
 */
export function publishAgentVersion(token: string, agentId: string, body: AgentVersionWrite) {
  return apiRequest<AgentVersionDetail>(`/agents/versions/${agentId}/`, {
    method: 'PUT',
    body,
    token,
  });
}

/** DRAFT/DISABLED → ACTIVE. 서버가 모델·도구를 다시 검증한다(409면 그 사유). */
export function activateAgentVersion(token: string, agentId: string) {
  return apiRequest<AgentVersionDetail>(`/agents/versions/${agentId}/activate/`, {
    method: 'POST',
    token,
  });
}

/** ACTIVE → DISABLED. 검증 없이 바로 된다. */
export function disableAgentVersion(token: string, agentId: string) {
  return apiRequest<AgentVersionDetail>(`/agents/versions/${agentId}/disable/`, {
    method: 'POST',
    token,
  });
}

/** 논리적 에이전트를 지운다(서버는 ARCHIVED로 내린다). 만든 사람이거나
 * 팀장만 할 수 있다 — 아니면 403. */
export function deleteAgentVersion(token: string, agentId: string) {
  return apiRequest<void>(`/agents/versions/${agentId}/`, { method: 'DELETE', token });
}

/** 이 에이전트를 서브 에이전트로 쓰는 다른 에이전트 이름 목록. 비어 있어야
 * 지울 수 있다 — 삭제 버튼을 누른 시점에 확인 모달보다 먼저 물어본다. */
export function getAgentVersionDependents(token: string, agentId: string) {
  return apiRequest<{ parent_names: string[] }>(`/agents/versions/${agentId}/dependents/`, {
    token,
  });
}
