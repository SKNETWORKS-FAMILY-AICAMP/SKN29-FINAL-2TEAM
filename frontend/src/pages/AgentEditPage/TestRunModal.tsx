import { useEffect, useState } from 'react';
import { Badge, Button, Icon, Input, Modal } from '../../components';
import type { BadgeTone } from '../../components';
import { runBuilderTest } from '../../api/agents';
import type { BuilderTestEvent, ToolChoice } from '../../api/agents';
import { ApiError } from '../../api/client';
import { InstructionCheckPanel } from './InstructionCheckPanel';
import { ToolCheckPanel } from './ToolCheckPanel';
import pageStyles from './AgentEditPage.module.css';
import styles from './TestRunModal.module.css';

type Stage = 'check' | 'chat';

const STAGES: { key: Stage; label: string }[] = [
  { key: 'check', label: '검증' },
  { key: 'chat', label: '대화 테스트' },
];

interface TestStep {
  key: string;
  toolRef: string;
  toolName: string;
  status: 'running' | 'OK' | 'FAILED' | 'SIMULATED';
  errorCode?: string;
  arguments?: Record<string, unknown>;
}

export interface TestRunModalProps {
  open: boolean;
  onClose: () => void;
  token: string | null;
  name: string;
  description: string;
  instruction: string;
  toolRefs: string[];
  model: string;
  reasoningEffort: string;
  maxIterations: number;
  allTools: ToolChoice[];
  onApplyInstruction: (text: string) => void;
  onApplyDescription: (text: string) => void;
  /** 도구 확인 섹션에서 칩의 × 로 도구 하나를 뺀다. */
  onToggleTool: (ref: string) => void;
  /** 도구 확인 섹션의 「도구 추가/제외」 — 메인 화면과 같은 선택 팝업을 연다. */
  onOpenToolPicker: () => void;
}

const STATUS_LABEL: Record<TestStep['status'], { tone: BadgeTone; label: string }> = {
  running: { tone: 'info', label: '실행 중' },
  OK: { tone: 'success', label: '성공' },
  FAILED: { tone: 'danger', label: '실패' },
  SIMULATED: { tone: 'warning', label: '시뮬레이션 (실제로 부르지 않음)' },
};

/**
 * 저장 전 검증 → 대화 테스트 2단계 스테퍼.
 *
 * 1단계(코드 검증 + LLM 의미 검증·보정)에서 확정한 설명·지시문은 콜백으로
 * 부모(`AgentEditPage`)의 상태에 반영되고, 그 상태가 2단계 대화 테스트의
 * 입력이 된다. 개별 도구를 모델 판단 없이 직접 불러보는 확인은 2단계 안의
 * 선택적 보조 기능으로 접혀 들어간다. 모달을 열 때마다 1단계로 리셋한다.
 */
export function TestRunModal({
  open,
  onClose,
  token,
  name,
  description,
  instruction,
  toolRefs,
  model,
  reasoningEffort,
  maxIterations,
  allTools,
  onApplyInstruction,
  onApplyDescription,
  onToggleTool,
  onOpenToolPicker,
}: TestRunModalProps) {
  const [stage, setStage] = useState<Stage>('check');
  const [userInput, setUserInput] = useState('');
  const [running, setRunning] = useState(false);
  const [steps, setSteps] = useState<TestStep[]>([]);
  const [statusLine, setStatusLine] = useState<string | null>(null);
  const [resultText, setResultText] = useState<string | null>(null);
  const [resultComplete, setResultComplete] = useState(false);
  const [resultGrounded, setResultGrounded] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 검증 패널이 알려주는 최신 설명·지시문·"다음 단계로 넘어가도 되는가".
  const [checkedDescription, setCheckedDescription] = useState(description);
  const [checkedInstruction, setCheckedInstruction] = useState(instruction);
  const [canProceed, setCanProceed] = useState(false);

  useEffect(() => {
    if (open) {
      setStage('check');
      setUserInput('');
      setSteps([]);
      setStatusLine(null);
      setResultText(null);
      setResultComplete(false);
      setResultGrounded(null);
      setError(null);
      setCheckedDescription(description);
      setCheckedInstruction(instruction);
      setCanProceed(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  async function run() {
    if (!token || !userInput.trim() || running) return;
    setRunning(true);
    setSteps([]);
    setResultText(null);
    setResultComplete(false);
    setResultGrounded(null);
    setError(null);
    setStatusLine('시작하는 중…');
    let stepId = 0;
    try {
      await runBuilderTest(
        token,
        {
          instruction: checkedInstruction,
          tool_refs: toolRefs,
          model,
          reasoning_effort: reasoningEffort,
          max_iterations: maxIterations,
          user_input: userInput.trim(),
        },
        (event: BuilderTestEvent) => {
          switch (event.type) {
            case 'stage':
              setStatusLine(`생각하는 중 (${event.step}/${event.total})`);
              break;
            case 'tool_call_started':
              stepId += 1;
              setSteps((prev) => [
                ...prev,
                { key: String(stepId), toolRef: event.tool_ref, toolName: event.tool_name, status: 'running' },
              ]);
              setStatusLine(`「${event.tool_name}」 부르는 중`);
              break;
            case 'tool_call_finished':
              setSteps((prev) => {
                if (prev.length === 0) return prev;
                const next = [...prev];
                next[next.length - 1] = {
                  ...next[next.length - 1],
                  status: event.status,
                  errorCode: event.error_code,
                  arguments: event.arguments,
                };
                return next;
              });
              break;
            case 'result':
              setStatusLine(event.complete ? '완료' : `중단됨 (${event.stopped_reason ?? '알 수 없음'})`);
              setResultText(event.text || '');
              setResultComplete(event.complete);
              setResultGrounded(event.grounded ?? null);
              break;
            case 'error':
              setError(event.detail);
              break;
            default:
              break;
          }
        },
      );
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : '테스트 실행에 실패했습니다.');
    } finally {
      setRunning(false);
    }
  }

  const toolByRef = new Map(allTools.map((tool) => [tool.tool_ref, tool]));
  const calledRefs = new Set(steps.map((step) => step.toolRef));
  const uncalledRefs = toolRefs.filter((ref) => !calledRefs.has(ref));

  /** 1단계 검증을 통과(`canProceed`)해야만 2단계로 넘어간다. 설명·지시문은
   * `onStateChange`가 이미 실시간으로 부모 폼에 반영해 둔 상태라 여기서
   * 따로 넘길 게 없다 — 상단 탭과 하단 버튼이 이 함수 하나를 공유해야
   * 탭을 눌러 검증을 우회하는 구멍이 없다. */
  function moveToChatStage() {
    if (!canProceed) return;
    setStage('chat');
  }

  function moveToStage(next: Stage) {
    if (next === 'check') {
      setStage('check');
      return;
    }
    moveToChatStage();
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="검증"
      width={560}
      dismissible={!running}
      footer={
        <Button variant="outline" onClick={onClose} disabled={running}>
          닫기
        </Button>
      }
    >
      <div className={styles.tabs} role="tablist">
        {STAGES.map((s, index) => {
          const disabled = s.key === 'chat' && !canProceed;
          return (
            <button
              key={s.key}
              type="button"
              role="tab"
              aria-selected={stage === s.key}
              disabled={disabled}
              aria-disabled={disabled}
              className={[styles.tab, stage === s.key ? styles.tabOn : ''].filter(Boolean).join(' ')}
              onClick={() => moveToStage(s.key)}
            >
              {index + 1}. {s.label}
            </button>
          );
        })}
      </div>

      {stage === 'check' && (
        <>
          <InstructionCheckPanel
            token={token}
            name={name}
            toolRefs={toolRefs}
            description={description}
            instruction={instruction}
            onStateChange={(desc, instr, proceedable) => {
              setCheckedDescription(desc);
              setCheckedInstruction(instr);
              setCanProceed(proceedable);
              // 팝업 안의 편집 내용을 그 자리에서 부모(실제 저장 대상)로 흘려
              //보낸다. 예전엔 「다음 단계: 대화 테스트」를 눌러야만 반영됐는데,
              // 그 전에 팝업을 닫으면(제안 적용 후 그냥 닫기 등) 방금 통과시킨
              // 내용이 저장 대상에는 전혀 안 실린 채로 사라졌다 — 저장하면
              // 여전히 적용 전(warn이었던) 문장이 나갔다.
              onApplyDescription(desc);
              onApplyInstruction(instr);
            }}
          />
          <div className={styles.stepActions}>
            <Button disabled={!canProceed} onClick={moveToChatStage}>
              다음 단계: 대화 테스트
            </Button>
          </div>
        </>
      )}

      {stage === 'chat' && (
        <>
          <button type="button" className={styles.stageBack} onClick={() => setStage('check')}>
            ← 1단계로 돌아가기
          </button>
          <p className={pageStyles.help}>
            저장하지 않고 지금 설정 그대로 한 번 돌려봅니다. 어떤 도구를 부를지는 모델이 정합니다
            — 모델이 안 부른 도구는 여기서 확인되지 않습니다. 승인이 필요한 도구(Jira 등록·수정
            등)는 실제로 부르지 않고 어떤 값으로 부르려 했는지만 보여줍니다.
          </p>
          <div className={styles.inputRow}>
            <Input
              label="테스트로 보낼 메시지"
              id="test-run-input"
              name="testRunInput"
              placeholder="예: 이번 주 마감인 업무 알려줘"
              value={userInput}
              disabled={running}
              onChange={(event) => setUserInput(event.target.value)}
            />
            <Button onClick={run} disabled={running || !userInput.trim()}>
              {running ? '실행 중…' : '실행'}
            </Button>
          </div>
          {error && <p className={pageStyles.error}>{error}</p>}
          {(statusLine || steps.length > 0) && (
            <div className={styles.trace}>
              {statusLine && (
                <p className={styles.statusLine}>
                  {running && <Icon name="loader" size={14} spin />}
                  {statusLine}
                </p>
              )}
              {steps.length === 0 && !running && (
                <p className={pageStyles.help}>도구를 하나도 부르지 않고 바로 답했습니다.</p>
              )}
              {steps.map((step, index) => {
                const chip = STATUS_LABEL[step.status];
                return (
                  <div key={step.key} className={styles.step}>
                    <span className={styles.stepOrder}>{index + 1}</span>
                    <div className={styles.stepBody}>
                      <span className={styles.stepName}>
                        {step.toolName}
                        <Badge tone={chip.tone}>{chip.label}</Badge>
                      </span>
                      {step.status === 'FAILED' && step.errorCode && (
                        <span className={pageStyles.help}>오류: {step.errorCode}</span>
                      )}
                      {step.arguments && Object.keys(step.arguments).length > 0 && (
                        <pre className={styles.args}>{JSON.stringify(step.arguments, null, 2)}</pre>
                      )}
                    </div>
                  </div>
                );
              })}
              {resultText !== null && (
                <div className={styles.resultBox}>
                  <span className={pageStyles.fieldLabel}>최종 답변</span>
                  <p>{resultText || '(도구만 부르고 답변 텍스트는 남기지 않았습니다)'}</p>
                </div>
              )}
              {resultComplete && resultGrounded === false && (
                <p className={pageStyles.error}>
                  이 답변은 쓸 수 있는 도구를 하나도 안 부르고 나왔습니다 — 근거 없이 단정한 내용일
                  수 있습니다. 아래 「도구 확인」에서 관련 도구를 직접 불러 사실 여부를 확인해
                  보세요.
                </p>
              )}
              {resultComplete && toolRefs.length > 0 && (
                <div className={styles.step}>
                  <div className={styles.stepBody}>
                    <span className={styles.stepName}>선택한 도구 대비 호출 결과</span>
                    {uncalledRefs.length === 0 ? (
                      <span className={pageStyles.help}>선택한 도구를 이번 대화에서 다 불렀습니다.</span>
                    ) : (
                      <span className={pageStyles.help}>
                        이번 대화에서 안 부른 도구:{' '}
                        {uncalledRefs.map((ref) => toolByRef.get(ref)?.name ?? ref).join(', ')} — 이
                        질문에 필요 없었을 수도 있고, 모델이 놓쳤을 수도 있습니다. 아래 「도구
                        확인」에서 직접 불러보거나 다른 질문으로 다시 테스트해 보세요.
                      </span>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          <div className={pageStyles.cardHead} style={{ marginTop: 'var(--space-4)' }}>
            <h2>도구 확인</h2>
          </div>
          <ToolCheckPanel
            token={token}
            allTools={allTools}
            toolRefs={toolRefs}
            onToggleTool={onToggleTool}
            onOpenToolPicker={onOpenToolPicker}
          />
        </>
      )}
    </Modal>
  );
}
