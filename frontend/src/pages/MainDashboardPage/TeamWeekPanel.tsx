import type { PersonWorkload, WorkloadResult } from '../../api/projects';
import styles from './TeamDashboard.module.css';

const BLOCKED_LABEL: Record<string, string> = {
  NO_SCHEDULE: '근무조건 없음',
  ON_LEAVE: '휴직',
  NO_EFFECTIVE_CAPACITY: '가용 없음',
};

function label(iso: string): string {
  return iso.slice(5).replace('-', '/');
}

/** 한 칸의 색. 용량을 모르면 칠하지 않는다 — 모르는 것을 여유로 보이게 하지 않는다. */
function cellClass(hours: number, capacity: number | null): string {
  if (capacity === null || capacity <= 0) return styles.cellUnknown;
  if (hours === 0) return styles.cellEmpty;
  const ratio = hours / capacity;
  if (ratio > 1) return styles.cellOver;
  if (ratio >= 0.8) return styles.cellHigh;
  return styles.cellNormal;
}

function PersonWeeks({ person }: { person: PersonWorkload }) {
  const total =
    Math.round((person.current_allocation + person.unscheduled_backlog_hours) * 10) / 10;

  return (
    <div className={styles.weekRow}>
      <div className={styles.weekName}>
        <span className={styles.memberName}>{person.name ?? person.person_id}</span>
        {person.job_role && <span className={styles.memberRole}>{person.job_role}</span>}
      </div>

      {person.by_week.map((week) => (
        <span
          key={week.week_start}
          className={`${styles.cell} ${cellClass(week.hours, week.capacity)}`}
          title={`${label(week.week_start)} 주 · ${week.hours}h${
            week.capacity === null ? '' : ` / 가용 ${week.capacity}h`
          }`}
        >
          {week.hours === 0 ? '·' : Math.round(week.hours)}
        </span>
      ))}

      {/* 조회 기간 뒤 마감은 칸이 없다. 총량이 어긋나 보이지 않도록 따로 적는다. */}
      <span className={styles.weekLater}>
        {person.later_hours > 0 ? `+${Math.round(person.later_hours)}h` : '—'}
      </span>

      <span className={styles.weekTotal}>
        {person.blocked_reason ? (
          <span className={styles.weekBlocked}>
            {BLOCKED_LABEL[person.blocked_reason] ?? person.blocked_reason}
          </span>
        ) : (
          <>
            {Math.round(total)}h
            {person.runway_days !== null && (
              <span className={styles.weekRunway}>{person.runway_days}일치</span>
            )}
          </>
        )}
      </span>
    </div>
  );
}

/**
 * 인원별 주차별 업무량.
 *
 * 부하율 막대를 대신한다. 막대는 "이 기간 평균 몇 %"만 말해서, 122.5%가 사실은
 * 셋째 주에 100h가 겹친 것이라는 사실이 보이지 않았다. 마감이 속한 주에 공수를
 * 얹어 두면 **총량과 몰리는 시점이 한 그림에** 들어온다.
 *
 * 업무를 며칠에 걸쳐 어떻게 쪼갤지는 우리가 알 수 없다. 아는 것은 "그때까지
 * 끝나야 한다"뿐이라 마감 주에 통째로 얹는다.
 */
export function TeamWeekPanel({ workload }: { workload: WorkloadResult }) {
  const weeks = workload.people[0]?.by_week ?? [];
  const people = [...workload.people].sort(
    (a, b) =>
      b.current_allocation + b.unscheduled_backlog_hours -
      (a.current_allocation + a.unscheduled_backlog_hours),
  );

  return (
    <div className={styles.card} style={{ ["--weeks" as string]: weeks.length }}>
      <div className={styles.cardHeader}>
        <p className={styles.cardTitle}>인원별 주차별 업무량</p>
        <span className={styles.cardNote}>마감이 속한 주 기준 · 칸 안은 시간</span>
      </div>

      <div className={styles.weekHead}>
        <span />
        {weeks.map((week) => (
          <span key={week.week_start} className={styles.weekLabel}>
            {label(week.week_start)}
          </span>
        ))}
        <span className={styles.weekLabel}>이후</span>
        <span className={styles.weekLabel}>총량</span>
      </div>

      <div className={styles.weekList}>
        {people.map((person) => (
          <PersonWeeks key={person.person_id} person={person} />
        ))}
        {people.length === 0 && <p className={styles.empty}>팀원이 없습니다.</p>}
      </div>
    </div>
  );
}

export default TeamWeekPanel;
