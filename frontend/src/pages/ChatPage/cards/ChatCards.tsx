import { useState } from 'react';
import { Button, Checkbox, Icon } from '../../../components';
import type { CreatedIssue, ExtractedTask, ProgressStep } from '../cardTypes';
import styles from './cards.module.css';

/**
 * Chat 스트림에 뜨는 카드.
 *
 * **데이터는 전부 props 다.** mock 은 없앴다(개발지시_3차) — 카드가 자기
 * 기본값을 들고 있으면 서버가 아무것도 안 줘도 그럴듯한 화면이 나와서, 연동이
 * 안 된 것과 데이터가 없는 것을 구별할 수 없다.
 *
 * 카피는 Figma 문안 그대로다. 정직 표기 원칙 — 부분 상태를 성공처럼 뭉개지
 * 않는다(「근거 없어 비움」·「17/20 등록 완료」·「판정 보류」).
 */

export interface ProgressCardProps {
  steps: ProgressStep[];
  /** 도구가 낸 검색어. 에이전트가 실제로 한 판단이라 그대로 보여준다. */
  queries?: string[];
  evidenceCount?: number;
  title?: string;
  /**
   * Loop 회전(`tool_ref` 없는 stage). 도구 단계와 **다른 축**이라 진행 바에
   * 섞지 않고 부제로만 쓴다 — 섞으면 카운트가 1/4 → 1/5 → 2/5 로 튄다.
   */
  loop?: { step: number; total: number };
}

/** ① 진행 카드 — 장시간 작업의 단계·검색어·근거 수. 기존 진행 모달의 인라인판. */
export function ProgressCard({
  steps,
  queries = [],
  evidenceCount,
  title = '업무를 정리하는 중',
  loop,
}: ProgressCardProps) {
  const doneCount = steps.filter((step) => step.state === 'done').length;
  const total = Math.max(steps.length, 1);
  const shown = Math.min(doneCount + (steps.some((s) => s.state === 'doing') ? 1 : 0), total);

  return (
    <section className={styles.card}>
      <div className={styles.progressHead}>
        <span className={styles.progressTitle}>
          <Icon name="loader" size={16} color="var(--color-primary)" spin />
          {title}
        </span>
        <span className={styles.progressCount}>
          {steps.length > 0 ? `${shown} / ${total} 단계` : '준비 중'}
          {loop && loop.total > 0 ? ` · 에이전트 ${loop.step}/${loop.total} 회전` : ''}
        </span>
      </div>

      <div className={styles.progressTrack}>
        <span className={styles.progressFill} style={{ width: `${(shown / total) * 100}%` }} />
      </div>

      <ul className={styles.steps}>
        {steps.map((step, index) => (
          <li key={`${step.label}-${index}`} className={styles.step}>
            {step.state === 'done' && <Icon name="check-circle" size={15} color="var(--color-success)" />}
            {step.state === 'doing' && <Icon name="loader" size={15} color="var(--color-primary)" spin />}
            {step.state === 'todo' && <Icon name="circle-help" size={15} color="var(--color-border)" />}
            <span className={step.state === 'todo' ? styles.stepLabelTodo : styles.stepLabel}>{step.label}</span>
            {step.meta && <span className={styles.stepMeta}>{step.meta}</span>}
          </li>
        ))}
      </ul>

      {queries.length > 0 && (
        <ul className={styles.queries}>
          {queries.map((query) => (
            <li key={query} className={styles.query}>
              <Icon name="search" size={13} color="var(--color-placeholder)" />
              {query}
            </li>
          ))}
        </ul>
      )}

      <p className={styles.foot}>
        {evidenceCount ? `근거 ${evidenceCount}건 · ` : ''}몇 분 걸립니다 · 창을 닫지 않아도 됩니다
      </p>
    </section>
  );
}

/** ② 근거 카드 — 업무별 근거 접기/펼치기. TaskExtractionPage TaskCard(63-152)의 후신. */
function TaskRow({
  task,
  checked,
  onToggle,
}: {
  task: ExtractedTask;
  checked?: boolean;
  onToggle?: (next: boolean) => void;
}) {
  const [localChecked, setLocalChecked] = useState(task.checked);
  const [open, setOpen] = useState(task.evidence.length > 0);
  // 선택 상태를 바깥이 쥐면(실연동) 그것을 따르고, 아니면(mock) 자기가 쥔다.
  const isChecked = checked ?? localChecked;

  return (
    <div className={styles.taskRow}>
      <Checkbox checked={isChecked} onChange={onToggle ?? setLocalChecked} />
      <div className={styles.taskBody}>
        <span className={styles.taskTitle}>{task.title}</span>

        <div className={styles.facts}>
          {task.facts.map((fact) => (
            <span key={fact.label} className={styles.fact}>
              <span className={styles.factLabel}>{fact.label}</span>
              <strong>{fact.value}</strong>
            </span>
          ))}
        </div>

        {/* 근거가 없어 비운 것과 모델이 놓친 것을 사람이 구분하게 하는 장치. */}
        {task.missing && <p className={styles.missing}>{task.missing}</p>}

        <button type="button" className={styles.evidenceToggle} onClick={() => setOpen((prev) => !prev)}>
          <Icon name={open ? 'chevron-down' : 'chevron-right'} size={14} color="var(--color-primary)" />
          원문 근거 {task.evidenceCount}건
        </button>

        {open && task.evidence.length > 0 && (
          <div className={styles.evidenceList}>
            {task.evidence.map((item) => (
              <blockquote key={item.meta} className={styles.evidence}>
                <p>{item.quote}</p>
                <footer>
                  <span>{item.meta}</span>
                  <span className={styles.evidenceSource}>{item.source}</span>
                </footer>
              </blockquote>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export interface ConfirmCardProps {
  tasks: ExtractedTask[];
  warnings?: string[];
  trace?: string;
  /** 체크된 업무의 **인덱스**. 승인 API 에 이 값만 보낸다. */
  selected: number[];
  onSelectedChange: (next: number[]) => void;
  onApprove?: () => void;
  busy?: boolean;
}

/** ③ 확인 카드 — E2E STEP 6. 승인 전까지 Jira에 아무것도 만들지 않는다. */
export function ConfirmCard({
  tasks,
  warnings,
  trace,
  selected,
  onSelectedChange,
  onApprove,
  busy = false,
}: ConfirmCardProps) {
  const chosen = selected;
  const allOn = chosen.length === tasks.length && tasks.length > 0;

  function toggle(index: number, next: boolean) {
    onSelectedChange(
      next ? [...chosen, index].sort((a, b) => a - b) : chosen.filter((item) => item !== index),
    );
  }

  return (
    <section className={styles.cardFlush}>
      <div className={styles.confirmHead}>
        <span className={styles.confirmLeft}>
          <Checkbox
            checked={allOn}
            onChange={(next) => onSelectedChange(next ? tasks.map((_, index) => index) : [])}
          />
          <strong>전체 선택</strong>
          <span className={styles.muted}>{chosen.length}건 선택됨</span>
        </span>
        <span className={styles.muted}>업무 {tasks.length}건</span>
      </div>

      {/* 서버가 준 경고만 보여준다. 없으면 안 띄운다 — 없는 주의를 지어내면
          다음에 진짜 경고가 왔을 때 사람이 안 읽는다. */}
      {(warnings ?? []).map((warning) => (
        <p key={warning} className={styles.warnBanner}>
          {warning}
        </p>
      ))}

      {tasks.map((task, index) => (
        <TaskRow
          key={task.no}
          task={task}
          checked={chosen.includes(index)}
          onToggle={(next) => toggle(index, next)}
        />
      ))}

      {trace && <p className={styles.trace}>{trace}</p>}

      <div className={styles.confirmActions}>
        <span className={styles.muted}>승인하기 전까지 Jira에는 아무것도 만들지 않습니다.</span>
        {/* `onApprove` 가 없으면 지나간 턴의 카드다 — 눌리는 모양으로 두면
            읽기 전용인 줄 모르고 클릭하게 된다(6차 단계 1-3). */}
        <Button size="sm" onClick={onApprove} disabled={busy || chosen.length === 0 || !onApprove}>
          {busy ? '등록하는 중…' : `선택한 ${chosen.length}건 Jira에 등록`}
        </Button>
      </div>
    </section>
  );
}

export interface ResultCardProps {
  created: CreatedIssue[];
  failures: { title: string; reason: string }[];
  onRetryFailed?: () => void;
}

/** ④ 결과 카드 — 전부 성공 / 부분 실패. 성공분은 롤백하지 않는다(E2E §2). */
export function ResultCard({ created, failures, onRetryFailed }: ResultCardProps) {
  const partial = failures.length > 0;
  const total = created.length + failures.length;

  return (
    <section className={styles.cardFlush}>
      <div className={partial ? styles.resultHeadWarn : styles.resultHeadOk}>
        <span className={styles.resultTitle}>
          <Icon
            name={partial ? 'triangle-alert' : 'check-circle'}
            size={18}
            color={partial ? 'var(--color-warning-text)' : 'var(--color-success-text)'}
          />
          {/* 실패를 성공에 섞지 않는다 — 분모를 밝혀 「17/20」로 적는다. */}
          {created.length}/{total} 등록 완료
          {partial ? ` — ${failures.length}건 실패` : ''}
        </span>
        <span className={styles.resultMeta}>
          {partial ? '성공분은 되돌리지 않습니다' : ''}
        </span>
      </div>

      {created.length > 0 && (
        <>
          <div className={styles.issueHead}>
            <strong>등록된 이슈 {created.length}건</strong>
            <span className={styles.muted}>이슈를 누르면 Jira에서 열립니다</span>
          </div>

          {created.map((issue) => (
            <div key={issue.key} className={styles.issueRow}>
              <span className={styles.issueKey}>{issue.key}</span>
              <span className={styles.issueBody}>
                <strong>{issue.title}</strong>
                <span className={styles.muted}>{issue.meta}</span>
              </span>
              <span className={styles.issueEvidence}>근거 {issue.evidence}</span>
              <Icon name="arrow-right" size={14} color="var(--color-placeholder)" />
            </div>
          ))}
        </>
      )}

      {partial && (
        <>
          <div className={styles.failHead}>
            <Icon name="circle-x" size={15} color="var(--color-danger)" />
            <strong>실패 {failures.length}건 — 사유</strong>
          </div>
          {failures.map((failure) => (
            <div key={failure.title} className={styles.failRow}>
              <strong>{failure.title}</strong>
              <span className={styles.failReason}>{failure.reason}</span>
            </div>
          ))}
        </>
      )}

      <div className={styles.confirmActions}>
        <span className={styles.muted}>
          {partial
            ? `실패한 ${failures.length}건만 다시 시도합니다. 이미 등록된 ${created.length}건은 그대로 둡니다.`
            : '업무별 근거는 이 대화에 그대로 저장됩니다. 새로고침해도 사라지지 않습니다.'}
        </span>
        {partial && onRetryFailed && (
          <Button size="sm" iconLeft={<Icon name="refresh" size={14} />} onClick={onRetryFailed}>
            실패분 {failures.length}건 재시도
          </Button>
        )}
      </div>
    </section>
  );
}

export interface ErrorCardProps {
  detail?: string;
  /** 백엔드 오류 코드 계약(11_MCP_설계 §6): 401 · 429 · validation · timeout · unreachable. */
  errorCode?: string;
  onRetry?: () => void;
  onOpenSettings?: () => void;
}

/** 오류 코드별 안내. 코드가 화면 문구를 정한다 — 지어내지 않는다. */
const ERROR_HINTS: Record<string, string> = {
  '401': '연결 인증이 만료되었습니다. 설정에서 연결을 다시 확인해 주세요.',
  '429': '요청 한도를 초과했습니다. 잠시 후 다시 시도하면 됩니다.',
  timeout: '외부 서버가 시간 안에 응답하지 않았습니다. 다시 시도해 주세요.',
  unreachable: '외부 서버에 연결하지 못했습니다. 주소와 상태를 확인해 주세요.',
  validation: '요청 값이 받아들여지지 않았습니다. 아래 사유를 확인해 주세요.',
};

/** ⑤ 오류 카드 — 스트림이 끊긴 지점에 뜨고, 이전 결과물은 위에 보존된다. */
export function ErrorCard({ detail, errorCode, onRetry, onOpenSettings }: ErrorCardProps) {
  const hint = errorCode ? ERROR_HINTS[errorCode] : undefined;

  return (
    <section className={styles.errorCard}>
      <span className={styles.errorTitle}>
        <Icon name="triangle-alert" size={18} color="var(--color-danger)" />
        {detail ?? 'Jira에 연결하지 못했습니다'}
      </span>
      <p className={styles.errorBody}>
        {hint ??
          'MCP Server 인증이 만료되었습니다 (401 Unauthorized). 설정 > MCP에서 Jira 연결을 다시 확인해 주세요.'}{' '}
        정리된 업무와 근거는 위에 그대로 남아 있으니, 고친 뒤 재시도하면 됩니다.
      </p>
      <div className={styles.errorActions}>
        <Button size="sm" variant="outline" onClick={onOpenSettings}>
          설정에서 연결 확인
        </Button>
        <Button size="sm" onClick={onRetry} disabled={!onRetry}>
          다시 시도
        </Button>
      </div>
      {errorCode && <code className={styles.errorRaw}>error · {errorCode}</code>}
    </section>
  );
}

/*
 * 문서 선택 카드(Figma 47:654)는 뺐다.
 *
 * **서버가 그 카드를 내보내는 경로가 없다.** 기준 문서는 사람이 별도 화면에서
 * 미리 고른 것(`doc_role='PRIMARY'`)을 쓰고, `task_extraction` 은 문서 id 를
 * 받지도 않는다(1차 단계 4). mock 을 걷어내니 데이터 출처가 없는 컴포넌트만
 * 남아서 지웠다 — 되살리려면 Chat 이 문서 후보를 되묻는 흐름을 백엔드에
 * 먼저 만들어야 한다. CSS(`.docHead`·`.docRow`…)는 그때 다시 쓰도록 남겨 뒀다.
 */
