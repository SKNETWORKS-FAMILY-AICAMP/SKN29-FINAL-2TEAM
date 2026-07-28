import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ApiError } from '../../api/http';
import { getProjects } from '../../api/projects';
import type { Project } from '../../api/types';
import type { BadgeTone } from '../../components';
import { Icon, TopNav, useToast } from '../../components';
import { MAIN_NAV_TABS } from '../../routes';
import { ProjectRow } from './ProjectRow';
import styles from './ProjectListPage.module.css';

type ActiveStatus = 'progress' | 'notstarted' | 'ontrack' | 'delayed';
type FilterValue = 'all' | ActiveStatus;
type SortValue = 'date' | 'progress';
type LoadState = 'loading' | 'ready' | 'empty' | 'blocked' | 'error' | 'demo';

interface ActiveProject {
  id: string;
  title: string;
  desc: string;
  status: ActiveStatus;
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

const STATUS_LABEL: Record<ActiveStatus, string> = {
  progress: '진행중',
  notstarted: '시작 전',
  ontrack: '순조',
  delayed: '지연',
};

const STATUS_TONE: Record<ActiveStatus, BadgeTone> = {
  progress: 'info',
  notstarted: 'warning',
  ontrack: 'success',
  delayed: 'danger',
};

const ACTIVE_PROJECTS: ActiveProject[] = [
  { id: 'a1', title: '결제 시스템 개선', desc: '토스페이먼츠 및 카카오페이 신규 연동 및 결제 실패율 감소를 위한 트랜잭션 에러 트래킹 고도화', status: 'progress', date: '2025-01-15', progressText: '2/6 업무 완료', progressValue: 33 },
  { id: 'a2', title: '모바일 앱 v2', desc: 'React Native 기반 프론트엔드 전체 마이그레이션 및 푸시 알림 수신 성공률 최적화', status: 'progress', date: '2025-01-20', progressText: '1/4 업무 완료', progressValue: 25 },
  { id: 'a3', title: '보안 감사 대응', desc: '', status: 'notstarted', date: '2025-01-22', progressText: '0/5 업무 완료', progressValue: 0 },
  { id: 'a4', title: '사용자 인증 개선', desc: '', status: 'ontrack', date: '2025-01-25', progressText: '3/5 업무 완료', progressValue: 60 },
  { id: 'a5', title: '데이터 파이프라인 구축', desc: '', status: 'delayed', date: '2025-01-28', progressText: '1/7 업무 완료', progressValue: 14 },
  { id: 'a6', title: '관리자 대시보드 개발', desc: '', status: 'progress', date: '2025-02-02', progressText: '2/9 업무 완료', progressValue: 22 },
  { id: 'a7', title: '고객 지원 챗봇 도입', desc: 'GPT 기반 1차 응대 자동화 및 상담원 라우팅 규칙 최적화', status: 'ontrack', date: '2025-02-05', progressText: '4/6 업무 완료', progressValue: 67 },
  { id: 'a8', title: '인프라 비용 최적화', desc: '유휴 리소스 정리 및 오토스케일링 정책 재설계로 클라우드 비용 절감', status: 'notstarted', date: '2025-02-10', progressText: '0/4 업무 완료', progressValue: 0 },
];

const COMPLETED_PROJECTS: CompletedProject[] = [
  { id: 'c1', title: 'halil v1.0 출시', desc: 'AI 기반 자동 업무 분배 및 리소스 매핑 시스템 핵심 모듈 설계, 1단계 릴리즈 및 서비스 안정화 완료', date: '2025-01-10' },
  { id: 'c2', title: 'API 리팩토링', desc: '', date: '2025-01-05' },
  { id: 'c3', title: '온보딩 플로우 개선', desc: '', date: '2024-12-20' },
  { id: 'c4', title: '알림 시스템 구축', desc: '', date: '2024-12-12' },
  { id: 'c5', title: '로그 모니터링 세팅', desc: '', date: '2024-11-30' },
  { id: 'c6', title: '검색 기능 고도화', desc: '', date: '2024-11-15' },
  { id: 'c7', title: '결제 실패 알림 자동화', desc: '', date: '2024-11-02' },
  { id: 'c8', title: '사내 위키 마이그레이션', desc: '', date: '2024-10-20' },
  { id: 'c9', title: '테스트 자동화 파이프라인', desc: '', date: '2024-10-05' },
  { id: 'c10', title: '디자인 시스템 v1 구축', desc: '', date: '2024-09-28' },
];

const FILTER_CHIPS: Array<{ value: FilterValue; label: string }> = [
  { value: 'all', label: '전체' },
  { value: 'progress', label: '진행중' },
  { value: 'notstarted', label: '시작 전' },
  { value: 'ontrack', label: '순조' },
  { value: 'delayed', label: '지연' },
];

function formatDate(iso: string): string {
  return iso.slice(0, 10).replace(/-/g, '.');
}

function toActiveProject(project: Project): ActiveProject {
  return {
    id: project.project_id,
    title: project.name,
    desc: project.description,
    status: project.status === 'DRAFT' ? 'notstarted' : 'progress',
    date: project.updated_at,
    progressText: '진행 정보 없음',
    progressValue: 0,
  };
}

function toCompletedProject(project: Project): CompletedProject {
  return {
    id: project.project_id,
    title: project.name,
    desc: project.description,
    date: project.updated_at,
  };
}

export default function ProjectListPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const isDemo = searchParams.get('mode') === 'demo';
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<FilterValue>('all');
  const [sort, setSort] = useState<SortValue>('date');
  const [selectedActiveId, setSelectedActiveId] = useState<string | null>(null);
  const [selectedCompletedId, setSelectedCompletedId] = useState<string | null>(null);
  const [apiProjects, setApiProjects] = useState<Project[]>([]);
  const [loadState, setLoadState] = useState<LoadState>(isDemo ? 'demo' : 'loading');
  const [loadReason, setLoadReason] = useState('');
  const { showToast } = useToast();

  const query = search.trim().toLowerCase();
  const activeProjects = useMemo(
    () => (isDemo ? ACTIVE_PROJECTS : apiProjects.filter((project) => project.status !== 'ARCHIVED').map(toActiveProject)),
    [apiProjects, isDemo],
  );
  const completedProjects = useMemo(
    () => (isDemo ? COMPLETED_PROJECTS : apiProjects.filter((project) => project.status === 'ARCHIVED').map(toCompletedProject)),
    [apiProjects, isDemo],
  );
  const visibleFilterChips = isDemo
    ? FILTER_CHIPS
    : FILTER_CHIPS.filter((chip) => chip.value === 'all' || chip.value === 'progress' || chip.value === 'notstarted');

  useEffect(() => {
    setFilter('all');
    setSelectedActiveId(null);
    setSelectedCompletedId(null);

    if (isDemo) {
      setLoadState('demo');
      setLoadReason('');
      return;
    }

    let cancelled = false;
    setLoadState('loading');
    setLoadReason('');

    getProjects()
      .then((projects) => {
        if (cancelled) return;
        setApiProjects(projects);
        setLoadState(projects.length > 0 ? 'ready' : 'empty');
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
          setLoadState('blocked');
          setLoadReason('인증된 세션이 필요하지만 React 로그인 연동이 아직 확정되지 않았습니다.');
          return;
        }
        setLoadState('error');
        setLoadReason(error instanceof Error ? error.message : '프로젝트 API 응답을 확인할 수 없습니다.');
      });

    return () => {
      cancelled = true;
    };
  }, [isDemo]);

  const filteredActive = useMemo(() => {
    const matches = activeProjects.filter((project) => {
      const matchesSearch =
        !query || project.title.toLowerCase().includes(query) || project.desc.toLowerCase().includes(query);
      const matchesFilter = filter === 'all' || project.status === filter;
      return matchesSearch && matchesFilter;
    });
    const sorted = [...matches].sort((a, b) =>
      sort === 'progress' ? b.progressValue - a.progressValue : new Date(b.date).getTime() - new Date(a.date).getTime(),
    );
    return sorted;
  }, [activeProjects, query, filter, sort]);

  const filteredCompleted = useMemo(
    () =>
      completedProjects.filter(
        (project) => !query || project.title.toLowerCase().includes(query) || project.desc.toLowerCase().includes(query),
      ),
    [completedProjects, query],
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
    if (!isDemo) {
      showToast('BLOCKED · 실제 파일 등록 API와 Connector가 연결되지 않아 업무 분배를 시작할 수 없습니다.', 'error');
      return;
    }

    if (!selectedActiveId) {
      showToast('업무 분배를 시작할 진행 중 프로젝트를 먼저 선택해 주세요.', 'info');
      return;
    }

    showToast('업무 분배 워크플로우로 이동합니다', 'info');
    setTimeout(() => {
      navigate(`/files/new?projectId=${encodeURIComponent(selectedActiveId)}&view=review&mode=demo`);
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
              <span className={styles.statValue}>{activeProjects.length}개</span>
            </div>
            <div className={styles.statDivider} />
            <div className={styles.statItem}>
              <span className={styles.statLabel}>완료된 프로젝트</span>
              <span className={styles.statValue}>{completedProjects.length}개</span>
            </div>
          </div>
        </div>

        <div
          className={[
            styles.statusPanel,
            loadState === 'blocked' || loadState === 'error' ? styles.statusBlocked : '',
            loadState === 'demo' ? styles.statusDemo : '',
          ]
            .filter(Boolean)
            .join(' ')}
          role="status"
        >
          <div>
            <strong>
              {loadState === 'loading' && '프로젝트 API 연결 중'}
              {loadState === 'ready' && 'CONDITIONAL · 실제 프로젝트 목록'}
              {loadState === 'empty' && 'CONDITIONAL · 등록된 프로젝트 없음'}
              {loadState === 'blocked' && 'BLOCKED · 프로젝트 조회 불가'}
              {loadState === 'error' && 'BLOCKED · 프로젝트 API 오류'}
              {loadState === 'demo' && 'DEMO · 정적 프로젝트 데이터'}
            </strong>
            <p>
              {loadState === 'loading' && '백엔드에서 프로젝트를 불러오고 있습니다.'}
              {loadState === 'ready' && '목록은 실제 API 데이터입니다. 진행률과 파일 등록 데이터가 없어 업무 분배 시작은 차단됩니다.'}
              {loadState === 'empty' && 'API 연결은 성공했지만 표시할 프로젝트가 없습니다.'}
              {(loadState === 'blocked' || loadState === 'error') && loadReason}
              {loadState === 'demo' && 'UI 흐름 검증용 데이터이며 실제 프로젝트나 분석 결과가 아닙니다.'}
            </p>
          </div>
          {!isDemo && (
            <button type="button" className={styles.demoButton} onClick={() => setSearchParams({ mode: 'demo' })}>
              정적 데모 보기
            </button>
          )}
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
          <div className={styles.filterChips}>
            {visibleFilterChips.map((chip) => (
              <button
                key={chip.value}
                type="button"
                className={[styles.chip, filter === chip.value ? styles.chipActive : ''].filter(Boolean).join(' ')}
                onClick={() => setFilter(chip.value)}
              >
                {chip.label}
              </button>
            ))}
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
                statusLabel={STATUS_LABEL[project.status]}
                statusTone={STATUS_TONE[project.status]}
                date={formatDate(project.date)}
                progressText={project.progressText}
                selected={selectedActiveId === project.id}
                onSelect={() => handleSelectActive(project)}
              />
            ))}
            {filteredActive.length === 0 && <p className={styles.emptyRow}>검색 결과가 없습니다.</p>}
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
                statusLabel="완료"
                statusTone="success"
                date={formatDate(project.date)}
                progressText="완료"
                done
                selected={selectedCompletedId === project.id}
                onSelect={() => handleSelectCompleted(project)}
              />
            ))}
            {filteredCompleted.length === 0 && <p className={styles.emptyRow}>검색 결과가 없습니다.</p>}
          </div>
        </section>
      </main>

      <button
        type="button"
        className={styles.floatingCta}
        onClick={handleStartWorkflow}
        disabled={!isDemo}
        title={!isDemo ? '실제 파일 등록 API와 Connector 연동이 필요합니다.' : undefined}
      >
        <Icon name="sparkles" size={20} color="#fff" />
        <span>업무 분배 시작</span>
      </button>
    </div>
  );
}
