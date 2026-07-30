/** part/total을 백분율로 계산한다. total이 0이면 NaN 대신 0을 돌려준다. */
export function pct(part: number, total: number): number {
  return total > 0 ? (part / total) * 100 : 0;
}
