import { useEffect, useState } from 'react';
import type { Account } from '../api/auth';

const SESSION_STORAGE_KEY = 'halil.session';

export interface Session {
  token: string;
  account: Account;
}

/**
 * 세션이 바뀌면(로그인·로그아웃, 토큰 만료로 인한 강제 정리) 이를 구독한
 * 화면들이 함께 갱신되도록 한다. localStorage만 보면 같은 탭 안에서 일어난
 * 변경을 React가 알 수 없다.
 */
const listeners = new Set<() => void>();

function notifySessionChanged() {
  for (const listener of listeners) listener();
}

export function subscribeSession(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
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
  notifySessionChanged();
}

export function clearSession() {
  try {
    localStorage.removeItem(SESSION_STORAGE_KEY);
  } catch {
    // ignore storage failures (e.g. private browsing)
  }
  notifySessionChanged();
}

export function loadSessionToken(): string | null {
  return loadSession()?.token ?? null;
}

/** 현재 세션. 로그아웃이나 토큰 만료가 감지되면 자동으로 null이 된다. */
export function useSession(): Session | null {
  const [session, setSession] = useState<Session | null>(loadSession);

  useEffect(() => subscribeSession(() => setSession(loadSession())), []);

  return session;
}
