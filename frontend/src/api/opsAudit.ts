import { opsRequest } from './opsClient';

/**
 * 감사 로그 — **운영 활동 하나뿐이다.**
 *
 * 「분석·결정 기록」 탭 4종(배정 실행·추천 결과·검증 결과·PM 결정)이 있었고
 * 넷 다 항상 0건이었다. 그 테이블에 쓰는 추천 파이프라인이 이 저장소에 없고,
 * 제품이 업무 배정 추천에서 물러나면서 앞으로도 생기지 않는다 — 화면·API·SQL을
 * 함께 걷었다(2026-08-13). 파이프라인이 다시 생기면 git 이력에서 되살리면 된다.
 */
export interface OpsOperationLog {
  audit_id: string;
  actor_account_id: string;
  actor_display_name: string | null;
  actor_email: string | null;
  action: string;
  proj_id: string | null;
  target_type: string | null;
  target_id: string | null;
  payload: unknown;
  occurred_at: string;
}

export function fetchOperationLogs(token: string) {
  return opsRequest<OpsOperationLog[]>('/ops/audit/operations/', { token });
}
