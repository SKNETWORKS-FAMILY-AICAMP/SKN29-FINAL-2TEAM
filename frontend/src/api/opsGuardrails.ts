import { opsRequest } from './opsClient';

/**
 * 운영자가 팀에 붙여 주는 **외부 가드레일**.
 *
 * 고객이 이미 가진 것(OpenAI Guardrails·Bedrock·Azure)을 등록해서 그 팀의 대화가
 * 그걸 거쳐 돌게 한다. **팀이 스스로 등록하지 않는다** — 엔드포인트와 키를 알아야
 * 하는 일이라 커스텀 도구(`opsMcp.ts`)·모델(`opsModels.ts`)과 같은 자리에 둔다.
 */
export type GuardrailKind = 'OPENAI_GUARDRAILS' | 'BEDROCK_GUARDRAILS' | 'AZURE_CONTENT_SAFETY';
export type GuardrailProviderStatus = 'UNCHECKED' | 'CONNECTED' | 'ERROR';
/**
 * 검사기가 응답하지 않을 때 **그 팀이** 무엇을 할지.
 *
 * `OPEN` 그대로 보낸다 — 검사기 장애가 채팅 장애가 되지 않는다.
 * `CLOSED` 보내지 않는다 — 「검사 못 했는데 그냥 보냈다」가 계약 위반이 되는 곳.
 *
 * 우리가 임시 검사를 대신 돌리지는 않는다 — 고객이 동의한 적 없는 기준으로
 * 막는 것이고, 「왜 막혔나」에 답할 수 없다.
 */
export type GuardrailOnFailure = 'OPEN' | 'CLOSED';

export interface OpsGuardrailProvider {
  provider_id: string;
  team_id: string;
  /** 팀이 지워졌으면 null. 그때는 화면이 team_id 를 그대로 보여준다. */
  team_name: string | null;
  name: string;
  kind: GuardrailKind;
  /** 공급자마다 다른 설정값(주소·리전·가드레일 ID·설정 JSON). **비밀값은 여기 없다.** */
  config: Record<string, unknown>;
  status: GuardrailProviderStatus;
  /** 그 팀이 **실제로 쓰는** 하나. 나머지는 등록만 돼 있다. */
  is_active: boolean;
  on_failure: GuardrailOnFailure;
  last_checked_at: string | null;
  /** **키 자체는 오지 않는다.** 있는지 여부만. */
  has_credential: boolean;
  created_by: string | null;
  created_at: string | null;
}

export function fetchOpsGuardrails(token: string) {
  return opsRequest<OpsGuardrailProvider[]>('/ops/guardrails/', { token });
}

export function registerOpsGuardrail(
  token: string,
  body: {
    team_id: string;
    name: string;
    kind: GuardrailKind;
    config?: Record<string, unknown>;
    credential?: Record<string, unknown> | null;
    on_failure?: GuardrailOnFailure;
  },
) {
  return opsRequest<OpsGuardrailProvider>('/ops/guardrails/', { method: 'POST', token, body });
}

/**
 * 고친다. **키는 `replace_credential` 이 참일 때만 바뀐다** — 화면이 저장된 키를
 * 다시 보여주지 않으므로, 안 보낸 것을 「지우라」로 읽으면 이름만 고쳐도 키가
 * 날아간다.
 *
 * 종류나 설정이 바뀌면 서버가 상태를 `UNCHECKED` 로 되돌린다 — 이전 「연결 확인」
 * 결과는 다른 곳에 대고 잰 것이기 때문이다.
 */
export function updateOpsGuardrail(
  token: string,
  providerId: string,
  body: {
    name: string;
    kind: GuardrailKind;
    config?: Record<string, unknown>;
    credential?: Record<string, unknown> | null;
    replace_credential?: boolean;
    on_failure?: GuardrailOnFailure;
  },
) {
  return opsRequest<OpsGuardrailProvider>(`/ops/guardrails/${providerId}/`, {
    method: 'PATCH',
    token,
    body,
  });
}

export function removeOpsGuardrail(token: string, providerId: string) {
  return opsRequest<void>(`/ops/guardrails/${providerId}/`, { method: 'DELETE', token });
}

/**
 * 연결 확인. **무해한 문장 하나를 실제로 보내 본다** — 자격증명 형식만 보면
 * 「등록은 됐는데 부를 때 401」을 못 잡는다.
 *
 * 실패해도 등록은 남고 상태가 `ERROR` 로 바뀐다. 이유는 `detail` 에 온다.
 */
export function testOpsGuardrail(token: string, providerId: string) {
  return opsRequest<OpsGuardrailProvider & { detail: string | null }>(
    `/ops/guardrails/${providerId}/test/`,
    { method: 'POST', token },
  );
}

/**
 * **저장하기 전에** 그 설정·키로 실제 붙는지 본다. 행을 만들지 않는다.
 *
 * 안 되는 것을 등록해 두면 그 팀의 대화가 조용히 검사를 건너뛴다 — 우리 런타임은
 * 「연결 확인」을 통과한 것만 부르기 때문이다. 커스텀 도구의 「연결 확인」·모델의
 * 「모델 불러오기」와 같은 자리다.
 */
export function probeOpsGuardrail(
  token: string,
  body: {
    kind: GuardrailKind;
    config?: Record<string, unknown>;
    credential?: Record<string, unknown> | null;
  },
) {
  return opsRequest<{ ok: boolean; detail: string | null }>('/ops/guardrails/probe/', {
    method: 'POST',
    token,
    body,
  });
}

/**
 * 그 팀이 **무엇을 쓸지** 정한다. `null` 이면 아무것도 안 쓴다(등록은 남는다).
 *
 * **등록 목록이 아니라 팀 상세에서 고른다** — 목록은 전 팀의 등록물이라 거기서
 * 켜면 「어느 팀의 무엇을 켜는가」가 흐려진다. 기본 채팅 모델이 이미 같은 길을
 * 갔다(`opsModels.saveOpsTeamDefaultModel`).
 */
export function setTeamActiveGuardrail(token: string, teamId: string, providerId: string | null) {
  return opsRequest<OpsGuardrailProvider | { provider_id: null }>(
    `/ops/guardrails/teams/${teamId}/active/`,
    { method: 'PUT', token, body: { provider_id: providerId } },
  );
}
