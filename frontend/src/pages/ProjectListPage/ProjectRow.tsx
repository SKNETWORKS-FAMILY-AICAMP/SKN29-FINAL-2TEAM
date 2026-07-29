import { Badge } from '../../components';
import type { BadgeTone } from '../../components';
import styles from './ProjectRow.module.css';

export interface ProjectRowProps {
  title: string;
  desc?: string;
  statusLabel: string;
  statusTone: BadgeTone;
  date: string;
  progressText: string;
  done?: boolean;
  selected: boolean;
  onSelect: () => void;
}

export function ProjectRow({
  title,
  desc,
  statusLabel,
  statusTone,
  date,
  progressText,
  done = false,
  selected,
  onSelect,
}: ProjectRowProps) {
  return (
    <button
      type="button"
      className={[styles.row, selected ? styles.selected : ''].filter(Boolean).join(' ')}
      onClick={onSelect}
    >
      <div className={styles.colName}>
        <span className={styles.name}>{title}</span>
        {desc && <span className={styles.desc}>{desc}</span>}
      </div>
      <div className={styles.colStatus}>
        <Badge tone={statusTone}>{statusLabel}</Badge>
      </div>
      <div className={styles.colDate}>{date}</div>
      <div className={[styles.colProgress, done ? styles.doneText : ''].filter(Boolean).join(' ')}>
        {progressText}
      </div>
    </button>
  );
}

export default ProjectRow;
