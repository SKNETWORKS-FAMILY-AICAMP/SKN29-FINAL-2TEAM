import { apiRequest, ApiError } from './client';

/**
 * 「스킬」 — 사람이 적어 두는 업무 절차. 에이전트가 필요할 때 골라 읽는다.
 *
 * **사람의 「기술 스택」과 다른 것이다**(`SkillList.tsx`). 그쪽은 HR 이 아는
 * 보유 역량이고, 이건 「구매 검토는 이렇게 한다」 같은 **절차 문서**다. 같은
 * 말을 쓰면 화면에서 갈리지 않아 2026-08-21 에 사람 쪽을 기술 스택으로 옮겼다.
 *
 * ## 서버가 아직 없다
 *
 * 이 모듈은 **화면과 서버 사이의 계약**이다(2026-08-21, 준 → 주연 인계).
 * 프론트만 먼저 만들고 저장·런타임 배선은 주연 몫이라, 지금 부르면 404 가
 * 온다 — `SkillsTab` 이 그 404 만 따로 받아 「준비 중」으로 그린다.
 *
 * ## 칸이 셋뿐인 이유
 *
 * deepagents `SkillsMiddleware` 가 읽는 `SKILL.md` 의 모양 그대로다
 * (`docs/작업기록/Deep_Agents/2026-08-13_03_…벤치마킹.md` §9-3) — frontmatter
 * 의 `name`·`description` 만 매 턴 시스템 프롬프트에 실리고, `body` 는
 * 모델이 그 스킬을 고른 뒤에야 파일로 읽는다. 그래서 **`description` 이
 * 「고를지 말지」의 유일한 근거**다. 칸을 더 만들지 않는다 — 미들웨어가
 * 안 읽는 값을 받아 두면 화면에만 있는 값이 된다.
 */
export interface Skill {
  skill_id: string;
  /** frontmatter `name`. 스킬을 가리키는 이름이다. */
  name: string;
  /** frontmatter `description`. **모델이 이것만 보고 고른다.** */
  description: string;
  /** `SKILL.md` 본문(마크다운). 목록 응답에서는 안 준다 — 길어서 목록이 무거워진다. */
  body?: string;
  updated_at: string | null;
}

/** 내가 만든 스킬. 목록에는 `body` 를 싣지 않는다. */
export function listMySkills(token: string) {
  return apiRequest<Skill[]>('/me/skills/', { token });
}

/** 한 건. 본문까지 필요할 때(수정 화면을 열 때) 부른다. */
export function getMySkill(token: string, skillId: string) {
  return apiRequest<Skill>(`/me/skills/${skillId}/`, { token });
}

export function createMySkill(
  token: string,
  input: { name: string; description: string; body: string },
) {
  return apiRequest<Skill>('/me/skills/', { method: 'POST', body: input, token });
}

export function updateMySkill(
  token: string,
  skillId: string,
  input: { name?: string; description?: string; body?: string },
) {
  return apiRequest<Skill>(`/me/skills/${skillId}/`, { method: 'PATCH', body: input, token });
}

/** **되돌릴 수 없다.** 원본이 우리뿐이다(`deletePersonalFile` 과 같은 이유). */
export function deleteMySkill(token: string, skillId: string) {
  return apiRequest<void>(`/me/skills/${skillId}/`, { method: 'DELETE', token });
}

export { ApiError };
