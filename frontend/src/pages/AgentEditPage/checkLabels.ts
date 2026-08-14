import type { BadgeTone } from '../../components';

/**
 * 도구 검증 결과를 **한 곳에서만** 말한다.
 *
 * 「시험 실행」과 「도구 확인」은 형제 화면이고 겹치는 세 값(OK·FAILED·SIMULATED)의
 * 문구가 토씨까지 같았다 — 복붙이다. 특히 `SIMULATED` 의 「실제로 부르지 않음」은
 * **사용자에게 무엇이 안 일어났는지 알리는 문장**이라, 한쪽만 고쳐지면 같은 상황을
 * 두 화면이 다르게 설명하게 된다(2026-08-13).
 *
 * 각 화면에만 있는 값(`running`·`SKIPPED`)은 여기 두지 않고 그쪽에서 덧붙인다.
 */
export const CHECK_STATUS: Record<'OK' | 'FAILED' | 'SIMULATED', { tone: BadgeTone; label: string }> = {
  OK: { tone: 'success', label: '성공' },
  FAILED: { tone: 'danger', label: '실패' },
  SIMULATED: { tone: 'warning', label: '시뮬레이션 (실제로 부르지 않음)' },
};
