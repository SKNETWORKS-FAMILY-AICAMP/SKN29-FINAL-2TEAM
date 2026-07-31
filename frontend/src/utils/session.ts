import { useEffect, useState } from 'react';
import type { Account } from '../api/auth';

const SESSION_STORAGE_KEY = 'halil.session';

export interface Session {
  token: string;
  /** 서버가 알려준 토큰 만료 시각(ISO8601). 지나면 세션을 스스로 버린다. */
  expires_at: string;
  account: Account;
}

/**
 * 세션이 바뀌면(로그인·로그아웃, 토큰 만료로 인한 강제 정리) 이를 구독한
 * 화면들이 함께 갱신되도록 한다. 스토리지만 보면 같은 탭 안에서 일어난
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

function isExpired(session: Session): boolean {
  const expiresAt = Date.parse(session.expires_at);
  // 만료 시각을 못 읽으면 만료로 보지 않는다. 보호 API가 401을 주면 어차피
  // 세션이 정리되므로, 여기서 끊으면 멀쩡한 세션만 잃는다.
  return Number.isFinite(expiresAt) && expiresAt <= Date.now();
}

/**
 * The logged-in session. The backend keeps no server-side session table, so
 * the signed token issued at login/signup is the whole of it — losing this
 * value just means logging in again.
 *
 * `sessionStorage`라서 탭·브라우저를 닫으면 사라진다. 그 안에서도 서버가 알려준
 * 만료 시각이 지나면 버린다 — 랜딩처럼 보호 API를 부르지 않는 화면은 401을 받을
 * 일이 없어서, 만료를 직접 보지 않으면 죽은 토큰으로 로그인 상태를 보여준다.
 */
export function loadSession(): Session | null {
  try {
    const raw = sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Session;
    if (!parsed?.token) return null;
    if (isExpired(parsed)) {
      sessionStorage.removeItem(SESSION_STORAGE_KEY);
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function saveSession(session: Session) {
  try {
    sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
  } catch {
    // ignore storage failures (e.g. private browsing)
  }
  notifySessionChanged();
}

export function clearSession() {
  try {
    sessionStorage.removeItem(SESSION_STORAGE_KEY);
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
