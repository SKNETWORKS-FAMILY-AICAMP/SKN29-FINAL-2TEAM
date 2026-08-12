import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppShell, Badge, Button, Icon, useToast } from '../../components';
import { deleteAgent, listAgents, listToolChoices } from '../../api/agents';
import type { Agent, ToolChoice } from '../../api/agents';
import { ApiError } from '../../api/client';
import { PATHS } from '../../routes';
import { loadSessionToken } from '../../utils/session';
import styles from './AgentListPage.module.css';

/**
 * 에이전트 목록. 기본 제공과 우리 팀 것을 나눠 보여준다.
 *
 * 기본 제공 카드의 「복제」 버튼은 넣지 않는다 — 7_홈화면_정의 §6-3이 v1 고정을
 * 제안했고 8/12 멘토링에서 확정하기로 했다(개발지시 2차 「멘토링 대기」).
 */
export default function AgentListPage() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const token = loadSessionToken();

  const [agents, setAgents] = useState<Agent[]>([]);
  const [tools, setTools] = useState<ToolChoice[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    Promise.all([listAgents(token), listToolChoices(token)])
      .then(([rows, choices]) => {
        setAgents(rows);
        setTools(choices);
      })
      .catch((exc) =>
        setError(exc instanceof ApiError ? exc.message : '에이전트를 불러오지 못했습니다.'),
      )
      .finally(() => setLoading(false));
  }, [token]);

  /** tool_ref → 사람이 읽는 이름. 서버 카탈로그에 없으면 ref 를 그대로 보여준다
   *  — 지워진 MCP 도구가 아직 붙어 있다는 사실이 보여야 고칠 수 있다. */
  function toolNames(agent: Agent): string[] {
    return agent.tool_refs.map(
      (ref) => tools.find((tool) => tool.tool_ref === ref)?.name ?? ref,
    );
  }

  async function remove(agent: Agent) {
    if (!token) return;
    try {
      await deleteAgent(token, agent.agent_id);
      setAgents((prev) => prev.filter((item) => item.agent_id !== agent.agent_id));
      showToast(`「${agent.name}」을 내렸습니다.`, 'success');
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '지우지 못했습니다.', 'error');
    }
  }

  function renderSection(title: string, sub: string, rows: Agent[]) {
    if (rows.length === 0) return null;
    return (
      <section className={styles.section}>
        <div className={styles.sectionHead}>
          <h2 className={styles.sectionTitle}>{title}</h2>
          <span className={styles.sectionSub}>{sub}</span>
        </div>

        <div className={styles.grid}>
          {rows.map((agent) => (
            <article key={agent.agent_id} className={styles.card}>
              <div className={styles.cardTop}>
                <span className={styles.cardIcon}>
                  <Icon name="sparkles" size={20} color="var(--color-primary)" />
                </span>
                <div className={styles.cardName}>
                  <strong>{agent.name}</strong>
                  <Badge tone={agent.is_prebuilt ? 'primary' : 'success'}>
                    {agent.is_prebuilt ? '기본 제공' : '팀 공유'}
                  </Badge>
                </div>
              </div>

              <p className={styles.cardDesc}>{agent.description}</p>

              <div className={styles.tools}>
                {toolNames(agent).map((name) => (
                  <span key={name} className={styles.tool}>
                    {name}
                  </span>
                ))}
              </div>

              <div className={styles.cardFoot}>
                <span className={styles.cardMeta}>
                  {agent.is_prebuilt ? 'halil 제공' : agent.owner_name ?? '팀'}
                </span>
                <Button size="sm" variant="secondary" onClick={() => navigate(PATHS.chat)}>
                  Chat에서 사용
                </Button>
                {/* 기본 제공은 편집·삭제가 서버에서 403 이다. 눌리는 버튼을 두면
                    사용자가 고칠 수 있다고 믿게 된다. */}
                {!agent.is_prebuilt && (
                  <>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => navigate(PATHS.agentEdit.replace(':agentId', agent.agent_id))}
                    >
                      편집
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => remove(agent)}>
                      내리기
                    </Button>
                  </>
                )}
              </div>
            </article>
          ))}
        </div>
      </section>
    );
  }

  return (
    <AppShell>
      <div className={styles.page}>
        <header className={styles.header}>
          <div className={styles.headerText}>
            <h1 className={styles.title}>에이전트</h1>
            <p className={styles.subtitle}>
              우리 팀 업무에 맞는 에이전트를 만들어 둡니다. 채팅에서 그 일에 맞는 에이전트가 불려 나옵니다.
            </p>
          </div>
          <Button onClick={() => navigate(PATHS.agentNew)} iconLeft={<Icon name="plus" size={16} />}>
            새 에이전트
          </Button>
        </header>

        {error && <p className={styles.error}>{error}</p>}
        {loading && <p className={styles.sectionSub}>불러오는 중…</p>}

        {/* **기본 제공 에이전트는 여기 없다.**
            그건 우리가 넣어 둔 플랫폼의 일부이지 팀이 관리할 물건이 아니다 —
            편집도 삭제도 서버가 403 으로 막고, 화면에 두면 「지울 수 없는 카드」가
            목록 맨 위를 차지한다. 이 화면은 팀이 만든 것만 보여준다.
            채팅은 기본 에이전트를 알아서 쓰고, 여기 만든 에이전트는 그 아래에서
            불려 나온다(`agent:*` 위임). */}
        {renderSection(
          '우리 팀 에이전트',
          'Builder에서 만든 것 · 채팅에서 그 일에 맞을 때 불려 나옵니다',
          agents.filter((a) => !a.is_prebuilt),
        )}

        {!loading && !error && agents.filter((a) => !a.is_prebuilt).length === 0 && (
          <p className={styles.sectionSub}>
            아직 우리 팀 에이전트가 없습니다. 「새 에이전트」로 만들어 보세요.
          </p>
        )}
      </div>
    </AppShell>
  );
}
