import { useState } from 'react';
import styles from './WorkloadPanel.module.css';

type Tone = 'danger' | 'info' | 'warning' | 'success';

interface TeamWorkload {
  team: string;
  pct: number;
  tone: Tone;
}

interface TopMember {
  rank: number;
  name: string;
  avatar: string;
  team: string;
  pct: number;
  tone: Tone;
}

const TEAM_WORKLOAD: TeamWorkload[] = [
  { team: '백엔드팀', pct: 88, tone: 'danger' },
  { team: '프론트엔드팀', pct: 65, tone: 'info' },
  { team: '인프라팀', pct: 50, tone: 'warning' },
  { team: '기획&디자인', pct: 30, tone: 'success' },
];

const TOP5: TopMember[] = [
  { rank: 1, name: '박서준', avatar: '박', team: '백엔드팀', pct: 95, tone: 'danger' },
  { rank: 2, name: '이동현', avatar: '이', team: '백엔드팀', pct: 90, tone: 'danger' },
  { rank: 3, name: '김지은', avatar: '김', team: '프론트엔드팀', pct: 82, tone: 'warning' },
  { rank: 4, name: '한유진', avatar: '한', team: '프론트엔드팀', pct: 78, tone: 'warning' },
  { rank: 5, name: '정현우', avatar: '정', team: '인프라팀', pct: 72, tone: 'warning' },
];

const TONE_CLASS: Record<Tone, string> = {
  danger: styles.toneDanger,
  info: styles.toneInfo,
  warning: styles.toneWarning,
  success: styles.toneSuccess,
};

export function WorkloadPanel() {
  const [selectedRanks, setSelectedRanks] = useState<Set<number>>(new Set());

  function toggleRank(rank: number) {
    setSelectedRanks((prev) => {
      const next = new Set(prev);
      if (next.has(rank)) {
        next.delete(rank);
      } else {
        next.add(rank);
      }
      return next;
    });
  }

  return (
    <>
      <div className={styles.card}>
        <p className={styles.cardTitle}>팀별 업무 부하 분석</p>
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
        <p className={styles.cardTitle}>부하도 Top 5</p>
        <div className={styles.top5List}>
          {TOP5.map((member) => {
            const selected = selectedRanks.has(member.rank);
            return (
              <button
                type="button"
                key={member.rank}
                className={[styles.top5Row, selected ? styles.top5RowSelected : ''].filter(Boolean).join(' ')}
                onClick={() => toggleRank(member.rank)}
              >
                <p className={styles.top5Rank}>{member.rank}</p>
                <div className={styles.top5Avatar}>{member.avatar}</div>
                <p className={styles.top5Name}>{member.name}</p>
                <p className={styles.top5Team}>{member.team}</p>
                <div className={styles.top5Progress}>
                  <div className={styles.top5Track}>
                    <div
                      className={[styles.top5Fill, TONE_CLASS[member.tone]].join(' ')}
                      style={{ width: `${member.pct}%` }}
                    />
                  </div>
                  <p className={styles.top5Pct}>{member.pct}%</p>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </>
  );
}

export default WorkloadPanel;
