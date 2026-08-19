import { useEffect, useRef, useState } from 'react';
import { Button, Checkbox, Icon } from '../../../components';
import type { JiraIssue, SourceRef } from '../../../api/chat';
import type { CreatedIssue, ExtractedTask, ProgressStep, SubagentRun, TimelineEntry } from '../cardTypes';
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
  /** `document_search`가 좁힌 문서·`web_search`가 찾은 페이지 — "출처"(2026-08-18). */
  sources?: SourceRef[];
  /** 이 턴에서 다른 에이전트에게 위임한 작업들(2026-08-18). */
  subagents?: SubagentRun[];
  evidenceCount?: number;
  title?: string;
  /**
   * 아직 돌고 있는가.
   *
   * **끝난 뒤에도 계속 회전했다**(2026-08-12 QA). 승인 카드가 뜨고 답까지 나왔는데
   * 머리에서 스피너가 돌면 「아직 뭔가 하는 중」으로 읽혀서, 승인 버튼을 눌러도
   * 되는지 사람이 판단하지 못한다.
   */
  running?: boolean;
}

/** ① 진행 카드 — 장시간 작업의 단계·검색어·근거 수. 기존 진행 모달의 인라인판. */
export function ProgressCard({
  steps,
  queries = [],
  sources = [],
  subagents = [],
  evidenceCount,
  title = '업무를 정리하는 중',
  running = true,
}: ProgressCardProps) {
  const doneCount = steps.filter((step) => step.state === 'done').length;
  const total = Math.max(steps.length, 1);
  const shown = Math.min(doneCount + (steps.some((s) => s.state === 'doing') ? 1 : 0), total);

  return (
    <section className={styles.card}>
      <div className={styles.progressHead}>
        <span className={styles.progressTitle}>
          {running ? (
            <Icon name="loader" size={16} color="var(--color-primary)" spin />
          ) : (
            <Icon name="check-circle" size={16} color="var(--color-success)" />
          )}
          {title}
        </span>
        {/* **회전 수는 보여주지 않는다.**
            Loop 이 몇 바퀴 돌았는지는 우리가 디버깅할 때 보는 값이지 사람이 할
            행동을 바꾸는 정보가 아니다. 「1/8」은 여덟 번 돌 예정인 것처럼 읽히고
            (실제로는 상한이다), 「2번째 생각」은 그냥 소음이다.
            실행 회전 수가 필요하면 `agent_run.iterations` 에 남아 있다. */}
        <span className={styles.progressCount}>
          {steps.length > 0 ? `${shown} / ${total} 단계` : '대기 중'}
        </span>
      </div>

      <div className={styles.progressTrack}>
        <span className={styles.progressFill} style={{ width: `${(shown / total) * 100}%` }} />
      </div>

      <ul className={styles.steps}>
        {/* 끝났으면 남아 있는 `doing` 도 더는 돌지 않는다 — 스트림이 닫혔는데
            마지막 단계만 회전하고 있으면 멈춘 것처럼 보인다. */}
        {(running ? steps : steps.map((s) => (s.state === 'doing' ? { ...s, state: 'done' as const } : s))).map((step, index) => (
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

      {/* "출처"(2026-08-18) — document_search가 실제로 좁혀서 보고 있는
          문서, web_search가 찾은 페이지. 색인 여부와 무관하게 전부
          보여준다(정직 표기 원칙 — not_indexed와 같은 이유). `url`이 있으면
          웹 결과라 새 탭 링크로, 없으면(내부 문서) 그냥 텍스트로 그린다. */}
      {sources.length > 0 && (
        <ul className={styles.queries}>
          {sources.map((source) =>
            source.url ? (
              <li key={source.id} className={styles.query}>
                <Icon name="link" size={13} color="var(--color-placeholder)" />
                <a href={source.url} target="_blank" rel="noreferrer" className={styles.sourceLink}>
                  {source.label}
                </a>
              </li>
            ) : (
              <li key={source.id} className={styles.query}>
                <Icon name="file-text" size={13} color="var(--color-placeholder)" />
                {source.label}
              </li>
            ),
          )}
        </ul>
      )}

      {/* 다른 에이전트에게 위임한 작업들(2026-08-18) — 위임 자체가 걸린
          동안 진행 카드가 멈춘 것처럼 보이던 문제(서브 에이전트가 일하는
          동안 화면에 아무 변화가 없었다)를 고치려고 추가했다. 서브 에이전트
          *자신의* reasoning·도구 진행은 여전히 안 보여준다 — "지금
          위임했다/끝났다"는 사실만 보여준다. */}
      {subagents.length > 0 && (
        <ul className={styles.steps}>
          {subagents.map((run) => (
            <li key={run.runId} className={styles.step}>
              {run.status === 'RUNNING' && <Icon name="loader" size={15} color="var(--color-primary)" spin />}
              {run.status === 'DONE' && <Icon name="check-circle" size={15} color="var(--color-success)" />}
              {run.status === 'FAILED' && <Icon name="circle-x" size={15} color="var(--color-danger)" />}
              <span className={styles.stepLabel}>
                {run.name ?? run.alias ?? '다른 에이전트'}에게 위임
                {run.status === 'DONE' && ' 완료'}
                {run.status === 'FAILED' && ' 실패'}
              </span>
              {run.taskSummary && <span className={styles.stepMeta}>{run.taskSummary}</span>}
            </li>
          ))}
        </ul>
      )}

      {/* **끝나면 「몇 분 걸립니다」를 지운다**(2026-08-18 QA). 위 단계 아이콘은
          `running` 을 보고 회전을 멈추는데 이 줄만 무조건 그려져서, 답변이 다
          나온 뒤에도 카드가 아직 도는 것처럼 보였다. 끝난 뒤 남길 값은 근거
          수뿐이고, 그것도 없으면 줄 자체를 안 그린다. */}
      {(running || Boolean(evidenceCount)) && (
        <p className={styles.foot}>
          {evidenceCount ? `근거 ${evidenceCount}건` : ''}
          {running && `${evidenceCount ? ' · ' : ''}처리 중입니다. 완료되면 결과가 표시됩니다`}
        </p>
      )}
    </section>
  );
}

export interface ReasoningTraceProps {
  /**
   * 이 턴의 생각·도구 호출·위임을 실제 순서대로. 비어 있으면 컴포넌트
   * 자체를 안 그린다(2026-08-18 — 예전엔 reasoning 조각만 받았는데, "어떤
   * 도구가 몇 번째 생각 다음에 불렸는지" 순서를 보여 달라는 요청으로
   * 도구·위임까지 같이 받는 하나의 타임라인으로 바뀌었다).
   */
  entries: TimelineEntry[];
  /**
   * 처음 그릴 때부터 펼쳐 둘지(2026-08-18, 토큰 단위 실시간 스트리밍 도입).
   * **딱 처음 마운트될 때만** 본다(그 뒤 이 값이 바뀌어도 `useState` 초기값이라
   * 안 따라간다) — 지금 스트리밍 중인 턴(`live.running`)에 `true`를 주면,
   * 답이 다 나온 뒤가 아니라 **쓰는 동안 실시간으로** 보인다. 새로고침으로
   * 다시 그리는 지난 턴은 이미 `running=false`라 여전히 접혀서 시작한다.
   */
  defaultOpen?: boolean;
  /**
   * 지금 이 턴이 스트리밍 중인가(2026-08-18, 로그 뷰 도입). `defaultOpen`과
   * 달리 이 값은 리렌더마다 그대로 따라간다 — 항목이 늘 때마다 로그 맨
   * 아래로 자동 스크롤하고, 마지막 줄에 커서를 깜빡이는 데 쓴다. 스트림이
   * 끝나 `false`가 되면 자동 스크롤도 커서도 멈춘다.
   */
  running?: boolean;
}

/**
 * ⓪ 생각 과정 카드(2026-08-18) — 추론 모델(gpt-5.6-luna 등)이 도구를 부르기
 * 전이나 최종 답 전에 내는 생각을, **실제로 부른 도구·위임과 같은 순서로
 * 섞어서** 보여준다. `services/agent_runtime/events.py`가 내는 `reasoning`
 * 조각과 `tool_started`/`tool_completed`/`subagent_started`/`subagent_completed`
 * 를 `liveChat.ts`의 `reduce()`가 하나의 `timeline` 배열로 순서대로 쌓는다 —
 * 전에는 이 둘이 서로 다른 배열에 각자 쌓여서 "몇 번째 생각 다음에 이
 * 도구를 불렀는지" 순서 정보가 화면에서 사라졌었다.
 *
 * **지난 턴은 접어서 시작한다.** 추론 모델은 답 하나에도 여러 단락을
 * 생각하는데, 다 펼쳐 두면 정작 찾는 답이 아래로 밀린다 — 근거 카드
 * (`TaskRow`)의 「원문 근거」와 같은 판단이다. **지금 스트리밍 중인 턴은
 * `defaultOpen`으로 펼쳐서 시작한다** — 실시간으로 쓰는 걸 보여주는 게
 * 이 기능의 목적이라, 접어 두면 매번 사람이 직접 펴야 그 효과를 본다.
 */
export function ReasoningTrace({ entries, defaultOpen = false, running = false }: ReasoningTraceProps) {
  const [open, setOpen] = useState(defaultOpen);
  const logRef = useRef<HTMLOListElement>(null);
  // 도구 반환값은 기본으로는 접혀 있다 — 눌러야만 펼쳐 보인다(2026-08-18,
  // "그 스트리밍된 툴을 눌러야만 보이게 해줘" 요청). index로 여닫힘을 추적한다
  // — entries는 순서만 늘고 위치가 안 바뀌므로 li의 key(index)와 그대로 맞는다.
  const [expandedOutputs, setExpandedOutputs] = useState<Set<number>>(new Set());

  function toggleOutput(index: number) {
    setExpandedOutputs((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  }

  // 로그 창처럼 새 줄이 생길 때마다 맨 아래로 따라간다. 스트림이 끝나면
  // (running=false) 사람이 스크롤을 올려 지난 로그를 봐도 다시 끌어내리지 않는다.
  useEffect(() => {
    if (!open || !running) return;
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [entries, open, running]);

  if (entries.length === 0) return null;

  return (
    <section className={styles.card}>
      <button type="button" className={styles.evidenceToggle} onClick={() => setOpen((prev) => !prev)}>
        <Icon name={open ? 'chevron-down' : 'chevron-right'} size={14} color="var(--color-primary)" />
        생각 과정 {entries.length}단계
      </button>

      {open && (
        <ol className={styles.reasoningList} ref={logRef}>
          {entries.map((entry, index) => {
            const isLast = index === entries.length - 1;
            if (entry.kind === 'reasoning') {
              return (
                <li key={index} className={styles.reasoningStep}>
                  <span>
                    {entry.text}
                    {running && isLast && <span className={styles.reasoningCursor} />}
                  </span>
                </li>
              );
            }
            if (entry.kind === 'tool') {
              const isExpanded = expandedOutputs.has(index);
              return (
                <li key={index} className={styles.reasoningToolGroup}>
                  {/* 도구가 실제로 뭘 반환했는지는 눌러야만 펼쳐진다(2026-08-18) —
                      로그 한 줄 한 줄이 다 자동으로 늘어지면 정작 보고 싶은 흐름이
                      아래로 밀린다. 반환값이 없으면(아직 RUNNING) 누를 게 없다. */}
                  <button
                    type="button"
                    className={styles.reasoningTool}
                    onClick={() => toggleOutput(index)}
                    disabled={!entry.output}
                  >
                    {entry.status === 'RUNNING' && <Icon name="loader" size={13} color="var(--color-primary)" spin />}
                    {entry.status === 'OK' && <Icon name="check-circle" size={13} color="var(--color-success)" />}
                    {entry.status === 'FAILED' && <Icon name="circle-x" size={13} color="var(--color-danger)" />}
                    <span>
                      {entry.toolName ?? entry.toolRef} 호출
                      {entry.status === 'OK' && ' 완료'}
                      {entry.status === 'FAILED' && ' 실패'}
                    </span>
                    {entry.output && (
                      <Icon
                        name={isExpanded ? 'chevron-down' : 'chevron-right'}
                        size={12}
                        color="var(--color-placeholder)"
                      />
                    )}
                  </button>
                  {isExpanded && entry.output && <pre className={styles.reasoningOutput}>{entry.output}</pre>}
                </li>
              );
            }
            return (
              <li key={index} className={styles.reasoningTool}>
                {entry.status === 'RUNNING' && <Icon name="loader" size={13} color="var(--color-primary)" spin />}
                {entry.status === 'DONE' && <Icon name="check-circle" size={13} color="var(--color-success)" />}
                {entry.status === 'FAILED' && <Icon name="circle-x" size={13} color="var(--color-danger)" />}
                <span>
                  {entry.name ?? entry.alias ?? '다른 에이전트'}에게 위임
                  {entry.status === 'DONE' && ' 완료'}
                  {entry.status === 'FAILED' && ' 실패'}
                </span>
              </li>
            );
          })}
        </ol>
      )}
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
  // **접은 채로 시작한다.** 업무가 10건이면 근거가 수십 개 펼쳐져 목록을 훑는
  // 것 자체가 안 된다. 근거는 한 건을 의심할 때 여는 것이지 늘 보는 것이 아니다.
  const [open, setOpen] = useState(false);
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
  /**
   * 고를 목록이 없는 승인에 **무엇을 승인하는지** 한 줄로 적는다(2026-08-18).
   * 그런 카드는 체크박스가 없어서 머리에 「전체 선택 · 업무 0건」만 남았는데,
   * 그건 아무것도 설명하지 않는다 — 사람은 무엇을 승인하는지 모르는 채로
   * 「승인」을 누르게 된다. 목록이 있는 카드에는 넘기지 않는다(그쪽은 업무가
   * 곧 설명이다).
   */
  subject?: string;
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
  subject,
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
      {/* 고를 것이 있을 때만 선택 줄을 그린다. 없으면 무엇을 승인하는지 적는다.
          — 예전엔 목록이 없어도 이 줄을 그려서 「전체 선택 · 0건 선택됨 ·
          업무 0건」이 남았다(2026-08-18 QA). 체크할 것도 없는데 전체 선택이
          있고, 대상이 15건인데 「0건」이라고 적혀 서로 어긋났다. */}
      {tasks.length > 0 ? (
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
      ) : subject ? (
        <div className={styles.confirmHead}>
          <strong>{subject}</strong>
        </div>
      ) : null}

      {/* ⚠ 경고 배너를 걷어냈다(PM 요청, 2026-08-11). 서버는 여전히 경고를
          보내고 있고(`warnings` prop), 거기에는 「근거가 확인되지 않아 제외했다」
          같은 **빠진 업무의 사유**가 들어 있다. 지금은 화면 어디에도 안 나온다.
          다시 보여야 하면 배너가 아니라 조용한 한 줄로 되살릴 것. */}

      {tasks.map((task, index) => (
        <TaskRow
          key={task.no}
          task={task}
          checked={chosen.includes(index)}
          onToggle={(next) => toggle(index, next)}
        />
      ))}

      {trace && <p className={styles.trace}>{trace}</p>}

      {/* **승인할 것이 있을 때만 승인 줄을 그린다.**
          추출만 끝나고 등록 도구를 아직 안 부른 상태에서도 「승인하기 전까지
          아무것도 등록되지 않습니다」를 띄우고 죽은 버튼을 놔뒀었다 — 사람은
          승인을 찾다가 못 찾는다. 승인 대상이 없으면 그 사실을 말한다. */}
      {onApprove ? (
        <div className={styles.confirmActions}>
          <span className={styles.muted}>
            {/* 무엇을 승인하는지는 도구가 정한다 — 화면이 「Jira」라고 못박아 두면
                우리 플랫폼에 등록하는 승인에도 Jira 라고 쓰게 된다. */}
            승인하기 전까지 아무것도 등록되지 않습니다.
          </span>
          {/* ⚠ 업무가 없는 승인(추출을 안 거친 도구)은 고를 것이 없으므로
              `chosen` 으로 막지 않는다 — 막으면 버튼이 영원히 비활성이다. */}
          <Button
            size="sm"
            onClick={onApprove}
            disabled={busy || (tasks.length > 0 && chosen.length === 0)}
          >
            {busy ? '등록하는 중…' : tasks.length > 0 ? `선택한 ${chosen.length}건 등록` : '승인'}
          </Button>
        </div>
      ) : (
        <div className={styles.confirmActions}>
          <span className={styles.muted}>
            아직 등록되지 않았습니다. ‘프로젝트 업무로 등록해줘’라고 말하면 승인 카드가 뜹니다.
          </span>
        </div>
      )}
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
          {partial ? ` · ${failures.length}건 실패` : ''}
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
            <strong>실패 {failures.length}건의 사유</strong>
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
  /**
   * 이 턴에 **모델의 답이 있는가.**
   *
   * 도구가 실패하면 모델은 그 사유를 자기 말로 다시 쓴다. 그러면 같은 이야기가
   * 말풍선과 이 카드에 두 번 나온다(2026-08-12 QA §B-0). 두 문장은 **글자로는
   * 달라서** 문자열 비교로는 못 거른다 — 실제로 그렇게 만들었다가 브라우저에서
   * 그대로 두 번 나오는 것을 봤다(2026-08-15).
   *
   * 그래서 답이 있으면 사유를 **지우지 않고 「기술 정보」 안으로 내린다.** 화면에는
   * 한 번만 보이고, 서버가 준 정확한 문장은 한 번 펼치면 그대로 있다.
   */
  answered?: boolean;
  onRetry?: () => void;
  onOpenSettings?: () => void;
}

/**
 * 오류 코드별 안내. **코드가 아는 것만 말한다 — 지어내지 않는다.**
 *
 * 여기 없는 코드에는 문구를 붙이지 않는다. 예전에는 기본값으로 「MCP Server
 * 인증이 만료되었습니다 (401 Unauthorized)」를 깔아 놔서, 프로젝트를 안 골라
 * 생긴 `ValueError` 에도 인증 이야기를 했다 — 사람이 설정만 계속 확인하게 된다.
 */
const ERROR_HINTS: Record<string, string> = {
  '401': '연결 인증이 만료되었습니다. 설정에서 연결 상태를 확인하세요.',
  '429': '요청 한도를 초과했습니다. 잠시 후 다시 시도하세요.',
  timeout: '외부 서버가 시간 안에 응답하지 않았습니다. 다시 시도하세요.',
  unreachable: '외부 서버에 연결하지 못했습니다. 주소와 상태를 확인하세요.',
  validation: '요청 값이 받아들여지지 않았습니다. 아래 사유를 확인하세요.',
};

/**
 * 설정으로 보내도 소용 있는 오류인가. 아니면 그 버튼을 주지 않는다.
 *
 * `RepositoryError`·`OAuthError` 가 여기 있는 이유는 **커넥터 자격증명이 만료된
 * 경로가 그 예외로 온다**는 것이다(`ConnectorRepository.get_credential` →
 * "연결이 만료됐습니다. 다시 연결해 주세요."). 그때는 설정에서 다시 연결하는
 * 것이 정확히 사람이 할 일이다.
 */
const CONNECTION_CODES = new Set([
  '401',
  '429',
  'timeout',
  'unreachable',
  'RepositoryError',
  'OAuthError',
]);

/** ⑤ 오류 카드 — 스트림이 끊긴 지점에 뜨고, 이전 결과물은 위에 보존된다. */
export function ErrorCard({ detail, errorCode, answered, onRetry, onOpenSettings }: ErrorCardProps) {
  // 서버가 준 사유가 가장 정확하다. 그것이 없을 때만 코드로 안내한다.
  // 답이 이미 사유를 말했으면 여기서는 접어 둔다(`answered` 주석 참조).
  const body = answered ? undefined : detail ?? (errorCode ? ERROR_HINTS[errorCode] : undefined);
  const folded = answered ? detail : undefined;
  const showSettings = Boolean(onOpenSettings) && CONNECTION_CODES.has(errorCode ?? '');

  return (
    <section className={styles.errorCard}>
      <span className={styles.errorTitle}>
        <Icon name="triangle-alert" size={18} color="var(--color-danger)" />
        요청을 끝내지 못했습니다
      </span>
      {/* **「지금까지 정리된 내용은 위에 그대로 남아 있습니다」를 걷었다**
          (2026-08-18 PM). 정리된 것이 하나도 없을 때도 그 말이 나왔다 —
          아무것도 없는 화면을 두고 「위에 남아 있다」고 하면 거짓말이다. */}
      {body && <p className={styles.errorBody}>{body}</p>}
      <div className={styles.errorActions}>
        {showSettings && (
          <Button size="sm" variant="outline" onClick={onOpenSettings}>
            설정에서 연결 확인
          </Button>
        )}
        {onRetry && (
          <Button size="sm" onClick={onRetry}>
            다시 시도
          </Button>
        )}
      </div>
      {/* **코드를 지우지는 않는다 — 버그 보고에 쓰인다.** 다만 `ToolInputError`
          같은 클래스명이 첫눈에 보이면 사람은 자기가 뭘 잘못했는지 알 수 없고,
          그건 「MCP·Tool Calling 같은 용어를 그대로 노출하지 않는다」(§0 원칙 2)를
          우리가 어기는 것이다. 접어 두고 이름을 사람 말로 바꾼다. */}
      {(errorCode || folded) && (
        <details className={styles.errorTech}>
          <summary>기술 정보</summary>
          {folded && <p className={styles.errorBody}>{folded}</p>}
          {errorCode && <code className={styles.errorRaw}>{errorCode}</code>}
        </details>
      )}
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

/** 상태 카테고리별 표시. `status_category` 만 분기에 쓴다 — `status` 는 사이트마다 다르다. */
const JIRA_CATEGORY = [
  { key: 'IN_PROGRESS', label: '진행 중', tone: 'progress' },
  { key: 'TO_DO', label: '할 일', tone: 'todo' },
  { key: 'DONE', label: '완료', tone: 'done' },
] as const;

/** 마감이 오늘로부터 며칠 남았는가. 지난 것은 음수다. */
function daysLeft(due: string): number {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((new Date(`${due}T00:00:00`).getTime() - today.getTime()) / 86400000);
}

export interface JiraStatusCardProps {
  /** 사람이 부르는 이름. 없을 때만 Jira 키로 대신한다. */
  projectName?: string | null;
  projectKey: string;
  counts: Record<string, number>;
  issues: JiraIssue[];
}

/**
 * ⑥ Jira 현황 카드.
 *
 * **도구가 준 숫자를 그대로 그린다.** 모델이 문장으로 풀어 쓰면 15건을 옮겨
 * 적다 틀릴 수 있고, 사람도 문단보다 표를 빨리 읽는다 — `task_extraction` 이
 * 결과를 이벤트로 내보내고 화면이 카드로 그리는 것과 같은 규칙이다.
 */
export function JiraStatusCard({
  projectName,
  projectKey,
  counts,
  issues,
}: JiraStatusCardProps) {
  const total = issues.length;
  // 마감이 있는 미완료 건만, 이른 순으로. **지난 것을 숨기지 않는다** —
  // 늦은 일이야말로 사람이 봐야 하는 것이다.
  const upcoming = issues
    .filter((issue) => issue.due_at && issue.status_category !== 'DONE')
    .sort((a, b) => (a.due_at ?? '').localeCompare(b.due_at ?? ''))
    .slice(0, 5);

  return (
    <section className={styles.card}>
      <div className={styles.jiraHead}>
        {/* **Jira 키를 제목에 쓰지 않는다.** `AIP` 는 내부 식별자이고, 사람은
            이미 그 프로젝트의 대화에 있다. 이름을 모를 때만 키로 대신한다 —
            그때는 그것이 우리가 아는 전부다. */}
        <span className={styles.jiraTitle}>
          <Icon name="app-window" size={16} color="var(--color-primary)" />
          {projectName ? `${projectName} 업무 현황` : `${projectKey} 업무 현황`}
        </span>
        <span className={styles.muted}>전체 {total}건</span>
      </div>

      <div className={styles.jiraCounts}>
        {JIRA_CATEGORY.map(({ key, label, tone }) => (
          <div key={key} className={styles.jiraCount}>
            <span className={[styles.jiraDot, styles[tone]].join(' ')} />
            <strong>{counts[key] ?? 0}</strong>
            <span className={styles.muted}>{label}</span>
          </div>
        ))}
        {/* 상태를 모르는 이슈를 조용히 빼지 않는다 — 합계가 안 맞으면 사람이 센다. */}
        {(counts.UNKNOWN ?? 0) > 0 && (
          <div className={styles.jiraCount}>
            <span className={[styles.jiraDot, styles.unknown].join(' ')} />
            <strong>{counts.UNKNOWN}</strong>
            <span className={styles.muted}>상태 미상</span>
          </div>
        )}
      </div>

      {upcoming.length > 0 && (
        <>
          <span className={styles.jiraSubTitle}>마감 임박</span>
          <ul className={styles.jiraList}>
            {upcoming.map((issue) => {
              const left = daysLeft(issue.due_at as string);
              return (
                /* 이슈 키는 Jira 에서 찾을 때만 쓰는 값이라 툴팁으로 내린다. */
                <li key={issue.jira_issue_id} className={styles.jiraRow} title={issue.jira_issue_id}>
                  <span className={styles.jiraSummary}>
                    {issue.summary ?? issue.jira_issue_id}
                  </span>
                  <span className={left < 0 ? styles.jiraOverdue : styles.muted}>
                    {issue.due_at}
                    {left < 0 ? ` · ${-left}일 지남` : left === 0 ? ' · 오늘' : ` · ${left}일 남음`}
                  </span>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </section>
  );
}
