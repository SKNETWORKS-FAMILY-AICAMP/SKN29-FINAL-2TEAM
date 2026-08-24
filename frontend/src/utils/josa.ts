/**
 * 이름 뒤에 붙일 조사를 고른다.
 *
 * **문구에 조사를 박아 두면 이름에 따라 틀린다.** 화면 곳곳이
 * `` `「${name}」을 활성화했습니다` `` 처럼 「을」을 박아 놨는데, 이름이 모음으로
 * 끝나면 「알파」을 이 된다. 이름은 사람이 자유롭게 짓는 값이다.
 *
 * **한글로 끝날 때만 고른다.** 「GPT-4」처럼 영문·숫자로 끝나면 읽는 소리를
 * 알 수 없어서(지피티포 → 를), 그때는 둘 다 적는 형태로 물러선다 — 프로젝트
 * 삭제 확인창이 이미 쓰는 방식이다(`을(를) 지웁니다`).
 */

const PAIRS = {
  '을/를': ['을', '를', '을(를)'],
  '이/가': ['이', '가', '이(가)'],
  '은/는': ['은', '는', '은(는)'],
  '와/과': ['과', '와', '와(과)'],
} as const;

export type JosaPair = keyof typeof PAIRS;

export function josa(word: string, pair: JosaPair): string {
  const [withBatchim, withoutBatchim, both] = PAIRS[pair];
  const last = word.trim().slice(-1);
  const code = last.charCodeAt(0);
  // 한글 음절 영역이 아니면 소리를 모른다.
  if (!last || code < 0xac00 || code > 0xd7a3) return both;
  // 종성이 없으면 (코드 - 0xAC00) % 28 === 0.
  return (code - 0xac00) % 28 === 0 ? withoutBatchim : withBatchim;
}
