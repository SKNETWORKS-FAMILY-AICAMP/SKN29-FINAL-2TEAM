import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { AppShell, Button, Checkbox, Icon, Input, Select, useToast } from '../../components';
import { AGENT_MODELS, AVAILABLE_TOOLS, findMockAgent } from '../../data/mockAgents';
import type { AgentModelId } from '../../data/mockAgents';
import { PATHS } from '../../routes';
import styles from './AgentEditPage.module.css';

const EFFORT_OPTIONS = [
  { value: 'low', label: '낮음 (low)' },
  { value: 'medium', label: '보통 (medium)' },
  { value: 'xhigh', label: '높음 (xhigh)' },
];

/**
 * 에이전트 생성·편집. 비개발자가 정하는 것은 세 가지 — 무슨 일을 하는지 /
 * 어떻게 행동할지 / 어떤 데이터와 도구를 쓸지(6_시각화 ④).
 *
 * 공개 범위(「나만 보기」) 토글은 넣지 않는다 — Q12가 v1 팀 공유 고정을
 * 제안했고 8/12 멘토링에서 확정한다(개발지시 2차 「멘토링 대기」).
 */
export default function AgentEditPage() {
  const navigate = useNavigate();
  const { agentId } = useParams();
  const { showToast } = useToast();
  const existing = findMockAgent(agentId);

  const [name, setName] = useState(existing?.name ?? '');
  const [description, setDescription] = useState(existing?.description ?? '');
  const [instruction, setInstruction] = useState(existing?.instruction ?? '');
  const [model, setModel] = useState<AgentModelId>(existing?.model ?? 'luna');
  const [effort, setEffort] = useState(existing?.model === 'sol' ? 'xhigh' : 'low');
  const [toolIds, setToolIds] = useState<string[]>(existing?.toolIds ?? ['document_search']);

  function toggleTool(id: string) {
    setToolIds((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]));
  }

  function handleSave() {
    // 저장 API(백엔드 단계 2)가 붙기 전까지는 계약만 맞춰 두고 알림으로 대신한다.
    showToast('에이전트 저장은 agent API 연결 후 동작합니다.', 'error');
  }

  return (
    <AppShell>
      <div className={styles.page}>
        <button type="button" className={styles.back} onClick={() => navigate(PATHS.agents)}>
          <Icon name="arrow-left" size={15} color="var(--color-muted)" />
          에이전트
        </button>

        <header className={styles.header}>
          <h1 className={styles.title}>{existing ? existing.name : '새 에이전트'}</h1>
          <p className={styles.subtitle}>
            비개발자가 정하는 것은 세 가지입니다 — 무슨 일을 하는지 / 어떻게 행동할지 / 어떤 데이터와 도구를 쓸지.
          </p>
        </header>

        <section className={styles.card}>
          <div className={styles.cardHead}>
            <h2>Profile</h2>
            <p>이름과 설명은 Chat 선택기에 그대로 보이고, 설명은 “이 요청에 이 에이전트가 맞는가” 판단에도 쓰입니다.</p>
          </div>

          <Input
            label="이름"
            id="agent-name"
            name="agentName"
            placeholder="회의록 정리 에이전트"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <Input
            label="설명 (Description)"
            id="agent-description"
            name="agentDescription"
            placeholder="무엇을 하는 에이전트인지 한 줄로 적어 주세요"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
          <p className={styles.help}>호출 판단에 사용됩니다 — 무엇을 하는 에이전트인지 한 줄로 적어 주세요.</p>
        </section>

        <section className={styles.card}>
          <div className={styles.cardHead}>
            <h2>행동 지시</h2>
            <p>어떻게 일해야 하는지 평소 말로 적어 주세요. 형식이나 문법은 신경 쓰지 않아도 됩니다.</p>
          </div>

          <label className={styles.field}>
            <span className={styles.fieldLabel}>지시문</span>
            <textarea
              className={styles.textarea}
              rows={7}
              value={instruction}
              placeholder="회의록을 읽고 결정된 것과 해야 할 일을 나눠서 정리해줘. 담당자가 없으면 지어내지 말고 미지정으로 남겨."
              onChange={(event) => setInstruction(event.target.value)}
            />
          </label>
        </section>

        <section className={styles.card}>
          <div className={styles.cardHead}>
            <h2>참고 데이터 · 도구</h2>
            <p>에이전트가 무엇을 읽고 무엇을 할 수 있는지 정합니다.</p>
          </div>

          <div className={styles.selectRow}>
            <label className={styles.field}>
              <span className={styles.fieldLabel}>모델</span>
              <Select
                options={AGENT_MODELS}
                value={model}
                onChange={(event) => setModel(event.target.value as AgentModelId)}
              />
            </label>
            <label className={styles.field}>
              <span className={styles.fieldLabel}>응답 방식</span>
              <Select options={EFFORT_OPTIONS} value={effort} onChange={(event) => setEffort(event.target.value)} />
            </label>
          </div>

          <div className={styles.field}>
            <span className={styles.fieldLabel}>사용할 도구</span>
            <div className={styles.toolList}>
              {AVAILABLE_TOOLS.map((tool) => {
                const checked = toolIds.includes(tool.id);
                return (
                  <div
                    key={tool.id}
                    className={[styles.toolRow, checked ? styles.toolRowOn : ''].filter(Boolean).join(' ')}
                  >
                    <Checkbox checked={checked} onChange={() => toggleTool(tool.id)} />
                    <div className={styles.toolText}>
                      <strong>{tool.name}</strong>
                      <span>{tool.desc}</span>
                    </div>
                    <span className={styles.toolSource}>{tool.source}</span>
                  </div>
                );
              })}
            </div>
          </div>

          <p className={styles.notice}>
            <Icon name="info" size={15} color="var(--color-info)" />
            <span>쓸 수 있는 도구는 설정 &gt; MCP에서 연결한 서비스에 따라 달라집니다.</span>
            <button type="button" className={styles.noticeLink} onClick={() => navigate(PATHS.settingsMcp)}>
              설정으로 이동 →
            </button>
          </p>
        </section>

        <div className={styles.actions}>
          <span className={styles.actionsNote}>
            저장하면 Chat의 에이전트 선택기에 바로 나타납니다. 별도 테스트 화면 없이 Chat에서 바로 써 보세요.
          </span>
          <Button variant="outline" onClick={() => navigate(PATHS.agents)}>
            취소
          </Button>
          <Button onClick={handleSave}>저장하고 Chat에서 써보기</Button>
        </div>
      </div>
    </AppShell>
  );
}
