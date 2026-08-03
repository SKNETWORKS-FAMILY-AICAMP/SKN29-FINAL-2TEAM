import type { WorkloadResult } from '../../api/projects';
import styles from './TeamDashboard.module.css';

const SEGMENT_CLASS = [styles.segmentPrimary, styles.segmentSecondary];

/**
 * 프로젝트별로 배정된 잔여 공수와 그 비중.
 *
 * 인원별 카드와 같은 데이터를 다른 방향으로 자른 것이다. 인원 기준으로는
 * "임준이 과부하"지만 프로젝트 기준으로는 "KAN에 80%가 몰려 있다"가 보인다 —
 * 배정을 바꿀지 프로젝트를 미룰지는 다른 판단이라 둘 다 필요하다.
 */
export function TeamProjectPanel({ workload }: { workload: WorkloadResult }) {
  const totals = new Map<string, { name: string; hours: number }>();
  for (const person of workload.people) {
    for (const entry of person.by_project) {
      const current = totals.get(entry.project_key);
      totals.set(entry.project_key, {
        name: entry.project_name || entry.project_key,
        hours: (current?.hours ?? 0) + entry.hours,
      });
    }
  }

  const rows = [...totals.entries()].sort((a, b) => b[1].hours - a[1].hours);
  const sum = rows.reduce((acc, [, entry]) => acc + entry.hours, 0);
  const capacity = workload.people.reduce(
    (acc, person) => acc + (person.effective_capacity ?? 0),
    0,
  );

  return (
    <div className={styles.card}>
      <div className={styles.cardHeader}>
        <p className={styles.cardTitle}>프로젝트별 업무량</p>
      </div>
      <p className={styles.cardNote}>
        {sum > 0
          ? `배정 공수 ${Math.round(sum)}h · 팀 가용용량 ${Math.round(capacity)}h`
          : '집계할 업무가 없습니다.'}
      </p>

      <div className={styles.memberList}>
        {rows.map(([key, entry], index) => (
          <div key={key} className={styles.projectRow}>
            <div className={styles.projectHead}>
              <span className={styles.projectKey}>{entry.name}</span>
              {entry.name !== key && <span className={styles.memberRole}>{key}</span>}
              <span className={styles.projectHours}>
                {entry.hours}h · {sum > 0 ? Math.round((entry.hours / sum) * 100) : 0}%
              </span>
            </div>
            <div className={styles.track}>
              <div
                className={`${styles.segment} ${SEGMENT_CLASS[index % SEGMENT_CLASS.length]}`}
                style={{ width: `${sum > 0 ? (entry.hours / sum) * 100 : 0}%` }}
              />
            </div>
          </div>
        ))}
        {rows.length === 0 && <p className={styles.empty}>Jira에서 가져온 업무가 없습니다.</p>}
      </div>
    </div>
  );
}

export default TeamProjectPanel;
