import { clearOpsSession, loadOpsToken } from '../utils/opsSession';
import { ApiError, parseErrorBody } from './client';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api';

interface OpsRequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  token?: string | null;
}

/**
 * 운영자 콘솔 전용 fetch 래퍼. 일반 로그인 세션(`api/client.ts`의 `apiRequest`)과
 * 완전히 분리해서, 운영자 토큰이 만료·무효화됐을 때 ops 세션만 비운다.
 */
export async function opsRequest<T>(path: string, options: OpsRequestOptions = {}): Promise<T> {
  const { method = 'GET', body, token } = options;

  const headers: Record<string, string> = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (token) headers.Authorization = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError('서버에 연결할 수 없습니다. 백엔드가 실행 중인지 확인해 주세요.', 0);
  }

  if (response.status === 401 && token && token === loadOpsToken()) {
    clearOpsSession();
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;

  if (!response.ok) throw parseErrorBody(payload, response.status);
  return payload as T;
}
