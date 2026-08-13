import type { OpsTone } from '../../components';

/**
 * 연결 서비스 목록과 상세가 **같은 말을 하게 하는 자리.**
 *
 * 계정·초대와 같은 이유다 — 상세를 별도 페이지로 가르면 두 화면이 각자 라벨을
 * 들게 되고, 언젠가 한쪽만 고쳐진다(2026-08-13 PM).
 *
 * People DB·등록 모델은 애초에 API 응답에 없다(`OpsConnectorRepository`) —
 * 본인 확인용 내부 커넥터와, 표만 빌려 쓰는 등록 모델이라 「연결 서비스」가 아니다.
 */

const TYPE_LABELS: Record<string, string> = {
  GOOGLE_DRIVE: '구글 드라이브',
  JIRA: 'Jira',
};

const STATUS_LABELS: Record<string, string> = {
  CONNECTED: '연결됨',
  EXPIRED: '확인 필요',
  ERROR: '오류',
  // 만료와 굳이 가른다 — 고객이 「토큰이 만료됐나 보다」와 「운영자가 끊었다」를
  // 구별할 수 있어야 한다.
  REVOKED: '해제됨',
};

const STATUS_TONES: Record<string, OpsTone> = {
  CONNECTED: 'success',
  EXPIRED: 'warning',
  ERROR: 'danger',
  REVOKED: 'neutral',
};

/** 모르는 값은 원본을 그대로 보여준다 — 화면이 조용히 감추면 원인을 못 찾는다. */
export function typeLabel(type: string) {
  return TYPE_LABELS[type] ?? type;
}

export function statusLabel(status: string) {
  return STATUS_LABELS[status] ?? status;
}

export function statusTone(status: string): OpsTone {
  return STATUS_TONES[status] ?? 'neutral';
}

/** 이 연결이 끊기면 무엇이 서는가. 유형마다 매달린 것이 다르다. */
export function sourceNoun(type: string) {
  return type === 'GOOGLE_DRIVE' ? '읽던 폴더' : '연결된 Jira 프로젝트';
}

export function formatConnectedAt(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(date.getMonth() + 1)}.${p(date.getDate())} ${p(date.getHours())}:${p(date.getMinutes())}`;
}
