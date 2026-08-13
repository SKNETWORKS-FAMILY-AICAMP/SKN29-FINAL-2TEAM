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
  /** 운영자 콘솔에 들어올 수 있는 계정인가. */
  is_admin: boolean;
  team_id: string | null;
  team_name: string | null;
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

/**
 * 운영자 권한을 켜고 끈다.
 *
 * **최초 운영자는 여전히 CLI 로만 만든다**(`grant_admin.py`). 여기는 이미 들어와
 * 있는 운영자가 다음 사람을 들이는 자리다. 자기 권한 회수와 마지막 운영자 회수는
 * 서버가 막는다.
 */
export function setAccountAdmin(token: string, accountId: string, isAdmin: boolean, reason: string) {
  return opsRequest<{ account_id: string; is_admin: boolean }>(`/ops/accounts/${accountId}/admin/`, {
    method: 'POST',
    token,
    body: { is_admin: isAdmin, reason },
  });
}

/**
 * 계정 한 건. 상세가 별도 페이지가 되면서 필요해졌다 — 주소로 바로 들어올 수
 * 있어야 하므로 목록을 통째로 받아 골라내는 것으로는 부족하다.
 */
export function fetchAccount(token: string, accountId: string) {
  return opsRequest<OpsAccount>(`/ops/accounts/${accountId}/`, { token });
}
