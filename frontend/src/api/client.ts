import { clearSession, loadSessionToken } from '../utils/session';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api';

/**
 * A failed API call. `status` is 0 when the request never reached the server
 * (dev server not running, CORS, offline), which the auth screens surface
 * differently from a real 4xx.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly fieldErrors: Record<string, string>;

  constructor(message: string, status: number, fieldErrors: Record<string, string> = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.fieldErrors = fieldErrors;
  }
}

/**
 * DRF returns `{ detail: '...' }` for domain errors and
 * `{ field: ['...'] }` for serializer validation errors. Flatten both into a
 * message plus a per-field map the forms can bind to.
 */
function parseErrorBody(body: unknown, status: number): ApiError {
  if (body && typeof body === 'object') {
    const record = body as Record<string, unknown>;
    if (typeof record.detail === 'string') {
      return new ApiError(record.detail, status);
    }

    const fieldErrors: Record<string, string> = {};
    for (const [field, value] of Object.entries(record)) {
      if (Array.isArray(value) && typeof value[0] === 'string') {
        fieldErrors[field] = value[0];
      } else if (typeof value === 'string') {
        fieldErrors[field] = value;
      }
    }
    const first = Object.values(fieldErrors)[0];
    if (first) return new ApiError(first, status, fieldErrors);
  }

  return new ApiError('요청을 처리하지 못했습니다.', status);
}

interface RequestOptions {
  method?: 'GET' | 'POST';
  body?: unknown;
  token?: string | null;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
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

  // 토큰이 만료되거나 무효해졌다면 들고 있어도 쓸모가 없다. 세션을 비우면
  // 이를 구독하는 화면들이 로그인으로 되돌린다. 로그인 실패의 401은 애초에
  // 지울 세션이 없으므로 그냥 통과한다.
  if (response.status === 401 && token && token === loadSessionToken()) {
    clearSession();
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;

  if (!response.ok) throw parseErrorBody(payload, response.status);
  return payload as T;
}
