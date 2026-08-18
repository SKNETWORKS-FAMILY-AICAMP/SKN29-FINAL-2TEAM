import { opsRequest } from './opsClient';
import type { McpServer } from './mcp';

/**
 * 운영자가 팀에 붙여 주는 Customizing Tool 서버.
 *
 * **팀이 스스로 등록하지 않는다**(2026-08-18 멘토링). 설정 탭에는 목록만 남고
 * 등록·수정·삭제·연결 확인이 여기로 왔다 — 모델(`opsModels.ts`)과 같은 모양이다.
 */
export interface OpsMcpServer {
  mcp_server_id: string;
  team_id: string;
  /** 팀이 지워졌으면 null. 그때는 화면이 team_id 를 그대로 보여준다. */
  team_name: string | null;
  name: string;
  endpoint_url: string;
  status: 'UNCHECKED' | 'CONNECTED' | 'ERROR';
  last_checked_at: string | null;
  /** **토큰 자체는 오지 않는다**(11_MCP_설계 §4-2). 있는지 여부만. */
  has_token: boolean;
  tool_count: number;
}

export function fetchOpsMcpServers(token: string) {
  return opsRequest<OpsMcpServer[]>('/ops/mcp/', { token });
}

export function registerOpsMcpServer(
  token: string,
  body: { team_id: string; name: string; endpoint_url: string; auth_token?: string },
) {
  return opsRequest<McpServer>('/ops/mcp/', { method: 'POST', token, body });
}

/**
 * 고친다. **토큰은 `replace_token` 이 참일 때만 바뀐다** — 화면이 저장된 토큰을
 * 다시 보여주지 않으므로, 안 보낸 것을 「지우라」로 읽으면 이름만 고쳐도 토큰이
 * 날아간다.
 *
 * 주소를 바꾸면 서버가 도구 목록을 지우고 `UNCHECKED` 로 되돌린다 — 이전에 읽은
 * 도구는 다른 서버의 것이기 때문이다.
 */
export function updateOpsMcpServer(
  token: string,
  serverId: string,
  body: {
    team_id: string;
    name: string;
    endpoint_url: string;
    auth_token?: string;
    replace_token?: boolean;
  },
) {
  return opsRequest<McpServer>(`/ops/mcp/${serverId}/`, { method: 'PATCH', token, body });
}

/** 팀을 함께 보낸다 — server_id 하나로 지우면 어느 팀 것인지 보는 자물쇠가 없다. */
export function removeOpsMcpServer(token: string, serverId: string, teamId: string) {
  return opsRequest<void>(`/ops/mcp/${serverId}/?team_id=${encodeURIComponent(teamId)}`, {
    method: 'DELETE',
    token,
  });
}

/**
 * 연결 확인(initialize + tools/list). 실패는 502 로 오고 `detail` 이 이유다 —
 * `opsRequest` 가 그것을 `ApiError.message` 로 만들어 던진다.
 */
export function testOpsMcpServer(token: string, serverId: string, teamId: string) {
  return opsRequest<{ status: 'CONNECTED'; tool_count: number }>(`/ops/mcp/${serverId}/test/`, {
    method: 'POST',
    token,
    body: { team_id: teamId },
  });
}
