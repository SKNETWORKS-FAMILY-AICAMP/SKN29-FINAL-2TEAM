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

/** 그 팀의 **기본 채팅 모델** — 아무 에이전트도 안 고르고 말을 걸었을 때 도는 것. */
export interface OpsTeamDefaultModel {
  /** 팀에 정문이 아직 없으면 null. 그때 화면은 「없다」고 말한다. */
  model: string | null;
  agent_name: string | null;
  /** 기본 제공 + 그 팀에 등록된 것. **외워 적게 하지 않는다.** */
  choices: string[];
}

export function fetchOpsTeamDefaultModel(token: string, teamId: string) {
  return opsRequest<OpsTeamDefaultModel>(`/ops/models/teams/${teamId}/default/`, { token });
}

/** 팀별로 정한다 — 전역 하나로 두면 계약·리전 요건이 다른 회사를 못 받는다. */
export function saveOpsTeamDefaultModel(token: string, teamId: string, model: string) {
  return opsRequest<{ model: string; agent_name: string }>(
    `/ops/models/teams/${teamId}/default/`,
    { method: 'PUT', token, body: { model } },
  );
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

/**
 * 그 주소·키가 가진 모델 이름 목록. 못 주면 빈 목록과 이유가 온다.
 *
 * **이름을 외워 적게 하지 않는다** — 오타 하나가 실행 시점 404 가 되고, 그때
 * 죽는 것은 등록해 준 우리가 아니라 그 팀의 대화다.
 */
export function probeOpsModels(token: string, baseUrl: string, apiKey: string) {
  return opsRequest<{ models: string[]; detail: string | null }>('/ops/models/probe/', {
    method: 'POST',
    token,
    body: { base_url: baseUrl, api_key: apiKey },
  });
}
