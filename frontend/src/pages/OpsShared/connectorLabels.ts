/**
 * 연결 서비스 목록과 상세가 **같은 말을 하게 하는 자리.**
 *
 * 계정·초대와 같은 이유다 — 상세를 별도 페이지로 가르면 두 화면이 각자 라벨을
 * 들게 되고, 언젠가 한쪽만 고쳐진다(2026-08-13 PM).
 *
 * **상태 라벨은 여기 없다.** 고객 설정 화면도 같은 상태를 보여주는데 각자 표를
 * 들고 있다가 이미 다른 말을 하고 있었다(`EXPIRED` 가 고객에게는 「만료됨」,
 * 운영자에게는 「확인 필요」였다). `data/connectorStatus.ts` 한 곳으로 옮겼다 —
 * 여기 남은 것은 운영자 화면에만 필요한 것들이다.
 *
 * People DB·등록 모델은 애초에 API 응답에 없다(`OpsConnectorRepository`) —
 * 본인 확인용 내부 커넥터와, 표만 빌려 쓰는 등록 모델이라 「연결 서비스」가 아니다.
 */

export {
  connectorStatusLabel as statusLabel,
  connectorStatusTone as statusTone,
} from '../../data/connectorStatus';

const TYPE_LABELS: Record<string, string> = {
  GOOGLE_DRIVE: '구글 드라이브',
  JIRA: 'Jira',
};

/** 모르는 값은 원본을 그대로 보여준다 — 화면이 조용히 감추면 원인을 못 찾는다. */
export function typeLabel(type: string) {
  return TYPE_LABELS[type] ?? type;
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
