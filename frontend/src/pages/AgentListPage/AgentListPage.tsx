import { useNavigate } from 'react-router-dom';
import { AppShell, Badge, Button, Icon } from '../../components';
import { AVAILABLE_TOOLS, MOCK_AGENTS } from '../../data/mockAgents';
import type { MockAgent } from '../../data/mockAgents';
import { PATHS } from '../../routes';
import styles from './AgentListPage.module.css';

function toolNames(agent: MockAgent): string[] {
  return agent.toolIds
    .map((id) => AVAILABLE_TOOLS.find((tool) => tool.id === id)?.name)
    .filter((name): name is string => Boolean(name));
}

/**
 * 에이전트 목록. 기본 제공과 우리 팀 것을 나눠 보여준다.
 *
 * 기본 제공 카드의 「복제」 버튼은 넣지 않는다 — 7_홈화면_정의 §6-3이 v1 고정을
 * 제안했고 8/12 멘토링에서 확정하기로 했다(개발지시 2차 「멘토링 대기」).
 */
export default function AgentListPage() {
  const navigate = useNavigate();
  const prebuilt = MOCK_AGENTS.filter((agent) => agent.isPrebuilt);
  const team = MOCK_AGENTS.filter((agent) => !agent.isPrebuilt);

  function renderSection(title: string, sub: string, agents: MockAgent[]) {
    return (
      <section className={styles.section}>
        <div className={styles.sectionHead}>
          <h2 className={styles.sectionTitle}>{title}</h2>
          <span className={styles.sectionSub}>{sub}</span>
        </div>

        <div className={styles.grid}>
          {agents.map((agent) => (
            <article key={agent.id} className={styles.card}>
              <div className={styles.cardTop}>
                <span className={styles.cardIcon}>
                  <Icon name="sparkles" size={20} color="var(--color-primary)" />
                </span>
                <div className={styles.cardName}>
                  <strong>{agent.name}</strong>
                  <Badge tone={agent.isPrebuilt ? 'primary' : 'success'}>
                    {agent.isPrebuilt ? '기본 제공' : '팀 공유'}
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
                  {agent.owner} · {agent.updatedAt}
                </span>
                <Button size="sm" variant="secondary" onClick={() => navigate(PATHS.chat)}>
                  Chat에서 사용
                </Button>
                {!agent.isPrebuilt && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => navigate(PATHS.agentEdit.replace(':agentId', agent.id))}
                  >
                    편집
                  </Button>
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
              기본 제공 에이전트를 그대로 쓰거나, 우리 팀 업무에 맞는 에이전트를 직접 만듭니다.
            </p>
          </div>
          <Button onClick={() => navigate(PATHS.agentNew)} iconLeft={<Icon name="plus" size={16} />}>
            새 에이전트
          </Button>
        </header>

        {renderSection('기본 제공', '팀 전체가 바로 쓸 수 있습니다', prebuilt)}
        {renderSection('우리 팀 에이전트', 'Builder에서 만든 것 · Chat 선택기에 즉시 노출', team)}
      </div>
    </AppShell>
  );
}
