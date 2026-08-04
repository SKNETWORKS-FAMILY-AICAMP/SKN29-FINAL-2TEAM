import { Link } from 'react-router-dom';
import type { DeadlineTask } from '../../api/projects';
import styles from './TeamDashboard.module.css';

/** 「-4일」이 「4일 지났다」보다 짧고, 옆줄과 자릿수가 맞아 훑기 좋다. */
function overdueLabel(days: number): string {
  return `${days}일`;
}

/**
 * 지연된 업무.
 *
 * 화면에서 가장 큰 타일이다. 팀장이 대시보드를 여는 이유 중 제일 급한 것이고,
 * 여기만 유일하게 **건수가 아니라 이슈 자체**를 보여준다 — "지연 3건"은 알림이지만
 * "KAN-31이 4일째"는 지금 무엇을 할지까지 말해 준다.
 */
export function OverduePanel({ tasks, limit = 6 }: { tasks: DeadlineTask[]; limit?: number }) {
  const shown = tasks.slice(0, limit);

  return (
    <section
      className={`${styles.tile} ${styles.tileHero} ${tasks.length > 0 ? styles.tileHeroFilled : ''}`}
    >
      <div className={styles.heroHead}>
        <div>
          <span className={`${styles.heroValue} ${tasks.length > 0 ? styles.heroValueDanger : ''}`}>
            {tasks.length}건
          </span>
          <span className={styles.heroLabel}>지연</span>
        </div>
        <span className={styles.heroNote}>마감이 지났는데 안 끝난 업무</span>
      </div>

      {tasks.length === 0 ? (
        <p className={styles.heroEmpty}>지연된 업무가 없습니다.</p>
      ) : (
        <ul className={styles.overdueList}>
          {shown.map((task) => (
            <li key={task.exist_task_id} className={styles.overdueRow}>
              <span className={styles.overdueDays}>{overdueLabel(task.days)}</span>
              <Link to={`/projects/${task.proj_id}`} className={styles.overdueKey}>
                {task.jira_issue_id}
              </Link>
              {/* 제목이 없는 행은 지어내지 않는다. 이슈 키만으로도 찾아갈 수 있다. */}
              <span className={styles.overdueSummary}>{task.summary ?? '제목 없음'}</span>
              <span className={styles.overdueWho}>{task.assignee_name ?? '미지정'}</span>
            </li>
          ))}
        </ul>
      )}

      {tasks.length > shown.length && (
        <p className={styles.heroMore}>외 {tasks.length - shown.length}건</p>
      )}
    </section>
  );
}

export default OverduePanel;
