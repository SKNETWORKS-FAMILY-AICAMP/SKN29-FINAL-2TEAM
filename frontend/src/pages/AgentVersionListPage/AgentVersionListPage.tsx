import { useEffect, useMemo, useState } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { AppShell, Badge, Button, Icon, Modal, useToast } from '../../components';
import { AGENT_STATUS } from '../../data/agentLabels';
import {
  activateAgentVersion,
  deleteAgentVersion,
  disableAgentVersion,
  getAgentVersionDependents,
  listAgentVersions,
  setAgentVersionFavorite,
} from '../../api/agentVersions';
import type { AgentVersionSummary } from '../../api/agentVersions';
import { ApiError } from '../../api/client';
import { PATHS } from '../../routes';
import { loadSessionToken, useSession } from '../../utils/session';
import styles from './AgentVersionListPage.module.css';

/**
 * 새 버전 스키마(`agents`/`agent_versions`) 목록 — `/agents`(옛 비버전 화면)와
 * 나란히 존재한다.
 *
 * DRAFT(개인 탭)는 소유자만 Chat에서 부를 수 있다(2026-08-18,
 * `_resolve_session_agent`가 `owner_account_id` 일치를 확인) — 팀에
 * 공유하려면 활성화해서 ACTIVE(팀 공유 탭)로 넘겨야 한다.
 */
export default function AgentVersionListPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { showToast } = useToast();
  const token = loadSessionToken();
  const session = useSession();
  /** 세 탭 — 개인/팀 공유는 기존 그대로, 즐겨찾기는 2026-08-18 추가.
   * 즐겨찾기는 개인·팀 공유와 무관하게 이 계정이 별을 누른 것만 모은
   * 가로 축이라 status 기반 필터와 나란히 두지 않고 별도 갈래로 뺐다. */
  const activeTab: 'personal' | 'team' | 'favorites' =
    location.pathname === PATHS.agentVersionsTeam
      ? 'team'
      : location.pathname === PATHS.agentVersionsFavorites
        ? 'favorites'
        : 'personal';
  const isTeamTab = activeTab === 'team';

  const [agents, setAgents] = useState<AgentVersionSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  // 활성화는 서버가 모델·도구를 다시 검증하느라 시간이 걸릴 수 있다 — 그동안
  // 버튼을 잠가 중복 요청을 막는다.
  const [pendingId, setPendingId] = useState<string | null>(null);
  /** 삭제는 되돌릴 수 없어 한 번 확인한다 — ChatPage의 대화 삭제 확인과 같은 패턴. */
  const [pendingDelete, setPendingDelete] = useState<AgentVersionSummary | null>(null);
  /** 다른 에이전트가 서브 에이전트로 쓰고 있어 못 지우는 경우 — 확인 모달 대신
   * 이걸 먼저 보여준다(삭제 시도 후 오류가 아니라, 누르자마자 바로). */
  const [blockedDelete, setBlockedDelete] = useState<{ agent: AgentVersionSummary; parentNames: string[] } | null>(
    null,
  );

  useEffect(() => {
    if (!token) return;
    listAgentVersions(token)
      .then(setAgents)
      .catch((exc) =>
        setError(exc instanceof ApiError ? exc.message : '에이전트를 불러오지 못했습니다.'),
      )
      .finally(() => setLoading(false));
  }, [token]);

  function replaceAgent(updated: AgentVersionSummary) {
    setAgents((prev) => prev.map((item) => (item.agent_id === updated.agent_id ? updated : item)));
  }

  /** 팀의 기본 챗 에이전트는 이 화면에 안 보인다 — 사람이 고르지 않는다,
   * Chat이 아무것도 안 고르면 자동으로 그 에이전트로 떨어진다
   * (ChatPage.tsx의 `is_default_chat` 자동 선택 참고). 관리 화면에 올려서
   * 편집·삭제 대상처럼 보이게 하지 않는다. */
  const visibleAgents = useMemo(() => agents.filter((agent) => !agent.is_default_chat), [agents]);

  /** "개인" = DRAFT(서버가 이미 본인 것만 돌려준다, `list_for_team()` 참고).
   * "팀 공유" = ACTIVE·DISABLED(한 번이라도 활성화된 적이 있으면 팀 전체가 본다,
   * 2026-08-18 결정 — 사용 중지해도 팀 공유 쪽에 남는다). "즐겨찾기"(2026-08-18)
   * 는 상태와 무관하게 `is_favorite`(이 계정 기준)만 본다 — 개인 DRAFT든
   * 팀 공유 ACTIVE/DISABLED든 별을 눌렀으면 여기 모인다.
   *
   * 팀 공유 탭에서는 내가 만든 것을 맨 위로 올린다 — 관리 버튼이 뜨는(=내가
   * 손댈 수 있는) 것부터 보이는 게 자연스럽다. 개인·즐겨찾기 탭은 정렬할
   * 이유가 없다(개인은 어차피 전부 내 것, 즐겨찾기는 상태가 안 섞여도
   * 이미 소수다). `Array.sort`는 안정 정렬이라 같은 그룹 안에서는 서버가
   * 정한 순서(이름순)가 그대로 유지된다. */
  const tabAgents = useMemo(() => {
    if (activeTab === 'favorites') {
      return visibleAgents.filter((agent) => agent.is_favorite);
    }
    const filtered = visibleAgents.filter((agent) =>
      isTeamTab ? agent.status !== 'DRAFT' : agent.status === 'DRAFT',
    );
    if (!isTeamTab || !session) return filtered;
    const myId = session.account.account_id;
    return [...filtered].sort(
      (a, b) => Number(b.owner_account_id === myId) - Number(a.owner_account_id === myId),
    );
  }, [visibleAgents, activeTab, isTeamTab, session]);

  /** 만든 사람이거나 팀장만 편집·활성화·사용 중지·삭제할 수 있다 — 서버도
   * 같은 규칙으로 한 번 더 막는다(`require_owner_or_leader`, `put`/
   * `AgentVersionActivateAPIView`/`AgentVersionDisableAPIView`/`delete`).
   * 화면은 안내일 뿐이다. */
  function canManage(agent: AgentVersionSummary): boolean {
    if (!session) return false;
    return session.account.account_id === agent.owner_account_id || session.account.role === 'leader';
  }

  /** 삭제 버튼을 누른 시점에 먼저 물어본다. 다른 에이전트가 쓰고 있으면
   * 확인 모달 대신 그 목록을 바로 보여주고, 아니면 평소대로 확인 모달을 연다. */
  async function startDelete(agent: AgentVersionSummary) {
    if (!token || pendingId) return;
    setPendingId(agent.agent_id);
    try {
      const { parent_names: parentNames } = await getAgentVersionDependents(token, agent.agent_id);
      if (parentNames.length > 0) {
        setBlockedDelete({ agent, parentNames });
      } else {
        setPendingDelete(agent);
      }
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '확인하지 못했습니다.', 'error');
    } finally {
      setPendingId(null);
    }
  }

  async function remove(agent: AgentVersionSummary) {
    if (!token || pendingId) return;
    setPendingId(agent.agent_id);
    try {
      await deleteAgentVersion(token, agent.agent_id);
      setAgents((prev) => prev.filter((item) => item.agent_id !== agent.agent_id));
      showToast(`「${agent.name}」을 지웠습니다.`, 'success');
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '지우지 못했습니다.', 'error');
    } finally {
      setPendingId(null);
      setPendingDelete(null);
    }
  }

  async function activate(agent: AgentVersionSummary) {
    if (!token || pendingId) return;
    setPendingId(agent.agent_id);
    try {
      const updated = await activateAgentVersion(token, agent.agent_id);
      replaceAgent(updated);
      // 이 버전이 참조하는 개인 DRAFT 서브 에이전트가 있으면 서버가 같이
      // 활성화하고 이름을 실어 보낸다(2026-08-18) — 조용히 켜지면 사람이
      // 모르니 알린다.
      if (updated.cascaded_subagent_names?.length) {
        showToast(
          `「${updated.name}」을 활성화했습니다. 서브 에이전트 「${updated.cascaded_subagent_names.join('」·「')}」도 초안 상태였어서 함께 활성화했습니다.`,
          'success',
        );
      } else {
        showToast(`「${updated.name}」을 활성화했습니다.`, 'success');
      }
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '활성화하지 못했습니다.', 'error');
    } finally {
      setPendingId(null);
    }
  }

  async function disable(agent: AgentVersionSummary) {
    if (!token || pendingId) return;
    setPendingId(agent.agent_id);
    try {
      const updated = await disableAgentVersion(token, agent.agent_id);
      replaceAgent(updated);
      showToast(`「${updated.name}」을 사용 중지했습니다.`, 'success');
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '사용 중지하지 못했습니다.', 'error');
    } finally {
      setPendingId(null);
    }
  }

  /** 별 토글 — 활성화·중지처럼 재검증이 필요한 상태 전이가 아니라 눈에
   * 바로 반영하고(낙관적 갱신), 실패하면 되돌린다. `pendingId`를 안 쓴다 —
   * 그건 다른 버튼들이 쓰는 잠금이라 즐겨찾기까지 물고 늘어지면 오히려
   * 굼떠 보인다. */
  async function toggleFavorite(agent: AgentVersionSummary) {
    if (!token) return;
    const next = !agent.is_favorite;
    replaceAgent({ ...agent, is_favorite: next });
    try {
      const updated = await setAgentVersionFavorite(token, agent.agent_id, next);
      replaceAgent(updated);
    } catch (exc) {
      replaceAgent(agent);
      showToast(exc instanceof ApiError ? exc.message : '즐겨찾기를 바꾸지 못했습니다.', 'error');
    }
  }

  return (
    <AppShell>
      <div className={styles.page}>
        <header className={styles.header}>
          <div className={styles.headerText}>
            <h1 className={styles.title}>에이전트</h1>
            <p className={styles.subtitle}>
              저장할 때마다 새 버전이 발행됩니다. 발행된 버전은 이후 고칠 수 없습니다 — 바꾸려면 새 버전을 다시 발행합니다.
            </p>
          </div>
          <Button
            onClick={() => navigate(PATHS.agentVersionNew)}
            iconLeft={<Icon name="plus" size={16} />}
          >
            새 에이전트
          </Button>
        </header>

        {activeTab === 'personal' && (
          <p className={styles.notice}>
            <Icon name="info" size={15} color="var(--color-info)" />
            여기서 만든 에이전트는 나만 Chat에서 부를 수 있습니다 — 먼저 검증해 보고, 팀에 공유하려면 활성화하세요.
          </p>
        )}

        {/* 저장만 하면 "개인"에 머문다 — 활성화해야 "팀 공유"로 넘어간다.
            "즐겨찾기"(2026-08-18)는 개인·팀 공유와 별개 갈래 — 상태와 무관하게
            이 계정이 별을 누른 것만 모은다. */}
        <nav className={styles.tabBar}>
          <NavLink
            to={PATHS.agentVersions}
            end
            className={({ isActive }) => [styles.tab, isActive ? styles.tabActive : ''].filter(Boolean).join(' ')}
          >
            개인
          </NavLink>
          <NavLink
            to={PATHS.agentVersionsTeam}
            end
            className={({ isActive }) => [styles.tab, isActive ? styles.tabActive : ''].filter(Boolean).join(' ')}
          >
            팀 공유
          </NavLink>
          <NavLink
            to={PATHS.agentVersionsFavorites}
            end
            className={({ isActive }) => [styles.tab, isActive ? styles.tabActive : ''].filter(Boolean).join(' ')}
          >
            즐겨찾기
          </NavLink>
        </nav>

        {error && <p className={styles.error}>{error}</p>}
        {loading && <p className={styles.sectionSub}>불러오는 중…</p>}

        {!loading && !error && tabAgents.length === 0 && (
          <p className={styles.sectionSub}>
            {activeTab === 'team'
              ? '아직 팀에 공유된 에이전트가 없습니다 — 개인 탭에서 만들고 활성화하면 여기 보입니다.'
              : activeTab === 'favorites'
                ? '아직 즐겨찾기한 에이전트가 없습니다 — 카드 오른쪽 위 별을 눌러 추가하세요.'
                : '아직 만든(미공유) 에이전트가 없습니다. 「새 에이전트」로 만들어 보세요.'}
          </p>
        )}

        <div className={styles.grid}>
          {tabAgents.map((agent) => {
            // DISABLED는 Chat이 못 받는다(usable = ACTIVE | DRAFT, ChatPage.tsx) —
            // 눌러서 넘어가 봐야 그 화면 드롭다운에 없는 에이전트라 아무것도
            // 못 한다. 카드 자체를 안 눌리게 막는다(2026-08-18).
            const chattable = agent.status !== 'DISABLED';
            return (
            <article
              key={agent.agent_id}
              className={[styles.card, chattable ? styles.cardClickable : ''].filter(Boolean).join(' ')}
              role={chattable ? 'button' : undefined}
              tabIndex={chattable ? 0 : undefined}
              onClick={chattable ? () => navigate(`${PATHS.chat}?agent=${agent.agent_id}`) : undefined}
              onKeyDown={
                chattable
                  ? (event) => {
                      if (event.key !== 'Enter' && event.key !== ' ') return;
                      event.preventDefault();
                      navigate(`${PATHS.chat}?agent=${agent.agent_id}`);
                    }
                  : undefined
              }
            >
              {/* 카드 자체가 챗으로 넘어가는 버튼이라(2026-08-18), 안에 있는
                  버튼들은 클릭이 카드까지 올라가지 않게 막는다 — 안 막으면
                  "사용 중지"를 누르는 동시에 챗으로 튕겨 나간다. */}
              <button
                type="button"
                className={styles.favoriteButton}
                onClick={(event) => {
                  event.stopPropagation();
                  void toggleFavorite(agent);
                }}
                aria-label={agent.is_favorite ? '즐겨찾기 해제' : '즐겨찾기 추가'}
                aria-pressed={agent.is_favorite}
              >
                {/* 별 색은 의미(경고 등) 없는 순전히 장식적 선택이라 시맨틱
                    토큰(--color-warning 등)을 안 쓰고 고정 노란색을 직접 쓴다. */}
                <Icon
                  name={agent.is_favorite ? 'star-filled' : 'star'}
                  size={18}
                  color={agent.is_favorite ? '#facc15' : 'var(--color-placeholder)'}
                />
              </button>

              <div className={styles.cardTop}>
                <span className={styles.cardIcon}>
                  <Icon name="sparkles" size={20} color="var(--color-primary)" />
                </span>
                <div className={styles.cardName}>
                  <strong>{agent.name}</strong>
                  <Badge tone={AGENT_STATUS[agent.status].tone}>{AGENT_STATUS[agent.status].label}</Badge>
                </div>
              </div>

              <p className={styles.cardDesc}>{agent.description}</p>

              {agent.subagent_names.length > 0 && (
                <p className={styles.cardSubagents}>
                  <Icon name="chart-network" size={13} color="var(--color-muted)" />
                  {agent.subagent_names.join(', ')}
                </p>
              )}

              <div className={styles.cardFoot} onClick={(event) => event.stopPropagation()}>
                <span className={styles.cardMeta}>{agent.model ?? '모델 미지정'}</span>
                {agent.status === 'ACTIVE' && canManage(agent) && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => disable(agent)}
                    disabled={pendingId === agent.agent_id}
                  >
                    {pendingId === agent.agent_id ? '처리하는 중…' : '사용 중지'}
                  </Button>
                )}
                {(agent.status === 'DRAFT' || agent.status === 'DISABLED') && canManage(agent) && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => activate(agent)}
                    disabled={pendingId === agent.agent_id}
                  >
                    {pendingId === agent.agent_id ? '검증하는 중…' : '활성화'}
                  </Button>
                )}
                {canManage(agent) && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => navigate(PATHS.agentVersionEdit.replace(':agentId', agent.agent_id))}
                  >
                    새 버전 편집
                  </Button>
                )}
                {canManage(agent) && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => startDelete(agent)}
                    disabled={pendingId === agent.agent_id}
                  >
                    {pendingId === agent.agent_id ? '확인하는 중…' : '삭제'}
                  </Button>
                )}
              </div>
            </article>
            );
          })}
        </div>
      </div>

      {/* 되돌릴 수 없는 삭제라 한 번 묻는다 — ChatPage의 대화 삭제 확인과 같은 패턴. */}
      <Modal
        open={Boolean(pendingDelete)}
        onClose={() => setPendingDelete(null)}
        title="이 에이전트를 지울까요?"
        width={420}
        footer={
          <>
            <Button variant="outline" size="sm" onClick={() => setPendingDelete(null)}>
              취소
            </Button>
            <Button
              size="sm"
              variant="danger"
              onClick={() => pendingDelete && void remove(pendingDelete)}
              disabled={pendingId === pendingDelete?.agent_id}
            >
              {pendingId === pendingDelete?.agent_id ? '지우는 중…' : '지우기'}
            </Button>
          </>
        }
      >
        <p className={styles.deleteBody}>
          <strong>{pendingDelete?.name}</strong>
          <span>되돌릴 수 없습니다.</span>
        </p>
      </Modal>

      {/* 다른 에이전트가 서브 에이전트로 쓰고 있어 못 지우는 경우 — 확인 대신
          바로 이걸 보여준다(startDelete 참고). */}
      <Modal
        open={Boolean(blockedDelete)}
        onClose={() => setBlockedDelete(null)}
        title="지금은 지울 수 없습니다"
        width={420}
        footer={
          <Button size="sm" onClick={() => setBlockedDelete(null)}>
            확인
          </Button>
        }
      >
        <p className={styles.deleteBody}>
          <strong>{blockedDelete?.agent.name}</strong>
          <span>다음 에이전트가 이 에이전트를 서브 에이전트로 쓰고 있어 지울 수 없습니다. 먼저 그 연결을 빼거나 그 에이전트를 지워 주세요.</span>
        </p>
        <ul className={styles.dependentList}>
          {blockedDelete?.parentNames.map((name) => <li key={name}>{name}</li>)}
        </ul>
      </Modal>
    </AppShell>
  );
}
