import type { OpsTone } from '../components';

/**
 * 커넥터 연결 상태를 **한 곳에서만** 말한다.
 *
 * 고객 설정 화면과 운영자 콘솔이 각자 표를 들고 있었고, 이미 서로 다른 말을
 * 하고 있었다 — 같은 `EXPIRED` 를 고객에게는 「만료됨」, 운영자에게는 「확인
 * 필요」로 보여줬다. 운영자가 「확인 필요 상태네요」라고 말하면 고객 화면에는
 * 그런 말이 없다(2026-08-13 지적).
 *
 * 「만료됨」으로 맞춘다 — **무엇을 해야 하는가가 아니라 무슨 일이 일어났는가**를
 * 말하는 쪽이다. 할 일은 어차피 둘 다 재연결이고, 그건 `next_action` 이 따로 말한다.
 *
 * `OpsTone` 은 `BadgeTone` 의 부분집합이라 양쪽 뱃지에 그대로 쓸 수 있다.
 */
export const CONNECTOR_STATUS_LABELS: Record<string, string> = {
  CONNECTED: '연결됨',
  EXPIRED: '만료됨',
  ERROR: '오류',
  // 만료와 가른다 — 「토큰이 낡았다」와 「운영자가 끊었다」는 다음에 할 일이
  // 같아도(다시 연결) 이유가 다르다.
  REVOKED: '해제됨',
};

export const CONNECTOR_STATUS_TONES: Record<string, OpsTone> = {
  CONNECTED: 'success',
  EXPIRED: 'warning',
  ERROR: 'danger',
  REVOKED: 'neutral',
};

/** 모르는 값은 원본을 그대로 보여준다 — 화면이 조용히 감추면 원인을 못 찾는다. */
export function connectorStatusLabel(status: string) {
  return CONNECTOR_STATUS_LABELS[status] ?? status;
}

export function connectorStatusTone(status: string): OpsTone {
  return CONNECTOR_STATUS_TONES[status] ?? 'neutral';
}
