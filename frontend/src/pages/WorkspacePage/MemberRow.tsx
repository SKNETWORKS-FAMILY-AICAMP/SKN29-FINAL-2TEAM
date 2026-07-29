import type { MouseEvent } from 'react';
import { Checkbox } from '../../components';
import styles from './MemberRow.module.css';

export type MemberStatus = 'available' | 'busy' | 'overloaded';

export interface WorkspaceMember {
  id: string;
  name: string;
  role: string;
  team: string | null;
  status: MemberStatus;
  avatarColor: string;
  avatarInitial: string;
}

const STATUS_LABEL: Record<MemberStatus, string> = {
  available: '가용',
  busy: '작업중',
  overloaded: '과부하',
};

const STATUS_CLASS: Record<MemberStatus, string> = {
  available: styles.statusAvailable,
  busy: styles.statusBusy,
  overloaded: styles.statusOverloaded,
};

interface MemberRowProps {
  member: WorkspaceMember;
  checked: boolean;
  onToggle: (id: string) => void;
}

export function MemberRow({ member, checked, onToggle }: MemberRowProps) {
  function handleCheckboxWrapperClick(event: MouseEvent<HTMLDivElement>) {
    event.stopPropagation();
  }

  return (
    <button
      type="button"
      className={[styles.row, checked ? styles.checked : ''].filter(Boolean).join(' ')}
      onClick={() => onToggle(member.id)}
    >
      <div className={styles.checkboxCell} onClick={handleCheckboxWrapperClick}>
        <Checkbox checked={checked} onChange={() => onToggle(member.id)} />
      </div>
      <div className={styles.name}>
        <span className={styles.nameText}>{member.name}</span>
      </div>
      <div className={styles.role}>
        <span className={styles.roleText}>{member.role}</span>
      </div>
      <div className={styles.team}>
        <span className={[styles.teamText, !member.team ? styles.dash : ''].filter(Boolean).join(' ')}>
          {member.team ?? '-'}
        </span>
      </div>
      <div className={styles.status}>
        <span className={[styles.statusText, STATUS_CLASS[member.status]].join(' ')}>
          {STATUS_LABEL[member.status]}
        </span>
      </div>
    </button>
  );
}

export default MemberRow;
