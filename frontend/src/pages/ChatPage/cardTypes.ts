/**
 * 카드가 그리는 데이터 모양.
 *
 * `mockChat.ts`에 있던 타입을 옮겨 왔다 — mock 데이터는 지웠지만 **모양은
 * 카드 컴포넌트의 계약**이라 남는다. 서버 이벤트를 `liveChat.ts`가 이 모양으로
 * 접어 주고, 카드는 어디서 왔는지 모른 채 그린다.
 */

export type StepState = 'done' | 'doing' | 'todo';

/** 진행 카드의 한 단계. 도구가 내는 `stage`·`stage_done`이 채운다. */
export interface ProgressStep {
  state: StepState;
  label: string;
  meta?: string;
  /** 같은 단계가 여러 도구 호출에서 반복된 횟수. 진행 요약에서는 한 줄로 묶는다. */
  runs?: number;
}

/**
 * 다른 에이전트에게 위임한 작업 하나(2026-08-18). `subagent_started`가
 * `RUNNING`으로 만들고, 짝이 되는 `subagent_completed`가 `run_id`로 찾아
 * 상태만 바꾼다(`tool_started`/`tool_completed`와 같은 짝짓기 방식).
 */
export interface SubagentRun {
  runId: string;
  alias: string | null;
  name: string | null;
  taskSummary: string;
  status: 'RUNNING' | 'DONE' | 'FAILED';
}

/**
 * 작업 과정 카드에 순서대로 그릴 항목 하나. 사용자용 한국어 안내와
 * 도구 호출·위임을 **이벤트가 실제로 온 순서 그대로** 하나의 목록에 담는다.
 * 그 전에는 reasoning과 도구 진행이 서로 다른 배열(`reasoningSteps`/
 * `steps`)에 따로 쌓여서, 실제로는 하나의 스트림으로 순서대로 온 이벤트인데
 * 화면에서는 그 순서 정보가 사라져 있었다.
 *
 * 도구·위임 항목은 시작(`RUNNING`)으로 먼저 들어가고, 서버가 보내는
 * `tool_call_id`/`run_id`로 완료 이벤트와 짝을 맞춰 그 자리에서 상태만
 * 바꾼다 — 새 항목을 만들지 않는다(`liveChat.ts`의 `reduce()` 참고).
 */
export type TimelineEntry =
  | { kind: 'update'; text: string; source: 'model' | 'application_fallback' }
  | { kind: 'reasoning'; text: string }
  | {
      kind: 'skill';
      skillName: string;
      scope: 'personal' | 'team' | 'builtin';
    }
  | {
      kind: 'tool';
      toolCallId: string | null;
      toolRef: string;
      /**
       * 사람이 읽는 도구 이름(`tool_started`의 `tool_name` — 레지스트리 값).
       * 로그 줄에 이걸 쓴다. 레지스트리에 없는 커스텀 도구는 서버가 ref를
       * 그대로 주므로(`events.py`의 `_tool_label()`) null로 떨어지고, 그때만
       * `toolRef`로 그린다.
       */
      toolName: string | null;
      /** 모델이 실제 도구에 넘긴 입력. 일반 UI는 웹 검색어처럼 정제 가능한 값만 보여준다. */
      arguments?: Record<string, unknown>;
      status: 'RUNNING' | 'OK' | 'FAILED' | 'REJECTED';
      /** 도구 반환값(길이 제한 요약). 일반 UI는 검색 링크처럼 정제한 결과만 보여준다. */
      output?: string;
    }
  | {
      kind: 'subagent';
      runId: string;
      alias: string | null;
      name: string | null;
      taskSummary: string;
      status: 'RUNNING' | 'DONE' | 'FAILED';
    };

/** 근거 한 건. `meta`는 「E1 · DC001 · 유사도 87%」처럼 되짚을 정보다. */
export interface Evidence {
  quote: string;
  meta: string;
  source: string;
}

export interface ExtractedTask {
  no: string;
  title: string;
  facts: { label: string; value: string }[];
  /**
   * 근거를 못 찾아 비운 필드. **모델이 놓친 것과 문서에 없는 것을 사람이
   * 구분해야 한다** — 비어 있다는 사실 자체가 정보다(정직 표기 원칙).
   */
  missing?: string;
  evidence: Evidence[];
  evidenceCount: number;
  checked: boolean;
}

/** Jira에 실제로 만들어진 이슈. 지어내지 않는다 — 서버가 준 것만 담는다. */
export interface CreatedIssue {
  key: string;
  title: string;
  meta: string;
  evidence: string;
}
