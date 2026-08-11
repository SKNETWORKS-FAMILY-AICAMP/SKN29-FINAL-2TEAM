import type { ChatEvent, ExtractedTask as ApiTask, TaskExtractionPayload } from '../../api/chat';
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
export interface LiveChat {
  /** Loop 회전. `tool_ref` 없는 stage 에서만 온다. */
  loopStep: number;
  loopTotal: number;
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
  error: { detail: string; errorCode?: string } | null;
}

export function emptyLive(): LiveChat {
  return {
    loopStep: 0,
    loopTotal: 0,
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
  };
}

/** 이벤트 하나를 접어 넣는다. 불변으로 다뤄 React 가 변화를 알아채게 한다. */
export function reduce(state: LiveChat, event: ChatEvent): LiveChat {
  const toolRef = (event as { tool_ref?: string }).tool_ref;

  switch (event.type) {
    case 'stage': {
      if (!toolRef) {
        // Loop 회전. 진행 카드의 단계 목록에 넣지 않는다 — 넣으면 도구 단계와
        // 섞여 카운트가 튄다.
        return { ...state, loopStep: event.step, loopTotal: event.total };
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

    case 'tool_call_finished': {
      const steps = state.steps.map((step) =>
        step.state === 'doing' ? { ...step, state: 'done' as const } : step,
      );
      if (event.status === 'FAILED') {
        return {
          ...state,
          steps,
          error: {
            detail: `${event.tool_ref} 실행에 실패했습니다.`,
            errorCode: event.error_code,
          },
        };
      }
      return { ...state, steps };
    }

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
      ? `근거 없어 비움 · ${task.missing_fields.join(' · ')}`
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
          source: item.heading_path?.length ? `「${item.heading_path.join(' > ')}」` : '',
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
