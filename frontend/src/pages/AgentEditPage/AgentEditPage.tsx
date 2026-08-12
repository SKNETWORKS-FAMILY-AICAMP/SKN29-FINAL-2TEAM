import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { AppShell, Badge, Button, Icon, Input, Select, useToast } from '../../components';
import type { BadgeTone } from '../../components';
import {
  activateAgent,
  checkBuilderInput,
  createAgent,
  disableAgent,
  getAgent,
  listToolChoices,
  updateAgent,
} from '../../api/agents';
import type { Agent, ToolChoice } from '../../api/agents';
import { listMcpServers } from '../../api/mcp';
import type { McpServer } from '../../api/mcp';
import { ApiError } from '../../api/client';
import { PATHS } from '../../routes';
import { loadSessionToken } from '../../utils/session';
import { TestRunModal } from './TestRunModal';
import { ToolPickerModal } from './ToolPickerModal';
import styles from './AgentEditPage.module.css';

/** 서버 `AgentWriteSerializer.AGENT_MODELS` 와 같은 목록이어야 한다. */
const MODEL_OPTIONS = [
  { value: 'gpt-5.6-luna', label: 'gpt-5.6 luna — 짧은 판단 · 빠름' },
  { value: 'gpt-5.6-terra', label: 'gpt-5.6 terra — 일반' },
  { value: 'gpt-5.6-sol', label: 'gpt-5.6 sol — 긴 추론 · 느리고 비쌈' },
];

const EFFORT_OPTIONS = [
  { value: 'low', label: '낮음 (low)' },
  { value: 'medium', label: '보통 (medium)' },
  { value: 'high', label: '높음 (high)' },
  { value: 'xhigh', label: '아주 높음 (xhigh)' },
];

const STATUS_LABEL: Record<Agent['status'], { tone: BadgeTone; label: string }> = {
  DRAFT: { tone: 'neutral', label: '초안' },
  ACTIVE: { tone: 'success', label: '활성' },
  DISABLED: { tone: 'warning', label: '비활성' },
};

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
  const [mcpServers, setMcpServers] = useState<McpServer[]>([]);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [instruction, setInstruction] = useState('');
  const [model, setModel] = useState('gpt-5.6-luna');
  const [effort, setEffort] = useState('low');
  const [maxIterations, setMaxIterations] = useState(6);
  const [toolRefs, setToolRefs] = useState<string[]>(['document_search']);
  const [testRunOpen, setTestRunOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // URL 의 `editingId`와 별개로 둔다 — 「임시 저장」으로 처음 생겨난 에이전트는
  // 라우터가 아직 못 따라온 사이에도 곧바로 update 로 이어져야 한다.
  const [savedId, setSavedId] = useState<string | null>(editingId);
  // 새 에이전트는 아직 생성 전이라도 DRAFT 로 취급한다 — 버튼 구성이 그 기준이다.
  // 기존 에이전트는 불러오기 전까지 null 로 두어 「임시 저장/활성화」 쌍이
  // 잘못 잠깐 보이지 않게 한다.
  const [agentStatus, setAgentStatus] = useState<Agent['status'] | null>(editingId ? null : 'DRAFT');

  useEffect(() => {
    if (!token) return;
    listToolChoices(token).then(setTools).catch(() => setError('도구 목록을 불러오지 못했습니다.'));
    // MCP 서버 목록은 팝업의 「MCP 서버 선택」 탭이 쓴다. 못 불러와도 도구
    // 선택 자체는 막지 않는다 — 조용히 빈 목록으로 둔다.
    listMcpServers(token).then(setMcpServers).catch(() => {});
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
        setAgentStatus(agent.status);
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

  /** 칩에 표시할 이름. 내장 도구는 카탈로그에서, MCP 도구는 서버 목록에서 찾는다. */
  function toolLabel(ref: string): string {
    const fromCatalog = tools.find((item) => item.tool_ref === ref);
    if (fromCatalog) return fromCatalog.name;
    if (ref.startsWith('mcp:')) {
      const mcpToolId = ref.slice('mcp:'.length);
      for (const server of mcpServers) {
        const found = server.tools.find((item) => item.mcp_tool_id === mcpToolId);
        if (found) return found.name;
      }
    }
    return ref;
  }

  /**
   * 검증 없이 그대로 create/update 한다. 「임시 저장」과 「활성화」가 공유하는
   * 첫 단계 — 활성화도 결국 지금 화면 내용을 먼저 저장한 뒤에야 검증한다.
   *
   * 처음 만드는 에이전트(`savedId` 없음)는 여기서 생겨나 이후로는 update 로
   * 이어진다. `replace: true` 로 URL 만 바꿔치기해 뒤로가기를 눌러도 빈 폼이
   * 다시 뜨지 않게 한다.
   */
  async function saveDraft(): Promise<Agent> {
    if (!token) throw new Error('세션이 없습니다.');
    const body = {
      name: name.trim(),
      description,
      instruction,
      model,
      reasoning_effort: effort,
      max_iterations: maxIterations,
      tool_refs: toolRefs,
    };
    const saved = savedId ? await updateAgent(token, savedId, body) : await createAgent(token, body);
    setAgentStatus(saved.status);
    if (!savedId) {
      setSavedId(saved.agent_id);
      navigate(PATHS.agentEdit.replace(':agentId', saved.agent_id), { replace: true });
    }
    return saved;
  }

  async function handleTempSave() {
    if (!token) return;
    if (!name.trim()) {
      setError('이름을 적어 주세요.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await saveDraft();
      showToast('임시 저장했습니다. 활성화해야 Chat에서 위임 대상으로 쓰입니다.', 'success');
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : '저장하지 못했습니다.');
    } finally {
      setSaving(false);
    }
  }

  /** DRAFT/DISABLED → ACTIVE. 지금 내용을 먼저 저장한 뒤, 그 저장된 값으로
   * 서버가 다시 검증한다(`activateAgent`). `reject`(409)면 에이전트는 이미
   * DRAFT 로 저장돼 있으니 입력한 내용을 잃지 않는다. */
  async function handleActivate() {
    if (!token) return;
    if (!name.trim()) {
      setError('이름을 적어 주세요.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const draft = await saveDraft();
      const activated = await activateAgent(token, draft.agent_id);
      setAgentStatus(activated.status);
      showToast(`「${activated.name}」을 활성화했습니다. Chat에서 바로 쓸 수 있습니다.`, 'success');
      navigate(PATHS.chat);
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : '활성화하지 못했습니다.');
    } finally {
      setSaving(false);
    }
  }

  async function handleDisable() {
    if (!token || !savedId) return;
    setSaving(true);
    setError(null);
    try {
      const disabled = await disableAgent(token, savedId);
      setAgentStatus(disabled.status);
      showToast(`「${disabled.name}」을 비활성화했습니다.`, 'success');
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : '비활성화하지 못했습니다.');
    } finally {
      setSaving(false);
    }
  }

  /** ACTIVE 에이전트 편집 저장. 이미 쓰이고 있는 에이전트라 저장 전에 계속
   * 검증한다 — `reject`면 저장 자체를 막는다(기존 동작 그대로 유지). */
  async function handleSaveActive() {
    if (!token || !savedId) return;
    setSaving(true);
    setError(null);
    try {
      const check = await checkBuilderInput(token, {
        name: name.trim(),
        description,
        behavior: instruction,
        tool_refs: toolRefs,
      });
      if (check.overall === 'reject') {
        setError(
          check.reject_reason ||
            '설명 또는 지시문 내용이 너무 부족해 저장할 수 없습니다. 「테스트로 실행해보기」의 1단계에서 내용을 다시 써 주세요.',
        );
        setSaving(false);
        return;
      }
    } catch {
      // 검증 서비스 자체가 실패하면 그것 때문에 저장까지 막지 않는다.
    }

    try {
      const saved = await saveDraft();
      showToast(`「${saved.name}」을 저장했습니다.`, 'success');
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
          <div className={styles.titleRow}>
            <h1 className={styles.title}>{savedId ? name || '에이전트 편집' : '새 에이전트'}</h1>
            {agentStatus && (
              <Badge tone={STATUS_LABEL[agentStatus].tone}>{STATUS_LABEL[agentStatus].label}</Badge>
            )}
          </div>
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
                options={MODEL_OPTIONS}
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
            <div className={styles.toolSummary}>
              {toolRefs.length === 0 && <p className={styles.help}>아직 고른 도구가 없습니다.</p>}
              {toolRefs.map((ref) => (
                <span key={ref} className={styles.toolChip}>
                  {toolLabel(ref)}
                  <button type="button" aria-label={`${toolLabel(ref)} 빼기`} onClick={() => toggleTool(ref)}>
                    <Icon name="x" size={11} />
                  </button>
                </span>
              ))}
            </div>
            <Button type="button" variant="outline" size="sm" onClick={() => setPickerOpen(true)}>
              도구 선택
            </Button>
          </div>

          <p className={styles.notice}>
            <Icon name="info" size={15} color="var(--color-info)" />
            <span>쓸 수 있는 도구는 설정 &gt; MCP에서 연결한 서비스에 따라 달라집니다.</span>
            <button type="button" className={styles.noticeLink} onClick={() => navigate(PATHS.settingsMcp)}>
              설정으로 이동 →
            </button>
          </p>
        </section>

        <ToolPickerModal
          open={pickerOpen}
          onClose={() => setPickerOpen(false)}
          builtinTools={tools.filter((tool) => !tool.tool_ref.startsWith('mcp:'))}
          mcpServers={mcpServers}
          toolRefs={toolRefs}
          onToggle={toggleTool}
          onGoToMcpSettings={() => {
            setPickerOpen(false);
            navigate(PATHS.settingsMcp);
          }}
        />

        <section className={styles.card}>
          <div className={styles.cardHead}>
            <h2>테스트로 실행해보기</h2>
            <p>저장하기 전에 지금 이름·설명·지시문·도구 설정 그대로 검증하고, 대화로 한 번 돌려 봅니다.</p>
          </div>
          <Button type="button" variant="outline" onClick={() => setTestRunOpen(true)}>
            테스트로 실행해보기
          </Button>
        </section>

        <TestRunModal
          open={testRunOpen}
          onClose={() => setTestRunOpen(false)}
          token={token}
          name={name}
          description={description}
          instruction={instruction}
          toolRefs={toolRefs}
          model={model}
          reasoningEffort={effort}
          maxIterations={maxIterations}
          allTools={tools}
          onApplyInstruction={setInstruction}
          onApplyDescription={setDescription}
        />

        <div className={styles.actions}>
          <span className={styles.actionsNote}>
            {agentStatus === 'ACTIVE'
              ? '저장하면 바로 반영됩니다.'
              : agentStatus === 'DISABLED'
                ? '다시 활성화해야 Chat에서 위임 대상으로 쓰입니다.'
                : '임시 저장은 언제든 가능합니다. 활성화해야 Chat에서 위임 대상으로 쓰입니다.'}
          </span>
          <Button variant="outline" onClick={() => navigate(PATHS.agents)}>
            취소
          </Button>

          {agentStatus === 'ACTIVE' && (
            <>
              <Button variant="outline" onClick={handleDisable} disabled={saving}>
                사용 중지
              </Button>
              <Button onClick={handleSaveActive} disabled={saving}>
                {saving ? '저장하는 중…' : '저장'}
              </Button>
            </>
          )}

          {(agentStatus === 'DRAFT' || agentStatus === 'DISABLED') && (
            <>
              <Button variant="outline" onClick={handleTempSave} disabled={saving}>
                {saving ? '저장하는 중…' : '임시 저장'}
              </Button>
              <Button onClick={handleActivate} disabled={saving}>
                {saving ? '처리하는 중…' : agentStatus === 'DISABLED' ? '다시 활성화' : '활성화'}
              </Button>
            </>
          )}
        </div>
      </div>
    </AppShell>
  );
}
