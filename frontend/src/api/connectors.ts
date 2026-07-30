import { apiRequest } from './client';

/** `connector_conn.connector_type`. People DB만 실제로 연결 가능하고 나머지는 아직 데모다. */
export type ConnectorType = 'PEOPLE_DB' | 'GOOGLE_DRIVE' | 'JIRA';

/** 화면의 커넥터 카드 id ↔ 서버의 connector_type 대응. */
export const CONNECTOR_TYPE_BY_ID: Record<string, ConnectorType> = {
  'people-db': 'PEOPLE_DB',
  'google-drive': 'GOOGLE_DRIVE',
  jira: 'JIRA',
};

export interface ConnectorConnection {
  conn_id: string;
  connector_type: ConnectorType;
  granted_scopes: string[];
  auth_status: 'CONNECTED' | 'EXPIRED' | 'ERROR';
  connected_at: string;
}

export interface HrPerson {
  person_id: string;
  name: string;
  email: string;
  org_id: string | null;
  org_name: string | null;
  job_role: string | null;
}

export interface PeopleDbSummary {
  org_count: number;
  person_count: number;
  my_org_name: string | null;
  my_org_person_count: number;
  /** 본인 조직 + 하위 조직 인원. 팀원을 초대할 수 있는 범위와 같은 기준이다. */
  scope_person_count: number;
  person: HrPerson | null;
}

export function listConnectors(token: string) {
  return apiRequest<ConnectorConnection[]>('/connectors/', { token });
}

/** HR에서 찾은 본인 후보. 확인 전이라 아직 매핑되지 않는다. 못 찾으면 404. */
export function fetchPeopleDbIdentity(token: string) {
  return apiRequest<HrPerson>('/connectors/people-db/identity/', { token });
}

/** HR 시스템 연결. 본인 PERSON을 찾지 못하면 실패한다. */
export function connectPeopleDb(token: string) {
  return apiRequest<PeopleDbSummary>('/connectors/people-db/', { method: 'POST', token });
}

/** 이미 연결된 계정의 HR 요약. 미연결이면 404. */
export function fetchPeopleDbSummary(token: string) {
  return apiRequest<PeopleDbSummary>('/connectors/people-db/summary/', { token });
}
