import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Badge, Icon, TopNav, useToast } from '../../components';
import type { BadgeTone } from '../../components';
import { ApiError } from '../../api/client';
import { getProject, setProjectStatus, syncProjectTasks } from '../../api/projects';
import type { ExistTask, ProjectDetail } from '../../api/projects';
import { MAIN_NAV_TABS } from '../../routes';
import { useSession } from '../../utils/session';
import styles from './ProjectDetailPage.module.css';

/** `status_category`만 분기에 쓴다. `status`는 프로젝트마다 표시 문자열이 다르다. */
const CATEGORY_LABEL: Record<string, string> = {
  TO_DO: '해야 할 일',
  IN_PROGRESS: '진행 중',
  DONE: '완료',
};

const CATEGORY_TONE: Record<string, BadgeTone> = {
  TO_DO: 'neutral',
  IN_PROGRESS: 'info',
  DONE: 'success',
};

const CATEGORY_ORDER = ['IN_PROGRESS', 'TO_DO', 'DONE'];

const collator = new Intl.Collator('ko', { numeric: true });

function formatDate(iso: string | null): string {
  if (!iso) return '-';
  return iso.slice(0, 10).replace(/-/g, '.');
}

/** 시간은 정수면 소수점을 붙이지 않는다 — 48h가 48.0h로 보일 이유가 없다. */
function hours(value: number | null): string {
  if (value === null) return '-';
  return `${Number.isInteger(value) ? value : value.toFixed(1)}h`;
}

interface AssigneeRow {
  name: string;
  total: number;
  open: number;
  remaining: number;
}

/** 이 프로젝트 안에서의 담당자별 배분. 팀 전체 부하율과는 다른 값이다. */
function byAssignee(tasks: ExistTask[]): AssigneeRow[] {
  const rows = new Map<string, AssigneeRow>();
  for (const task of tasks) {
    // 매핑이 안 된 담당자도 묶어서 보여준다. 빼면 합계가 목록과 어긋난다.
    const name = task.assignee_name ?? '담당자 미지정';
    const row = rows.get(name) ?? { name, total: 0, open: 0, remaining: 0 };
    row.total += 1;
    if (task.status_category !== 'DONE') {
      row.open += 1;
      row.remaining += task.remaining ?? 0;
    }
    rows.set(name, row);
  }
  return [...rows.values()].sort((a, b) => b.remaining - a.remaining || collator.compare(a.name, b.name));
}

/**
 * 프로젝트 상세.
 *
 * 진행률·업무 목록·담당자별 배분을 한 번의 요청으로 받는다. 나눠 부르면 그 사이
 * 「갱신」이 끼었을 때 서로 다른 시점의 숫자가 한 화면에 섞인다.
 */
export default function ProjectDetailPage() {
  const { projectId = '' } = useParams();
  const navigate = useNavigate();
  const session = useSession();
  const token = session?.token;
  const { showToast } = useToast();

  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [category, setCategory] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token || !projectId) return;
    setLoading(true);
    setError('');
    try {
      setProject(await getProject(token, projectId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '프로젝트를 불러오지 못했습니다.');
      setProject(null);
    } finally {
      setLoading(false);
    }
  }, [token, projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const tasks = useMemo(() => project?.tasks ?? [], [project]);

  const counts = useMemo(() => {
    const map: Record<string, number> = { TO_DO: 0, IN_PROGRESS: 0, DONE: 0 };
    for (const task of tasks) {
      if (task.status_category) map[task.status_category] += 1;
    }
    return map;
  }, [tasks]);

  const visibleTasks = useMemo(() => {
    const rows = category ? tasks.filter((task) => task.status_category === category) : tasks;
    return [...rows].sort(
      (a, b) =>
        CATEGORY_ORDER.indexOf(a.status_category ?? '') - CATEGORY_ORDER.indexOf(b.status_category ?? '') ||
        collator.compare(a.jira_issue_id, b.jira_issue_id),
    );
  }, [tasks, category]);

  const assignees = useMemo(() => byAssignee(tasks), [tasks]);

  async function handleSync() {
    if (!token || busy) return;
    setBusy(true);
    try {
      await syncProjectTasks(token, projectId);
      await load();
      showToast('Jira 업무를 다시 읽었습니다', 'success');
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : 'Jira 갱신에 실패했습니다', 'error');
    } finally {
      setBusy(false);
    }
  }

  async function handleToggleArchive() {
    if (!token || !project || busy) return;
    const next = project.status === 'ARCHIVED' ? 'ACTIVE' : 'ARCHIVED';
    setBusy(true);
    try {
      await setProjectStatus(token, projectId, next);
      await load();
      showToast(next === 'ARCHIVED' ? '완료 처리했습니다' : '진행 중으로 되돌렸습니다', 'success');
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : '상태를 바꾸지 못했습니다', 'error');
    } finally {
      setBusy(false);
    }
  }

  const progress = project?.progress ?? null;
  const archived = project?.status === 'ARCHIVED';

  return (
    <div className={styles.page}>
      <TopNav tabs={MAIN_NAV_TABS} activeTo="/projects" userLabel="관리자" />

      <main className={styles.mainContent}>
        <Link to="/projects" className={styles.back}>
          <Icon name="arrow-left" size={16} />
          <span>프로젝트</span>
        </Link>

        {loading && <p className={styles.notice}>프로젝트를 불러오는 중…</p>}
        {error && <p className={styles.error}>{error}</p>}

        {!loading && project && (
          <>
            <div className={styles.header}>
              <div className={styles.titleBlock}>
                <div className={styles.titleRow}>
                  <h1>{project.name}</h1>
                  <Badge tone={archived ? 'success' : 'info'}>{archived ? '완료' : '진행 중'}</Badge>
                </div>
                <p className={styles.meta}>
                  생성 {formatDate(project.created_at)} · 담당 {project.owner_name ?? '-'}
                </p>
              </div>

              <div className={styles.headerActions}>
                {project.has_jira_source && (
                  <button type="button" className={styles.ghostBtn} onClick={handleSync} disabled={busy}>
                    <Icon name="refresh" size={15} spin={busy} />
                    <span>갱신</span>
                  </button>
                )}
                <button type="button" className={styles.primaryBtn} onClick={handleToggleArchive} disabled={busy}>
                  {archived ? '진행 중으로' : '완료 처리'}
                </button>
              </div>
            </div>

            {progress ? (
              <section className={styles.card}>
                <div className={styles.progressHead}>
                  <span className={styles.cardTitle}>진행률</span>
                  <span className={styles.progressValue}>{progress.progress}%</span>
                </div>
                <div className={styles.bar}>
                  <div className={styles.barFill} style={{ width: `${Math.min(100, progress.progress)}%` }} />
                </div>
                <div className={styles.factRow}>
                  <span>
                    전체 <strong>{hours(progress.total_hours)}</strong>
                  </span>
                  <span>
                    완료·소진 <strong>{hours(progress.completed_hours)}</strong>
                  </span>
                  <span>
                    업무 <strong>{progress.task_count}건</strong> (완료 {progress.done_count})
                  </span>
                  {progress.missing_estimate > 0 && (
                    // 추정치가 없으면 분모에서 빠진다. 왜 진행률이 안 움직이는지 알려면 필요하다.
                    <span className={styles.warn}>추정치 없음 {progress.missing_estimate}건</span>
                  )}
                </div>
              </section>
            ) : (
              <section className={styles.card}>
                <p className={styles.notice}>
                  {project.has_jira_source
                    ? 'Jira 업무를 아직 읽지 않았습니다. 「갱신」을 눌러 주세요.'
                    : '연결된 Jira 프로젝트가 없어 진행률을 계산할 수 없습니다.'}
                </p>
              </section>
            )}

            {assignees.length > 0 && (
              <section className={styles.card}>
                <span className={styles.cardTitle}>담당자별 남은 업무</span>
                <div className={styles.assigneeList}>
                  {assignees.map((row) => (
                    <div key={row.name} className={styles.assigneeRow}>
                      <span className={styles.assigneeName}>{row.name}</span>
                      <span className={styles.assigneeCount}>
                        {row.open}건 / 전체 {row.total}건
                      </span>
                      <span className={styles.assigneeHours}>{hours(row.remaining)}</span>
                    </div>
                  ))}
                </div>
                <p className={styles.footnote}>
                  이 프로젝트 안의 잔여 공수입니다. 사람의 실제 부하는 다른 프로젝트까지 합쳐야 하며{' '}
                  <Link to="/tasks/workload">기간별 업무 부하</Link>에서 볼 수 있습니다.
                </p>
              </section>
            )}

            <section className={styles.card}>
              <div className={styles.tasksHead}>
                <span className={styles.cardTitle}>업무 {tasks.length}건</span>
                <div className={styles.filters}>
                  <button
                    type="button"
                    className={[styles.chip, category === null ? styles.chipActive : ''].filter(Boolean).join(' ')}
                    onClick={() => setCategory(null)}
                  >
                    전체 {tasks.length}
                  </button>
                  {CATEGORY_ORDER.map((key) => (
                    <button
                      key={key}
                      type="button"
                      className={[styles.chip, category === key ? styles.chipActive : ''].filter(Boolean).join(' ')}
                      onClick={() => setCategory(category === key ? null : key)}
                    >
                      {CATEGORY_LABEL[key]} {counts[key]}
                    </button>
                  ))}
                </div>
              </div>

              <div className={styles.tableHead}>
                <span>이슈</span>
                <span>제목</span>
                <span>담당</span>
                <span>상태</span>
                <span className={styles.right}>추정</span>
                <span className={styles.right}>잔여</span>
                <span className={styles.right}>마감</span>
              </div>
              <div className={styles.rowList}>
                {visibleTasks.map((task) => (
                  <div key={task.exist_task_id} className={styles.row}>
                    <span className={styles.issueKey}>{task.jira_issue_id}</span>
                    {/* 제목이 없는 행은 이슈 키로 대신한다 — 지어내지 않는다. */}
                    <span className={styles.summary}>{task.summary ?? '제목 없음'}</span>
                    <span className={styles.assignee}>{task.assignee_name ?? '미지정'}</span>
                    <span>
                      {task.status_category ? (
                        <Badge tone={CATEGORY_TONE[task.status_category]}>
                          {CATEGORY_LABEL[task.status_category]}
                        </Badge>
                      ) : (
                        <span className={styles.dim}>{task.status ?? '-'}</span>
                      )}
                    </span>
                    <span className={styles.right}>{hours(task.estimate)}</span>
                    <span className={styles.right}>{hours(task.remaining)}</span>
                    <span className={styles.right}>{formatDate(task.due_at)}</span>
                  </div>
                ))}
                {visibleTasks.length === 0 && (
                  <p className={styles.notice}>
                    {tasks.length === 0 ? '읽어온 업무가 없습니다.' : '해당 상태의 업무가 없습니다.'}
                  </p>
                )}
              </div>
            </section>
          </>
        )}

        {!loading && !project && !error && (
          <p className={styles.notice}>
            프로젝트를 찾을 수 없습니다.{' '}
            <button type="button" className={styles.linkBtn} onClick={() => navigate('/projects')}>
              목록으로
            </button>
          </p>
        )}
      </main>
    </div>
  );
}
