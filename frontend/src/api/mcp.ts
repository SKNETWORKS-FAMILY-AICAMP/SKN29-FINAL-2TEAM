import { apiRequest, ApiError } from './client';

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

/**
 * 우리 팀에 붙어 있는 서버와 그 도구들. **읽기뿐이다.**
 *
 * 등록·수정·삭제·연결 확인은 운영자 콘솔로 갔다(2026-08-18 멘토링 ·
 * `api/opsMcp.ts`). 여기 남겨 두면 부르는 곳이 없는 채로 화면이 다시 폼을
 * 붙일 수 있어서 함께 걷어냈다.
 */
export function listMcpServers(token: string) {
  return apiRequest<McpServer[]>('/mcp/servers/', { token });
}

export { ApiError };
