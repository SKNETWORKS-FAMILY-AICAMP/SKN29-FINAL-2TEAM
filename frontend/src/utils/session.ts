import type { Account } from '../api/auth';

const SESSION_STORAGE_KEY = 'halil.session';

export interface Session {
  token: string;
  account: Account;
}

/**
 * The logged-in session. The backend keeps no server-side session table, so
 * the signed token issued at login/signup is the whole of it — losing this
 * value just means logging in again.
 */
export function loadSession(): Session | null {
  try {
    const raw = localStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Session;
    return parsed?.token ? parsed : null;
  } catch {
    return null;
  }
}

export function saveSession(session: Session) {
  try {
    localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
  } catch {
    // ignore storage failures (e.g. private browsing)
  }
}

export function clearSession() {
  try {
    localStorage.removeItem(SESSION_STORAGE_KEY);
  } catch {
    // ignore storage failures (e.g. private browsing)
  }
}

export function loadSessionToken(): string | null {
  return loadSession()?.token ?? null;
}
