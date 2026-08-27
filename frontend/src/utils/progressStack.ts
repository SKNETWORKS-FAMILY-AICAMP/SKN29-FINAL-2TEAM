import { useEffect, type ReactNode } from 'react';

/**
 * 화면 오른쪽 아래에 뜨는 진행 카드들을 한 자리에 쌓는 저장소(2026-08-26).
 *
 * `IndexingProgress`("문서를 읽는 중")와 `SkillJobCenter`("스킬 검증 중")가
 * **동시에** 떠 있을 수 있다 — 문서 색인 중에 채팅에서 스킬을 등록할 수도
 * 있다. 각자 자기 자리에 `position: fixed`를 걸면 둘이 겹친다. 대신 이
 * 저장소에 카드 하나씩을 등록만 하면, `ProgressCardStack`(컴포넌트) 하나가
 * 오른쪽 아래에 세로로 쌓아 그린다 — 실제 배치는 몰라도 된다.
 *
 * `session.ts`의 `subscribeSession`과 같은 손으로 만든 구독 패턴이다 — 이
 * 프로젝트에 전역 상태 라이브러리가 없어서, 새로 들이는 대신 이미 쓰는
 * 방식을 그대로 따른다.
 */

interface Entry {
  key: string;
  /** 등록된 순서. **처음 등록될 때만** 정해지고 이후 갱신에는 안 바뀐다 —
   * 안 그러면 카드가 업데이트될 때마다(폴링마다) 스택 안에서 자리를 옮겨
   * 다녀서 사람이 카드를 놓친다. */
  order: number;
  node: ReactNode;
}

let entries: Entry[] = [];
let nextOrder = 0;
const listeners = new Set<() => void>();

function notify(): void {
  listeners.forEach((listener) => listener());
}

/**
 * 카드 하나를 등록하거나(두 번째 인자 O) 뗀다(두 번째 인자 `null`).
 * `key`가 이미 있으면 자리는 그대로 두고 내용만 바꾼다.
 */
function setStackedCard(key: string, node: ReactNode | null): void {
  const existingIndex = entries.findIndex((entry) => entry.key === key);
  if (node === null) {
    if (existingIndex === -1) return;
    entries = entries.filter((entry) => entry.key !== key);
    notify();
    return;
  }
  if (existingIndex === -1) {
    entries = [...entries, { key, order: nextOrder++, node }];
  } else {
    entries = entries.map((entry) => (entry.key === key ? { ...entry, node } : entry));
  }
  notify();
}

export function subscribeStackedCards(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getStackedCards(): Entry[] {
  return entries;
}

/**
 * 카드를 만드는 컴포넌트가 부르는 훅. `node`가 `null`이면 스택에서 빠진다 —
 * 컴포넌트가 스스로 "지금은 보여줄 게 없다"고 판단한 그대로 반영된다.
 * 언마운트되면(로그아웃 등) 자동으로 뗀다.
 */
export function useStackedCard(key: string, node: ReactNode | null): void {
  useEffect(() => {
    setStackedCard(key, node);
    return () => setStackedCard(key, null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, node]);
}
