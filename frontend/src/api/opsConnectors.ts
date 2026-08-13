import { opsRequest } from './opsClient';

export interface OpsConnectorPerson {
  person_id: string;
  // 링크는 있지만 대상 직원 레코드가 삭제된 경우(참조 무결성이 DB 제약으로
  // 강제되지 않음) name/org가 null일 수 있다. 이 화면은 어차피 name을 표시하지
  // 않지만, 타입은 실제 API 응답과 맞춰둔다.
  name: string | null;
  org_id: string | null;
  org_name: string | null;
}

export interface OpsConnector {
  conn_id: string;
  account_id: string;
  owner_email: string | null;
  connector_type: string;
  auth_status: string;
  connected_at: string;
  person: OpsConnectorPerson | null;
  diagnosis: string;
  next_action: string;
}

export function fetchConnectors(token: string) {
  return opsRequest<OpsConnector[]>('/ops/connectors/', { token });
}

export function fetchConnector(token: string, connId: string) {
  return opsRequest<OpsConnector>(`/ops/connectors/${connId}/`, { token });
}

/**
 * 연결을 끊는다. **행을 지우는 것이 아니라 자격증명을 지운다** — 고객이 다시
 * 연결하면 같은 연결로 되살아나므로 폴더·Jira 선택이 그대로 남는다.
 *
 * `affected_sources` 는 이 연결로 읽고 있던 폴더(Drive) 또는 프로젝트(Jira)
 * 수다. 무엇이 멈추는지 화면이 말해야 한다.
 */
export function revokeConnector(token: string, connId: string, reason: string) {
  return opsRequest<{
    conn_id: string;
    connector_type: string;
    auth_status: string;
    affected_sources: number;
  }>(`/ops/connectors/${connId}/revoke/`, { token, method: 'POST', body: { reason } });
}
