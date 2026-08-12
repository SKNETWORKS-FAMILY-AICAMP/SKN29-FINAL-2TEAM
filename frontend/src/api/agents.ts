import { apiRequest, streamNdjson } from './client';

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
  /**
   * DRAFT(작성 중, Chat·위임에 안 보임) / ACTIVE(활성) / DISABLED(팀이 내림).
   * 생성만으로는 ACTIVE가 안 된다 — `activateAgent()`로 검증을 통과해야 한다.
   */
  status: 'DRAFT' | 'ACTIVE' | 'DISABLED';
  owner_name: string | null;
  updated_at: string | null;
  tool_refs: string[];
}

/** 위임 도구. 이 값을 가진 행이 플랫폼의 정문이다. */
export const PLATFORM_TOOL = 'agent:*';

/**
 * **플랫폼의 정문인가.**
 *
 * 에이전트의 본질은 좁히는 것인데(회의록 정리는 문서만 본다), 정문은 도구를 다
 * 들고 다른 에이전트까지 부른다 — 아무것도 안 좁히므로 에이전트가 아니다.
 * `agent` 행 하나로 표현했을 뿐 개념적으로는 대화 그 자체다.
 *
 * **`is_prebuilt` 로는 못 가른다** — 예시 에이전트(복제해서 쓰는 시작점)도
 * 우리가 넣는 것이라 같은 플래그를 쓴다. 위임할 수 있는 것이 정문이고,
 * `agent:*` 는 Builder 의 도구 목록에 없어서 팀이 실수로 만들 수도 없다.
 */
export function isPlatformAgent(agent: Agent): boolean {
  return agent.tool_refs.includes(PLATFORM_TOOL);
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
  /** 기본 제공 도구만 갖는다. 「도구 확인」 패널이 입력 폼을 만드는 데 쓴다. */
  input_schema?: {
    properties?: Record<string, { type?: string; description?: string; default?: unknown }>;
    required?: string[];
  };
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

/**
 * DRAFT/DISABLED → ACTIVE. 서버가 저장된 값으로 다시 검증하고, `reject`면 409를
 * 던진다(`ApiError.status === 409`) — 에이전트 자체는 그대로 남으니 잃는 것은 없다.
 */
export function activateAgent(token: string, agentId: string) {
  return apiRequest<Agent>(`/agents/${agentId}/activate/`, { method: 'POST', token });
}

/** ACTIVE → DISABLED. 검증 없이 바로 된다. */
export function disableAgent(token: string, agentId: string) {
  return apiRequest<Agent>(`/agents/${agentId}/disable/`, { method: 'POST', token });
}

export function deleteAgent(token: string, agentId: string) {
  return apiRequest<void>(`/agents/${agentId}/`, { method: 'DELETE', token });
}

export function listToolChoices(token: string) {
  return apiRequest<ToolChoice[]>('/agents/tools/', { token });
}

/**
 * 저장하지 않은 설정을 그 자리에서 한 번 실행해 본 이벤트.
 *
 * `tool_call_finished`에 `tool_name`이 없다 — 서버가 `tool_call_started`에서만
 * 이름을 준다. 화면은 그 이름을 들고 있다가 갱신한다. `status`에 `SIMULATED`가
 * 오면 승인이 필요한 도구를 실제로 안 부르고 시뮬레이션했다는 뜻이다.
 */
export type BuilderTestEvent =
  | { type: 'stage'; step: number; total: number; label?: string }
  | { type: 'tool_call_started'; tool_call_id: string | null; tool_ref: string; tool_name: string }
  | {
      type: 'tool_call_finished';
      tool_call_id: string | null;
      tool_ref: string;
      status: 'OK' | 'FAILED' | 'SIMULATED';
      error_code?: string;
      arguments?: Record<string, unknown>;
    }
  | {
      type: 'awaiting_confirmation';
      run_id: string;
      tool_ref: string;
      tool_name: string;
      arguments: Record<string, unknown>;
    }
  | {
      type: 'result';
      text: string;
      complete: boolean;
      stopped_reason?: string;
      iterations?: number;
      /** 쓸 수 있는 도구가 있었는데 하나도 안 부르고 답했으면 false. */
      grounded?: boolean;
    }
  | { type: 'error'; detail: string };

export interface BuilderTestRunInput {
  instruction: string;
  tool_refs: string[];
  model?: string | null;
  reasoning_effort?: string | null;
  max_iterations?: number;
  user_input: string;
}

/** 저장하지 않은 설정을 그 자리에서 한 번 실행해 본다. */
export function runBuilderTest(
  token: string,
  body: BuilderTestRunInput,
  onEvent: (event: BuilderTestEvent) => void,
  signal?: AbortSignal,
) {
  return streamNdjson<BuilderTestEvent>('/agents/build/test/', token, body, onEvent, signal);
}

/** `overall`이 `warn`이어도 저장을 막지 않는다 — `reject`만 막는다. */
export interface BuilderCheckResult {
  /** behavior를 다듬은 지시문. reject일 때는 빈 문자열. */
  refined_instruction: string;
  description_check: { note: string | null };
  /** 트리거 조건·절차·도구 사용 기준·판단 기준 네 요소가 behavior에 있는지. */
  instruction_check: { note: string | null };
  tool_match_check: { missing_tools: string[]; unused_tools: string[] };
  overall: 'pass' | 'warn' | 'reject';
  reject_reason: string | null;
}

export interface BuilderCheckInput {
  name: string;
  description: string;
  /** 사용자가 쓴 원문 지시문. 검증 모델이 이걸 다듬어 refined_instruction을 낸다. */
  behavior: string;
  tool_refs: string[];
}

export function checkBuilderInput(token: string, body: BuilderCheckInput) {
  return apiRequest<BuilderCheckResult>('/agents/build/check/', { method: 'POST', body, token });
}

/** `checkBuilderInput`의 경량판 — description은 안 보고 지시문·도구 정합성만 다시 본다. */
export interface InstructionRecheckResult {
  instruction_check: { note: string | null };
  tool_match_check: { missing_tools: string[]; unused_tools: string[] };
  overall: 'pass' | 'warn' | 'reject';
  reject_reason: string | null;
}

export interface InstructionRecheckInput {
  instruction: string;
  tool_refs: string[];
}

/**
 * 1단계 보정안을 보고 지시문만 고쳤을 때 쓴다. 이름·설명까지 다시 보는
 * `checkBuilderInput`보다 가볍고 빠르다 — description을 안 건드렸을 때만 쓸 것.
 */
export function recheckInstruction(token: string, body: InstructionRecheckInput) {
  return apiRequest<InstructionRecheckResult>('/agents/build/recheck-instruction/', {
    method: 'POST',
    body,
    token,
  });
}

/** 채팅식 테스트와 달리 스트림이 아니라 한 번에 배열로 온다. */
export interface ToolCheckResult {
  tool_ref: string;
  tool_name: string;
  status: 'OK' | 'FAILED' | 'SIMULATED' | 'SKIPPED';
  error_code?: string;
  detail?: string;
  output?: unknown;
  arguments?: Record<string, unknown>;
}

/** 선택한 도구 전부를 모델 없이 순서대로 직접 불러 본다. */
export function checkBuilderTools(
  token: string,
  body: { tool_refs: string[]; arguments: Record<string, Record<string, unknown>> },
) {
  return apiRequest<{ results: ToolCheckResult[] }>('/agents/build/check-tools/', {
    method: 'POST',
    body,
    token,
  });
}
