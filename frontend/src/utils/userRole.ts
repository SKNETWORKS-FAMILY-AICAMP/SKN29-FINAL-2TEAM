import { loadSession } from './session';

export type UserRole = 'leader' | 'member';

const ROLE_STORAGE_KEY = 'halil.userRole';

/**
 * Decides whether to show the team-leader or team-member settings screen.
 * The logged-in account's role (판정 기준은 `org.mgr_id`) wins, but the
 * dev-only role switcher writes an explicit override to session storage so
 * either screen can still be opened without logging in.
 * Defaults to 'leader' so existing PM/admin flows keep working.
 */
export function loadUserRole(): UserRole {
  try {
    const override = sessionStorage.getItem(ROLE_STORAGE_KEY);
    if (override === 'member' || override === 'leader') return override;
  } catch {
    // ignore storage failures (e.g. private browsing)
  }

  return loadSession()?.account.role === 'member' ? 'member' : 'leader';
}

export function saveUserRole(role: UserRole) {
  try {
    sessionStorage.setItem(ROLE_STORAGE_KEY, role);
  } catch {
    // ignore storage failures (e.g. private browsing)
  }
}
