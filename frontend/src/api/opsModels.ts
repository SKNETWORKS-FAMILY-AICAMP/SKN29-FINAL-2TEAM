import { opsRequest } from './opsClient';

/** 어느 팀에 무엇이 등록돼 있는가. **키는 서버가 돌려주지 않는다.** */
export interface OpsModel {
  conn_id: string;
  team_id: string;
  /** 팀이 지워졌으면 null. 그때는 화면이 team_id 를 그대로 보여준다. */
  team_name: string | null;
  label: string;
  base_url: string;
  model: string;
  connected_at: string;
}

export interface OpsModelRegisterInput {
  team_id: string;
  label: string;
  base_url: string;
  api_key: string;
  model: string;
}

export function fetchOpsModels(token: string) {
  return opsRequest<OpsModel[]>('/ops/models/', { token });
}

/**
 * 등록 전에 서버가 그 주소·키·모델로 한 번 답을 받아 본다 — 실패하면 400.
 *
 * **목록을 돌려주지 않는다.** 등록이 끝난 뒤 목록을 다시 만들다 실패하면 이미
 * 성공한 등록이 실패로 보이기 때문이다(2026-08-13). 목록은 따로 받아 온다.
 */
export function registerOpsModel(token: string, body: OpsModelRegisterInput) {
  return opsRequest<{ team_id: string; model: string }>('/ops/models/', {
    method: 'POST',
    token,
    body,
  });
}

/** 그 모델을 쓰는 에이전트가 있으면 서버가 409 로 막는다. */
export function removeOpsModel(token: string, connId: string) {
  return opsRequest<void>(`/ops/models/${connId}/`, { method: 'DELETE', token });
}
