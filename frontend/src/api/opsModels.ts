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
  supports_image_input: boolean;
  connected_at: string;
}

export interface OpsModelRegisterInput {
  team_id: string;
  label: string;
  base_url: string;
  api_key: string;
  model: string;
  supports_image_input: boolean;
}

/** 그 팀의 **기본 채팅 모델** — 아무 에이전트도 안 고르고 말을 걸었을 때 도는 것.
 *
 * 저장 위치는 `team.default_model`이다(2026-08-22). 그 전에는 레거시 정문
 * 에이전트의 모델에 얹혀 있어서 「정문이 아직 없다」는 상태가 따로 있었는데,
 * 팀 설정으로 옮기면서 그 상태가 없어졌다 — 이제 어느 팀이든 정할 수 있다. */
export interface OpsTeamDefaultModel {
  /** 아직 정한 적이 없으면 null. 그때 화면은 「고르세요」를 띄운다 — 임의의
   *  기본값을 저장된 것처럼 보이면 안 된다. */
  model: string | null;
  /** 기본 제공 + 그 팀에 등록된 것. **외워 적게 하지 않는다.** */
  choices: string[];
}

export function fetchOpsTeamDefaultModel(token: string, teamId: string) {
  return opsRequest<OpsTeamDefaultModel>(`/ops/models/teams/${teamId}/default/`, { token });
}

/** 팀별로 정한다 — 전역 하나로 두면 계약·리전 요건이 다른 회사를 못 받는다. */
export function saveOpsTeamDefaultModel(token: string, teamId: string, model: string) {
  return opsRequest<{ model: string | null }>(
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
/** `warning`이 있으면 등록은 성공했지만(201) 그 서버가 토큰 사용량을 안 준다는
 *  뜻이다 — 막지 않는다. 답을 주는 것과 사용량을 알려주는 것은 별개 능력이라,
 *  후자가 없다고 채팅이 되는 모델을 등록 못 하게 할 이유는 없다. */
export function registerOpsModel(token: string, body: OpsModelRegisterInput) {
  return opsRequest<{ team_id: string; model: string; warning?: string }>('/ops/models/', {
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
