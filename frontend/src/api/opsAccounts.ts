import { opsRequest } from './opsClient';
import type { OpsPurgePreview, OpsPurgeResult } from './opsTeams';

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

/**
 * 상태를 바꾸는 조치는 **사유를 함께 보낸다.** 무엇을 했는지는 감사 로그가 이미
 * 남기지만 왜 했는지는 그때 그 사람 머릿속에만 있다. 빈 문자열도 서버가 받는다 —
 * 사유는 기록을 돕는 것이지 관문이 아니다(2026-08-13).
 */
export function lockAccount(token: string, accountId: string, reason: string) {
  return opsRequest<{ account_id: string; account_status: string }>(
    `/ops/accounts/${accountId}/lock/`,
    { method: 'POST', token, body: { reason } },
  );
}

export function unlockAccount(token: string, accountId: string, reason: string) {
  return opsRequest<{ account_id: string; account_status: string }>(
    `/ops/accounts/${accountId}/unlock/`,
    { method: 'POST', token, body: { reason } },
  );
}

export function unlinkAccountPerson(token: string, accountId: string, reason: string) {
  return opsRequest<{ account_id: string; revoked_person_ids: string[] }>(
    `/ops/accounts/${accountId}/unlink-person/`,
    { method: 'POST', token, body: { reason } },
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


/** 계정 삭제 미리보기·실행. 자세한 규격은 `opsTeams.ts` 의 같은 이름 참고. */
export function fetchAccountPurgePreview(token: string, accountId: string) {
  return opsRequest<OpsPurgePreview>(`/ops/accounts/${accountId}/purge/`, { token });
}

/**
 * 계정을 완전히 지운다. **되돌릴 수 없다.**
 *
 * 확인값은 이름이 아니라 **이메일**이다 — 이름은 겹칠 수 있어서(실제로 팀
 * 이름이 둘 다 「개발팀」이었다) 확인이 확인 구실을 못 한다.
 *
 * 그 사람이 만든 문서·프로젝트·에이전트는 **안 지운다.** 팀 자산이라 소유자만
 * 팀 소유자에게 넘어간다 — 사람이 나가도 팀이 일을 잃지 않는다.
 */
export function purgeAccount(token: string, accountId: string, confirmEmail: string) {
  return opsRequest<OpsPurgeResult>(`/ops/accounts/${accountId}/purge/`, {
    method: 'DELETE',
    token,
    body: { confirm_name: confirmEmail },
  });
}
