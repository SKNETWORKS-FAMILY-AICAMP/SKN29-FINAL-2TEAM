import type { HTMLAttributes } from 'react';
import styles from './Card.module.css';

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  padding?: 'sm' | 'md' | 'lg';
}

export function Card({ padding = 'md', className, ...rest }: CardProps) {
  const classes = [styles.card, styles[padding], className ?? ''].filter(Boolean).join(' ');

  return <div className={classes} {...rest} />;
}
