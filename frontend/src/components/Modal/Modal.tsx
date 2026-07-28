import { useEffect, useId } from 'react';
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
}

export function Modal({ open, onClose, title, children, width = 480, footer }: ModalProps) {
  const titleId = useId();

  useEffect(() => {
    if (!open) return;

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onClose();
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const dialogStyle: CSSProperties = { width };

  return (
    <div className={styles.backdrop} onClick={onClose}>
      <div
        className={styles.dialog}
        style={dialogStyle}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        onClick={(event) => event.stopPropagation()}
      >
        <button type="button" className={styles.close} aria-label="닫기" onClick={onClose}>
          <Icon name="x" size={18} />
        </button>
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
