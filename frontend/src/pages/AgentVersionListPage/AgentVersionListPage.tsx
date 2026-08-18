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
 * ⚠ **여기서 만든 에이전트는 아직 Chat에서 못 부른다.** Chat이 만드는 대화는
 * 여전히 옛 `agent` 테이블을 가리킨다(services/agent_runtime/legacy_bridge.py) —
 * "저장·발행"까지만 이 화면의 책임이고, 나머지 연결은 이후 작업(작업목록.md
 * "Deep Agent 런타임" 절)이다. 이 화면은 그 연결 전에 저장·버전 발행이 실제로
 * 동작하는지 확인하는 용도로 먼저 연다.
 */
export default function AgentVersionListPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { showToast } = useToast();
  const token = loadSessionToken();
  const session = useSession();
  const isTeamTab = location.pathname === PATHS.agentVersionsTeam;

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
   * 2026-08-18 결정 — 사용 중지해도 팀 공유 쪽에 남는다).
   *
   * 팀 공유 탭에서는 내가 만든 것을 맨 위로 올린다 — 관리 버튼이 뜨는(=내가
   * 손댈 수 있는) 것부터 보이는 게 자연스럽다. 개인 탭은 어차피 전부 내
   * 것이라 정렬할 이유가 없다. `Array.sort`는 안정 정렬이라 같은 그룹
   * 안에서는 서버가 정한 순서(이름순)가 그대로 유지된다. */
  const tabAgents = useMemo(() => {
    const filtered = visibleAgents.filter((agent) =>
      isTeamTab ? agent.status !== 'DRAFT' : agent.status === 'DRAFT',
    );
    if (!isTeamTab || !session) return filtered;
    const myId = session.account.account_id;
    return [...filtered].sort(
      (a, b) => Number(b.owner_account_id === myId) - Number(a.owner_account_id === myId),
    );
  }, [visibleAgents, isTeamTab, session]);

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
      showToast(`「${updated.name}」을 활성화했습니다.`, 'success');
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

  return (
    <AppShell>
      <div className={styles.page}>
        <header className={styles.header}>
          <div className={styles.headerText}>
            <h1 className={styles.title}>에이전트 (버전)</h1>
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

        <p className={styles.notice}>
          <Icon name="info" size={15} color="var(--color-info)" />
          여기서 만든 에이전트는 아직 Chat에서 부를 수 없습니다 — 실행 엔진 연결 전 저장·발행만 검증하는 화면입니다.
        </p>

        {/* 저장만 하면 "개인"에 머문다 — 활성화해야 "팀 공유"로 넘어간다. */}
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
        </nav>

        {error && <p className={styles.error}>{error}</p>}
        {loading && <p className={styles.sectionSub}>불러오는 중…</p>}

        {!loading && !error && tabAgents.length === 0 && (
          <p className={styles.sectionSub}>
            {isTeamTab
              ? '아직 팀에 공유된 에이전트가 없습니다 — 개인 탭에서 만들고 활성화하면 여기 보입니다.'
              : '아직 만든(미공유) 에이전트가 없습니다. 「새 에이전트」로 만들어 보세요.'}
          </p>
        )}

        <div className={styles.grid}>
          {tabAgents.map((agent) => (
            <article key={agent.agent_id} className={styles.card}>
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

              <div className={styles.cardFoot}>
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
          ))}
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
