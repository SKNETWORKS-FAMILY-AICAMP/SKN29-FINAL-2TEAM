import { useEffect, useState } from 'react';

const PROJECT_STORAGE_KEY = 'halil.projectContext';

/** 상단바에서 고른 프로젝트. 이름까지 같이 두는 이유는 아래 주석 참고. */
export interface ProjectContext {
  proj_id: string;
  name: string;
}

/**
 * 대화가 어느 프로젝트 문맥에서 열리는지를 정한다 — 새 대화를 만들 때
 * `chat_session.proj_id`로 실려 가고, 서버는 그 값으로 `task_extraction`의 기준
 * 문서를 찾는다(`services/harness/runner.py` `_injected`).
 *
 * `null`은 「전체(팀)」이다. 이 상태에서 업무 추출을 시키면 서버가 "프로젝트를
 * 먼저 고르세요"로 끝내는데, 그건 고장이 아니라 현 설계다 — 어느 문서로 뽑았는지가
 * 결과 전체의 전제라 사람이 정해야 한다. 되묻는 카드는 후속.
 *
 * id 만이 아니라 이름도 같이 담는다. 그러지 않으면 문맥 한 줄을 보여주려는
 * 화면마다 프로젝트 목록을 다시 받아야 한다 — 고른 사람이 이미 본 이름이다.
 *
 * `session.ts`와 같은 방식으로 구독한다. 스토리지만 보면 같은 탭 안의 변경을
 * React가 알 수 없다.
 */
const listeners = new Set<() => void>();

export function subscribeProjectContext(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function loadProjectContext(): ProjectContext | null {
  try {
    const raw = sessionStorage.getItem(PROJECT_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as ProjectContext;
    return parsed?.proj_id ? parsed : null;
  } catch {
    return null;
  }
}

export function saveProjectContext(context: ProjectContext | null) {
  try {
    if (context) sessionStorage.setItem(PROJECT_STORAGE_KEY, JSON.stringify(context));
    else sessionStorage.removeItem(PROJECT_STORAGE_KEY);
  } catch {
    // ignore storage failures (e.g. private browsing)
  }
  for (const listener of listeners) listener();
}

/** 현재 프로젝트 문맥. 「전체(팀)」이면 null. */
export function useProjectContext(): ProjectContext | null {
  const [context, setContext] = useState<ProjectContext | null>(loadProjectContext);

  useEffect(() => subscribeProjectContext(() => setContext(loadProjectContext())), []);

  return context;
}
