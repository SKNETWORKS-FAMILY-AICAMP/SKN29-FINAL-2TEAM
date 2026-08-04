import { Link } from 'react-router-dom';
import type { DeadlineTask, Project } from '../../api/projects';
import styles from './TeamDashboard.module.css';

interface Props {
  projects: Project[];
  overdue: DeadlineTask[];
}

/**
 * 프로젝트가 어디까지 갔는가.
 *
 * 앞서 있던 「프로젝트별 업무량」을 대신한다. 그쪽은 "KAN에 48%가 몰려 있다"는
 * **비중**을 보여 줬는데, 비중을 보고 팀장이 할 행동이 없었다. 진행률은 다르다 —
 * 늦은 프로젝트를 알면 인원을 옮기거나 일정을 다시 잡는다.
 *
 * 진행률이 없는 프로젝트는 0%가 아니라 "안 읽음"이다. 0으로 칠하면 시작도 안 한
 * 것처럼 보인다.
 */
export function ProjectProgressPanel({ projects, overdue }: Props) {
  const active = projects.filter((project) => project.status !== 'ARCHIVED');

  const overdueByProject = overdue.reduce<Record<string, number>>((acc, task) => {
    acc[task.proj_id] = (acc[task.proj_id] ?? 0) + 1;
    return acc;
  }, {});

  const rows = [...active].sort(
    (a, b) => (a.progress?.progress ?? 999) - (b.progress?.progress ?? 999),
  );

  return (
    <section className={styles.card}>
      <div className={styles.cardHeader}>
        <p className={styles.cardTitle}>프로젝트</p>
        <Link to="/projects" className={styles.cardLink}>
          전체 {active.length}개 →
        </Link>
      </div>

      <div className={styles.projectList}>
        {rows.map((project) => {
          const progress = project.progress;
          const late = overdueByProject[project.proj_id] ?? 0;

          return (
            <Link
              key={project.proj_id}
              to={`/projects/${project.proj_id}`}
              className={styles.projectRow}
            >
              <span className={styles.projectName}>{project.name}</span>
              <span className={styles.projectBar}>
                <span
                  className={styles.projectFill}
                  style={{ width: `${Math.min(100, progress?.progress ?? 0)}%` }}
                />
              </span>
              <span className={styles.projectPct}>
                {progress ? `${progress.progress}%` : '—'}
              </span>
              <span className={late > 0 ? styles.projectLate : styles.projectOnTime}>
                {late > 0 ? `지연 ${late}` : '—'}
              </span>
            </Link>
          );
        })}
        {rows.length === 0 && <p className={styles.empty}>진행 중인 프로젝트가 없습니다.</p>}
      </div>
    </section>
  );
}

export default ProjectProgressPanel;
