import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { Icon } from '../Icon/Icon';
import type { IconName } from '../Icon/Icon';
import styles from './Toast.module.css';

export type ToastTone = 'success' | 'error' | 'info';

export interface ToastContextValue {
  showToast: (message: string, tone?: ToastTone) => void;
}

interface ToastItem {
  id: number;
  message: string;
  tone: ToastTone;
}

const ToastContext = createContext<ToastContextValue | null>(null);

let toastIdCounter = 0;

const TOAST_ICON: Record<ToastTone, IconName> = {
  success: 'check-circle',
  error: 'circle-x',
  info: 'info',
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const timers = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

  useEffect(() => {
    const timerMap = timers.current;
    return () => {
      timerMap.forEach((timer) => clearTimeout(timer));
      timerMap.clear();
    };
  }, []);

  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
  }, []);

  const showToast = useCallback(
    (message: string, tone: ToastTone = 'info') => {
      const id = ++toastIdCounter;
      setToasts((prev) => [...prev, { id, message, tone }]);
      const timer = setTimeout(() => {
        removeToast(id);
      }, 2500);
      timers.current.set(id, timer);
    },
    [removeToast],
  );

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div className={styles.stack}>
        {toasts.map((toast) => (
          <div key={toast.id} className={[styles.toast, styles[toast.tone]].join(' ')}>
            <Icon name={TOAST_ICON[toast.tone]} size={18} color="#fff" />
            <span>{toast.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return ctx;
}
