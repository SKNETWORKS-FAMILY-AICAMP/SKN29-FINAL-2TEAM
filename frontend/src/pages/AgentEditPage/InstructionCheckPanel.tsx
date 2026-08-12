import { useEffect, useState } from 'react';
import { Badge, Button } from '../../components';
import type { BadgeTone } from '../../components';
import { checkBuilderInput, recheckInstruction } from '../../api/agents';
import type { BuilderCheckResult } from '../../api/agents';
import { ApiError } from '../../api/client';
import pageStyles from './AgentEditPage.module.css';
import styles from './TestRunModal.module.css';

export interface InstructionCheckPanelProps {
  token: string | null;
  name: string;
  toolRefs: string[];
  description: string;
  instruction: string;
  /**
   * 현재 설명·지시문·"다음 단계로 넘어가도 되는가"가 바뀔 때마다 부른다.
   * 진행 여부는 부모(`TestRunModal`)가 결정한다 — 이 패널은 더 이상 자체
   * "다음 단계" 버튼을 갖지 않는다(도구 확인과 나란히 자동으로 돈다).
   */
  onStateChange: (description: string, instruction: string, canProceed: boolean) => void;
}

const OVERALL_LABEL: Record<BuilderCheckResult['overall'], { tone: BadgeTone; label: string }> = {
  pass: { tone: 'success', label: '통과' },
  warn: { tone: 'warning', label: '확인 필요' },
  reject: { tone: 'danger', label: '반려 — 내용을 다시 써야 합니다' },
};

/** 설명·지시문·도구 선택 옆에 다는 작은 표시. 어느 항목이 걸렸는지 위쪽
 * 종합 배지 하나만으로는 알 수 없어서 항목별로 따로 붙인다. */
function FieldFlag() {
  return (
    <Badge tone="warning" className={styles.fieldFlag}>
      확인 필요
    </Badge>
  );
}

/**
 * 검증 단계 — 설명·지시문·도구 선택이 서로 맞는지 LLM으로 검토한다.
 *
 * 마운트 시 자동으로 한 번 검증을 돌린다. **`refined_instruction`을 지시문에
 * 자동으로 채우지 않는다** — 사용자가 모르는 채로 자기 글이 바뀌면 안 된다.
 * 대신 제안을 보여주고 [제안 적용]/[내 지시문 유지] 중 하나를 사람이 직접
 * 고르게 한다. `reject`일 때는 애초에 다듬은 게 없어서(빈 문자열) 비교할
 * 것도 없다.
 */
export function InstructionCheckPanel({
  token,
  name,
  toolRefs,
  description,
  instruction,
  onStateChange,
}: InstructionCheckPanelProps) {
  const [draftDescription, setDraftDescription] = useState(description);
  const [draftInstruction, setDraftInstruction] = useState(instruction);
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState<BuilderCheckResult | null>(null);
  // 이번 검증 결과의 제안을 사용자가 적용/유지 중 하나로 결정했는가.
  // 제안 자체가 없으면(reject, 또는 원문과 글자가 똑같음) 애초에 물을 게 없다.
  const [resolved, setResolved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 마지막으로 전체 검증(이름+설명+지시문+도구)을 돌렸을 때의 설명값. 여기서 설명이
  // 안 바뀌었으면 지시문만 고친 것이니 가벼운 재검증으로 충분하다.
  const [checkedDescription, setCheckedDescription] = useState(description);
  // 마지막 검증(전체든 경량이든)에 쓰인 지시문값. 지금 지시문과 같으면 "재검증할
  // 새 내용이 없다"는 뜻이라 재검증 버튼을 막는다.
  const [checkedInstruction, setCheckedInstruction] = useState(instruction);

  // `refined_instruction`은 `overall`이 'pass'여도 원문을 손질한 문장을
  // 돌려준다(모델이 항상 다듬기 때문) — 실측(2026-08-12): 트리거·절차·도구
  // 기준·판단 기준을 다 갖춘 지시문도 `pass`와 함께 재작성된 문장을 준다.
  // `pass`에서까지 제안 박스를 띄우면 이미 완료된 지시문도 계속 "더 손볼 게
  // 있다"는 인상을 준다 — 실제로 걸린 게 있는 `warn`에서만 보여준다.
  const descriptionHasIssue = !!result?.description_check?.note;
  const instructionHasIssue = !!result?.instruction_check?.note;
  const toolHasIssue =
    (result?.tool_match_check?.missing_tools?.length ?? 0) > 0 ||
    (result?.tool_match_check?.unused_tools?.length ?? 0) > 0;

  const hasSuggestion =
    result !== null &&
    result.overall === 'warn' &&
    result.refined_instruction.trim() !== '' &&
    result.refined_instruction.trim() !== draftInstruction.trim();

  async function run(desc: string, instr: string) {
    if (!token || checking) return;
    setChecking(true);
    setError(null);
    try {
      const response = await checkBuilderInput(token, {
        name,
        description: desc,
        behavior: instr,
        tool_refs: toolRefs,
      });
      setResult(response);
      setCheckedDescription(desc);
      setCheckedInstruction(instr);
      setResolved(false);
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : '검증에 실패했습니다.');
    } finally {
      setChecking(false);
    }
  }

  /**
   * 설명은 그대로 두고 지시문만 고쳤을 때 쓰는 경량 경로. `description_check`는
   * 이전 결과를 그대로 들고 있고, `instruction_check`/`tool_match_check`/`overall`만
   * 새로 받는다. 새로 다듬은 문장은 안 나오므로 제안 비교 블록은 접는다.
   */
  async function runInstructionOnly(instr: string) {
    if (!token || checking) return;
    setChecking(true);
    setError(null);
    try {
      const response = await recheckInstruction(token, { instruction: instr, tool_refs: toolRefs });
      setResult((prev) => ({
        refined_instruction: '',
        description_check: prev?.description_check ?? { note: null },
        instruction_check: response.instruction_check,
        tool_match_check: response.tool_match_check,
        overall: response.overall,
        reject_reason: response.reject_reason,
      }));
      setCheckedInstruction(instr);
      setResolved(true);
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : '지시문 재검증에 실패했습니다.');
    } finally {
      setChecking(false);
    }
  }

  const canUseLightRecheck = result !== null && draftDescription === checkedDescription;
  // 마지막 검증 이후로 설명·지시문 어느 쪽도 안 바뀌었으면 다시 불러도 같은
  // 결과만 나온다 — 재검증 버튼을 막는다. 제안을 적용하면 `applySuggestion`이
  // 그 자리에서 재검증하므로, 사람이 더 손대지 않는 한 이 상태가 유지된다.
  const nothingChangedSinceCheck =
    result !== null && draftDescription === checkedDescription && draftInstruction === checkedInstruction;

  function rerun() {
    if (canUseLightRecheck) {
      void runInstructionOnly(draftInstruction);
    } else {
      void run(draftDescription, draftInstruction);
    }
  }

  useEffect(() => {
    void run(description, instruction);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 부모에게 현재 값·진행 가능 여부를 알린다. 제안이 있는데 아직 안 골랐으면
  // 다음 단계로 못 넘어간다 — "한 번은 사람이 본다"는 원칙.
  useEffect(() => {
    const canProceed =
      !checking && result !== null && result.overall !== 'reject' && (!hasSuggestion || resolved);
    onStateChange(draftDescription, draftInstruction, canProceed);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftDescription, draftInstruction, checking, result, hasSuggestion, resolved]);

  /**
   * 제안을 적용한 순간의 배지는 **적용 전** 검증 결과(대개 warn)다 — 방금 그
   * 경고를 없애려고 받은 문장인데 화면은 여전히 경고를 보여주면 모순이다.
   * 적용한 지시문을 그 자리에서 가볍게 재검증해 배지를 지금 내용 기준으로
   * 맞춘다. 이 재검증이 끝나면 `checkedInstruction`이 지금 값과 같아져
   * 재검증 버튼도 자연히 다시 막힌다 — 더 손댈 것이 없을 때는 누를 이유가
   * 없다는 규칙 하나로 두 가지가 함께 해결된다.
   */
  function applySuggestion() {
    if (!result) return;
    const refined = result.refined_instruction;
    setDraftInstruction(refined);
    setResolved(true);
    void runInstructionOnly(refined);
  }

  function keepMine() {
    setResolved(true);
  }

  return (
    <div>
      <p className={pageStyles.help}>
        이름·설명·지시문·도구 선택이 서로 맞는지 검토합니다. 「확인 필요」는 걸린 항목
        옆에 표시되며 진행을 막지 않지만, 반려는 막습니다 — 내용을 다시 쓰고 재검증해야
        합니다.
      </p>
      {!name.trim() && <p className={pageStyles.help}>이름을 먼저 적어 주세요.</p>}
      {error && <p className={pageStyles.error}>{error}</p>}
      {/* `제안 적용` 뒤의 자동 재검증도 여기 걸린다 — `result`가 이미 있어도
          갱신 중임을 보여줘야, 배지가 잠깐 이전 결과(warn)를 들고 있는 동안
          "적용했는데 그대로다"로 오해하지 않는다. */}
      {checking && (
        <p className={pageStyles.help}>
          {result ? '방금 반영한 내용을 다시 확인하는 중…' : '검증하는 중…'}
        </p>
      )}
      {result && (
        <p className={styles.statusLine} style={checking ? { opacity: 0.5 } : undefined}>
          <Badge tone={(OVERALL_LABEL[result.overall] ?? { tone: 'neutral' as BadgeTone }).tone}>
            {OVERALL_LABEL[result.overall]?.label ?? result.overall}
          </Badge>
        </p>
      )}
      {result?.overall === 'reject' && result.reject_reason && (
        <p className={pageStyles.error}>{result.reject_reason}</p>
      )}

      <label className={pageStyles.field}>
        <span className={pageStyles.fieldLabel} style={{ display: 'inline-flex', alignItems: 'center' }}>
          설명
          {descriptionHasIssue && <FieldFlag />}
        </span>
        <textarea
          className={pageStyles.textarea}
          style={{ minHeight: 60 }}
          rows={2}
          value={draftDescription}
          onChange={(event) => setDraftDescription(event.target.value)}
        />
      </label>
      {result && (
        <span className={pageStyles.help}>
          검증 의견: {result.description_check?.note || '동사·대상·산출물이 잘 드러나 명확합니다.'}
        </span>
      )}

      <label className={pageStyles.field}>
        <span className={pageStyles.fieldLabel} style={{ display: 'inline-flex', alignItems: 'center' }}>
          지시문
          {instructionHasIssue && <FieldFlag />}
        </span>
        <textarea
          className={pageStyles.textarea}
          rows={7}
          value={draftInstruction}
          onChange={(event) => {
            setDraftInstruction(event.target.value);
            // 사람이 직접 고치면 그 자체가 "결정"이다 — 제안 비교 블록을 닫는다.
            if (hasSuggestion) setResolved(true);
          }}
        />
      </label>

      {hasSuggestion && !resolved && (
        <div className={styles.step}>
          <div className={styles.stepBody}>
            <span className={styles.stepName}>다듬은 지시문 제안</span>
            <p className={pageStyles.help} style={{ whiteSpace: 'pre-wrap' }}>
              {result!.refined_instruction}
            </p>
            <div className={styles.stepActions}>
              <Button size="sm" onClick={applySuggestion}>
                제안 적용
              </Button>
              <Button size="sm" variant="outline" onClick={keepMine}>
                내 지시문 유지
              </Button>
            </div>
          </div>
        </div>
      )}
      {hasSuggestion && resolved && (
        <span className={pageStyles.help}>
          {draftInstruction.trim() === result!.refined_instruction.trim()
            ? '제안을 적용했습니다.'
            : '원래 지시문을 유지했습니다.'}
        </span>
      )}

      {result && (
        <div className={styles.step}>
          <div className={styles.stepBody}>
            <span className={styles.stepName}>지시문 내용</span>
            <span className={pageStyles.help}>
              {result.instruction_check?.note ||
                '트리거 조건·절차·도구 사용 기준·판단 기준이 잘 드러나 있습니다.'}
            </span>
          </div>
        </div>
      )}

      {result && (
        <div className={styles.step}>
          <div className={styles.stepBody}>
            <span className={styles.stepName}>
              도구 선택
              {toolHasIssue && <FieldFlag />}
            </span>
            {(result.tool_match_check?.missing_tools?.length ?? 0) === 0 &&
            (result.tool_match_check?.unused_tools?.length ?? 0) === 0 ? (
              <span className={pageStyles.help}>지시문과 도구 선택이 잘 맞습니다.</span>
            ) : (
              <>
                {(result.tool_match_check?.missing_tools?.length ?? 0) > 0 && (
                  <span className={pageStyles.help}>
                    지시문에 필요해 보이는데 안 고른 도구: {result.tool_match_check.missing_tools.join(', ')}
                  </span>
                )}
                {(result.tool_match_check?.unused_tools?.length ?? 0) > 0 && (
                  <span className={pageStyles.help}>
                    골랐는데 지시문에서 안 쓰일 것 같은 도구: {result.tool_match_check.unused_tools.join(', ')}
                  </span>
                )}
              </>
            )}
          </div>
        </div>
      )}

      <div className={styles.stepActions}>
        <Button
          variant="outline"
          onClick={rerun}
          disabled={checking || !name.trim() || nothingChangedSinceCheck}
        >
          {checking
            ? '검증하는 중…'
            : canUseLightRecheck
              ? '지시문만 다시 검증하기'
              : '수정한 내용으로 다시 검증하기'}
        </Button>
      </div>
    </div>
  );
}
