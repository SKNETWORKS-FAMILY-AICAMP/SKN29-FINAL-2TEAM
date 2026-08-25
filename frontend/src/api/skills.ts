import { apiRequest, ApiError } from './client';

/**
 * 「스킬」 — 사람이 적어 두는 업무 절차. 에이전트가 필요할 때 골라 읽는다.
 *
 * **사람의 「기술 스택」과 다른 것이다**(`SkillList.tsx`). 그쪽은 HR 이 아는
 * 보유 역량이고, 이건 「구매 검토는 이렇게 한다」 같은 **절차 문서**다. 같은
 * 말을 쓰면 화면에서 갈리지 않아 2026-08-21 에 사람 쪽을 기술 스택으로 옮겼다.
 *
 * ## 서버가 붙었다 (2026-08-22)
 *
 * `apps/skills`가 실제 저장·조회를 한다(내부적으로는
 * `services.agent_runtime.skills.service` — 채팅의 `skill_register` 도구와
 * 같은 함수를 쓴다). 개인 스킬(`/me/skills/`)은 계정 본인 것만, 팀 스킬
 * (`/teams/skills/`)은 조회는 팀원 전체가·쓰기는 팀장만 할 수 있다.
 *
 * ## 칸이 넷뿐인 이유
 *
 * deepagents `SkillsMiddleware` 가 읽는 `SKILL.md` 의 모양 그대로다
 * (`docs/설계 및 구현/3_중간발표 이후/작업기록/Deep_Agents/2026-08-13_03_…벤치마킹.md` §9-3) — frontmatter
 * 의 `name`·`description` 만 매 턴 시스템 프롬프트에 실리고, `body` 는
 * 모델이 그 스킬을 고른 뒤에야 파일로 읽는다. 그래서 **`description` 이
 * 「고를지 말지」의 유일한 근거**다. `enabled` 만 예외로 하나 더 있다
 * (2026-08-26) — `SkillVisibilityMiddleware` 가 `metadata.enabled` 를 보고
 * 꺼진 스킬을 통째로 목록에서 뺀다. 그 외 칸을 더 만들지 않는다 — 미들웨어가
 * 안 읽는 값을 받아 두면 화면에만 있는 값이 된다.
 *
 * ## 이름은 한 번 정하면 못 바꾼다
 *
 * 저장 경로 자체가 이름으로 정해진다(`/skills/personal/{name}/SKILL.md`) —
 * 이름을 바꾸는 것은 실은 지우고 새로 만드는 일이다. 지금은 그 마이그레이션을
 * 안 하므로, 서버도 만들 때만 이름을 받고 수정(`PATCH`)에는 이름 칸이 없다.
 */
export interface Skill {
  skill_id: string;
  /** frontmatter `name`. 스킬을 가리키는 이름이자 저장 경로 — 한 번 정하면 못 바꾼다. */
  name: string;
  /** frontmatter `description`. **모델이 이것만 보고 고른다.** */
  description: string;
  /** `SKILL.md` 본문(마크다운). 목록 응답에서는 안 준다 — 길어서 목록이 무거워진다. */
  body?: string;
  /** frontmatter `metadata.enabled`. `false`면 에이전트에게 아예 안 보인다(삭제와 다름 — 값은 그대로 남는다). */
  enabled: boolean;
  updated_at: string | null;
}

export interface SkillInput {
  name: string;
  description: string;
  body: string;
}

/** 내가 만든 스킬. 목록에는 `body` 를 싣지 않는다. */
export function listMySkills(token: string) {
  return apiRequest<Skill[]>('/me/skills/', { token });
}

/** 한 건. 본문까지 필요할 때(수정 화면을 열 때) 부른다. */
export function getMySkill(token: string, skillId: string) {
  return apiRequest<Skill>(`/me/skills/${skillId}/`, { token });
}

export function createMySkill(token: string, input: SkillInput) {
  return apiRequest<Skill>('/me/skills/', { method: 'POST', body: input, token });
}

export function updateMySkill(
  token: string,
  skillId: string,
  input: { description?: string; body?: string; enabled?: boolean },
) {
  return apiRequest<Skill>(`/me/skills/${skillId}/`, { method: 'PATCH', body: input, token });
}

/** **되돌릴 수 없다.** 원본이 우리뿐이다(`deletePersonalFile` 과 같은 이유). */
export function deleteMySkill(token: string, skillId: string) {
  return apiRequest<void>(`/me/skills/${skillId}/`, { method: 'DELETE', token });
}

/**
 * 팀 스킬. **조회는 팀원 전체가 부를 수 있다** — 쓰기(create/update/delete)만
 * 서버가 팀장인지 확인한다(403). 화면에서도 미리 막아 두지만(버튼을 안 보이게),
 * 최종 판단은 항상 서버 쪽이다.
 */
export function listTeamSkills(token: string) {
  return apiRequest<Skill[]>('/teams/skills/', { token });
}

export function getTeamSkill(token: string, skillId: string) {
  return apiRequest<Skill>(`/teams/skills/${skillId}/`, { token });
}

export function createTeamSkill(token: string, input: SkillInput) {
  return apiRequest<Skill>('/teams/skills/', { method: 'POST', body: input, token });
}

export function updateTeamSkill(
  token: string,
  skillId: string,
  input: { description?: string; body?: string; enabled?: boolean },
) {
  return apiRequest<Skill>(`/teams/skills/${skillId}/`, { method: 'PATCH', body: input, token });
}

export function deleteTeamSkill(token: string, skillId: string) {
  return apiRequest<void>(`/teams/skills/${skillId}/`, { method: 'DELETE', token });
}

export { ApiError };
