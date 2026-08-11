import { API_BASE_URL, apiRequest, ApiError, parseErrorBody } from './client';

export interface McpTool {
  mcp_tool_id: string;
  name: string;
  description: string;
  enabled: boolean;
}

export interface McpServer {
  mcp_server_id: string;
  name: string;
  endpoint_url: string;
  /** UNCHECKED(등록만 함) / CONNECTED / ERROR. 셋은 서로 다른 상태다. */
  status: 'UNCHECKED' | 'CONNECTED' | 'ERROR';
  last_checked_at: string | null;
  /** **토큰 자체는 오지 않는다**(11_MCP_설계 §4-2). 있는지 여부만. */
  has_token: boolean;
  tools: McpTool[];
}

export interface McpTestResult {
  status: 'CONNECTED';
  tool_count: number;
  server?: McpServer;
}

export function listMcpServers(token: string) {
  return apiRequest<McpServer[]>('/mcp/servers/', { token });
}

export function createMcpServer(
  token: string,
  body: { name: string; endpoint_url: string; auth_token?: string },
) {
  return apiRequest<McpServer>('/mcp/servers/', { method: 'POST', body, token });
}

export function deleteMcpServer(token: string, serverId: string) {
  return apiRequest<void>(`/mcp/servers/${serverId}/`, { method: 'DELETE', token });
}

/**
 * 연결 테스트(initialize + tools/list).
 *
 * `apiRequest`를 쓰지 않는다 — 실패가 502 로 오는데 **그 본문이 정상 결과**다
 * (`error_code`가 화면 문구를 정한다). 예외로 던지면 그 코드를 잃는다.
 */
export async function testMcpServer(
  token: string,
  serverId: string,
): Promise<{ ok: true; result: McpTestResult } | { ok: false; errorCode: string; detail: string }> {
  const response = await fetch(`${API_BASE_URL}/mcp/servers/${serverId}/test/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: '{}',
  });
  const body = await response.json().catch(() => null);

  if (response.ok) return { ok: true, result: body as McpTestResult };
  if (response.status === 502 && body && typeof body === 'object' && 'error_code' in body) {
    const failure = body as { error_code: string; detail: string };
    return { ok: false, errorCode: failure.error_code, detail: failure.detail };
  }
  throw parseErrorBody(body, response.status);
}

export { ApiError };
