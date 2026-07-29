const apiBaseUrl = import.meta.env.DEV ? '/api' : (import.meta.env.VITE_API_BASE_URL ?? '/api')

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      ...init.headers,
    },
    ...init,
  })

  if (!response.ok) {
    let detail = `API 요청에 실패했습니다. (${response.status})`

    try {
      const body = (await response.json()) as { detail?: unknown }
      if (typeof body.detail === 'string' && body.detail.trim()) {
        detail = body.detail
      }
    } catch {
      // JSON 오류 본문이 아니면 상태 코드 기반 메시지를 사용한다.
    }

    throw new ApiError(response.status, detail)
  }

  return response.json() as Promise<T>
}

export { apiBaseUrl }
