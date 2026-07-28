import type { ReactNode } from 'react';
import styles from './Badge.module.css';

export type BadgeTone = 'neutral' | 'success' | 'warning' | 'danger' | 'info' | 'primary';

export interface BadgeProps {
  tone?: BadgeTone;
  dot?: boolean;
  children: ReactNode;
  className?: string;
}

export function Badge({ tone = 'neutral', dot = false, children, className }: BadgeProps) {
  const classes = [styles.badge, styles[tone], className ?? ''].filter(Boolean).join(' ');

  return (
    <span className={classes}>
      {dot && <span className={styles.dot} aria-hidden="true" />}
      {children}
    </span>
  );
}
