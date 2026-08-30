import type { OpsTone } from '../../components';
import type { OpsMappingStatus } from '../../api/opsAccounts';

/**
 * 계정 목록과 상세가 **같은 말을 하게 하는 자리.**
 *
 * 상세를 별도 페이지로 가르면서 두 화면이 각자 라벨을 들게 됐다. 그대로 두면
 * 언젠가 한쪽만 고쳐져 목록에서는 「잠김」인 계정이 상세에서는 다른 말이 된다 —
 * 이 프로젝트가 모델 목록에서 이미 한 번 겪은 일이다(2026-08-13).
 */

const STATUS_LABELS: Record<string, string> = {
  ACTIVE: '활성',
  LOCKED: '잠김',
  WITHDRAWN: '탈퇴',
};

const STATUS_TONES: Record<string, OpsTone> = {
  ACTIVE: 'success',
  LOCKED: 'danger',
  WITHDRAWN: 'neutral',
};

export const MAPPING_LABELS: Record<OpsMappingStatus, string> = {
  UNMAPPED: '미연결',
  LINKED: '연결됨',
  DUPLICATE: '중복 연결',
};

export const MAPPING_TONES: Record<OpsMappingStatus, OpsTone> = {
  UNMAPPED: 'neutral',
  LINKED: 'success',
  DUPLICATE: 'danger',
};

/** 모르는 값은 원본을 그대로 보여준다 — 화면이 조용히 감추면 원인을 못 찾는다. */
export function statusLabel(status: string) {
  return STATUS_LABELS[status] ?? status;
}

export function statusTone(status: string): OpsTone {
  return STATUS_TONES[status] ?? 'neutral';
}

/**
 * 커넥터 종류를 사람 말로. **원본 값을 그대로 뿌리지 않는다.**
 *
 * 계정 화면이 `GOOGLE_DRIVE · JIRA` 를 그대로 보여주고 있었다 — 운영자도 읽을
 * 수는 있지만 화면에 DB 값이 새는 것이고, 감사 로그 라벨을 만든 것과 같은
 * 이유로 여기도 옮긴다(2026-08-13).
 *
 * **표는 `connectorLabels` 것을 빌린다.** 같은 매핑을 여기 한 벌 더 두고 있었다 —
 * 이 폴더가 「같은 말을 하게 하는 자리」인데 그 안에서 갈라져 있었다.
 */
import { TYPE_LABELS } from './connectorLabels';

export function serviceLabels(services: string[]): string {
  return services.map((s) => TYPE_LABELS[s] ?? s).join(' · ');
}
