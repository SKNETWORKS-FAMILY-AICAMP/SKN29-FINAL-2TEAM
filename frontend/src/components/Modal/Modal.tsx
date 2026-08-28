import { useEffect, useId, useState } from 'react';
import type { ReactNode, CSSProperties } from 'react';
import { Icon } from '../Icon/Icon';
import styles from './Modal.module.css';

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
  width?: number;
  footer?: ReactNode;
  /**
   * 닫을 수 있는가. 진행 중인 작업을 보여주는 모달은 `false`로 둔다 — 닫아도
   * 요청은 계속 날아가므로, 닫기를 열어 두면 끝난 줄 알고 다시 누르게 된다.
   */
  dismissible?: boolean;
}

export function Modal({
  open,
  onClose,
  title,
  children,
  width = 480,
  footer,
  dismissible = true,
}: ModalProps) {
  const titleId = useId();
  const [rendered, setRendered] = useState(open);
  const [closing, setClosing] = useState(false);

  useEffect(() => {
    if (open) {
      setRendered(true);
      setClosing(false);
      return;
    }
    if (!rendered) return;

    setClosing(true);
    const timer = window.setTimeout(() => {
      setRendered(false);
      setClosing(false);
    }, 160);
    return () => window.clearTimeout(timer);
  }, [open, rendered]);

  useEffect(() => {
    if (!open || !dismissible) return;

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onClose();
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose, dismissible]);

  if (!rendered) return null;

  const dialogStyle: CSSProperties = { width };

  return (
    <div
      className={`${styles.backdrop} ${closing ? styles.closing : styles.opening}`}
      onClick={open && dismissible ? onClose : undefined}
    >
      <div
        className={styles.dialog}
        style={dialogStyle}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        onClick={(event) => event.stopPropagation()}
      >
        {dismissible && (
          <button type="button" className={styles.close} aria-label="닫기" onClick={onClose}>
            <Icon name="x" size={18} />
          </button>
        )}
        {title && (
          <h2 id={titleId} className={styles.title}>
            {title}
          </h2>
        )}
        <div className={styles.body}>{children}</div>
        {footer && <div className={styles.footer}>{footer}</div>}
      </div>
    </div>
  );
}
