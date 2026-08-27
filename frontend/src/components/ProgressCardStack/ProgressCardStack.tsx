import { useEffect, useState } from 'react';
import { getStackedCards, subscribeStackedCards } from '../../utils/progressStack';
import styles from './ProgressCardStack.module.css';

/**
 * 오른쪽 아래 진행 카드들의 실제 자리(2026-08-26).
 *
 * `IndexingProgress`("문서를 읽는 중")와 `SkillJobCenter`("스킬 검증 중")는
 * 이제 자기 카드를 직접 `position: fixed`로 그리지 않고,
 * `utils/progressStack.ts`의 `useStackedCard()`로 여기에 등록만 한다. 이
 * 컴포넌트 하나가 등록된 카드를 전부 모아 한 자리에 세로로 쌓는다 — 두
 * 카드가 동시에 떠도 겹치지 않는다.
 *
 * **새 카드가 위로 쌓인다.** `flex-direction: column-reverse`라 배열의 첫
 * 항목(가장 먼저 뜬 카드)이 화면 맨 아래에 그대로 있고, 나중에 뜨는 카드가
 * 그 위로 쌓인다 — 먼저 보던 카드가 자리를 옮기지 않아서 계속 같은 곳을
 * 본다.
 *
 * `App.tsx`에서 `<Routes>` 바깥에 한 번만 둔다 — `IndexingProgress`가 이미
 * 그 자리에 있던 것과 같은 이유(라우트가 바뀌어도 유지).
 */
export function ProgressCardStack() {
  const [, forceRender] = useState(0);

  useEffect(() => subscribeStackedCards(() => forceRender((n) => n + 1)), []);

  const cards = getStackedCards();
  if (cards.length === 0) return null;

  return (
    <div className={styles.stack}>
      {cards.map((card) => (
        <div key={card.key} className={styles.slot}>
          {card.node}
        </div>
      ))}
    </div>
  );
}

export default ProgressCardStack;
