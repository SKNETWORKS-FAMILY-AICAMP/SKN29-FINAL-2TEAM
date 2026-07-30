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
