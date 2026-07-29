export type UserRole = 'leader' | 'member';

const ROLE_STORAGE_KEY = 'halil.userRole';

/**
 * Reads the demo user's role (팀장/팀원) from session storage. There's no
 * real auth system in this static app, so the settings page uses this to
 * decide whether to show the team-leader or team-member settings screen.
 * Defaults to 'leader' so existing PM/admin flows keep working.
 */
export function loadUserRole(): UserRole {
  try {
    const raw = sessionStorage.getItem(ROLE_STORAGE_KEY);
    return raw === 'member' ? 'member' : 'leader';
  } catch {
    return 'leader';
  }
}

export function saveUserRole(role: UserRole) {
  try {
    sessionStorage.setItem(ROLE_STORAGE_KEY, role);
  } catch {
    // ignore storage failures (e.g. private browsing)
  }
}
