import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Checkbox, Icon, StepIndicator } from '../../components';
import { markConnectorConnected } from '../../utils/connectorStatus';
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

const INITIAL_PROJECTS: ProjectItem[] = [];

const STEPS = ['Jira 연동', '프로젝트 및 보드 선택', '필드 매핑'];

export default function JiraProjectSelectPage() {
  const navigate = useNavigate();
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [projects, setProjects] = useState<ProjectItem[]>(INITIAL_PROJECTS);
  const [expandedProjectId, setExpandedProjectId] = useState<string | null>(null);

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
              {projects.length === 0 && <p className={styles.emptyNote}>표시할 프로젝트가 없습니다.</p>}
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
          <Button variant="outline" onClick={() => navigate('/onboarding/connectors')}>
            이전 단계
          </Button>
          <Button
            variant="primary"
            disabled={loadState === 'loading'}
            onClick={() => {
              markConnectorConnected('jira');
              navigate('/onboarding/connectors');
            }}
          >
            설정 완료
          </Button>
        </div>
      </div>
    </div>
  );
}
