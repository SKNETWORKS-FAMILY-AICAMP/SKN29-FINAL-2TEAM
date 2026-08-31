import { useEffect, useId, useRef, useState } from 'react';
import type { ReactNode, CSSProperties, KeyboardEvent as ReactKeyboardEvent } from 'react';
import { createPortal } from 'react-dom';
import { Icon } from '../Icon/Icon';
import styles from './Modal.module.css';

let bodyScrollLockCount = 0;
let previousBodyOverflow = '';
let previousBodyPaddingRight = '';

function lockBodyScroll() {
  if (bodyScrollLockCount === 0) {
    previousBodyOverflow = document.body.style.overflow;
    previousBodyPaddingRight = document.body.style.paddingRight;
    const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;
    if (scrollbarWidth > 0) {
      const currentPadding = Number.parseFloat(window.getComputedStyle(document.body).paddingRight) || 0;
      document.body.style.paddingRight = `${currentPadding + scrollbarWidth}px`;
    }
    document.body.style.overflow = 'hidden';
  }
  bodyScrollLockCount += 1;
}

function unlockBodyScroll() {
  bodyScrollLockCount = Math.max(0, bodyScrollLockCount - 1);
  if (bodyScrollLockCount > 0) return;
  document.body.style.overflow = previousBodyOverflow;
  document.body.style.paddingRight = previousBodyPaddingRight;
}

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
  const dialogRef = useRef<HTMLDivElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
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

  /* 모달이 열리면 키보드 위치도 모달 안으로 옮기고, 닫히면 호출한 조작으로
     돌려놓는다. `aria-modal`만 붙이고 포커스를 배경에 남겨 두면 스크린리더는
     모달이라고 말하면서 실제 Tab은 뒤 페이지를 도는 모순이 생긴다. */
  useEffect(() => {
    if (!open || !rendered) return;

    const previous = document.activeElement;
    returnFocusRef.current = previous instanceof HTMLElement ? previous : null;
    const frame = window.requestAnimationFrame(() => {
      const dialog = dialogRef.current;
      if (!dialog) return;
      const first =
        dialog.querySelector<HTMLElement>('[autofocus]') ??
        dialog.querySelector<HTMLElement>(
          'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        );
      (first ?? dialog).focus();
    });

    return () => {
      window.cancelAnimationFrame(frame);
      const target = returnFocusRef.current;
      if (target?.isConnected) {
        window.requestAnimationFrame(() => target.focus());
      }
    };
  }, [open, rendered]);

  useEffect(() => {
    if (!rendered) return;
    lockBodyScroll();
    return unlockBodyScroll;
  }, [rendered]);

  if (!rendered) return null;

  function handleDialogKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape' && dismissible) {
      event.preventDefault();
      event.stopPropagation();
      onClose();
      return;
    }
    if (event.key !== 'Tab') return;

    const dialog = dialogRef.current;
    if (!dialog) return;
    const focusable = Array.from(
      dialog.querySelectorAll<HTMLElement>(
        'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ),
    ).filter((element) => element.getClientRects().length > 0 && element.getAttribute('aria-hidden') !== 'true');

    if (focusable.length === 0) {
      event.preventDefault();
      dialog.focus();
      return;
    }

    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const active = document.activeElement;
    if (event.shiftKey && (active === first || !dialog.contains(active))) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (active === last || !dialog.contains(active))) {
      event.preventDefault();
      first.focus();
    }
  }

  const dialogStyle: CSSProperties = { width };

  const modal = (
    <div
      className={`${styles.backdrop} ${closing ? styles.closing : styles.opening}`}
      onClick={open && dismissible ? onClose : undefined}
    >
      <div
        ref={dialogRef}
        className={styles.dialog}
        style={dialogStyle}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        tabIndex={-1}
        onKeyDown={handleDialogKeyDown}
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

  return createPortal(modal, document.body);
}
