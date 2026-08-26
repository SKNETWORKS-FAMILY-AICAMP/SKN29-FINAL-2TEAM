/**
 * 「색인이 방금 시작됐다」를 화면들 사이에 알리는 신호.
 *
 * 전역 진행 카드는 폴링으로만 상태를 안다. 그래서 폴더를 저장하거나 파일을
 * 올려도 **다음 idle 폴링(최대 60초)까지 뜨지 않았다** — 사람은 그 사이에
 * 「아무 일도 안 일어났다」고 읽는다.
 *
 * 시작시킨 쪽이 여기로 한마디 하면 카드가 그 자리에서 물어본다. 상태 저장소를
 * 새로 들이지 않고 `window` 이벤트를 쓰는 이유는 **오가는 값이 없기 때문**이다 —
 * 「무슨 일이 생겼으니 다시 물어봐」가 전부라, 어느 쪽도 상대를 알 필요가 없다.
 */

const EVENT = 'halil:indexing-started';

/**
 * 색인을 시작시킨 쪽이 부른다 — 폴더 저장, 내 파일 업로드, 색인 재시도.
 *
 * **서버 응답을 받은 뒤에 부른다.** 요청이 거절되면 시작된 것이 없다.
 */
export function notifyIndexingStarted(): void {
  window.dispatchEvent(new Event(EVENT));
}

/** 듣는 쪽. 해제 함수를 돌려준다(`useEffect` 가 그대로 반환하면 된다). */
export function onIndexingStarted(listener: () => void): () => void {
  window.addEventListener(EVENT, listener);
  return () => window.removeEventListener(EVENT, listener);
}
