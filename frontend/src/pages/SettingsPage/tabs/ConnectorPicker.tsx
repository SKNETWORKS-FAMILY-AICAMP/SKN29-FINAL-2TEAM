import { BrandIcon, Icon, Modal } from '../../../components';
import type { BrandName, IconName } from '../../../components';
import styles from './ConnectorPicker.module.css';

/**
 * 자리에 무엇을 꽂을지 고르는 모달.
 *
 * **문장 대신 구조로 말한다.** 줄마다 「지금은 Google Drive를 지원합니다」 같은
 * 설명을 달아 두었더니 문구가 길어지고, 그래도 「이 셋이 필수인가」가 안 풀렸다
 * (2026-08-12 PM 지적). 자리를 누르면 후보가 카드로 뜨는 편이 훨씬 짧게 같은
 * 말을 한다 — **자리가 있고 거기 꽂는 것이 있다.**
 *
 * 안 되는 것도 흐리게 보여 준다. 카드가 하나뿐이면 왜 고르게 하는지 알 수
 * 없고, 자리라는 개념도 안 드러난다. 대신 **「아직 지원하지 않습니다」를 반드시
 * 붙인다** — 곧 된다고 읽히면 그건 지키지 못할 약속이다.
 */

export interface PickerOption {
  id: string;
  label: string;
  /**
   * 로고가 있으면 로고를 쓴다 — 제품을 고르는 자리라 이름보다 마크가 먼저 읽힌다.
   * 예전에는 Notion 과 Confluence 가 똑같은 `file-text` 였다(2026-08-13 PM 지적).
   */
  brand?: BrandName;
  /** 로고가 없을 때 쓸 일반 글리프(예시 데이터·사내 시스템·SharePoint·Workday). */
  icon: IconName;
  /** 지금 붙일 수 있는가. `false` 면 흐리게, 누를 수 없다. */
  available: boolean;
  /** 이 자리에 지금 꽂혀 있는 것인가. */
  current?: boolean;
}

export function ConnectorPicker({
  open,
  onClose,
  title,
  options,
  onPick,
  busy = false,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  options: PickerOption[];
  onPick: (id: string) => void;
  busy?: boolean;
}) {
  return (
    <Modal open={open} onClose={onClose} title={title} width={460}>
      <div className={styles.grid}>
        {options.map((option) => (
          <button
            key={option.id}
            type="button"
            className={option.available ? styles.card : styles.cardOff}
            disabled={!option.available || busy}
            onClick={() => onPick(option.id)}
          >
            {option.brand ? (
              <BrandIcon name={option.brand} size={22} muted={!option.available} />
            ) : (
              <Icon
                name={option.icon}
                size={22}
                color={option.available ? 'var(--color-primary)' : 'var(--color-placeholder)'}
              />
            )}
            <span className={styles.name}>{option.label}</span>
            {option.current && <span className={styles.tagNow}>지금 연결됨</span>}
            {!option.available && <span className={styles.tagOff}>아직 지원하지 않습니다</span>}
          </button>
        ))}
      </div>
    </Modal>
  );
}
