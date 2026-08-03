import { Link } from 'react-router-dom';
import styles from './WorkloadPanel.module.css';

type Tone = 'danger' | 'info' | 'warning' | 'success';

interface TeamWorkload {
  team: string;
  pct: number;
  tone: Tone;
}

interface LeaveMember {
  id: string;
  name: string;
  team: string;
  dateLabel: string;
}

interface LeaveSection {
  key: string;
  label: string;
  items: LeaveMember[];
  emptyText: string;
}

const TEAM_WORKLOAD: TeamWorkload[] = [
  { team: '백엔드팀', pct: 88, tone: 'danger' },
  { team: '프론트엔드팀', pct: 65, tone: 'info' },
  { team: '인프라팀', pct: 50, tone: 'warning' },
  { team: '기획&디자인', pct: 30, tone: 'success' },
];

const CURRENT_LEAVE: LeaveMember[] = [];
const UPCOMING_LEAVE: LeaveMember[] = [];
const RETURNING_LEAVE: LeaveMember[] = [];

const LEAVE_SECTIONS: LeaveSection[] = [
  { key: 'current', label: '현재 휴가자', items: CURRENT_LEAVE, emptyText: '현재 휴가 중인 팀원이 없습니다.' },
  { key: 'upcoming', label: '이번주 휴가 예정자', items: UPCOMING_LEAVE, emptyText: '이번주 휴가 예정인 팀원이 없습니다.' },
  { key: 'returning', label: '휴가 복귀 예정자', items: RETURNING_LEAVE, emptyText: '휴가 복귀 예정인 팀원이 없습니다.' },
];

const TONE_CLASS: Record<Tone, string> = {
  danger: styles.toneDanger,
  info: styles.toneInfo,
  warning: styles.toneWarning,
  success: styles.toneSuccess,
};

export function WorkloadPanel() {
  return (
    <>
      <div className={styles.card}>
        {/*
          이 카드의 팀별 수치는 아직 목업이다. 실제 Jira·HR 데이터로 계산한
          사람별 부하는 아래 링크의 화면에 있다.
        */}
        <div className={styles.cardHeader}>
          <p className={styles.cardTitle}>팀별 업무 부하 분석</p>
          <Link to="/tasks/workload" className={styles.cardLink}>
            사람별 부하 보기 →
          </Link>
        </div>
        <div className={styles.workloadList}>
          {TEAM_WORKLOAD.map((item) => (
            <div key={item.team} className={styles.workloadRow}>
              <p className={styles.workloadLabel}>{item.team}</p>
              <div className={styles.workloadBarWrap}>
                <div className={styles.workloadTrack}>
                  <div
                    className={[styles.workloadFill, TONE_CLASS[item.tone]].join(' ')}
                    style={{ width: `${item.pct}%` }}
                  />
                </div>
                <p className={styles.workloadPct}>{item.pct}%</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className={styles.card}>
        <p className={styles.cardTitle}>휴가자 현황</p>
        <div className={styles.leaveSections}>
          {LEAVE_SECTIONS.map((section) => (
            <div key={section.key} className={styles.leaveSection}>
              <div className={styles.leaveSectionHeader}>
                <p className={styles.leaveSectionLabel}>{section.label}</p>
                <span className={styles.leaveSectionCount}>{section.items.length}명</span>
              </div>
              <div className={styles.leaveList}>
                {section.items.length === 0 && <p className={styles.leaveEmpty}>{section.emptyText}</p>}
                {section.items.map((member) => (
                  <div key={member.id} className={styles.leaveRow}>
                    <div className={styles.leaveAvatar}>{member.name.charAt(0)}</div>
                    <p className={styles.leaveName}>{member.name}</p>
                    <p className={styles.leaveTeam}>{member.team}</p>
                    <p className={styles.leaveDate}>{member.dateLabel}</p>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

export default WorkloadPanel;
