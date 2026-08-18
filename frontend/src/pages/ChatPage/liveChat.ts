import type {
  ChatEvent,
  ExtractedTask as ApiTask,
  JiraIssue,
  TaskExtractionPayload,
} from '../../api/chat';
import type { CreatedIssue, Evidence, ExtractedTask, ProgressStep } from './cardTypes';

/**
 * 이벤트 스트림 → 카드가 그릴 상태.
 *
 * **`tool_ref` 유무로 층을 가른다** — 백엔드 계약이다. Loop 의 `stage` 는 회전
 * 수(`step/total` = max_iterations)이고 도구의 `stage` 는 그 도구의 파이프라인
 * 단계다. 섞어서 그리면 진행 카드가 1/4 → 1/5 → 2/5 → 2/4 로 튄다.
 *
 * 화면이 보여주는 진행은 **도구 쪽**이다. 사용자가 알고 싶은 것은 "몇 번째
 * 생각 중"이 아니라 "무엇을 찾고 있나"이고, 그 문장은 도구가 낸다. Loop 회전은
 * 부제로만 쓴다.
 */
/**
 * 부모(루트)가 직접 부른 도구 호출 한 건 — 순서대로 쌓인다(2026-08-15,
 * 오른쪽 메모리 패널용). `EVENT_TOOL_STARTED`가 그 자리에서 `RUNNING`으로
 * 밀어 넣고, 짝이 되는 `EVENT_TOOL_COMPLETED`가 `tool_call_id`로 찾아 상태만
 * 바꾼다 — 새 항목을 만들지 않는다(병렬 호출이어도 자리가 안 밀리게).
 */
export interface ToolCallEntry {
  seq: number;
  toolCallId: string | null;
  toolRef: string;
  status: 'RUNNING' | 'OK' | 'FAILED';
  arguments?: Record<string, unknown>;
}

/** `services/agent_runtime/memory/backend.py`의 `MEMORY_PATH_PREFIX`와 같은 값. */
export const MEMORY_PATH_PREFIX = '/memories/';

/**
 * 도구 호출 인자에서 `/memories/` 아래를 가리키는 경로를 찾는다. 없으면 `null`
 * — 이 도구 호출이 장기 메모리가 아니라는 뜻이다(예: 세션 안 스크래치 파일).
 *
 * deepagents 내장 파일 도구는 관례상 `file_path` 인자를 쓰지만(Claude 자신의
 * Read/Write/Edit 도구와 같은 관례 — 실행 검증은 아직 못 함, 작업기록
 * `2026-08-15_02_장기메모리_설계.md` §5), 확정된 계약이 아니라서 `path`도
 * 같이 보고, 그래도 없으면 값 전체를 훑는 방어적 순서로 찾는다.
 */
export function memoryFilePath(args: Record<string, unknown> | undefined): string | null {
  if (!args) return null;
  const direct = args.file_path ?? args.path;
  if (typeof direct === 'string' && direct.startsWith(MEMORY_PATH_PREFIX)) return direct;
  for (const value of Object.values(args)) {
    if (typeof value === 'string' && value.startsWith(MEMORY_PATH_PREFIX)) return value;
  }
  return null;
}

export interface LiveChat {
  /** Loop 회전. `tool_ref` 없는 stage 에서만 온다. */
  /** 도구 내부 진행. `tool_ref` 있는 stage·queries·stage_done 이 채운다. */
  steps: ProgressStep[];
  toolName: string | null;
  /** 도구가 내는 검색어. 에이전트가 실제로 한 판단이라 그대로 보여준다. */
  queries: string[];
  evidenceCount: number;
  running: boolean;
  extraction: TaskExtractionPayload | null;
  tasks: ExtractedTask[];
  confirm: { toolName: string; runId: string; count: number } | null;
  created: CreatedIssue[];
  failures: { title: string; reason: string }[];
  answer: string;
  /** 상한에 걸려 멈춘 경우. 성공처럼 뭉개지 않는다. */
  stoppedReason: string | null;
  error: { detail?: string; errorCode?: string; toolRef?: string } | null;
  /** Jira 현황. 도구가 이벤트로 준 것을 화면이 카드로 그린다. */
  jira: { projectKey: string; counts: Record<string, number>; issues: JiraIssue[] } | null;
  /**
   * 루트가 직접 호출한 도구들의 순서(위임으로 들어간 서브 에이전트 내부
   * 호출은 안 담는다 — Child는 메모리가 없다). 오른쪽 메모리 패널이 이 중
   * `/memories/` 경로를 가리키는 것만 걸러 보여준다(`memoryFilePath`).
   */
  toolCalls: ToolCallEntry[];
}

export function emptyLive(): LiveChat {
  return {
    steps: [],
    toolName: null,
    queries: [],
    evidenceCount: 0,
    running: true,
    extraction: null,
    tasks: [],
    confirm: null,
    created: [],
    failures: [],
    answer: '',
    stoppedReason: null,
    error: null,
    jira: null,
    toolCalls: [],
  };
}

/** 이벤트 하나를 접어 넣는다. 불변으로 다뤄 React 가 변화를 알아채게 한다. */
export function reduce(state: LiveChat, event: ChatEvent): LiveChat {
  const toolRef = (event as { tool_ref?: string }).tool_ref;

  switch (event.type) {
    case 'stage': {
      if (!toolRef) {
        // Loop 회전. **버린다.** 진행 카드의 단계 목록에 넣으면 도구 단계와
        // 섞여 카운트가 튀고(1/4 → 1/5 → 2/5), 따로 보여 주자니 사람이 할
        // 행동을 바꾸지 않는 값이다 — 회전 수는 `agent_run.iterations` 에 남는다.
        return state;
      }
      // 도구 진행. 앞 단계는 끝난 것으로 확정하고 이번 단계를 doing 으로 만든다.
      const steps = state.steps.map((step) =>
        step.state === 'doing' ? { ...step, state: 'done' as const } : step,
      );
      steps.push({ state: 'doing', label: event.label ?? `${event.step}단계` });
      return { ...state, steps, queries: [] };
    }

    case 'queries':
      return toolRef ? { ...state, queries: event.queries } : state;

    case 'stage_done': {
      const steps = state.steps.map((step, index) =>
        index === state.steps.length - 1
          ? { ...step, state: 'done' as const, meta: `근거 ${event.found}건` }
          : step,
      );
      return { ...state, steps, evidenceCount: event.evidence };
    }

    case 'tool_call_started':
      return { ...state, toolName: event.tool_name };

    // 새 엔진이 실제로 내는 타입(위 `tool_call_started`와 다른 문자열 —
    // `api/chat.ts`의 2026-08-15 주석 참고). `subagent_alias`가 있으면
    // 서브 에이전트 자신의 호출이라 이 턴의 최상위 진행 표시에는 안 쓴다.
    case 'tool_started': {
      if (event.subagent_alias) return state;
      const entry: ToolCallEntry = {
        seq: state.toolCalls.length,
        toolCallId: event.tool_call_id ?? null,
        toolRef: event.tool_ref,
        status: 'RUNNING',
        arguments: event.arguments,
      };
      return { ...state, toolName: event.tool_ref, toolCalls: [...state.toolCalls, entry] };
    }

    case 'tool_completed': {
      if (event.subagent_alias) return state;
      // tool_call_id 로 짝을 맞춘다 — 병렬 호출이면 시작 순서와 끝나는 순서가
      // 다를 수 있어서다(events.py 모듈 docstring과 같은 이유).
      const toolCalls = state.toolCalls.map((call) =>
        call.status === 'RUNNING' && call.toolCallId !== null && call.toolCallId === event.tool_call_id
          ? { ...call, status: event.status }
          : call,
      );
      return { ...state, toolCalls };
    }

    case 'tool_call_finished': {
      const steps = state.steps.map((step) =>
        step.state === 'doing' ? { ...step, state: 'done' as const } : step,
      );
      if (event.status === 'FAILED') {
        return {
          ...state,
          steps,
          error: {
            // **서버가 준 사유를 그대로 쓴다.** 「프로젝트를 먼저 고르세요」처럼
            // 사람이 고칠 수 있는 말이다. 없으면 도구 이름만 말하고, 원인을
            // 지어내지 않는다 — 카드가 나머지를 판단한다.
            detail: event.detail ?? undefined,
            errorCode: event.error_code,
            toolRef: event.tool_ref,
          },
        };
      }
      return { ...state, steps };
    }

    case 'jira_status':
      return {
        ...state,
        jira: { projectKey: event.project_key, counts: event.counts, issues: event.issues },
      };

    case 'task_extraction_result':
      return {
        ...state,
        extraction: event.result,
        tasks: toCards(event.result),
      };

    case 'awaiting_confirmation':
      return {
        ...state,
        running: false,
        confirm: {
          toolName: event.tool_name,
          runId: event.run_id,
          count: countIssues(event.arguments),
        },
      };

    case 'result': {
      const jira = readJiraResult(state.extraction, event);
      return {
        ...state,
        running: false,
        // 결과가 나왔으면 기다리던 승인은 끝났다. 한 실행 안에서 confirm 과
        // result 가 같이 오는 일은 없지만(runner 가 confirm 에서 멈춘다),
        // **한 턴의 이벤트를 이어 붙일 때** 이 줄이 필요하다 — 승인·재개가
        // 실행 두 번이라 접으면 confirm 이 result 뒤까지 살아남고, 이미 등록이
        // 끝난 과거 턴에 승인 버튼이 다시 켜진다.
        confirm: null,
        answer: event.text ?? '',
        stoppedReason: event.complete ? null : event.stopped_reason ?? '알 수 없는 이유',
        created: jira.created,
        failures: jira.failures,
      };
    }

    case 'error':
      return { ...state, running: false, error: { detail: event.detail } };

    default:
      return state;
  }
}

/** 확인 카드가 「몇 건을 승인하는가」를 말할 수 있게. 목록형 인자 하나를 센다. */
function countIssues(args: Record<string, unknown>): number {
  const lists = Object.values(args).filter(Array.isArray);
  return lists.length === 1 ? (lists[0] as unknown[]).length : 0;
}

/**
 * Jira 등록 결과는 지금 `result.text` 안에 문장으로만 온다. 구조화된 등록 결과
 * 이벤트가 생기면 여기를 바꾼다 — 그때까지 결과 카드는 추출 결과만 그린다.
 *
 * **비어 있는 것을 채워 넣지 않는다.** 모르는 이슈 키를 지어내면 화면이
 * "등록됐다"고 말하는데 Jira 에는 없는 상태가 된다.
 */
function readJiraResult(
  _extraction: TaskExtractionPayload | null,
  _event: Extract<ChatEvent, { type: 'result' }>,
): { created: CreatedIssue[]; failures: { title: string; reason: string }[] } {
  return { created: [], failures: [] };
}

/**
 * `missing_fields` 와 `trace` 는 서버가 영문 키로 준다(`effort_hours`,
 * `TASK_DISCOVERY:12`). 사람에게 보일 이름은 화면이 붙인다 — 이 표는
 * `TaskExtractionPage`(4차 단계 3에서 삭제)가 쓰던 것을 그대로 옮긴 것이다.
 * 옮기지 않고 지우면 비개발자가 보는 카드에 영문 식별자가 남는다.
 */
const FIELD_LABEL: Record<string, string> = {
  required_role: '담당 역할',
  required_skills: '필요 기술',
  effort_hours: '공수',
  start_date: '시작',
  due_date: '마감',
  priority: '우선순위',
  dependencies: '선행 업무',
  constraints: '제약',
  risks: '위험',
  acceptance_criteria: '완료 기준',
  deliverables: '산출물',
};

const INTENT_LABEL: Record<string, string> = {
  TASK_DISCOVERY: '업무 후보 찾기',
  TASK_CORE: '요구사항·산출물',
  ASSIGNMENT_REQUIREMENT: '역할·기술',
  EXECUTION_CONDITION: '공수·일정·제약',
};

/**
 * 확인 카드 아래 한 줄 — 어느 단계에서 몇 건을 찾았는지와 쓴 모델.
 *
 * 결과가 빈약할 때 어느 단계가 비었는지 알아야 문서를 더 넣을지 판단할 수 있다.
 */
export function traceLine(payload: TaskExtractionPayload): string {
  const steps = payload.trace.map((step) => {
    const [intent, hits] = step.split(':');
    return `${INTENT_LABEL[intent] ?? intent} ${hits}건`;
  });
  const line = `검색 ${steps.join(' · ')} · ${payload.model}(${payload.reasoning_effort})`;
  // **고른 모델로 못 돌았으면 그 사실을 말한다.** 업무 추출은 `responses.parse`
  // 가 필요해 Claude·커스텀으로는 안 돈다. 서버는 이 사실을 실어 보내는데
  // 화면이 안 읽어서, 사람은 자기가 고른 모델로 돈 줄 알았다(정직 표기 원칙).
  return payload.model_fallback_from
    ? `${line} · ${payload.model_fallback_from} 로는 돌 수 없어 대체함`
    : line;
}

/** 추출 결과를 근거 카드 모양으로. `ref`(E1…)로 근거를 되짚는다. */
export function toCards(payload: TaskExtractionPayload): ExtractedTask[] {
  const byChunk = new Map(payload.evidence.map((item) => [item.chunk_id, item]));

  return payload.tasks.map((task, index) => ({
    no: String(index + 1),
    title: task.title,
    facts: facts(task),
    // **근거가 없어 비운 필드를 그대로 밝힌다.** 모델이 놓친 것과 문서에 없는
    // 것을 사람이 구분해야 한다(정직 표기 원칙).
    missing: task.missing_fields.length
      ? `근거 없어 비움 · ${task.missing_fields.map((field) => FIELD_LABEL[field] ?? field).join(' · ')}`
      : undefined,
    evidenceCount: task.evidence_chunk_ids.length,
    checked: true,
    evidence: task.evidence_chunk_ids
      .map((chunkId) => byChunk.get(chunkId))
      .filter((item): item is NonNullable<typeof item> => Boolean(item))
      .map(
        (item): Evidence => ({
          quote: item.text,
          meta: [item.ref, item.doc_id, score(item.retrieval_score)].filter(Boolean).join(' · '),
          source: item.heading_path?.length ? `‘${item.heading_path.join(' > ')}’` : '',
        }),
      ),
  }));
}

function facts(task: ApiTask): { label: string; value: string }[] {
  const rows: { label: string; value: string }[] = [];
  if (task.required_role) rows.push({ label: '담당 역할', value: task.required_role });
  if (task.effort_hours !== null) rows.push({ label: '공수', value: `${task.effort_hours}h` });
  if (task.start_date) rows.push({ label: '시작', value: task.start_date });
  if (task.due_date) rows.push({ label: '마감', value: task.due_date });
  if (task.priority) rows.push({ label: '우선순위', value: task.priority });
  return rows;
}

function score(value: number | undefined): string {
  return value === undefined ? '' : `유사도 ${Math.round(value * 100)}%`;
}
