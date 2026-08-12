import { clearSession, loadSessionToken } from '../utils/session';

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api';

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
export function parseErrorBody(body: unknown, status: number): ApiError {
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
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
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

/**
 * NDJSON 스트림 요청 — 한 줄에 이벤트 JSON 하나씩 오는 응답을 콜백으로 넘긴다.
 *
 * `apiRequest`를 못 쓴다 — 그쪽은 응답을 통째로 받아 JSON으로 바꾸는데, 여기서는
 * 서버가 보내는 대로 읽어야 진행이 보인다. 응답이 시작된 뒤의 실패는 상태 코드가
 * 아니라 마지막 줄의 `error` 이벤트로 온다.
 *
 * `signal`로 중단할 수 있다.
 */
export async function streamNdjson<TEvent>(
  path: string,
  token: string | null | undefined,
  body: unknown,
  onEvent: (event: TEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok || !response.body) {
    const failure = await response.json().catch(() => null);
    throw parseErrorBody(failure, response.status);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // 마지막 조각은 줄이 안 끝났을 수 있어 버퍼에 남긴다.
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      if (!line.trim()) continue;
      onEvent(JSON.parse(line) as TEvent);
    }
  }

  // `error`는 여기서 던지지 않는다. 스트림 중간에 온 오류도 이벤트로 그려야
  // 앞 단계 결과물이 화면에 남는다 — 던지면 그 카드까지 날아간다.
}

/**
 * 파일 업로드. `apiRequest`와 나눠 둔 이유는 **Content-Type을 직접 정하면 안 되기
 * 때문**이다 — multipart 는 경계 문자열이 헤더에 들어가야 하고, 그 값은 브라우저가
 * FormData 를 보면서 만든다. 직접 넣으면 서버가 본문을 파싱하지 못한다.
 */
export async function apiUpload<T>(
  path: string,
  file: File,
  options: { method?: 'POST' | 'PUT'; token?: string | null; field?: string } = {},
): Promise<T> {
  const { method = 'PUT', token, field = 'file' } = options;

  const form = new FormData();
  form.append(field, file);

  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { method, headers, body: form });
  } catch {
    throw new ApiError('서버에 연결할 수 없습니다. 백엔드가 실행 중인지 확인해 주세요.', 0);
  }

  if (response.status === 401 && token && token === loadSessionToken()) {
    clearSession();
  }
  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;
  if (!response.ok) throw parseErrorBody(payload, response.status);
  return payload as T;
}
