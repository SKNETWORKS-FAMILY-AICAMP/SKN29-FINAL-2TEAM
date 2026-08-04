import { Link } from 'react-router-dom';
import type { DeadlineTask } from '../../api/projects';
import styles from './TeamDashboard.module.css';

const WEEKDAY = ['일', '월', '화', '수', '목', '금', '토'];

function dayLabel(task: DeadlineTask): string {
  if (task.days === 0) return '오늘';
  if (task.days === 1) return '내일';
  const date = new Date(task.due_at);
  return `${date.getMonth() + 1}/${date.getDate()}(${WEEKDAY[date.getDay()]})`;
}

/**
 * 이번 주에 마감인 업무.
 *
 * 지연 타일이 "이미 늦은 것"이라면 여기는 "곧 늦을 것"이다. 둘을 한 목록에 섞으면
 * 지연이 예정에 묻힌다 — 지금 손대야 하는 것과 지켜보면 되는 것은 다른 판단이다.
 */
export function UpcomingPanel({ tasks }: { tasks: DeadlineTask[] }) {
  return (
    <section className={styles.card}>
      <div className={styles.cardHeader}>
        {/* 「일주일」은 서버의 `TeamDeadlineAPIView.SOON_DAYS`(7)와 맞춰 둔 말이다. */}
        <p className={styles.cardTitle}>일주일 내 마감 일정</p>
        <span className={styles.cardNote}>{tasks.length}건</span>
      </div>

      <div className={styles.upcomingList}>
        {tasks.map((task) => (
          <Link
            key={task.exist_task_id}
            to={`/projects/${task.proj_id}`}
            className={styles.upcomingRow}
          >
            <span className={styles.upcomingDay}>{dayLabel(task)}</span>
            <span className={styles.upcomingKey}>{task.jira_issue_id}</span>
            <span className={styles.upcomingSummary}>{task.summary ?? '제목 없음'}</span>
            <span className={styles.upcomingWho}>{task.assignee_name ?? '미지정'}</span>
          </Link>
        ))}
        {tasks.length === 0 && <p className={styles.empty}>일주일 안에 마감인 업무가 없습니다.</p>}
      </div>
    </section>
  );
}

export default UpcomingPanel;
