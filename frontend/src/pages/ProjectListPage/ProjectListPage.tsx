import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon, TopNav, useToast } from '../../components';
import { ApiError } from '../../api/client';
import { listMyProjects, syncTeamTasks } from '../../api/projects';
import type { Project } from '../../api/projects';
import { MAIN_NAV_TABS } from '../../routes';
import { useSession } from '../../utils/session';
import { ProjectRow } from './ProjectRow';
import styles from './ProjectListPage.module.css';

type SortValue = 'date' | 'progress';

/** `created_at`이 없는 프로젝트가 있다. 모르는 날짜를 지어내지 않는다. */
function formatDate(iso: string | null): string {
  if (!iso) return '-';
  return iso.slice(0, 10).replace(/-/g, '.');
}

/**
 * 마지막 갱신 시각. 하루 안쪽은 "몇 분 전"이 판단에 더 쓸모 있고, 그보다 오래되면
 * 정확한 날짜가 필요하다.
 */
function formatSince(iso: string | null): string {
  if (!iso) return '아직 읽지 않음';

  const elapsed = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(elapsed / 60000);
  if (minutes < 1) return '방금 전';
  if (minutes < 60) return `${minutes}분 전`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}시간 전`;

  return `${iso.slice(0, 10).replace(/-/g, '.')} ${iso.slice(11, 16)}`;
}

/**
 * 목록에 한 줄로 붙는 요약. Jira를 읽기 전과 읽었는데 업무가 없는 것은 다른
 * 상태라서 다르게 말한다.
 */
function summaryOf(project: Project): string {
  const progress = project.progress;
  if (!progress) {
    return project.has_jira_source ? 'Jira 업무를 아직 읽지 않았습니다' : '연결된 Jira 프로젝트가 없습니다';
  }

  const parts = [`업무 ${progress.task_count}건`, `완료 ${progress.done_count}건`];
  // 추정치가 없는 이슈는 진행률 분모에서 빠진다. 숫자만 보여주면 왜 안 움직이는지
  // 알 수 없어 건수를 같이 밝힌다.
  if (progress.missing_estimate > 0) parts.push(`추정치 없음 ${progress.missing_estimate}건`);
  return parts.join(' · ');
}

/** 정렬 기준이 없는 항목은 뒤로 보낸다. 0으로 치면 "진행률 0%"와 섞인다. */
function compareDesc(a: number | null, b: number | null): number {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  return b - a;
}

/**
 * 프로젝트.
 *
 * 진행 중 / 완료된 프로젝트를 나눠 보여준다. 진행률은 Jira 이슈의 공수 기준이라
 * 진입할 때는 DB에 있는 값을 그대로 읽고, Jira를 다시 읽는 것은 「갱신」이 한다 —
 * 화면을 옮길 때마다 `exist_task`를 통째로 다시 쓸 이유가 없다.
 */
export default function ProjectListPage() {
  const navigate = useNavigate();
  const session = useSession();
  const token = session?.token;
  const { showToast } = useToast();

  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState<SortValue>('date');

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError('');
    try {
      setProjects(await listMyProjects(token));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '프로젝트를 불러오지 못했습니다.');
      setProjects([]);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  const query = search.trim().toLowerCase();

  const matched = useMemo(
    () => projects.filter((project) => !query || project.name.toLowerCase().includes(query)),
    [projects, query],
  );

  const activeProjects = useMemo(() => {
    const rows = matched.filter((project) => project.status !== 'ARCHIVED');
    return [...rows].sort((a, b) =>
      sort === 'progress'
        ? compareDesc(a.progress?.progress ?? null, b.progress?.progress ?? null)
        : compareDesc(
            a.created_at ? new Date(a.created_at).getTime() : null,
            b.created_at ? new Date(b.created_at).getTime() : null,
          ),
    );
  }, [matched, sort]);

  const completedProjects = useMemo(
    () => matched.filter((project) => project.status === 'ARCHIVED'),
    [matched],
  );

  const syncable = useMemo(() => projects.filter((project) => project.has_jira_source), [projects]);

  // 소스가 여럿이면 가장 오래된 쪽을 쓴다. 최신 쪽을 보여주면 화면이 실제보다
  // 신선하다고 말하게 된다.
  const lastSyncAt = useMemo(() => {
    if (syncable.length === 0) return null;
    if (syncable.some((project) => !project.last_sync_at)) return null;
    return syncable.map((project) => project.last_sync_at as string).sort()[0];
  }, [syncable]);

  async function handleRefresh() {
    if (!token || syncing) return;
    setSyncing(true);
    try {
      await syncTeamTasks(token);
      await load();
      showToast('Jira 업무를 다시 읽었습니다', 'success');
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : 'Jira 갱신에 실패했습니다', 'error');
    } finally {
      setSyncing(false);
    }
  }

  function handleStartWorkflow() {
    showToast('업무 분배 워크플로우로 이동합니다', 'info');
    setTimeout(() => {
      navigate('/files/new?view=review');
    }, 700);
  }

  return (
    <div className={styles.page}>
      <TopNav tabs={MAIN_NAV_TABS} activeTo="/projects" userLabel="관리자" />

      <main className={styles.mainContent}>
        <div className={styles.pageHeader}>
          <div className={styles.titleBlock}>
            <h1>프로젝트</h1>
            <p>AI 분석 기반 프로젝트 업무 할당 현황을 관리하고 새 업무를 생성합니다.</p>
          </div>
          <div className={styles.quickStats}>
            <div className={styles.statItem}>
              <span className={styles.statLabel}>진행중인 프로젝트</span>
              <span className={styles.statValue}>
                {projects.filter((project) => project.status !== 'ARCHIVED').length}개
              </span>
            </div>
            <div className={styles.statDivider} />
            <div className={styles.statItem}>
              <span className={styles.statLabel}>완료된 프로젝트</span>
              <span className={styles.statValue}>
                {projects.filter((project) => project.status === 'ARCHIVED').length}개
              </span>
            </div>
          </div>
        </div>

        <div className={styles.toolbar}>
          <div className={styles.searchBox}>
            <Icon name="search" size={16} color="var(--color-placeholder)" />
            <input
              type="text"
              className={styles.searchInput}
              placeholder="프로젝트 이름 또는 내용 검색..."
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>

          {syncable.length > 0 && (
            <div className={styles.syncBox}>
              <span className={styles.syncLabel}>
                마지막 갱신 <strong>{formatSince(lastSyncAt)}</strong>
              </span>
              <button
                type="button"
                className={styles.refreshBtn}
                onClick={handleRefresh}
                disabled={syncing}
                title="Jira 업무를 다시 읽어 진행률을 갱신합니다"
                aria-label="갱신"
              >
                <Icon name="refresh" size={15} spin={syncing} />
                <span>{syncing ? '갱신 중…' : '갱신'}</span>
              </button>
            </div>
          )}
        </div>

        {error && <p className={styles.errorRow}>{error}</p>}

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <span className={styles.label}>진행중인 프로젝트</span>
            <span className={[styles.countBadge, styles.activeBadge].join(' ')}>{activeProjects.length}</span>
            <div className={styles.sortControls}>
              <button
                type="button"
                className={[styles.sortBtn, sort === 'date' ? styles.sortBtnActive : ''].filter(Boolean).join(' ')}
                onClick={() => setSort('date')}
              >
                최신순
              </button>
              <button
                type="button"
                className={[styles.sortBtn, sort === 'progress' ? styles.sortBtnActive : ''].filter(Boolean).join(' ')}
                onClick={() => setSort('progress')}
              >
                진행률순
              </button>
            </div>
          </div>
          <div className={[styles.listCard, styles.activeList].join(' ')}>
            {activeProjects.map((project) => (
              <ProjectRow
                key={project.proj_id}
                title={project.name}
                desc={summaryOf(project)}
                date={formatDate(project.created_at)}
                progressText={project.progress ? `${project.progress.progress}%` : '-'}
                onOpen={() => navigate(`/projects/${project.proj_id}`)}
              />
            ))}
            {activeProjects.length === 0 && (
              <p className={styles.emptyRow}>
                {loading
                  ? '프로젝트를 불러오는 중…'
                  : query
                    ? '검색 결과가 없습니다.'
                    : '진행중인 프로젝트가 없습니다.'}
              </p>
            )}
          </div>
        </section>

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <span className={styles.label}>완료된 프로젝트</span>
            <span className={[styles.countBadge, styles.completedBadge].join(' ')}>{completedProjects.length}</span>
          </div>
          <div className={[styles.listCard, styles.completedList].join(' ')}>
            {completedProjects.map((project) => (
              <ProjectRow
                key={project.proj_id}
                title={project.name}
                desc={summaryOf(project)}
                date={formatDate(project.created_at)}
                progressText="완료"
                done
                onOpen={() => navigate(`/projects/${project.proj_id}`)}
              />
            ))}
            {completedProjects.length === 0 && (
              <p className={styles.emptyRow}>
                {loading ? '프로젝트를 불러오는 중…' : query ? '검색 결과가 없습니다.' : '완료된 프로젝트가 없습니다.'}
              </p>
            )}
          </div>
        </section>
      </main>

      <button type="button" className={styles.floatingCta} onClick={handleStartWorkflow}>
        <Icon name="sparkles" size={20} color="#fff" />
        <span>업무 분배 시작</span>
      </button>
    </div>
  );
}
