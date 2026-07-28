import { useEffect, useState } from 'react';
import { Button, Checkbox, Icon, StepIndicator } from '../../components';
import styles from './JiraProjectSelectPage.module.css';

type LoadState = 'loading' | 'loaded';

interface BoardItem {
  id: string;
  name: string;
  checked: boolean;
}

interface ProjectItem {
  id: string;
  name: string;
  key: string;
  desc: string;
  checked: boolean;
  boards?: BoardItem[];
}

const INITIAL_PROJECTS: ProjectItem[] = [
  { id: 'backend', name: 'halil-backend', key: 'HBAK', desc: '백엔드 개발', checked: true },
  {
    id: 'frontend',
    name: 'halil-frontend',
    key: 'HFNT',
    desc: '프론트엔드 개발',
    checked: true,
    boards: [
      { id: 'sprint', name: 'Sprint Board', checked: true },
      { id: 'kanban', name: 'Kanban Board', checked: false },
    ],
  },
  { id: 'infra', name: 'halil-infra', key: 'HINF', desc: '인프라/DevOps', checked: false },
  { id: 'design', name: 'halil-design', key: 'HDSN', desc: '디자인 시스템', checked: false },
];

const STEPS = ['Jira 연동', '프로젝트 및 보드 선택', '필드 매핑'];

export default function JiraProjectSelectPage() {
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [projects, setProjects] = useState<ProjectItem[]>(INITIAL_PROJECTS);
  const [expandedProjectId, setExpandedProjectId] = useState<string | null>('frontend');

  useEffect(() => {
    const timer = setTimeout(() => setLoadState('loaded'), 1200);
    return () => clearTimeout(timer);
  }, []);

  function handleProjectCheckedChange(projectId: string, checked: boolean) {
    setProjects((prev) => prev.map((p) => (p.id === projectId ? { ...p, checked } : p)));
  }

  function handleBoardCheckedChange(projectId: string, boardId: string, checked: boolean) {
    setProjects((prev) =>
      prev.map((p) =>
        p.id === projectId
          ? {
              ...p,
              boards: p.boards?.map((b) => (b.id === boardId ? { ...b, checked } : b)),
            }
          : p,
      ),
    );
  }

  function toggleExpanded(projectId: string) {
    setExpandedProjectId((prev) => (prev === projectId ? null : projectId));
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.logo}>
          <div className={styles.logoMark}>h</div>
          <span className={styles.logoName}>halil</span>
        </div>
        <StepIndicator steps={STEPS} currentIndex={1} />
      </header>

      <div className={styles.contentWrapper}>
        <div className={styles.titleSection}>
          <h1>Jira 프로젝트 선택</h1>
          <p>이 팀에서 사용할 Jira 프로젝트를 골라주세요</p>
        </div>

        {loadState === 'loading' ? (
          <div className={[styles.mainCard, styles.loadingCard].join(' ')}>
            <div className={styles.loadingInner}>
              <Icon name="loader" size={48} color="var(--color-primary)" spin className={styles.spinner} />
              <div>
                <p className={styles.loadingTitle}>Jira에서 프로젝트 정보를 불러오는 중이에요</p>
                <p className={styles.loadingSub}>초기 설정 시 시간이 오래 걸릴 수 있습니다</p>
              </div>
            </div>
          </div>
        ) : (
          <div className={[styles.mainCard, styles.selectedCard].join(' ')}>
            <p className={styles.projectSectionTitle}>Jira 프로젝트 목록</p>
            <div className={styles.projectList}>
              {projects.map((project) => {
                const isExpanded = expandedProjectId === project.id && Boolean(project.boards);
                return (
                  <div key={project.id}>
                    <div
                      className={[styles.projectRow, isExpanded ? styles.activeRow : '']
                        .filter(Boolean)
                        .join(' ')}
                    >
                      <Checkbox
                        checked={project.checked}
                        onChange={(checked) => handleProjectCheckedChange(project.id, checked)}
                      />
                      <div
                        className={styles.projectInfo}
                        onClick={project.boards ? () => toggleExpanded(project.id) : undefined}
                        style={project.boards ? { cursor: 'pointer' } : undefined}
                      >
                        <span className={styles.pName}>{project.name}</span>
                        <span className={styles.pKey}>({project.key})</span>
                        <span className={styles.pDesc}>— {project.desc}</span>
                      </div>
                    </div>

                    {project.boards && (
                      <div
                        className={[styles.boardExpansion, isExpanded ? styles.open : '']
                          .filter(Boolean)
                          .join(' ')}
                      >
                        <p className={styles.boardSectionTitle}>보드 선택</p>
                        <div className={styles.boardList}>
                          {project.boards.map((board) => (
                            <Checkbox
                              key={board.id}
                              checked={board.checked}
                              onChange={(checked) => handleBoardCheckedChange(project.id, board.id, checked)}
                              label={
                                <span className={board.checked ? styles.checkedLabel : undefined}>
                                  {board.name}
                                </span>
                              }
                            />
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        <div className={styles.actionsBar}>
          <Button variant="outline">이전 단계</Button>
          <Button variant="primary" disabled={loadState === 'loading'}>
            다음: 필드 매핑 확인
          </Button>
        </div>
      </div>
    </div>
  );
}
