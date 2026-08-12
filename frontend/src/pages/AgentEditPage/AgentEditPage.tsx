import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { AppShell, Button, Checkbox, Icon, Input, Select, useToast } from '../../components';
import { createAgent, getAgent, listToolChoices, updateAgent } from '../../api/agents';
import type { ToolChoice } from '../../api/agents';
import { ApiError } from '../../api/client';
import { PATHS } from '../../routes';
import { loadSessionToken } from '../../utils/session';
import { MODEL_SELECT_OPTIONS, DEFAULT_MODEL } from '../../data/models';
import styles from './AgentEditPage.module.css';

/** 서버 `AgentWriteSerializer.AGENT_MODELS` 와 같은 목록이어야 한다. */

// 모델 목록은 `data/models.ts` 하나에서 온다 — 예전에는 여기와 Model 탭과
// 백엔드가 각각 달랐다(2026-08-12).
const EFFORT_OPTIONS = [
  { value: 'low', label: '낮음 (low)' },
  { value: 'medium', label: '보통 (medium)' },
  { value: 'high', label: '높음 (high)' },
  { value: 'xhigh', label: '아주 높음 (xhigh)' },
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
  const token = loadSessionToken();
  // `/agents/new/edit` 이 편집 라우트를 그대로 탄다. 'new' 는 id 가 아니다.
  const editingId = agentId && agentId !== 'new' ? agentId : null;

  const [tools, setTools] = useState<ToolChoice[]>([]);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [instruction, setInstruction] = useState('');
  const [model, setModel] = useState(DEFAULT_MODEL);
  const [effort, setEffort] = useState('low');
  const [maxIterations, setMaxIterations] = useState(6);
  const [toolRefs, setToolRefs] = useState<string[]>(['document_search']);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    listToolChoices(token).then(setTools).catch(() => setError('도구 목록을 불러오지 못했습니다.'));
  }, [token]);

  useEffect(() => {
    if (!token || !editingId) return;
    getAgent(token, editingId)
      .then((agent) => {
        setName(agent.name);
        setDescription(agent.description);
        setInstruction(agent.instruction);
        setModel(agent.model);
        setEffort(agent.reasoning_effort);
        setMaxIterations(agent.max_iterations);
        setToolRefs(agent.tool_refs);
        if (agent.is_prebuilt) {
          // 서버가 저장을 403 으로 막는다. 그 사실을 먼저 알린다 — 다 적고 나서
          // 거절당하는 것보다 낫다.
          setError('기본 제공 에이전트는 수정할 수 없습니다. 새로 만들어 쓰세요.');
        }
      })
      .catch((exc) =>
        setError(exc instanceof ApiError ? exc.message : '에이전트를 불러오지 못했습니다.'),
      );
  }, [token, editingId]);

  function toggleTool(ref: string) {
    setToolRefs((prev) => (prev.includes(ref) ? prev.filter((item) => item !== ref) : [...prev, ref]));
  }

  async function handleSave() {
    if (!token) return;
    if (!name.trim()) {
      setError('이름을 적어 주세요.');
      return;
    }
    setSaving(true);
    setError(null);
    const body = {
      name: name.trim(),
      description,
      instruction,
      model,
      reasoning_effort: effort,
      max_iterations: maxIterations,
      tool_refs: toolRefs,
    };
    try {
      const saved = editingId
        ? await updateAgent(token, editingId, body)
        : await createAgent(token, body);
      showToast(`「${saved.name}」을 저장했습니다. Chat 선택기에서 바로 쓸 수 있습니다.`, 'success');
      navigate(PATHS.chat);
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : '저장하지 못했습니다.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <AppShell>
      <div className={styles.page}>
        <button type="button" className={styles.back} onClick={() => navigate(PATHS.agents)}>
          <Icon name="arrow-left" size={15} color="var(--color-muted)" />
          에이전트
        </button>

        <header className={styles.header}>
          <h1 className={styles.title}>{editingId ? name || '에이전트 편집' : '새 에이전트'}</h1>
          <p className={styles.subtitle}>
            비개발자가 정하는 것은 세 가지입니다 — 무슨 일을 하는지 / 어떻게 행동할지 / 어떤 데이터와 도구를 쓸지.
          </p>
        </header>

        {error && <p className={styles.error}>{error}</p>}

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
                options={MODEL_SELECT_OPTIONS}
                value={model}
                onChange={(event) => setModel(event.target.value)}
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
              {tools.map((tool) => {
                const checked = toolRefs.includes(tool.tool_ref);
                return (
                  <div
                    key={tool.tool_ref}
                    className={[styles.toolRow, checked ? styles.toolRowOn : ''].filter(Boolean).join(' ')}
                  >
                    <Checkbox checked={checked} onChange={() => toggleTool(tool.tool_ref)} />
                    <div className={styles.toolText}>
                      <strong>
                        {tool.name}
                        {/* 승인 게이트를 타는 도구인지 미리 알려준다 — 외부를
                            바꾸는 도구를 붙였다는 사실은 저장 전에 보여야 한다. */}
                        {tool.side_effect && <span className={styles.gate}> · 승인 필요</span>}
                      </strong>
                      <span>{tool.description}</span>
                    </div>
                    <span className={styles.toolSource}>{tool.source}</span>
                  </div>
                );
              })}
              {tools.length === 0 && <p className={styles.help}>쓸 수 있는 도구가 없습니다.</p>}
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
          <Button onClick={handleSave} disabled={saving}>
            {saving ? '저장하는 중…' : '저장하고 Chat에서 써보기'}
          </Button>
        </div>
      </div>
    </AppShell>
  );
}
