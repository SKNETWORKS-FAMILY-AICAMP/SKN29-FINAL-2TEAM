import { apiRequest } from './client';

/** 팀의 에이전트. 목록은 서버가 기본 제공 → 이름 순으로 정렬해 준다. */
export interface Agent {
  agent_id: string;
  name: string;
  description: string;
  instruction: string;
  model: string;
  reasoning_effort: string;
  max_iterations: number;
  /** 우리가 제공하는 것. **수정·삭제가 막혀 있다**(서버가 403). */
  is_prebuilt: boolean;
  owner_name: string | null;
  updated_at: string | null;
  tool_refs: string[];
}

/**
 * 편집 화면이 고를 수 있는 도구.
 *
 * **목록은 서버가 준다** — 화면이 내장 도구를 적어 두면 Registry 가 바뀔 때
 * 화면만 옛 목록으로 남는다(실제로 tool id 계약이 두 번 바뀌었다).
 */
export interface ToolChoice {
  tool_ref: string;
  name: string;
  description: string;
  /** '기본 제공' 또는 'MCP · <서버명>'. */
  source: string;
  /** 승인 게이트를 타는 도구인가. 화면이 「승인 필요」를 표시한다. */
  side_effect: boolean;
  server_status?: string;
}

export interface AgentWrite {
  name: string;
  description: string;
  instruction: string;
  model: string;
  reasoning_effort: string;
  max_iterations: number;
  tool_refs: string[];
}

export function listAgents(token: string) {
  return apiRequest<Agent[]>('/agents/', { token });
}

export function getAgent(token: string, agentId: string) {
  return apiRequest<Agent>(`/agents/${agentId}/`, { token });
}

export function createAgent(token: string, body: AgentWrite) {
  return apiRequest<Agent>('/agents/', { method: 'POST', body, token });
}

export function updateAgent(token: string, agentId: string, body: AgentWrite) {
  return apiRequest<Agent>(`/agents/${agentId}/`, { method: 'PUT', body, token });
}

export function deleteAgent(token: string, agentId: string) {
  return apiRequest<void>(`/agents/${agentId}/`, { method: 'DELETE', token });
}

export function listToolChoices(token: string) {
  return apiRequest<ToolChoice[]>('/agents/tools/', { token });
}
