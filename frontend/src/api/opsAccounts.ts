import { opsRequest } from './opsClient';

export type OpsMappingStatus = 'UNMAPPED' | 'LINKED' | 'DUPLICATE';

export interface OpsAccountPerson {
  person_id: string;
  // 링크는 있지만 대상 직원 레코드가 삭제된 경우(참조 무결성이 DB 제약으로
  // 강제되지 않음) name/org가 null일 수 있다.
  name: string | null;
  org_id: string | null;
  org_name: string | null;
}

export interface OpsAccount {
  account_id: string;
  email: string;
  display_name: string;
  account_status: string;
  mapping_status: OpsMappingStatus;
  link_count: number;
  person: OpsAccountPerson | null;
  services: string[];
}

export function fetchAccounts(token: string) {
  return opsRequest<OpsAccount[]>('/ops/accounts/', { token });
}

export function lockAccount(token: string, accountId: string) {
  return opsRequest<{ account_id: string; account_status: string }>(
    `/ops/accounts/${accountId}/lock/`,
    { method: 'POST', token },
  );
}

export function unlockAccount(token: string, accountId: string) {
  return opsRequest<{ account_id: string; account_status: string }>(
    `/ops/accounts/${accountId}/unlock/`,
    { method: 'POST', token },
  );
}

export function unlinkAccountPerson(token: string, accountId: string) {
  return opsRequest<{ account_id: string; revoked_person_ids: string[] }>(
    `/ops/accounts/${accountId}/unlink-person/`,
    { method: 'POST', token },
  );
}
