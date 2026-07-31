import { apiRequest } from './client';

export interface Team {
  team_id: string;
  name: string;
  owner_account_id: string;
  src_org_id: string | null;
  member_count: number | null;
  created_at: string;
}

/**
 * 팀을 만든다. 우리 플랫폼을 쓰는 단위는 회사 전체가 아니라 그 안의 그룹이라,
 * 팀장이 이름을 붙여 명시적으로 만든다. 팀장 본인은 고르지 않아도 팀원이다.
 */
export function createTeam(token: string, name: string, personIds: string[]) {
  return apiRequest<Team>('/teams/', {
    method: 'POST',
    token,
    body: { name, person_ids: personIds },
  });
}

export function fetchMyTeam(token: string) {
  return apiRequest<Team>('/teams/', { token });
}
