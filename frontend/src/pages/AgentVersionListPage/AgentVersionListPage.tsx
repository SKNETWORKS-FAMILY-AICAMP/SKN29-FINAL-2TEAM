import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppShell, Badge, Button, Icon, useToast } from '../../components';
import { AGENT_STATUS } from '../../data/agentLabels';
import {
  activateAgentVersion,
  disableAgentVersion,
  listAgentVersions,
} from '../../api/agentVersions';
import type { AgentVersionSummary } from '../../api/agentVersions';
import { ApiError } from '../../api/client';
import { PATHS } from '../../routes';
import { loadSessionToken } from '../../utils/session';
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
  const { showToast } = useToast();
  const token = loadSessionToken();

  const [agents, setAgents] = useState<AgentVersionSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  // 활성화는 서버가 모델·도구를 다시 검증하느라 시간이 걸릴 수 있다 — 그동안
  // 버튼을 잠가 중복 요청을 막는다.
  const [pendingId, setPendingId] = useState<string | null>(null);

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

        {error && <p className={styles.error}>{error}</p>}
        {loading && <p className={styles.sectionSub}>불러오는 중…</p>}

        {!loading && !error && agents.length === 0 && (
          <p className={styles.sectionSub}>아직 만든 에이전트가 없습니다. 「새 에이전트」로 만들어 보세요.</p>
        )}

        <div className={styles.grid}>
          {agents.map((agent) => (
            <article key={agent.agent_id} className={styles.card}>
              <div className={styles.cardTop}>
                <span className={styles.cardIcon}>
                  <Icon name="sparkles" size={20} color="var(--color-primary)" />
                </span>
                <div className={styles.cardName}>
                  <strong>{agent.name}</strong>
                  <Badge tone={AGENT_STATUS[agent.status].tone}>{AGENT_STATUS[agent.status].label}</Badge>
                  {agent.version !== null && <Badge tone="neutral">v{agent.version}</Badge>}
                </div>
              </div>

              <p className={styles.cardDesc}>{agent.description}</p>

              <div className={styles.cardFoot}>
                <span className={styles.cardMeta}>{agent.model ?? '모델 미지정'}</span>
                {agent.status === 'ACTIVE' && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => disable(agent)}
                    disabled={pendingId === agent.agent_id}
                  >
                    {pendingId === agent.agent_id ? '처리하는 중…' : '사용 중지'}
                  </Button>
                )}
                {(agent.status === 'DRAFT' || agent.status === 'DISABLED') && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => activate(agent)}
                    disabled={pendingId === agent.agent_id}
                  >
                    {pendingId === agent.agent_id ? '검증하는 중…' : '활성화'}
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => navigate(PATHS.agentVersionEdit.replace(':agentId', agent.agent_id))}
                >
                  새 버전 편집
                </Button>
              </div>
            </article>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
