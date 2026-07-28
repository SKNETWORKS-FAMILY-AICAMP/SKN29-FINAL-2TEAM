import { Icon } from '../Icon/Icon';
import styles from './StepIndicator.module.css';

export interface StepIndicatorProps {
  steps: string[];
  currentIndex: number;
}

export function StepIndicator({ steps, currentIndex }: StepIndicatorProps) {
  return (
    <ol className={styles.root}>
      {steps.map((step, index) => {
        const state = index < currentIndex ? 'done' : index === currentIndex ? 'active' : 'upcoming';
        const circleClasses = [styles.circle, styles[state]].join(' ');
        const labelClasses = [styles.label, styles[state]].join(' ');

        return (
          <li key={step} className={styles.item}>
            <span className={circleClasses}>
              {state === 'done' ? <Icon name="check" size={12} color="#fff" /> : index + 1}
            </span>
            <span className={labelClasses}>{step}</span>
            {index < steps.length - 1 && (
              <Icon name="chevron-right" size={14} className={styles.chevron} />
            )}
          </li>
        );
      })}
    </ol>
  );
}
