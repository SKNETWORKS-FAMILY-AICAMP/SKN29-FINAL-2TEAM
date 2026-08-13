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

/** 등록 전에 서버가 그 주소·키·모델로 한 번 답을 받아 본다 — 실패하면 400. */
export function registerOpsModel(token: string, body: OpsModelRegisterInput) {
  return opsRequest<OpsModel[]>('/ops/models/', { method: 'POST', token, body });
}

export function removeOpsModel(token: string, connId: string) {
  return opsRequest<OpsModel[]>(`/ops/models/${connId}/`, { method: 'DELETE', token });
}
