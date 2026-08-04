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

/**
 * 팀 명부 한 줄. 사람·계정·초대를 함께 담는다.
 *
 * 초대 현황과 다르다 — 초대는 "계정을 만들라고 보낸 것"이고 명부는 "업무 배정
 * 대상"이다. 직접 가입한 팀장은 초대 기록이 없어 초대 목록에는 아예 없다.
 */
export interface TeamMember {
  team_member_id: string;
  person_id: string;
  name: string | null;
  org_name: string | null;
  /** 직급이 아니라 직책에 가깝다(HR의 person.job_role). */
  job_role: string | null;
  added_at: string | null;
  /** 이 팀의 계정을 쓰고 있으면 채워진다. 없으면 아직 가입 전이다. */
  account_id: string | null;
  account_email: string | null;
  account_status: string | null;
  /** 팀을 만든 사람은 명부에서 뺄 수 없다. */
  is_owner: boolean;
  /** 가장 최근 초대 하나. */
  invite_id: string | null;
  invite_status: 'PENDING' | 'ACCEPTED' | 'EXPIRED' | 'REVOKED' | null;
  invited_at: string | null;
}

export function listTeamMembers(token: string) {
  return apiRequest<TeamMember[]>('/teams/members/', { token });
}

/** 팀 명부에 더한다. 초대 가능 범위와 같은 기준(본인 소속 조직과 그 하위)이다. */
export function addTeamMember(token: string, personId: string) {
  return apiRequest<TeamMember[]>('/teams/members/', {
    method: 'POST',
    token,
    body: { person_id: personId },
  });
}

/** 명부에서 뺀다. 팀 계정을 쓰는 사람과 팀 소유자는 서버가 막는다. */
export function removeTeamMember(token: string, personId: string) {
  return apiRequest<TeamMember[]>(`/teams/members/${personId}/`, { method: 'DELETE', token });
}

/**
 * 팀 업무량 기준.
 *
 * 셋 다 비울 수 있고 비우면 "설정 안 함"이다 — HR 값·100%·4주로 돌아간다.
 * `hr_*`·`default_*`는 비웠을 때 실제로 쓰이는 값이라, 화면이 빈 칸에 회색
 * 글씨로 보여 준다. 안 보여 주면 비운 것이 "모른다"로 읽힌다.
 */
export interface TeamSettings {
  /** 팀 공통 주 근무시간. null이면 HR의 사람별 값을 그대로 쓴다. */
  capacity_wk_hours: number | null;
  /** 이 비율을 넘으면 과부하. null이면 100. */
  overload_pct: number | null;
  /** 부하 조회 기본 기간(주). null이면 4. */
  workload_weeks: number | null;
  /** HR이 아는 팀원들의 주 근무시간 범위. 사람마다 다르면 min≠max다. */
  hr_wk_hours_min: number | null;
  hr_wk_hours_max: number | null;
  default_overload_pct: number;
  default_workload_weeks: number;
}

export function fetchTeamSettings(token: string) {
  return apiRequest<TeamSettings>('/teams/settings/', { token });
}

/** 빈 문자열은 "설정 안 함"으로 되돌린다. */
export function saveTeamSettings(
  token: string,
  values: {
    capacity_wk_hours: string;
    overload_pct: string;
    workload_weeks: string;
  },
) {
  return apiRequest<TeamSettings>('/teams/settings/', { method: 'PUT', token, body: values });
}
