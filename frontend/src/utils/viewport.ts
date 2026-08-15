import { useEffect, useState } from 'react';

/**
 * 사이드바가 자리를 차지할 수 없는 폭. 이 아래에서는 **덮어서 여는 패널**이 된다.
 *
 * 240px 짜리 사이드바는 375px 화면의 2/3 를 먹어서, 남은 본문에 글자가 한 자씩
 * 흐른다. 좁히는 것으로는 안 된다 — 좁은 사이드바는 사이드바도 본문도 둘 다 못
 * 쓰게 만든다.
 */
export const NARROW_VIEWPORT = '(max-width: 760px)';

/**
 * 지금 화면이 좁은가.
 *
 * **CSS 만으로는 안 되는 자리에만 쓴다.** 라벨을 감출지(`AppShell`), 드래그로
 * 정한 폭을 무시할지(`ChatPage`)처럼 **판단이 JS 에 있는 것**들이다. 단순히
 * 배치를 바꾸는 것은 CSS 의 일이고 여기로 가져오지 않는다.
 */
export function useNarrowViewport(): boolean {
  const [narrow, setNarrow] = useState(() => window.matchMedia(NARROW_VIEWPORT).matches);

  useEffect(() => {
    const query = window.matchMedia(NARROW_VIEWPORT);
    const sync = (event: MediaQueryListEvent) => setNarrow(event.matches);
    query.addEventListener('change', sync);
    return () => query.removeEventListener('change', sync);
  }, []);

  return narrow;
}
