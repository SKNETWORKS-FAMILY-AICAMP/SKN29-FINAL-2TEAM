import type { ReactNode } from 'react';
import { Icon } from '../Icon/Icon';
import styles from './Checkbox.module.css';

export interface CheckboxProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label?: ReactNode;
  disabled?: boolean;
  className?: string;
}

export function Checkbox({ checked, onChange, label, disabled, className }: CheckboxProps) {
  const rootClasses = [styles.root, disabled ? styles.disabled : '', className ?? '']
    .filter(Boolean)
    .join(' ');
  const boxClasses = [styles.box, checked ? styles.checked : ''].filter(Boolean).join(' ');

  return (
    <label className={rootClasses}>
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
        className={styles.nativeInput}
      />
      <span className={boxClasses} aria-hidden="true">
        {checked && <Icon name="check" size={13} color="#fff" />}
      </span>
      {label && <span className={styles.label}>{label}</span>}
    </label>
  );
}
