/**
 * 「스킬 검증 job이 방금 생겼다」를 화면들 사이에 알리는 신호.
 *
 * `indexingSignal.ts`와 정확히 같은 이유·같은 모양이다 — `SkillJobCenter`는
 * 폴링으로만 상태를 알고, idle 폴링 간격까지 기다리면 방금 시킨 검증이
 * 한참 있다가 뜬 것처럼 보인다. 오가는 값이 없는 이유도 같다: "무슨 일이
 * 생겼으니 다시 물어봐"가 전부라 어느 쪽도 job_id를 알 필요가 없다 — 어차피
 * `SkillJobCenter`는 "내 열린 job" 목록 전체를 다시 받아서 새로 생긴 것을
 * 스스로 찾아낸다.
 */

const STARTED_EVENT = 'halil:skill-job-started';
const REMOVED_EVENT = 'halil:skill-job-removed';

/** 검증을 시작시킨 쪽이 부른다 — 채팅의 `skill_register` 승인, 설정 화면의 검증 생성. */
export function notifySkillJobStarted(): void {
  window.dispatchEvent(new Event(STARTED_EVENT));
}

/** 듣는 쪽. 해제 함수를 돌려준다(`useEffect`가 그대로 반환하면 된다). */
export function onSkillJobStarted(listener: () => void): () => void {
  window.addEventListener(STARTED_EVENT, listener);
  return () => window.removeEventListener(STARTED_EVENT, listener);
}

/** 설정 화면에서 실패 기록을 지웠을 때 전역 진행 카드도 즉시 없앤다. */
export function notifySkillJobRemoved(jobId: string): void {
  window.dispatchEvent(new CustomEvent<string>(REMOVED_EVENT, { detail: jobId }));
}

export function onSkillJobRemoved(listener: (jobId: string) => void): () => void {
  const handler = (event: Event) => listener((event as CustomEvent<string>).detail);
  window.addEventListener(REMOVED_EVENT, handler);
  return () => window.removeEventListener(REMOVED_EVENT, handler);
}
