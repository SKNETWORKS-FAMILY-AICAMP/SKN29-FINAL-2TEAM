import { apiRequest, ApiError } from './client';
import type { SkillJob } from './skillJobs';

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
 * ## 화면에서 편집하는 칸이 넷뿐인 이유
 *
 * deepagents `SkillsMiddleware` 가 읽는 `SKILL.md` 의 모양 그대로다
 * (`docs/설계 및 구현/3_중간발표 이후/작업기록/Deep_Agents/2026-08-13_03_…벤치마킹.md` §9-3) — frontmatter
 * 의 `name`·`description` 만 매 턴 시스템 프롬프트에 실리고, `body` 는
 * 모델이 그 스킬을 고른 뒤에야 파일로 읽는다. 그래서 **`description` 이
 * 「고를지 말지」의 유일한 근거**다. 비활성 스킬은 별도 namespace로 옮긴다.
 * 업로드 파일의 `license`, `compatibility`, `allowed-tools`, 추가 metadata는
 * 화면에서 직접 편집하지 않지만 서버가 원문대로 보존한다.
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
  /** 비활성 스킬은 별도 보관소에 남고 에이전트 source에서는 제외된다. */
  enabled: boolean;
  /** 팀 스킬일 때, 현재 사용자가 자신의 개인 스킬에서 공유한 항목인지. */
  shared_by_me: boolean;
  /** 개인 스킬일 때, 팀 공유 카탈로그에서 가져온 독립 사본인지. */
  imported_from_team: boolean;
  /** 팀 스킬일 때, 현재 사용자가 이미 개인 사본으로 가져왔는지. */
  imported_by_me: boolean;
  /** 팀 스킬을 공유 목록에서 삭제할 수 있는지. 서버가 현재 팀 역할로 판정한다. */
  can_delete: boolean;
  /** 팀 공유본이 현재 검증 영수증을 갖는지. */
  validation_state: 'VERIFIED' | 'LEGACY_UNVERIFIED' | null;
  requires_validation: boolean;
  updated_at: string | null;
}

export interface SkillInput {
  name: string;
  description: string;
  body: string;
  /** 업로드한 원본. 서버가 추가 frontmatter까지 손실 없이 검증·저장한다. */
  source_content?: string;
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
  return apiRequest<SkillJob>('/me/skills/', { method: 'POST', body: input, token });
}

export function submitMySkillUpdate(
  token: string,
  skillId: string,
  input: { description?: string; body?: string },
) {
  return apiRequest<SkillJob>(`/me/skills/${skillId}/`, { method: 'PATCH', body: input, token });
}

/** 활성 상태는 본문 검증과 무관하므로 즉시 변경한다. */
export function setMySkillEnabled(token: string, skillId: string, enabled: boolean) {
  return apiRequest<Skill>(`/me/skills/${skillId}/`, { method: 'PATCH', body: { enabled }, token });
}

/** **되돌릴 수 없다.** 원본이 우리뿐이다(`deletePersonalFile` 과 같은 이유). */
export function deleteMySkill(token: string, skillId: string) {
  return apiRequest<void>(`/me/skills/${skillId}/`, { method: 'DELETE', token });
}

/** 개인 스킬을 현재 팀에 공유한다. 개인 원본은 그대로 유지된다. */
export function shareMySkill(token: string, skillId: string) {
  return apiRequest<Skill>(`/me/skills/${skillId}/share/`, { method: 'POST', token });
}

/** 내가 만든 팀 공유본만 제거한다. 개인 원본은 삭제하지 않는다. */
export function stopSharingMySkill(token: string, skillId: string) {
  return apiRequest<void>(`/me/skills/${skillId}/share/`, { method: 'DELETE', token });
}

/**
 * 팀 스킬은 검증된 개인 스킬을 공유해 채우는 카탈로그다. 팀원은 조회·가져오기,
 * 공유자는 공유 중지, 팀장은 카탈로그 삭제만 할 수 있다.
 */
export function listTeamSkills(token: string) {
  return apiRequest<Skill[]>('/teams/skills/', { token });
}

export function getTeamSkill(token: string, skillId: string) {
  return apiRequest<Skill>(`/teams/skills/${skillId}/`, { token });
}

/**
 * 팀 공유 카탈로그의 스킬을 독립적인 내 스킬로 복사한다. 팀 카탈로그에는
 * 검증된 스킬만 올라오므로 가져올 때 재검증하지 않고 바로 복사한다.
 */
export function importTeamSkill(token: string, skillId: string) {
  return apiRequest<Skill>(`/teams/skills/${skillId}/import/`, { method: 'POST', token });
}

export function deleteTeamSkill(token: string, skillId: string) {
  return apiRequest<void>(`/teams/skills/${skillId}/`, { method: 'DELETE', token });
}

export { ApiError };
