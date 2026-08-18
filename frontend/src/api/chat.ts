import { apiRequest, ApiError, streamNdjson } from './client';

/** 대화 목록 한 줄. */
export interface ChatSession {
  session_id: string;
  agent_id: string;
  agent_name: string | null;
  /**
   * 이 대화 전용 도구·MCP 커스터마이즈(2026-08-18, Chat "+" 버튼). `null` =
   * 커스터마이즈 안 함(에이전트 원래 도구를 그대로 씀). 빈 배열은 "이
   * 대화에서 도구를 전부 껐다"는 실제 선택이라 `null`과 다르다.
   */
  tool_refs_override: string[] | null;
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
/**
 * `tool_progress` 이벤트의 `detail`이 실제로 가질 수 있는 모양들 — 아래
 * `ChatEvent`의 `stage`/`queries`/`stage_done`/`task_extraction_result`/
 * `jira_status`와 각각 같다(`tool_ref`/`tool_call_id`는 감싸는 바깥 이벤트
 * 쪽에 있어 `detail`엔 없다). 알려지지 않은 `type`도 올 수 있어(새 진행
 * 이벤트를 도구가 더 낼 때) 마지막에 인덱스 시그니처로 열어 둔다 — 화면은
 * 모르는 타입을 조용히 무시한다.
 */
/**
 * "출처" 표시용 항목 하나(2026-08-18) — `document_search`가 좁힌 문서,
 * `web_search`가 찾은 페이지가 같은 모양을 쓴다. `url`이 있으면 웹 결과라
 * 화면이 링크로 그린다(`document_search`의 내부 문서는 `url`이 없다 —
 * `id`는 그때 `doc_id`).
 */
export interface SourceRef {
  id: string;
  label: string;
  url?: string;
}

export type ToolProgressDetail =
  | { type: 'stage'; step: number; total: number; label?: string; intent?: string }
  | { type: 'queries'; step: number; queries: string[] }
  | { type: 'stage_done'; step: number; found: number; evidence: number }
  | { type: 'sources'; step: number; documents: SourceRef[] }
  | { type: 'task_extraction_result'; proj_id: string; result: TaskExtractionPayload }
  | { type: 'jira_status'; project_key: string; counts: Record<string, number>; issues: JiraIssue[] }
  | { type: string; [key: string]: unknown };

export type ChatEvent =
  | { type: 'stage'; step: number; total: number; label?: string; intent?: string; tool_ref?: string; tool_call_id?: string }
  | { type: 'queries'; step: number; queries: string[]; tool_ref?: string; tool_call_id?: string }
  /**
   * "출처" 목록(2026-08-18) — `document_search`가 coarse 단계에서 좁힌
   * 문서, `web_search`가 찾은 페이지가 같은 이 모양으로 온다. `tool_progress`로
   * 감싸져 온다(위 `ToolProgressDetail` 참고) — 최상위로 직접 오는 일은
   * 없지만 `stage`/`queries`처럼 같은 계약 형태를 유지한다.
   */
  | { type: 'sources'; step: number; documents: SourceRef[]; tool_ref?: string; tool_call_id?: string }
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
  /**
   * 2026-08-15 추가 — 새 엔진(`services/agent_runtime/events.py`)이 실제로
   * 내보내는 타입 태그다. **`tool_call_started`/`tool_call_finished`(위 두 개)와
   * 다른 문자열이다** — 레거시 Harness(`services/harness/runner.py`)의 이름을
   * 그대로 흉내 낸 게 아니라 새 엔진이 직접 정한 이름이라, 지금까지 이 파일에
   * 없어서 화면이 조용히 못 알아보고 있었다(`liveChat.ts`의 `default` 분기로
   * 빠져 `toolName`/진행 카드가 갱신되지 않던 문제 — `_run_deep_agent`가
   * 2026-08-14부터 유일한 실행 경로라 실제로 매번 이 타입으로 온다).
   *
   * `subagent_alias`가 있으면 서브 에이전트(Child) 자신의 직접 호출, 없으면
   * 루트가 직접 부른 것이다 — Child는 메모리가 없으므로(§4, 장기메모리 설계
   * 문서) 메모리 패널은 `subagent_alias == null`인 것만 본다.
   */
  | {
      type: 'tool_started';
      run_id?: string | null;
      parent_run_id?: string | null;
      subagent_alias?: string | null;
      tool_ref: string;
      tool_call_id?: string | null;
      /** 부모 자신의 직접 호출일 때만 채워진다(`events.py` `_classify_parent_tool_calls`/자식 분기). */
      arguments?: Record<string, unknown>;
    }
  | {
      type: 'tool_completed';
      run_id?: string | null;
      parent_run_id?: string | null;
      subagent_alias?: string | null;
      tool_ref: string;
      tool_call_id?: string | null;
      status: 'OK' | 'FAILED';
      /** 도구가 실제로 반환한 값(길이 제한 요약, 2026-08-18). `events.py`의 `_summarize_tool_output()` 참고. */
      output?: string;
    }
  /**
   * 도구 핸들러가 제너레이터로 흘리는 진행 이벤트(`task_extraction`,
   * `jira_get_issues` — `get_stream_writer()` 경로). **`detail`이 실제로는
   * 아래 `stage`/`queries`/`stage_done`/`task_extraction_result`/
   * `jira_status` 중 하나와 같은 모양이다** — `services/agent_runtime
   * /events.py`의 `_classify_progress`가 그 원본 이벤트를 통째로 `detail`에
   * 옮겨 담고 감싸기 때문이다(2026-08-14 엔진 교체 이후 전부 이 모양으로
   * 옴 — 옛 엔진 시절처럼 저 다섯 타입이 최상위로 직접 오는 게 아니다).
   * `liveChat.ts`의 `unwrapToolProgress()`가 이 포장을 풀어서 아래 다섯
   * 케이스가 그대로 처리하게 한다.
   */
  | {
      type: 'tool_progress';
      run_id?: string | null;
      parent_run_id?: string | null;
      subagent_alias?: string | null;
      tool_ref: string;
      detail?: ToolProgressDetail;
    }
  | {
      type: 'subagent_started';
      run_id: string;
      parent_run_id?: string | null;
      agent_id?: string | null;
      agent_version_id?: string | null;
      subagent_alias: string | null;
      subagent_name?: string | null;
      task_summary?: string;
    }
  | {
      type: 'subagent_completed';
      run_id?: string | null;
      parent_run_id?: string | null;
      agent_id?: string | null;
      agent_version_id?: string | null;
      subagent_alias?: string | null;
      subagent_name?: string | null;
      status: 'DONE' | 'FAILED';
      error_code?: string;
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
  /**
   * 추론 모델(gpt-5.6-luna 등, OpenAI Responses API 경로)이 도구를 부르기
   * 전이나 최종 답 전에 내는 생각 — 토큰·조각 단위로 실시간으로 온다
   * (2026-08-18, `stream_mode="messages"` 채택). `text`는 이번 조각만이지
   * 누적된 전체가 아니다.
   *
   * `append`가 이 조각을 화면이 어떻게 붙일지 정한다 — `true`면 방금 그
   * 문단이 이어지는 델타라 마지막 `reasoningSteps` 항목에 이어붙이고,
   * `false`면 새 문단(OpenAI의 reasoning summary가 여러 문단으로 올 때마다)
   * 이라 새 항목을 만든다. 서버(`events.py`의 `_classify_reasoning_delta`)가
   * `(block_index, summary_index)` 커서로 이미 판정해서 보낸다 — 화면은
   * 이 플래그만 보면 된다.
   */
  | {
      type: 'reasoning';
      text: string;
      append: boolean;
      run_id?: string | null;
      parent_run_id?: string | null;
      subagent_alias?: string | null;
    }
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
  /**
   * 에이전트가 고른 모델로 못 돌아 대체한 경우의 **원래 모델**.
   *
   * 업무 추출은 `responses.parse` 가 필요해 Claude·커스텀 모델로는 돌지 않는다.
   * 서버는 조용히 떨어뜨리지 않고 이 값을 실어 보내는데(`service.py:370`),
   * **화면이 그걸 읽지 않아 사람은 자기가 고른 모델로 돈 줄 알았다.**
   */
  model_fallback_from?: string | null;
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
 * 이 대화 전용 도구·MCP 목록을 저장한다(2026-08-18, Chat "+" 버튼). 에이전트
 * 원본은 안 건드린다 — `toolRefs=null`을 주면 커스터마이즈를 지우고
 * 에이전트 원래 값으로 되돌린다.
 */
export function setSessionToolRefs(token: string, sessionId: string, toolRefs: string[] | null) {
  return apiRequest<ChatSession>(`/chat/sessions/${sessionId}/tools/`, {
    method: 'PUT',
    body: { tool_refs: toolRefs },
    token,
  });
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
  return streamNdjson<ChatEvent>(`/chat/sessions/${sessionId}/messages/`, token, { content }, onEvent, signal);
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
  return streamNdjson<ChatEvent>(
    `/chat/sessions/${sessionId}/confirm/`,
    token,
    selected === undefined ? {} : { selected },
    onEvent,
    signal,
  );
}

export { ApiError };
