import { opsRequest } from './opsClient';

/**
 * 사용 현황 — 관측성의 **「요약」 층**.
 *
 * 시중 제품은 관측성을 요약 → 목록 → 상세 세 층으로 나눠 보여준다
 * (Copilot Studio Analytics · watsonx Orchestrate Agent analytics). 우리는
 * 실행 이력을 2026-08-13 부터 쌓고 있었는데 **첫 층이 통째로 없었다** —
 * 팀 상세의 「최근 실행」이 유일한 노출이고 그마저 비어 있다.
 *
 * **세 번째 층(실행 하나를 따라가는 트레이스)은 여기서 만들지 않는다.**
 * Langfuse 로 보낸다 — watsonx 도 같은 구성이다.
 */

/** 30일 창의 실행 집계. */
export interface UsageRuns {
  runs: number;
  runs_done: number;
  runs_failed: number;
  token_in: number;
  token_out: number;
  /** 토큰을 못 잰 실행. **합계만 보이면 「적게 썼다」와 「못 쟀다」가 같아진다.** */
  runs_without_tokens: number;
}

export interface UsageTools {
  calls: number;
  calls_ok: number;
  calls_failed: number;
  calls_rejected: number;
  calls_pending: number;
}

export interface UsageGuardrail {
  events: number;
  blocked: number;
}

export interface UsageTeamRow {
  team_id: string | null;
  team_name: string | null;
  runs: number;
  runs_done: number;
  token_in: number;
  token_out: number;
}

export interface UsageModelRow {
  model: string;
  /** 레거시 harness 실행은 이 값이 없다. 그게 정상이다. */
  resolved_provider: string | null;
  runs: number;
  token_in: number;
  token_out: number;
}

export interface UsageToolRow {
  tool_ref: string;
  calls: number;
  calls_ok: number;
  calls_failed: number;
  /** 승인 대기 또는 현재 실행 중인 호출. 성공률 분모에서 제외한다. */
  calls_pending: number;
  /** 사용자가 거부해 실제 handler가 실행되지 않은 호출. 실패가 아니다. */
  calls_rejected: number;
  avg_ms: number | null;
}

export interface OpsUsage {
  window_days: number;
  runs: UsageRuns;
  tools: UsageTools;
  guardrail: UsageGuardrail;
  by_team: UsageTeamRow[];
  by_model: UsageModelRow[];
  by_tool: UsageToolRow[];
}

export function fetchUsage(token: string) {
  return opsRequest<OpsUsage>('/ops/usage/', { token });
}
