import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { listMyProjects } from '../../api/projects';
import type { Project } from '../../api/projects';
import { Icon, TopNav, useToast } from '../../components';
import { MAIN_NAV_TABS } from '../../routes';
import { loadSessionToken } from '../../utils/session';
import { ProjectRow } from './ProjectRow';
import styles from './ProjectListPage.module.css';

type SortValue = 'date' | 'progress';

export default function ProjectListPage() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [projects, setProjects] = useState<Project[]>([]);
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState<SortValue>('date');
  const [selectedActiveId, setSelectedActiveId] = useState<string | null>(null);
  const [selectedCompletedId, setSelectedCompletedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = loadSessionToken();
    if (!token) return;
    listMyProjects(token).then(setProjects).catch((reason: Error) => setError(reason.message));
  }, []);

  const query = search.trim().toLowerCase();
  const active = useMemo(() => {
    const rows = projects.filter(
      (project) => project.status !== 'ARCHIVED' && (!query || project.name.toLowerCase().includes(query)),
    );
    return [...rows].sort((a, b) =>
      sort === 'progress' ? a.status.localeCompare(b.status) : b.proj_id.localeCompare(a.proj_id),
    );
  }, [projects, query, sort]);
  const completed = useMemo(
    () => projects.filter(
      (project) => project.status === 'ARCHIVED' && (!query || project.name.toLowerCase().includes(query)),
    ),
    [projects, query],
  );

  function selectActive(project: Project) {
    const next = selectedActiveId === project.proj_id ? null : project.proj_id;
    setSelectedActiveId(next);
    if (next) showToast(`${project.name} 선택됨`, 'info');
  }

  function startWorkflow() {
    if (!selectedActiveId) {
      showToast('진행할 프로젝트를 먼저 선택해 주세요', 'error');
      return;
    }
    navigate(`/projects/${selectedActiveId}/select-source-document`);
  }

  return (
    <div className={styles.page}>
      <TopNav tabs={MAIN_NAV_TABS} activeTo="/projects" userLabel="관리자" />
      <main className={styles.mainContent}>
        <div className={styles.pageHeader}>
          <div className={styles.titleBlock}>
            <h1>프로젝트</h1>
            <p>업무 추출을 시작할 프로젝트를 선택하세요.</p>
          </div>
          <div className={styles.quickStats}>
            <div className={styles.statItem}><span className={styles.statLabel}>진행중</span><span className={styles.statValue}>{active.length}개</span></div>
            <div className={styles.statDivider} />
            <div className={styles.statItem}><span className={styles.statLabel}>완료</span><span className={styles.statValue}>{completed.length}개</span></div>
          </div>
        </div>
        <div className={styles.toolbar}>
          <div className={styles.searchBox}>
            <Icon name="search" size={16} color="var(--color-placeholder)" />
            <input className={styles.searchInput} placeholder="프로젝트 이름 검색..." value={search} onChange={(event) => setSearch(event.target.value)} />
          </div>
        </div>
        {error && <p className={styles.emptyRow} role="alert">{error}</p>}
        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <span className={styles.label}>진행중인 프로젝트</span>
            <span className={[styles.countBadge, styles.activeBadge].join(' ')}>{active.length}</span>
            <div className={styles.sortControls}>
              <button type="button" className={[styles.sortBtn, sort === 'date' ? styles.sortBtnActive : ''].filter(Boolean).join(' ')} onClick={() => setSort('date')}>최신순</button>
              <button type="button" className={[styles.sortBtn, sort === 'progress' ? styles.sortBtnActive : ''].filter(Boolean).join(' ')} onClick={() => setSort('progress')}>상태순</button>
            </div>
          </div>
          <div className={[styles.listCard, styles.activeList].join(' ')}>
            {active.map((project) => (
              <ProjectRow key={project.proj_id} title={project.name} statusLabel={project.status} statusTone="info" date="-" progressText="업무 분배 가능" selected={selectedActiveId === project.proj_id} onSelect={() => selectActive(project)} />
            ))}
            {!active.length && <p className={styles.emptyRow}>진행중인 프로젝트가 없습니다.</p>}
          </div>
        </section>
        <section className={styles.section}>
          <div className={styles.sectionHeader}><span className={styles.label}>완료된 프로젝트</span><span className={[styles.countBadge, styles.completedBadge].join(' ')}>{completed.length}</span></div>
          <div className={[styles.listCard, styles.completedList].join(' ')}>
            {completed.map((project) => (
              <ProjectRow key={project.proj_id} title={project.name} date="-" progressText="완료" done selected={selectedCompletedId === project.proj_id} onSelect={() => setSelectedCompletedId(project.proj_id)} />
            ))}
            {!completed.length && <p className={styles.emptyRow}>완료된 프로젝트가 없습니다.</p>}
          </div>
        </section>
      </main>
      <button type="button" className={styles.floatingCta} onClick={startWorkflow}>
        <Icon name="sparkles" size={20} color="#fff" /><span>업무 분배 시작</span>
      </button>
    </div>
  );
}
