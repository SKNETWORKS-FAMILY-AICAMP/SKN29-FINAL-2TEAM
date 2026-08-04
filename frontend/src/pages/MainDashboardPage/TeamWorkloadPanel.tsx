import { Link } from 'react-router-dom';
import type { PersonWorkload, WorkloadResult } from '../../api/projects';
import styles from './TeamDashboard.module.css';

const BLOCKED_LABEL: Record<string, string> = {
  NO_SCHEDULE: '근무조건 없음',
  ON_LEAVE: '휴직·휴가',
  NO_EFFECTIVE_CAPACITY: '가용시간 0',
};

const SEGMENT_CLASS = [styles.segmentPrimary, styles.segmentSecondary];

/** 과부하 기준은 팀장이 정한다. 화면이 100을 박아 두면 설정이 거짓말이 된다. */
function rateClass(rate: number | null, overloadPct: number): string {
  if (rate === null) return styles.rateBlocked;
  if (rate > overloadPct) return styles.rateOver;
  // 기준의 80%부터 "곧 찬다"로 본다. 기준이 120이면 96부터다.
  if (rate >= overloadPct * 0.8) return styles.rateHigh;
  return styles.rateNormal;
}

function MemberRow({
  person,
  scale,
  overloadPct,
}: {
  person: PersonWorkload;
  scale: number;
  overloadPct: number;
}) {
  const blocked = person.blocked_reason !== null;

  return (
    <div className={styles.memberRow}>
      <div className={styles.memberHead}>
        <span className={styles.memberName}>{person.name ?? person.person_id}</span>
        {person.job_role && <span className={styles.memberRole}>{person.job_role}</span>}
        <span className={styles.memberHours}>
          {blocked ? `${person.current_allocation}h` : `${person.current_allocation} / ${person.effective_capacity}h`}
        </span>
        <span className={`${styles.memberRate} ${rateClass(person.load_rate, overloadPct)}`}>
          {blocked
            ? BLOCKED_LABEL[person.blocked_reason!] ?? person.blocked_reason
            : `${person.load_rate}%`}
        </span>
      </div>

      <div className={styles.barWrap}>
        <div className={styles.track}>
          {/* 프로젝트별로 쌓는다 — 한 칸만 보면 90%인데 합치면 100%를 넘는 것이 보인다. */}
          {!blocked &&
            person.by_project.map((entry, index) => (
              <div
                key={entry.project_key}
                className={`${styles.segment} ${SEGMENT_CLASS[index % SEGMENT_CLASS.length]}`}
                style={{ width: `${((entry.load_rate ?? 0) / scale) * 100}%` }}
                title={`${entry.project_key} ${entry.hours}h (${entry.load_rate}%)`}
              />
            ))}
        </div>
        <div className={styles.fullMark} style={{ left: `${(overloadPct / scale) * 100}%` }} />
      </div>

      {!blocked && person.by_project.length > 0 && (
        <div className={styles.chips}>
          {person.by_project.map((entry, index) => (
            <span key={entry.project_key} className={styles.chip}>
              <span className={`${styles.legendDot} ${SEGMENT_CLASS[index % SEGMENT_CLASS.length]}`} />
              {entry.project_name || entry.project_key} {entry.hours}h ({entry.load_rate}%)
            </span>
          ))}
          {person.missing_estimate_count > 0 && (
            <span className={styles.chip}>공수 미입력 {person.missing_estimate_count}건</span>
          )}
        </div>
      )}
    </div>
  );
}

export function TeamWorkloadPanel({ workload }: { workload: WorkloadResult }) {
  // 100%를 넘는 사람도 얼마나 넘었는지 보이도록 축을 최대치까지 늘린다.
  // 팀이 정한 기준. 화면이 100을 박아 두면 설정이 거짓말이 된다.
  const overloadPct = workload.overload_pct ?? 100;
  const maxRate = Math.max(overloadPct, ...workload.people.map((p) => p.load_rate ?? 0));
  const scale = Math.ceil(maxRate / 10) * 10;

  // 키로 묶되 표시는 이름으로 한다. 이름이 없는 예전 소스는 키가 그대로 온다.
  const projectNames = new Map<string, string>();
  for (const person of workload.people) {
    for (const entry of person.by_project) {
      projectNames.set(entry.project_key, entry.project_name || entry.project_key);
    }
  }
  const projectKeys = [...projectNames.keys()].sort();

  const sorted = [...workload.people].sort((a, b) => (b.load_rate ?? -1) - (a.load_rate ?? -1));

  return (
    <div className={styles.card}>
      <div className={styles.cardHeader}>
        <p className={styles.cardTitle}>팀원 업무 부하</p>
        <Link to="/tasks/workload" className={styles.cardLink}>
          기간 바꿔 보기 →
        </Link>
      </div>
      <p className={styles.cardNote}>
        {workload.period_start} ~ {workload.period_end} · 근무일 {workload.workdays}일 · 세로선이 {overloadPct}%
      </p>

      {projectKeys.length > 0 && (
        <div className={styles.legend}>
          {projectKeys.map((key, index) => (
            <span key={key} className={styles.legendItem}>
              <span className={`${styles.legendDot} ${SEGMENT_CLASS[index % SEGMENT_CLASS.length]}`} />
              {projectNames.get(key)}
            </span>
          ))}
        </div>
      )}

      <div className={styles.memberList}>
        {sorted.map((person) => (
          <MemberRow
            key={person.person_id}
            person={person}
            scale={scale}
            overloadPct={overloadPct}
          />
        ))}
        {sorted.length === 0 && <p className={styles.empty}>팀원이 없습니다.</p>}
      </div>
    </div>
  );
}

export default TeamWorkloadPanel;
