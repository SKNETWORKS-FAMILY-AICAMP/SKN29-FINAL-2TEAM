import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Checkbox, Icon, StepIndicator } from '../../components';
import { ApiError } from '../../api/client';
import { listJiraProjects } from '../../api/connectors';
import type { JiraProject } from '../../api/connectors';
import { listRegisteredJiraProjects, registerJiraProjects } from '../../api/projects';
import { markConnectorConnected } from '../../utils/connectorStatus';
import { useSession } from '../../utils/session';
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

const STEPS = ['Jira 연동', '프로젝트 및 보드 선택', '필드 매핑'];

/** 설명이 비어 있는 프로젝트가 많아 종류와 리드로 대신 채운다. */
function projectDescription(project: JiraProject): string {
  if (project.description) return project.description;
  return [project.project_type, project.lead_name && `리드 ${project.lead_name}`]
    .filter(Boolean)
    .join(' · ');
}

export default function JiraProjectSelectPage() {
  const navigate = useNavigate();
  const session = useSession();
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [expandedProjectId, setExpandedProjectId] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [needsReconnect, setNeedsReconnect] = useState(false);
  const [saving, setSaving] = useState(false);

  const token = session?.token;

  useEffect(() => {
    if (!token) return;

    let cancelled = false;
    setLoadState('loading');
    void (async () => {
      let rows: JiraProject[];
      try {
        rows = await listJiraProjects(token);
      } catch (err) {
        if (cancelled) return;
        // 404는 아직 연결되지 않은 것, 502는 갱신이 실패해 재연결이 필요한 것.
        if (err instanceof ApiError && (err.status === 404 || err.status === 502)) {
          setNeedsReconnect(true);
        }
        setError(err instanceof ApiError ? err.message : '프로젝트 목록을 불러오지 못했습니다.');
        setLoadState('loaded');
        return;
      }

      // 이미 등록된 Jira 프로젝트를 체크 상태로 되살린다.
      let savedKeys = new Set<string>();
      try {
        savedKeys = new Set((await listRegisteredJiraProjects(token)).map((row) => row.project_key));
      } catch {
        // 저장된 선택을 못 읽어도 목록은 보여준다. 다시 고르면 된다.
      }

      if (cancelled) return;
      setProjects(
        rows.map((project) => ({
          id: project.project_key,
          name: project.name,
          key: project.project_key,
          desc: projectDescription(project),
          checked: savedKeys.has(project.project_key),
        })),
      );
      setLoadState('loaded');
    })();

    return () => {
      cancelled = true;
    };
  }, [token]);

  async function handleSaveAndFinish() {
    if (!token) return;

    const checked = projects.filter((project) => project.checked);
    setSaving(true);
    try {
      // **고르는 것이 곧 등록이다.** Jira 프로젝트 하나에는 프로젝트 하나의 업무가
      // 들어 있으므로, 고른 개수만큼 프로젝트가 생긴다.
      //
      // 이름을 지금 같이 넘긴다. 나중에 화면이 'KAN' 대신 실제 이름을 쓰려고 Jira에
      // 다시 물어보면, 토큰이 만료됐을 때 저장된 데이터는 멀쩡한데 이름을 못 읽어
      // 화면이 깨진다.
      await registerJiraProjects(
        token,
        checked.map((item) => ({ project_key: item.key, name: item.name })),
      );
      markConnectorConnected('jira');
      navigate('/onboarding/connectors');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '프로젝트를 저장하지 못했습니다.');
      setSaving(false);
    }
  }

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
        ) : error ? (
          <div className={[styles.mainCard, styles.loadingCard].join(' ')}>
            <div className={styles.loadingInner}>
              <Icon name="triangle-alert" size={48} color="var(--color-danger)" />
              <div>
                <p className={styles.loadingTitle}>{error}</p>
                {needsReconnect && (
                  <p className={styles.loadingSub}>
                    커넥터 화면에서 Jira를 먼저 연결해 주세요.
                  </p>
                )}
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
                        {project.desc && <span className={styles.pDesc}>— {project.desc}</span>}
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
            disabled={loadState === 'loading' || Boolean(error) || saving}
            onClick={() => void handleSaveAndFinish()}
          >
            {saving ? '저장 중…' : '설정 완료'}
          </Button>
        </div>
      </div>
    </div>
  );
}
