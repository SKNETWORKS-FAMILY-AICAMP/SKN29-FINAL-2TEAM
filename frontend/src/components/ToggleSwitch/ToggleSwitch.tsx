import type { ReactNode } from 'react';
import styles from './ToggleSwitch.module.css';

export interface ToggleSwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  label?: ReactNode;
}

export function ToggleSwitch({ checked, onChange, disabled, label }: ToggleSwitchProps) {
  const rootClasses = [styles.root, disabled ? styles.disabled : ''].filter(Boolean).join(' ');
  const trackClasses = [styles.track, checked ? styles.on : ''].filter(Boolean).join(' ');

  return (
    <label className={rootClasses}>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        className={trackClasses}
        onClick={() => {
          if (!disabled) onChange(!checked);
        }}
      >
        <span className={styles.thumb} />
      </button>
      {label && <span className={styles.label}>{label}</span>}
    </label>
  );
}
