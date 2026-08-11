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
}

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
