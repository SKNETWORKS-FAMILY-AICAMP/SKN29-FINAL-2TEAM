import { API_BASE_URL, apiRequest, apiUpload } from './client';

/**
 * 가입 경로로 정해지는 역할. 초대 코드로 들어온 계정만 팀원이고 직접 가입은
 * 팀장이다 — HR 시스템 연결 권한이 회사에서 팀장에게만 주어진다는 전제.
 */
export type AccountRole = 'leader' | 'member';

export interface AccountPerson {
  person_id: string;
  name: string;
  email: string;
  org_id: string | null;
  org_name: string | null;
  /**
   * HR의 `person.job_role`. **직급이 아니라 직책에 가깝다** — 목업 57명 중 51명은
   * 직급 값(대리·사원·주임·과장)이 그대로 들어 있고 6명만 직책(팀장·대표이사)이다.
   * 진짜 직급은 `level` 테이블(사원~대표이사, rank_ord 1~8)에 따로 있다.
   */
  job_role: string | null;
}

export interface Account {
  account_id: string;
  email: string;
  display_name: string;
  account_status: string;
  role: AccountRole;
  /** 본인 조직 + 하위 조직. 팀원 초대 범위와 같은 기준. HR 미연결이면 빈 배열. */
  scope_org_ids: string[];
  person: AccountPerson | null;
  /** HR이 아는 보유 스킬. 숙련도 높은 순. HR 미연결이거나 등록이 없으면 빈 배열. */
  skills: PersonSkill[];
  /** 프로필 사진을 올렸는가. 저장소 키는 서버 내부 사정이라 내려오지 않는다. */
  has_avatar: boolean;
}

/** `mock_hr.person_skill` 한 줄. */
export interface PersonSkill {
  skill_id: string;
  name: string;
  category: string | null;
  /** 1~5. */
  proficiency: number;
  /** HR / RESUME / USER_ADDED / AI_INFERRED. 화면이 한국어를 정한다. */
  source: string | null;
  /** AI가 추정한 것에만 값이 있다. 확인된 스킬은 null. */
  confidence: number | null;
}

export interface AuthResult {
  token: string;
  /** 토큰 만료 시각(ISO8601). 프론트엔드가 만료된 세션을 스스로 버리는 데 쓴다. */
  expires_at: string;
  account: Account;
}

export function login(email: string, password: string) {
  return apiRequest<AuthResult>('/auth/login/', {
    method: 'POST',
    body: { email, password },
  });
}

export function signup(params: {
  email: string;
  password: string;
  displayName: string;
  inviteCode?: string;
}) {
  return apiRequest<AuthResult>('/auth/signup/', {
    method: 'POST',
    body: {
      email: params.email,
      password: params.password,
      display_name: params.displayName,
      invite_code: params.inviteCode ?? '',
    },
  });
}

export function fetchCurrentAccount(token: string) {
  return apiRequest<Account>('/auth/me/', { token });
}

/** 계정 존재 여부를 노출하지 않으려고 서버가 항상 같은 응답을 준다. */
export function requestPasswordReset(email: string) {
  return apiRequest<{ detail: string }>('/auth/password-reset/', {
    method: 'POST',
    body: { email },
  });
}

export function confirmPasswordReset(token: string, password: string) {
  return apiRequest<{ detail: string }>('/auth/password-reset/confirm/', {
    method: 'POST',
    body: { token, password },
  });
}

/**
 * 로그인한 사용자가 스스로 비밀번호를 바꾼다. 현재 비밀번호를 함께 보낸다 —
 * 토큰만으로 바꾸게 하면 자리를 비운 사이 남이 세션을 잡아 갈아 끼울 수 있다.
 */
export function changePassword(token: string, currentPassword: string, password: string) {
  return apiRequest<{ detail: string }>('/auth/password/change/', {
    method: 'POST',
    token,
    body: { current_password: currentPassword, password },
  });
}

/**
 * 내 프로필 사진을 **토큰을 붙여** 받아 온다.
 *
 * `<img src>` 로는 못 받는다. 브라우저가 이미지 요청에 `Authorization` 헤더를
 * 실어 주지 않는데 이 엔드포인트는 Bearer 토큰을 요구해서(`CurrentAvatarAPIView`),
 * **올리기는 성공하고 사진은 영원히 안 보이는** 상태였다 — 401 이 나면 화면이
 * 이름 첫 글자로 되돌아가므로 아무 일도 안 일어난 것처럼 보인다.
 *
 * 주소에 토큰을 얹는 방법은 쓰지 않는다. 주소는 로그·기록·공유에 남는다.
 *
 * 사진이 없으면 서버가 404 를 준다 — **오류가 아니라 정상 흐름**이라 `null` 로
 * 돌려주고, 화면은 이름 첫 글자를 그린다.
 */
export async function fetchAvatarBlob(token: string): Promise<Blob | null> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/auth/me/avatar/`, {
      headers: { Authorization: `Bearer ${token}` },
      // 같은 주소로 새 사진이 올라오므로 캐시를 타면 옛 사진이 남는다.
      cache: 'no-store',
    });
  } catch {
    return null;
  }
  return response.ok ? response.blob() : null;
}

/** 프로필 사진을 올린다(JPG·PNG·WEBP, 2MB 이하). 같은 키를 덮어쓴다. */
export function uploadAvatar(token: string, file: File) {
  return apiUpload<{ detail: string }>('/auth/me/avatar/', file, { token });
}

export function deleteAvatar(token: string) {
  return apiRequest<{ detail: string }>('/auth/me/avatar/', { method: 'DELETE', token });
}
