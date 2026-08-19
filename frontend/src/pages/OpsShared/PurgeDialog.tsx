import { useEffect, useState } from 'react';
import { Button } from '../../components/Button/Button';
import { Modal } from '../../components/Modal/Modal';
import type { OpsPurgePreview } from '../../api/opsTeams';
import styles from './OpsPages.module.css';

export interface PurgeDialogProps {
  open: boolean;
  onClose: () => void;
  /** 「팀」·「계정」. 제목과 안내에 그대로 들어간다. */
  kind: string;
  /** 지울 대상의 이름 — 사람이 알아보는 값. */
  label: string;
  /**
   * 사람이 그대로 입력해야 하는 값. 팀은 이름, 계정은 **이메일**이다.
   * 이름은 겹칠 수 있어서(2026-08-19: 팀 둘이 다 「개발팀」이었다) 계정 쪽은
   * 이메일이라야 확인이 확인 구실을 한다.
   */
  confirmValue: string;
  /** 모달을 열 때 서버에서 받아 온 「무엇이 몇 건 사라지는지」. */
  preview: OpsPurgePreview | null;
  busy?: boolean;
  onConfirm: () => void;
}

/**
 * 완전 삭제 확인. **되돌릴 수 없는 것에만 쓴다.**
 *
 * 확인 모달 한 번으로는 실수로 누른 것과 정말 지우려는 것이 구분되지 않는다.
 * 그래서 이름을 그대로 입력받는다 — 옮겨 적는 동안 무엇을 지우는지 한 번 더
 * 읽게 된다. 서버도 같은 값을 다시 검사한다(화면만 막으면 API 직접 호출이
 * 열린 채로 남는다).
 */
export function PurgeDialog({
  open,
  onClose,
  kind,
  label,
  confirmValue,
  preview,
  busy = false,
  onConfirm,
}: PurgeDialogProps) {
  const [typed, setTyped] = useState('');

  // 닫았다 다시 열면 비운다. 안 비우면 앞서 입력한 값이 남아 **버튼이 이미
  // 열린 채로** 모달이 뜬다 — 확인 절차가 통째로 무력해진다.
  useEffect(() => {
    if (open) setTyped('');
  }, [open]);

  const matched = typed.trim() === confirmValue;

  return (
    <Modal
      open={open}
      onClose={() => (busy ? null : onClose())}
      title={`${kind} 완전 삭제`}
      footer={(
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            취소
          </Button>
          <Button variant="danger" onClick={onConfirm} disabled={!matched || busy}>
            {busy ? '삭제하는 중…' : '완전 삭제'}
          </Button>
        </>
      )}
    >
      <div className={styles.formGrid}>
        <p className={styles.purgeWarn}>
          <strong>{label}</strong>을(를) 완전히 삭제합니다. <strong>되돌릴 수 없습니다.</strong>
        </p>

        {/* 무엇이 사라지는지 먼저 보여준다. 0 건인 항목은 서버가 빼고 준다 —
            지워질 것만 보여야 목록이 경고 구실을 한다. */}
        {preview === null ? (
          <p className={styles.inlineEmpty}>확인하는 중…</p>
        ) : preview.items.length === 0 ? (
          <p className={styles.inlineEmpty}>함께 사라지는 데이터가 없습니다.</p>
        ) : (
          <ul className={styles.purgeList}>
            {preview.items.map((item) => (
              <li key={item.label}>
                <span>{item.label}</span>
                <strong>{item.count}건</strong>
              </li>
            ))}
          </ul>
        )}

        <div className={styles.fieldGroup}>
          <label htmlFor="purge-confirm">
            확인을 위해 <code>{confirmValue}</code> 을(를) 입력하세요
          </label>
          <input
            id="purge-confirm"
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
            autoComplete="off"
            placeholder={confirmValue}
          />
        </div>
      </div>
    </Modal>
  );
}
