import { API_BASE_URL, apiRequest, ApiError, parseErrorBody } from './client';

/** 대화 목록 한 줄. */
export interface ChatSession {
  session_id: string;
  agent_id: string;
  agent_name: string | null;
  proj_id: string | null;
  title: string | null;
  created_at: string | null;
  updated_at: string | null;
}

/** 저장된 메시지. `content`는 카드 구조 그대로다(새로고침 재현용). */
export interface ChatMessage {
  message_id: string;
  role: 'user' | 'agent' | 'system';
  content: ChatMessageContent;
  created_at: string | null;
}

export interface ChatMessageContent {
  type: 'text' | 'result' | 'awaiting_confirmation' | 'error';
  text?: string;
  complete?: boolean;
  /** 에이전트 답에 붙는 이벤트 전체. 화면은 이걸로 카드를 다시 그린다. */
  events?: ChatEvent[];
  tool_ref?: string;
  tool_name?: string;
  arguments?: Record<string, unknown>;
}

export interface ChatSessionDetail extends ChatSession {
  messages: ChatMessage[];
}

/**
 * 스트림 이벤트. **`tool_ref` 유무가 층을 가른다** — 백엔드 계약이다
 * (개발지시_1차 단계 2 결과 · 개발지시_2차 단계 D 결과).
 *
 *   `tool_ref` 없음 → Harness Loop 의 회전. `step/total` 이 `max_iterations` 기준
 *   `tool_ref` 있음 → 그 도구의 내부 진행. `step/total` 이 도구 파이프라인 기준
 *
 * 두 층이 같은 `stage` 타입으로 오기 때문에, 구별하지 않고 그리면 진행 카드가
 * 1/4 → 1/5 → 2/5 → 2/4 로 튄다(실호출에서 확인된 문제).
 */
export type ChatEvent =
  | { type: 'stage'; step: number; total: number; label?: string; intent?: string; tool_ref?: string; tool_call_id?: string }
  | { type: 'queries'; step: number; queries: string[]; tool_ref?: string; tool_call_id?: string }
  | { type: 'stage_done'; step: number; found: number; evidence: number; tool_ref?: string; tool_call_id?: string }
  | { type: 'tool_call_started'; tool_call_id: string | null; tool_ref: string; tool_name: string }
  | {
      type: 'tool_call_finished';
      tool_call_id: string | null;
      tool_ref: string;
      status: 'OK' | 'FAILED';
      error_code?: string;
      /**
       * 사람이 고칠 수 있는 실패 사유. 서버가 `registry.ToolInputError` 일 때만
       * 채운다 — 그 밖의 예외는 문자열에 문서 원문·토큰이 섞일 수 있어 코드만 온다.
       */
      detail?: string | null;
    }
  | { type: 'task_extraction_result'; proj_id: string; result: TaskExtractionPayload; tool_ref?: string; tool_call_id?: string }
  | {
      type: 'jira_status';
      project_key: string;
      counts: Record<string, number>;
      issues: JiraIssue[];
      tool_ref?: string;
      tool_call_id?: string;
    }
  | { type: 'awaiting_confirmation'; run_id: string; tool_ref: string; tool_name: string; arguments: Record<string, unknown> }
  | { type: 'result'; text: string; complete: boolean; stopped_reason?: string; iterations?: number }
  /**
   * 첫 답이 끝난 뒤 서버가 지은 이 대화의 이름. **한 대화에 한 번만** 온다.
   *
   * 만들 때는 첫 발화를 그대로 제목으로 두는데, 「업무 뽑기」는 늘 같은 문장을
   * 보내서 대화 둘이 글자까지 똑같아졌다(2026-08-12 QA).
   */
  | { type: 'session_title'; title: string }
  | { type: 'error'; detail: string };

/** Jira 이슈 한 건. `jira_get_issues` 가 이벤트로 내보내는 모양 그대로. */
export interface JiraIssue {
  jira_issue_id: string;
  summary: string | null;
  /** 사이트마다 다른 표시 문자열. 분기에 쓰지 않는다. */
  status: string | null;
  /** 로직은 이 값만 본다. 모르는 값은 null 이다. */
  status_category: 'TO_DO' | 'IN_PROGRESS' | 'DONE' | null;
  priority: string | null;
  assignee_email: string | null;
  due_at: string | null;
}

export interface TaskExtractionPayload {
  tasks: ExtractedTask[];
  warnings: string[];
  evidence: EvidenceItem[];
  trace: string[];
  model: string;
  reasoning_effort: string;
}

export interface ExtractedTask {
  title: string;
  description: string;
  required_role: string | null;
  effort_hours: number | null;
  start_date: string | null;
  due_date: string | null;
  priority: string | null;
  /** 근거를 못 찾아 비운 필드. **채우지 않았다는 사실 자체가 정보다.** */
  missing_fields: string[];
  evidence_chunk_ids: string[];
}

export interface EvidenceItem {
  chunk_id: string;
  doc_id: string;
  ref?: string;
  text: string;
  heading_path?: string[];
  retrieval_score?: number;
}

/** `tool_ref`가 붙어 있으면 도구의 내부 진행이다. 없으면 Loop 회전. */
export function isToolProgress(event: ChatEvent): boolean {
  return 'tool_ref' in event && Boolean((event as { tool_ref?: string }).tool_ref);
}

export function listSessions(token: string) {
  return apiRequest<ChatSession[]>('/chat/sessions/', { token });
}

export function createSession(
  token: string,
  body: { agent_id: string; proj_id?: string | null; title?: string | null },
) {
  return apiRequest<ChatSession>('/chat/sessions/', { method: 'POST', body, token });
}

export function getSession(token: string, sessionId: string) {
  return apiRequest<ChatSessionDetail>(`/chat/sessions/${sessionId}/`, { token });
}

export function deleteSession(token: string, sessionId: string) {
  return apiRequest<void>(`/chat/sessions/${sessionId}/`, { method: 'DELETE', token });
}

/**
 * 발화를 보내고 이벤트를 받아 가며 기다린다.
 *
 * `apiRequest`를 못 쓴다 — 그쪽은 응답을 통째로 받아 JSON으로 바꾸는데, 여기서는
 * 서버가 보내는 대로 읽어야 진행이 보인다. 응답이 시작된 뒤의 실패는 상태 코드가
 * 아니라 마지막 줄의 `error`로 온다(`streamTaskExtraction`과 같은 규약).
 *
 * `signal`로 중단할 수 있다. 중단해도 서버는 그 run을 FAILED로 닫는다.
 */
export function streamMessage(
  token: string,
  sessionId: string,
  content: string,
  onEvent: (event: ChatEvent) => void,
  signal?: AbortSignal,
) {
  return streamNdjson(`/chat/sessions/${sessionId}/messages/`, token, { content }, onEvent, signal);
}

/**
 * 확인 카드 승인 → 멈춘 실행을 이어 돌린다.
 *
 * **실행할 인자를 보내지 않는다.** 승인 대상은 서버가 저장해 둔 그 호출이고,
 * 화면이 보내는 것은 체크한 항목의 **인덱스뿐**이다 — 화면이 인자를 보내면
 * 그 값으로 외부 시스템이 바뀌므로 승인 게이트가 아무것도 막지 못한다.
 *
 * `selected`를 비우면(undefined) 전체 승인이다.
 */
export function confirmMessage(
  token: string,
  sessionId: string,
  selected: number[] | undefined,
  onEvent: (event: ChatEvent) => void,
  signal?: AbortSignal,
) {
  return streamNdjson(
    `/chat/sessions/${sessionId}/confirm/`,
    token,
    selected === undefined ? {} : { selected },
    onEvent,
    signal,
  );
}

async function streamNdjson(
  path: string,
  token: string,
  body: unknown,
  onEvent: (event: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok || !response.body) {
    const failure = await response.json().catch(() => null);
    throw parseErrorBody(failure, response.status);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // 마지막 조각은 줄이 안 끝났을 수 있어 버퍼에 남긴다.
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      if (!line.trim()) continue;
      onEvent(JSON.parse(line) as ChatEvent);
    }
  }

  // `error`는 여기서 던지지 않는다. 스트림 중간에 온 오류도 이벤트로 그려야
  // 앞 단계 결과물이 화면에 남는다(E2E §2-3) — 던지면 그 카드까지 날아간다.
}

export { ApiError };
