import { apiRequest } from './client';

/**
 * `agents`/`agent_versions` 스키마 API 클라이언트.
 *
 * Chat 상단 드롭다운이 이 스키마의 에이전트를 직접 선택한다 — 팀마다 자동으로
 * 있는 `is_default_chat` 에이전트가 기본 선택값이다.
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
  /** 이 계정이 즐겨찾기했는가(2026-08-18). 팀 전체 값이 아니라 요청한
   * 계정만의 값이다 — 같은 에이전트라도 계정마다 다를 수 있다. */
  is_favorite: boolean;
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
  /**
   * 활성화(또는 이미 활성 상태에서 재발행)로 같이 켜진 개인 서브 에이전트
   * 이름들(2026-08-18). **활성화·저장 응답에만 있다** — 평소 목록 조회에는
   * 안 실린다(그때는 켤 게 없어서). 화면이 이 필드로 "서브 에이전트도
   * 같이 활성화됐다"는 토스트를 띄운다.
   */
  cascaded_subagent_names?: string[];
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

/** 즐겨찾기 별 토글(2026-08-18). 계정별 개인 설정 — 소유자·팀장 제한이
 * 없다(누구나 자기 시야에 있는 에이전트를 즐겨찾기할 수 있다). */
export function setAgentVersionFavorite(token: string, agentId: string, favorite: boolean) {
  return apiRequest<AgentVersionSummary>(`/agents/versions/${agentId}/favorite/`, {
    method: 'PUT',
    body: { favorite },
    token,
  });
}
