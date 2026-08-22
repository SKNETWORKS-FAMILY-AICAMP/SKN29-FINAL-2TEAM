import type {
  ChatEvent,
  ExtractedTask as ApiTask,
  JiraIssue,
  SourceRef,
  TaskExtractionPayload,
} from '../../api/chat';
import type { CreatedIssue, Evidence, ExtractedTask, ProgressStep, SubagentRun, TimelineEntry } from './cardTypes';

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
  /** 도구 내부 진행. `tool_ref` 있는 stage·queries·stage_done 이 채운다. */
  steps: ProgressStep[];
  toolName: string | null;
  /** 도구가 내는 검색어. 에이전트가 실제로 한 판단이라 그대로 보여준다. */
  queries: string[];
  /** `document_search`가 좁힌 문서들 — "출처"(2026-08-18). */
  sources: SourceRef[];
  evidenceCount: number;
  running: boolean;
  extraction: TaskExtractionPayload | null;
  tasks: ExtractedTask[];
  /**
   * `actions`(2026-08-21, 병렬실행 Phase 2)는 이 카드에 걸린 호출 **전부**다.
   * 모델이 한 턴에 side_effect 도구를 여러 개 부르면 전부 한 번에
   * interrupt되는데(`HumanInTheLoopMiddleware.after_model`), 예전엔 첫 호출만
   * 화면에 보여주고 승인은 전부에 일괄 적용했다 — "Jira 3건은 승인하되
   * 이메일만 거절"이 불가능했고, 무엇이 같이 실행되는지 보이지도 않았다.
   * 길이가 1이면 예전과 똑같이 그린다.
   *
   * 레거시 엔진 카드는 도구 하나짜리라 항상 길이 1이다.
   */
  confirm: {
    toolName: string;
    runId: string;
    count: number;
    actions: { name: string; count: number }[];
  } | null;
  created: CreatedIssue[];
  failures: { title: string; reason: string }[];
  answer: string;
  /**
   * 이 실행이 걸린 총 시간(ms, 2026-08-19 §12순위) — `result`/`error`
   * 이벤트의 `duration_ms`를 그대로 옮긴다. 재개(resume) 스트림에는 서버가
   * 이 필드를 아예 안 붙이므로 `null`(0초로 지어내지 않는다) — 화면은
   * `null`이면 표시를 생략한다.
   */
  durationMs: number | null;
  /** 상한에 걸려 멈춘 경우. 성공처럼 뭉개지 않는다. */
  stoppedReason: string | null;
  /**
   * `title` 은 **보내기 자체가 실패한 경우**에만 채운다 — 기본 머리말이
   * 「요청을 끝내지 못했습니다」인데, 가드레일이 막았을 때는 시작조차 안 했다.
   */
  error: { detail?: string; errorCode?: string; toolRef?: string; title?: string } | null;
  /** Jira 현황. 도구가 이벤트로 준 것을 화면이 카드로 그린다. */
  jira: { projectKey: string; counts: Record<string, number>; issues: JiraIssue[] } | null;
  /**
   * 생각·도구 호출·위임을 실제 순서대로 섞어 담는다(2026-08-18) — "어떤 도구가
   * 몇 번째 생각 다음에 불렸는지" 순서를 보여 달라는 요청. 서브 에이전트
   * 자신의 항목은 안 담는다 — `subagent_alias`가 있으면 이 턴의 최상위
   * 표시에는 안 쓴다(기존 `reasoningSteps`/`toolName`과 같은 규칙).
   */
  timeline: TimelineEntry[];
  /**
   * 이 턴에서 다른 에이전트에게 위임한 작업들(2026-08-18). 서브 에이전트
   * **자신의** reasoning·도구 진행은 여전히 최상위에 안 보여준다(위와 같은
   * 원칙) — 이건 "지금 위임 중이다/끝났다"는 사실만 보여준다. 병렬 위임도
   * 있을 수 있어 배열이다.
   */
  subagents: SubagentRun[];
}

export function emptyLive(): LiveChat {
  return {
    steps: [],
    toolName: null,
    queries: [],
    sources: [],
    evidenceCount: 0,
    running: true,
    extraction: null,
    tasks: [],
    confirm: null,
    created: [],
    failures: [],
    answer: '',
    durationMs: null,
    stoppedReason: null,
    error: null,
    jira: null,
    timeline: [],
    subagents: [],
  };
}

/**
 * `tool_progress`의 포장을 풀어 원래 이벤트 모양으로 되돌린다(2026-08-18
 * 발견·수정). `services/agent_runtime/events.py`의 `_classify_progress`가
 * `task_extraction`/`jira_get_issues`가 흘리는 모든 진행 이벤트(`stage`/
 * `queries`/`stage_done`/`task_extraction_result`/`jira_status`)를
 * `type: "tool_progress"`, 원본은 `detail`에 통째로 옮겨 담아 보낸다
 * (2026-08-14 엔진 교체 이후 항상 이 모양) — 그런데 이 화면은 저 다섯
 * 타입이 최상위로 직접 온다고 가정한 채로 안 고쳐져 있어서, 지금까지
 * `tool_progress`가 `default` 분기로 빠져 **검색어·진행 단계는 물론
 * 업무 추출 결과(확인 카드)·Jira 현황까지 채팅에서 조용히 사라지고
 * 있었다.** 포장을 풀어 기존 케이스가 그대로 처리하게 한다 — 로직을
 * 두 군데 두지 않기 위해서다.
 *
 * `subagent_alias`가 있으면(자식 네임스페이스의 진행) 이 턴의 최상위
 * 표시에는 안 쓴다 — `tool_started`/`reasoning`과 같은 규칙이라 여기서
 * 걸러서 애초에 풀지 않는다.
 */
export function unwrapToolProgress(event: ChatEvent): ChatEvent {
  if (event.type !== 'tool_progress' || !event.detail || event.subagent_alias) return event;
  return { ...event.detail, tool_ref: event.tool_ref } as ChatEvent;
}

/** 이벤트 하나를 접어 넣는다. 불변으로 다뤄 React 가 변화를 알아채게 한다. */
export function reduce(state: LiveChat, rawEvent: ChatEvent): LiveChat {
  const event = unwrapToolProgress(rawEvent);
  const toolRef = (event as { tool_ref?: string }).tool_ref;

  switch (event.type) {
    case 'skill_applied':
      return {
        ...state,
        timeline: [
          ...state.timeline,
          { kind: 'skill', skillName: event.skill_name, scope: event.scope },
        ],
      };

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

    // `document_search`가 coarse 단계에서 좁힌 문서들(2026-08-18) — "출처".
    // `stage`처럼 초기화하지 않는다 — 다음 단계(본문 검색)가 도는 동안에도
    // "무엇으로 좁혔는지"는 계속 보여야 한다.
    case 'sources':
      return toolRef ? { ...state, sources: event.documents } : state;

    case 'stage_done': {
      const steps = state.steps.map((step, index) =>
        index === state.steps.length - 1
          ? { ...step, state: 'done' as const, meta: `근거 ${event.found}건` }
          : step,
      );
      return { ...state, steps, evidenceCount: event.evidence };
    }

    // 서브 에이전트 자신의 생각은 이 턴의 최상위 표시에 안 쓴다 —
    // `tool_started`/`tool_completed`가 `subagent_alias`로 거르는 것과 같은
    // 규칙. `append`(2026-08-18, 토큰 단위 실시간 스트리밍)가 true면 이어지는
    // 델타라 타임라인의 마지막 항목(그것도 reasoning이어야 한다 — 그
    // 사이에 도구 호출이 끼었으면 새 문단으로 봐야 맞다)에 붙이고, false면
    // 새 문단이라 항목을 새로 만든다.
    case 'reasoning': {
      if (event.subagent_alias) return state;
      const timeline = state.timeline.slice();
      const last = timeline[timeline.length - 1];
      if (event.append && last?.kind === 'reasoning') {
        timeline[timeline.length - 1] = { ...last, text: last.text + event.text };
      } else {
        timeline.push({ kind: 'reasoning', text: event.text });
      }
      return { ...state, timeline };
    }

    case 'tool_call_started':
      return { ...state, toolName: event.tool_name };

    // 새 엔진이 실제로 내는 타입(위 `tool_call_started`와 다른 문자열 —
    // `api/chat.ts`의 2026-08-15 주석 참고). `subagent_alias`가 있으면
    // 서브 에이전트 자신의 호출이라 이 턴의 최상위 진행 표시에는 안 쓴다.
    // 타임라인에도 같이 넣는다(2026-08-18) — "몇 번째 생각 다음에 이 도구를
    // 불렀는지" 순서를 보여 달라는 요청. 상태줄(toolName)은 **사람이 읽는
    // 이름**을 쓴다(main, 2026-08-18) — 예전엔 `tool_ref` 라 「task_register
    // 실행 중」처럼 내부 이름이 보였다. 서버가 아직 안 보내는 경우(레거시
    // 이벤트)만 ref 로 떨어진다.
    case 'tool_started': {
      if (event.subagent_alias) return state;
      return {
        ...state,
        toolName: event.tool_name ?? event.tool_ref,
        timeline: [
          ...state.timeline,
          {
            kind: 'tool',
            toolCallId: event.tool_call_id ?? null,
            toolRef: event.tool_ref,
            // 상태줄과 **같은 값**을 쓴다 — 한 화면에서 같은 도구가 위에서는
            // 「업무 등록」, 아래 로그에서는 `task_register` 로 갈리면 안 된다.
            toolName: event.tool_name ?? null,
            status: 'RUNNING',
          },
        ],
      };
    }

    // 도구 완료 — tool_call_id로 타임라인의 그 항목만 찾아 상태를 바꾼다
    // (병렬 호출이면 완료 순서가 시작 순서와 다를 수 있어서, subagent_started/
    // completed가 run_id로 짝짓는 것과 같은 이유). 예전엔 이 이벤트를 아예
    // 안 읽었다 — steps/toolName만으로는 완료 여부가 필요 없었지만, 타임라인은
    // "이 도구가 끝났다/실패했다"까지 보여줘야 한다.
    case 'tool_completed': {
      if (event.subagent_alias) return state;
      return {
        ...state,
        timeline: state.timeline.map((entry) =>
          entry.kind === 'tool' && entry.toolCallId !== null && entry.toolCallId === event.tool_call_id
            ? { ...entry, status: event.status, output: event.output }
            : entry,
        ),
      };
    }

    // 다른 에이전트에게 위임을 시작했다(2026-08-18). 위임 자체는 부모
    // 네임스페이스에서 나오는 이벤트라 subagent_alias로 거를 대상이 아니다
    // — "누구에게 위임했나"가 곧 이 이벤트의 내용이다. 서브 에이전트
    // *자신의* reasoning·도구 진행은 여전히 안 보여준다(위 케이스들 그대로).
    // 타임라인과 subagents 둘 다에 넣는다 — subagents는 ProgressCard의 요약
    // 목록용으로 그대로 두고, 타임라인은 순서를 보여준다.
    case 'subagent_started': {
      const run: SubagentRun = {
        runId: event.run_id,
        alias: event.subagent_alias,
        name: event.subagent_name ?? null,
        taskSummary: event.task_summary ?? '',
        status: 'RUNNING',
      };
      return {
        ...state,
        subagents: [...state.subagents, run],
        timeline: [...state.timeline, { kind: 'subagent', ...run }],
      };
    }

    // 위임 완료 — run_id로 정확히 짝을 맞춘다(tool_started/tool_completed와
    // 같은 이유: 병렬 위임이면 완료 순서가 시작 순서와 다를 수 있다).
    case 'subagent_completed':
      return {
        ...state,
        subagents: state.subagents.map((run) =>
          run.runId === event.run_id ? { ...run, status: event.status } : run,
        ),
        timeline: state.timeline.map((entry) =>
          entry.kind === 'subagent' && entry.runId === event.run_id ? { ...entry, status: event.status } : entry,
        ),
      };

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

    case 'awaiting_confirmation': {
      // 두 엔진이 서로 다른 모양으로 보낸다(../../api/chat.ts의 타입 주석
      // 참고) — `action_requests` 유무로 가른다. **레거시 필드
      // (`tool_name`/`arguments`)로 새 엔진 이벤트를 읽으면 둘 다
      // `undefined`가 되어 카드가 안 뜬다**(2026-08-20, 실제로 겪음 — 화면이
      // 멈춘 것처럼 보이고 오류만 떴다). `if`/`else`로 갈라야 각 분기 안에서
      // `event`가 해당 모양으로 좁혀진다 — 한 줄 삼항연산자로 값만 꺼내면
      // 그 좁힘이 다음 줄까지 안 이어져 타입 오류가 난다.
      let toolName: string | undefined;
      let args: Record<string, unknown> | undefined;
      // 2026-08-21, 병렬실행 Phase 2 — 첫 호출만 보지 않고 전부 담는다.
      // 화면이 호출별로 승인·거절하려면 목록 전체가 있어야 한다.
      let actions: { name: string; count: number }[];
      if ('action_requests' in event) {
        const first = event.action_requests[0];
        toolName = first?.name;
        args = first?.args;
        actions = event.action_requests.map((request) => ({
          name: request.name,
          count: countIssues(request.args ?? {}),
        }));
      } else {
        toolName = event.tool_name;
        args = event.arguments;
        actions = [{ name: event.tool_name, count: countIssues(event.arguments ?? {}) }];
      }
      return {
        ...state,
        running: false,
        confirm: {
          toolName: toolName ?? '확인 필요',
          runId: event.run_id,
          count: countIssues(args ?? {}),
          actions,
        },
      };
    }

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
        durationMs: event.duration_ms ?? null,
        stoppedReason: event.complete ? null : event.stopped_reason ?? '알 수 없는 이유',
        created: jira.created,
        failures: jira.failures,
      };
    }

    case 'error':
      // 두 모양이 온다(../../api/chat.ts의 타입 주석 참고) — `detail`(스트림
      // 밖 크래시)이 없으면 `message`(그래프 실행 중 실패)를 쓴다. 2026-08-20
      // 발견: 이걸 안 하면 후자일 때 `ErrorCard`에 사유가 하나도 안 남는다
      // ("요청을 끝내지 못했습니다"만 뜨고 본문·기술 정보가 전부 빈다).
      return {
        ...state,
        running: false,
        durationMs: event.duration_ms ?? null,
        error: { detail: event.detail ?? event.message, errorCode: event.error_code },
      };

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
