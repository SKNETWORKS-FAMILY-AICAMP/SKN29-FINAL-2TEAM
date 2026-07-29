import type { MouseEvent } from 'react';
import { Badge, Checkbox } from '../../components';
import type { BadgeTone } from '../../components';
import styles from './MemberRow.module.css';

export type MemberStatus = 'available' | 'busy' | 'overloaded' | 'unknown';

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
  unknown: '확인 필요',
};

const STATUS_TONE: Record<MemberStatus, BadgeTone> = {
  available: 'success',
  busy: 'warning',
  overloaded: 'danger',
  unknown: 'neutral',
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
      <div className={styles.avatarCell}>
        <div className={styles.avatar} style={{ background: member.avatarColor }}>
          {member.avatarInitial}
        </div>
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
        <Badge tone={STATUS_TONE[member.status]}>{STATUS_LABEL[member.status]}</Badge>
      </div>
    </button>
  );
}

export default MemberRow;
