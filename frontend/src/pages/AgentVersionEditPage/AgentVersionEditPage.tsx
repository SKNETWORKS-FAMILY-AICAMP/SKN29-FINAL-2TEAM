import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { AppShell, Badge, Button, Icon, Input, Select, useToast } from '../../components';
import { AGENT_STATUS } from '../../data/agentLabels';
import {
  activateAgentVersion,
  createAgentVersion,
  disableAgentVersion,
  getAgentVersion,
  listAgentVersions,
  publishAgentVersion,
} from '../../api/agentVersions';
import type { AgentVersionDetail, AgentVersionStatus, AgentVersionSummary, SubagentRef } from '../../api/agentVersions';
import { listToolChoices, listCustomModels } from '../../api/agents';
import type { CustomModel, ToolChoice } from '../../api/agents';
import { listMcpServers } from '../../api/mcp';
import type { McpServer } from '../../api/mcp';
import { ApiError } from '../../api/client';
import { PATHS } from '../../routes';
import { loadSessionToken } from '../../utils/session';
import { modelSelectOptions, DEFAULT_MODEL } from '../../data/models';
import { ToolPickerModal } from '../AgentEditPage/ToolPickerModal';
import styles from './AgentVersionEditPage.module.css';

const EFFORT_OPTIONS = [
  { value: 'low', label: '낮음 (low)' },
  { value: 'medium', label: '보통 (medium)' },
  { value: 'high', label: '높음 (high)' },
  { value: 'xhigh', label: '아주 높음 (xhigh)' },
];

/**
 * 새 버전 스키마 생성·편집. `AgentEditPage`(옛 비버전 화면)와 나란히 존재한다.
 *
 * **저장이 곧 발행이다.** `agent_versions`는 불변이라(02 §5.2) 임시 저장이라는
 * 중간 상태가 없다 — 저장 버튼을 누르는 순간 새 버전이 생긴다. 그래서 옛
 * 화면에 있던 "임시 저장 / 활성화" 두 단계 구분이 여기서는 "저장(=새 버전
 * 발행) / 활성화" 두 단계로 바뀐다: 저장은 몇 번이든 다시 할 수 있지만(그때마다
 * 버전이 늘어난다), 활성화는 그 중 최신 버전을 Chat/위임 대상으로 여는 별도
 * 스텝이다.
 *
 * **저장 전 테스트 실행은 없다** — 새 실행 엔진용 테스트 엔드포인트가 아직
 * 없어서(2026-08-15 확인) 이번 v1 화면에서는 뺐다. 필요해지면 옛
 * `TestRunModal`과 같은 자리에 추가한다.
 */
export default function AgentVersionEditPage() {
  const navigate = useNavigate();
  const { agentId } = useParams();
  const { showToast } = useToast();
  const token = loadSessionToken();
  const editingId = agentId && agentId !== 'new' ? agentId : null;

  const [tools, setTools] = useState<ToolChoice[]>([]);
  const [mcpServers, setMcpServers] = useState<McpServer[]>([]);
  const [customModels, setCustomModels] = useState<CustomModel[] | null>(null);
  const [otherAgents, setOtherAgents] = useState<AgentVersionSummary[]>([]);
  const [pickerOpen, setPickerOpen] = useState(false);

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [model, setModel] = useState<string>(DEFAULT_MODEL);
  const [effort, setEffort] = useState('low');
  const [maxIterations, setMaxIterations] = useState(6);
  const [toolRefs, setToolRefs] = useState<string[]>([]);
  const [subagents, setSubagents] = useState<SubagentRef[]>([]);
  const [subagentFormOpen, setSubagentFormOpen] = useState(false);
  const [subagentChildId, setSubagentChildId] = useState('');

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedId, setSavedId] = useState<string | null>(editingId);
  const [status, setStatus] = useState<AgentVersionStatus | null>(editingId ? null : 'DRAFT');
  const [currentVersion, setCurrentVersion] = useState<number | null>(null);

  useEffect(() => {
    if (!token) return;
    listToolChoices(token).then(setTools).catch(() => setError('도구 목록을 불러오지 못했습니다.'));
    listMcpServers(token).then(setMcpServers).catch(() => {});
    listCustomModels(token).then(setCustomModels).catch(() => {});
    // 서브 에이전트 후보 — 자기 자신은 아래 렌더링에서 뺀다.
    listAgentVersions(token).then(setOtherAgents).catch(() => {});
  }, [token]);

  useEffect(() => {
    if (!token || !editingId) return;
    getAgentVersion(token, editingId)
      .then((agent: AgentVersionDetail) => {
        setName(agent.name);
        setDescription(agent.description);
        setSystemPrompt(agent.system_prompt);
        setModel(agent.model ?? DEFAULT_MODEL);
        setEffort(agent.reasoning_effort ?? 'low');
        setMaxIterations(agent.max_iterations ?? 6);
        setToolRefs(agent.tool_refs);
        setSubagents(agent.subagents);
        setStatus(agent.status);
        setCurrentVersion(agent.version);
      })
      .catch((exc) =>
        setError(exc instanceof ApiError ? exc.message : '에이전트를 불러오지 못했습니다.'),
      );
  }, [token, editingId]);

  const modelOptions = useMemo(() => {
    const options = modelSelectOptions(customModels ?? []);
    if (!model || options.some((option) => option.value === model)) return options;
    const label = customModels === null ? model : `${model} · 지금은 쓸 수 없음`;
    return [...options, { value: model, label }];
  }, [customModels, model]);

  /** 자기 자신은 뺀다 — 자기 참조는 서버가 어차피 409로 막지만, 화면에서
   * 애초에 고를 수 없게 하는 편이 낫다. */
  const subagentCandidates = useMemo(
    () => otherAgents.filter((a) => a.agent_id !== savedId && a.current_version_id !== null),
    [otherAgents, savedId],
  );

  function toggleTool(ref: string) {
    setToolRefs((prev) => (prev.includes(ref) ? prev.filter((item) => item !== ref) : [...prev, ref]));
  }

  /** 도구 선택 화면의 그룹(카테고리) 마스터 체크박스용(2026-08-18). */
  function toggleToolGroup(refs: string[], turnOn: boolean) {
    setToolRefs((prev) =>
      turnOn
        ? [...prev, ...refs.filter((ref) => !prev.includes(ref))]
        : prev.filter((item) => !refs.includes(item)),
    );
  }

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

  function agentName(agentId: string): string {
    return otherAgents.find((a) => a.agent_id === agentId)?.name ?? agentId;
  }

  /** alias·위임 설명은 별도로 안 받는다 — 고르는 에이전트 자신의 이름·설명을
   * 그대로 스냅샷으로 쓴다(부모가 저장된 뒤 자식 이름이 바뀌어도 이 부모는
   * 지금 값을 계속 쓴다, 위 subagentCandidates 주석과 같은 이유). */
  function addSubagent() {
    const candidate = subagentCandidates.find((a) => a.agent_id === subagentChildId);
    if (!candidate || !candidate.current_version_id) return;
    if (!candidate.description.trim()) {
      setError(`"${candidate.name}"에 설명이 없어 서브 에이전트로 추가할 수 없습니다. 그 에이전트의 설명을 먼저 채워 주세요.`);
      return;
    }
    if (subagents.some((s) => s.child_agent_id === candidate.agent_id)) {
      setError('이미 추가한 서브 에이전트입니다.');
      return;
    }
    if (subagents.some((s) => s.alias === candidate.name.trim())) {
      setError(`이미 추가한 서브 에이전트와 이름이 같습니다("${candidate.name}"). 한쪽 이름을 바꿔 주세요.`);
      return;
    }
    setSubagents((prev) => [
      ...prev,
      {
        child_agent_id: candidate.agent_id,
        child_version_id: candidate.current_version_id!,
        alias: candidate.name.trim(),
        delegation_description: candidate.description.trim(),
      },
    ]);
    setSubagentChildId('');
    setSubagentFormOpen(false);
    setError(null);
  }

  function removeSubagent(childAgentId: string) {
    setSubagents((prev) => prev.filter((s) => s.child_agent_id !== childAgentId));
  }

  /** 저장 = 새 버전 발행. 처음 만드는 에이전트는 여기서 생겨나 이후로는
   * publishAgentVersion으로 이어진다(버전 번호가 늘어난다). */
  async function saveVersion(): Promise<AgentVersionDetail> {
    if (!token) throw new Error('세션이 없습니다.');
    const body = {
      name: name.trim(),
      description,
      system_prompt: systemPrompt,
      model,
      reasoning_effort: effort,
      max_iterations: maxIterations,
      tool_refs: toolRefs,
      subagents,
    };
    const saved = savedId
      ? await publishAgentVersion(token, savedId, body)
      : await createAgentVersion(token, body);
    setStatus(saved.status);
    setCurrentVersion(saved.version);
    if (!savedId) {
      setSavedId(saved.agent_id);
      navigate(PATHS.agentVersionEdit.replace(':agentId', saved.agent_id), { replace: true });
    }
    return saved;
  }

  async function handleSave() {
    if (!token) return;
    if (!name.trim()) {
      setError('이름을 적어 주세요.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const saved = await saveVersion();
      showToast(`v${saved.version}로 저장했습니다. Chat에서 쓰려면 활성화가 필요합니다.`, 'success');
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : '저장하지 못했습니다.');
    } finally {
      setSaving(false);
    }
  }

  async function handleActivate() {
    if (!token || !savedId) return;
    setSaving(true);
    setError(null);
    try {
      const activated = await activateAgentVersion(token, savedId);
      setStatus(activated.status);
      showToast(`「${activated.name}」을 활성화했습니다.`, 'success');
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
      const disabled = await disableAgentVersion(token, savedId);
      setStatus(disabled.status);
      showToast(`「${disabled.name}」을 사용 중지했습니다.`, 'success');
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : '사용 중지하지 못했습니다.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <AppShell>
      <div className={styles.page}>
        <button type="button" className={styles.back} onClick={() => navigate(PATHS.agentVersions)}>
          <Icon name="arrow-left" size={15} color="var(--color-muted)" />
          에이전트
        </button>

        <header className={styles.header}>
          <div className={styles.titleRow}>
            <h1 className={styles.title}>{savedId ? name || '에이전트 편집' : '새 에이전트'}</h1>
            {status && <Badge tone={AGENT_STATUS[status].tone}>{AGENT_STATUS[status].label}</Badge>}
            {currentVersion !== null && <Badge tone="neutral">v{currentVersion}</Badge>}
          </div>
          <p className={styles.subtitle}>
            저장할 때마다 새 버전이 발행됩니다. 발행된 버전은 이후 고칠 수 없습니다.
          </p>
        </header>

        {error && <p className={styles.error}>{error}</p>}

        <section className={styles.card}>
          <div className={styles.cardHead}>
            <h2>Profile</h2>
            <p>이름과 설명은 다른 에이전트가 이 에이전트를 서브 에이전트로 고를 때 판단 근거가 됩니다.</p>
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
        </section>

        <section className={styles.card}>
          <div className={styles.cardHead}>
            <h2>행동 지시 (System Prompt)</h2>
            <p>어떻게 일해야 하는지 평소 말로 적어 주세요.</p>
          </div>
          <label className={styles.field}>
            <span className={styles.fieldLabel}>System Prompt</span>
            <textarea
              className={styles.textarea}
              rows={7}
              value={systemPrompt}
              placeholder="회의록을 읽고 결정된 것과 해야 할 일을 나눠서 정리해줘. 담당자가 없으면 지어내지 말고 미지정으로 남겨."
              onChange={(event) => setSystemPrompt(event.target.value)}
            />
          </label>
        </section>

        <section className={styles.card}>
          <div className={styles.cardHead}>
            <h2>모델 · 도구</h2>
            <p>에이전트가 어떤 모델로 돌지, 무엇을 할 수 있는지 정합니다.</p>
          </div>

          <div className={styles.selectRow}>
            <label className={styles.field}>
              <span className={styles.fieldLabel}>모델</span>
              <Select options={modelOptions} value={model} onChange={(event) => setModel(event.target.value)} />
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
        </section>

        <section className={styles.card}>
          <div className={styles.cardHead}>
            <h2>서브 에이전트</h2>
            <p>
              이 에이전트가 위임할 다른 에이전트를 고릅니다. 고른 자식은 **지금 발행된 버전**에 고정됩니다 —
              자식이 나중에 새 버전을 내도 이 부모는 계속 지금 고른 버전을 씁니다.
            </p>
          </div>

          <div className={styles.subagentList}>
            {subagents.length === 0 && <p className={styles.help}>아직 고른 서브 에이전트가 없습니다.</p>}
            {subagents.map((sub) => (
              <div key={sub.child_agent_id} className={styles.subagentRow}>
                <div className={styles.subagentText}>
                  <strong>{agentName(sub.child_agent_id)}</strong>
                  <span>{sub.delegation_description}</span>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => removeSubagent(sub.child_agent_id)}
                  aria-label={`${agentName(sub.child_agent_id)} 빼기`}
                >
                  <Icon name="x" size={13} />
                </Button>
              </div>
            ))}
          </div>

          {subagentFormOpen ? (
            <div className={styles.subagentForm}>
              <label className={styles.field}>
                <span className={styles.fieldLabel}>대상 에이전트</span>
                <Select
                  options={[
                    { value: '', label: '선택하세요' },
                    ...subagentCandidates.map((a) => ({ value: a.agent_id, label: `${a.name} (v${a.version})` })),
                  ]}
                  value={subagentChildId}
                  onChange={(event) => setSubagentChildId(event.target.value)}
                />
              </label>
              {subagentChildId && (
                <p className={styles.help}>
                  이 에이전트의 이름·설명을 그대로 위임 판단 근거로 씁니다:{' '}
                  <em>
                    {subagentCandidates.find((a) => a.agent_id === subagentChildId)?.description ||
                      '(설명 없음 — 위 Profile에서 채워 주세요)'}
                  </em>
                </p>
              )}
              <div className={styles.subagentFormActions}>
                <Button type="button" variant="outline" onClick={() => setSubagentFormOpen(false)}>
                  취소
                </Button>
                <Button type="button" onClick={addSubagent} disabled={!subagentChildId}>
                  추가
                </Button>
              </div>
            </div>
          ) : (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setSubagentFormOpen(true)}
              disabled={subagentCandidates.length === 0}
            >
              서브 에이전트 추가
            </Button>
          )}
          {subagentCandidates.length === 0 && (
            <p className={styles.help}>고를 수 있는 다른 에이전트가 아직 없습니다 — 먼저 다른 에이전트를 하나 저장해 주세요.</p>
          )}
        </section>

        <ToolPickerModal
          open={pickerOpen}
          onClose={() => setPickerOpen(false)}
          builtinTools={tools.filter((tool) => !tool.tool_ref.startsWith('mcp:'))}
          mcpServers={mcpServers}
          toolRefs={toolRefs}
          onToggle={toggleTool}
          onToggleGroup={toggleToolGroup}
          onGoToMcpSettings={() => {
            setPickerOpen(false);
            navigate(PATHS.settingsMcp);
          }}
        />

        <div className={styles.actions}>
          <span className={styles.actionsNote}>
            {status === 'ACTIVE'
              ? '저장하면 새 버전이 발행되고, 바로 그 버전으로 옮겨갑니다.'
              : '저장은 몇 번이든 다시 할 수 있습니다. 활성화해야 Chat/위임 대상으로 열립니다.'}
          </span>
          <Button variant="outline" onClick={() => navigate(PATHS.agentVersions)}>
            취소
          </Button>
          {status === 'ACTIVE' && (
            <Button variant="outline" onClick={handleDisable} disabled={saving}>
              사용 중지
            </Button>
          )}
          {(status === 'DRAFT' || status === 'DISABLED') && savedId && (
            <Button variant="outline" onClick={handleActivate} disabled={saving}>
              {saving ? '처리하는 중…' : '활성화'}
            </Button>
          )}
          <Button onClick={handleSave} disabled={saving}>
            {saving ? '저장하는 중…' : '저장 (새 버전 발행)'}
          </Button>
        </div>
      </div>
    </AppShell>
  );
}
