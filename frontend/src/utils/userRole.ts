import { loadSession } from './session';

export type UserRole = 'leader' | 'member';

/**
 * 팀장 화면과 팀원 화면 중 무엇을 보여줄지.
 *
 * **로그인 계정의 역할만 본다**(서버 `account.role` — 판정 기준은 `org.mgr_id`).
 * 예전에는 DEV 전환기가 sessionStorage 에 덮어쓸 수 있었는데, 그 override 때문에
 * 화면에서 본 것과 실제 권한이 달라도 알아채지 못했다. 개발지시_3차에서
 * 전환기를 걷어내면서 override 도 같이 없앴다.
 */
export function loadUserRole(): UserRole {
  return loadSession()?.account.role === 'member' ? 'member' : 'leader';
}
