import { Badge } from '../../components';
import type { BadgeTone } from '../../components';
import styles from './ProjectRow.module.css';

export interface ProjectRowProps {
  title: string;
  desc?: string;
  statusLabel?: string;
  statusTone?: BadgeTone;
  date: string;
  progressText: string;
  done?: boolean;
  onOpen: () => void;
}

export function ProjectRow({
  title,
  desc,
  statusLabel,
  statusTone,
  date,
  progressText,
  done = false,
  onOpen,
}: ProjectRowProps) {
  return (
    <button type="button" className={styles.row} onClick={onOpen}>
      <div className={styles.colName}>
        <span className={styles.name}>{title}</span>
        {desc && <span className={styles.desc}>{desc}</span>}
      </div>
      {statusLabel && statusTone && (
        <div className={styles.colStatus}>
          <Badge tone={statusTone}>{statusLabel}</Badge>
        </div>
      )}
      <div className={styles.colDate}>{date}</div>
      <div className={[styles.colProgress, done ? styles.doneText : ''].filter(Boolean).join(' ')}>
        {progressText}
      </div>
    </button>
  );
}

export default ProjectRow;
