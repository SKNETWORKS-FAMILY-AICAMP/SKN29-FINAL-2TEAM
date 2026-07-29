import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon, TopNav, useToast } from '../../components';
import { MAIN_NAV_TABS } from '../../routes';
import { ProjectRow } from './ProjectRow';
import styles from './ProjectListPage.module.css';

type SortValue = 'date' | 'progress';

interface ActiveProject {
  id: string;
  title: string;
  desc: string;
  date: string;
  progressText: string;
  progressValue: number;
}

interface CompletedProject {
  id: string;
  title: string;
  desc: string;
  date: string;
}

const ACTIVE_PROJECTS: ActiveProject[] = [];

const COMPLETED_PROJECTS: CompletedProject[] = [];

function formatDate(iso: string): string {
  return iso.slice(0, 10).replace(/-/g, '.');
}

export default function ProjectListPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState<SortValue>('date');
  const [selectedActiveId, setSelectedActiveId] = useState<string | null>(null);
  const [selectedCompletedId, setSelectedCompletedId] = useState<string | null>(null);
  const { showToast } = useToast();

  const query = search.trim().toLowerCase();

  const filteredActive = useMemo(() => {
    const matches = ACTIVE_PROJECTS.filter(
      (project) =>
        !query || project.title.toLowerCase().includes(query) || project.desc.toLowerCase().includes(query),
    );
    const sorted = [...matches].sort((a, b) =>
      sort === 'progress' ? b.progressValue - a.progressValue : new Date(b.date).getTime() - new Date(a.date).getTime(),
    );
    return sorted;
  }, [query, sort]);

  const filteredCompleted = useMemo(
    () =>
      COMPLETED_PROJECTS.filter(
        (project) => !query || project.title.toLowerCase().includes(query) || project.desc.toLowerCase().includes(query),
      ),
    [query],
  );

  function handleSelectActive(project: ActiveProject) {
    const next = selectedActiveId === project.id ? null : project.id;
    setSelectedActiveId(next);
    if (next) showToast(`${project.title} 선택됨`, 'info');
  }

  function handleSelectCompleted(project: CompletedProject) {
    const next = selectedCompletedId === project.id ? null : project.id;
    setSelectedCompletedId(next);
    if (next) showToast(`${project.title} 선택됨`, 'info');
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
              <span className={styles.statValue}>{ACTIVE_PROJECTS.length}개</span>
            </div>
            <div className={styles.statDivider} />
            <div className={styles.statItem}>
              <span className={styles.statLabel}>완료된 프로젝트</span>
              <span className={styles.statValue}>{COMPLETED_PROJECTS.length}개</span>
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
        </div>

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <span className={styles.label}>진행중인 프로젝트</span>
            <span className={[styles.countBadge, styles.activeBadge].join(' ')}>{filteredActive.length}</span>
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
            {filteredActive.map((project) => (
              <ProjectRow
                key={project.id}
                title={project.title}
                desc={project.desc || undefined}
                date={formatDate(project.date)}
                progressText={project.progressText}
                selected={selectedActiveId === project.id}
                onSelect={() => handleSelectActive(project)}
              />
            ))}
            {filteredActive.length === 0 && (
              <p className={styles.emptyRow}>{query ? '검색 결과가 없습니다.' : '진행중인 프로젝트가 없습니다.'}</p>
            )}
          </div>
        </section>

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <span className={styles.label}>완료된 프로젝트</span>
            <span className={[styles.countBadge, styles.completedBadge].join(' ')}>{filteredCompleted.length}</span>
          </div>
          <div className={[styles.listCard, styles.completedList].join(' ')}>
            {filteredCompleted.map((project) => (
              <ProjectRow
                key={project.id}
                title={project.title}
                desc={project.desc || undefined}
                date={formatDate(project.date)}
                progressText="완료"
                done
                selected={selectedCompletedId === project.id}
                onSelect={() => handleSelectCompleted(project)}
              />
            ))}
            {filteredCompleted.length === 0 && (
              <p className={styles.emptyRow}>{query ? '검색 결과가 없습니다.' : '완료된 프로젝트가 없습니다.'}</p>
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
