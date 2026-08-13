import type { OpsTone } from '../../components';
import type { OpsInviteStatus } from '../../api/opsInvites';

/**
 * 초대 목록과 상세가 **같은 말을 하게 하는 자리.**
 *
 * 상세를 별도 페이지로 가르면서 두 화면이 각자 라벨을 들게 됐다 — 계정 쪽과
 * 같은 이유로 하나로 모은다(`accountLabels.ts` 참고).
 */

/** 필터 드롭다운이 이 키 순서를 그대로 쓴다 — 화면마다 다시 적지 않는다. */
export const STATUS_LABELS: Record<OpsInviteStatus, string> = {
  PENDING: '수락 대기',
  ACCEPTED: '수락 완료',
  EXPIRED: '만료',
  REVOKED: '취소됨',
};

const STATUS_TONES: Record<OpsInviteStatus, OpsTone> = {
  PENDING: 'info',
  ACCEPTED: 'success',
  EXPIRED: 'neutral',
  REVOKED: 'neutral',
};

export function statusLabel(status: OpsInviteStatus) {
  return STATUS_LABELS[status] ?? status;
}

export function statusTone(status: OpsInviteStatus): OpsTone {
  return STATUS_TONES[status] ?? 'neutral';
}
