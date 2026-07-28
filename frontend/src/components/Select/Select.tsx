import type { SelectHTMLAttributes } from 'react';
import styles from './Select.module.css';

export interface SelectOption {
  label: string;
  value: string;
}

export interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'size'> {
  options: SelectOption[];
  size?: 'sm' | 'md';
}

export function Select({ options, size = 'md', className, ...rest }: SelectProps) {
  const classes = [styles.select, styles[size], className ?? ''].filter(Boolean).join(' ');

  return (
    <select className={classes} {...rest}>
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}
