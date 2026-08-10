import { useState } from 'react';
import { Badge, Button, Checkbox, Icon } from '../../../components';
import {
  MOCK_DOC_CANDIDATES,
  MOCK_FAILURES,
  MOCK_ISSUES,
  MOCK_STEPS,
  MOCK_TASKS,
} from '../mockChat';
import type { ExtractedTask } from '../mockChat';
import styles from './cards.module.css';

/**
 * Chat 스트림에 뜨는 카드 6종. 전부 mock 데이터를 본다 — 실연동은 백엔드
 * 단계 3(NDJSON 스트림·확인 게이트 API) 이후.
 *
 * 카피는 Figma 문안 그대로다. 정직 표기 원칙 — 부분 상태를 성공처럼 뭉개지
 * 않는다(「근거 없어 비움」·「17/20 등록 완료」·「판정 보류」).
 */

/** ① 진행 카드 — 장시간 작업의 단계·검색어·근거 수. 기존 진행 모달의 인라인판. */
export function ProgressCard() {
  const doneCount = MOCK_STEPS.filter((step) => step.state === 'done').length + 1;

  return (
    <section className={styles.card}>
      <div className={styles.progressHead}>
        <span className={styles.progressTitle}>
          <Icon name="loader" size={16} color="var(--color-primary)" spin />
          업무를 정리하는 중
        </span>
        <span className={styles.progressCount}>
          {doneCount} / {MOCK_STEPS.length} 단계 · 1분 12초
        </span>
      </div>

      <div className={styles.progressTrack}>
        <span className={styles.progressFill} style={{ width: `${(doneCount / MOCK_STEPS.length) * 100}%` }} />
      </div>

      <ul className={styles.steps}>
        {MOCK_STEPS.map((step) => (
          <li key={step.label} className={styles.step}>
            {step.state === 'done' && <Icon name="check-circle" size={15} color="var(--color-success)" />}
            {step.state === 'doing' && <Icon name="loader" size={15} color="var(--color-primary)" spin />}
            {step.state === 'todo' && <Icon name="circle-help" size={15} color="var(--color-border)" />}
            <span className={step.state === 'todo' ? styles.stepLabelTodo : styles.stepLabel}>{step.label}</span>
            {step.meta && <span className={styles.stepMeta}>{step.meta}</span>}
          </li>
        ))}
      </ul>

      <p className={styles.foot}>근거 24건 · 몇 분 걸립니다 · 창을 닫지 않아도 됩니다</p>
    </section>
  );
}

/** ② 근거 카드 — 업무별 근거 접기/펼치기. TaskExtractionPage TaskCard(63-152)의 후신. */
function TaskRow({ task }: { task: ExtractedTask }) {
  const [checked, setChecked] = useState(task.checked);
  const [open, setOpen] = useState(task.evidence.length > 0);

  return (
    <div className={styles.taskRow}>
      <Checkbox checked={checked} onChange={setChecked} />
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

/** ③ 확인 카드 — E2E STEP 6. 승인 전까지 Jira에 아무것도 만들지 않는다. */
export function ConfirmCard() {
  return (
    <section className={styles.cardFlush}>
      <div className={styles.confirmHead}>
        <span className={styles.confirmLeft}>
          <Checkbox checked onChange={() => undefined} />
          <strong>전체 선택</strong>
          <span className={styles.muted}>20건 모두 선택됨 · 공수 합계 184h</span>
        </span>
        <span className={styles.muted}>업무 20건 · 근거 24개 문단</span>
      </div>

      <p className={styles.warnBanner}>
        기준 문서에서 마감일 근거를 찾지 못한 업무가 있습니다. 근거 없는 항목은 채우지 않고 「근거 없어 비움」으로
        표시합니다.
      </p>

      {MOCK_TASKS.map((task) => (
        <TaskRow key={task.no} task={task} />
      ))}

      <button type="button" className={styles.more}>
        외 17건 보기
      </button>

      <p className={styles.trace}>검색 단계 4단계 · 검색어 gpt-5.6 luna(low) · 근거 정리 gpt-5.6 sol(xhigh)</p>

      <div className={styles.confirmActions}>
        <span className={styles.muted}>승인하기 전까지 Jira에는 아무것도 만들지 않습니다.</span>
        <Button size="sm">선택한 20건 Jira에 등록</Button>
      </div>
    </section>
  );
}

/** ④ 결과 카드 — 전부 성공 / 부분 실패. 성공분은 롤백하지 않는다(E2E §2). */
export function ResultCard({ partial }: { partial: boolean }) {
  return (
    <section className={styles.cardFlush}>
      <div className={partial ? styles.resultHeadWarn : styles.resultHeadOk}>
        <span className={styles.resultTitle}>
          <Icon
            name={partial ? 'triangle-alert' : 'check-circle'}
            size={18}
            color={partial ? 'var(--color-warning-text)' : 'var(--color-success-text)'}
          />
          {partial ? '17/20 등록 완료 — 3건 실패' : '20/20 등록 완료'}
        </span>
        <span className={styles.resultMeta}>
          {partial ? '성공분은 되돌리지 않습니다' : '통합포털 개편 (PORTAL) · 1분 48초 소요'}
        </span>
      </div>

      <div className={styles.issueHead}>
        <strong>등록된 이슈 {partial ? '17건' : ''}</strong>
        <span className={styles.muted}>이슈를 누르면 Jira에서 열립니다</span>
      </div>

      {MOCK_ISSUES.map((issue) => (
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

      <button type="button" className={styles.more}>
        외 {partial ? 14 : 17}건 보기
      </button>

      {partial && (
        <>
          <div className={styles.failHead}>
            <Icon name="circle-x" size={15} color="var(--color-danger)" />
            <strong>실패 3건 — 사유</strong>
          </div>
          {MOCK_FAILURES.map((failure) => (
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
            ? '실패한 3건만 다시 시도합니다. 이미 등록된 17건은 그대로 둡니다.'
            : '업무별 근거(E1~E24)는 이 대화에 그대로 저장됩니다. 새로고침해도 사라지지 않습니다.'}
        </span>
        {partial ? (
          <Button size="sm" iconLeft={<Icon name="refresh" size={14} />}>
            실패분 3건 재시도
          </Button>
        ) : (
          <Button size="sm" variant="outline">
            Jira에서 열기
          </Button>
        )}
      </div>
    </section>
  );
}

/** ⑤ 오류 카드 — 스트림이 끊긴 지점에 뜨고, 이전 결과물은 위에 보존된다. */
export function ErrorCard() {
  return (
    <section className={styles.errorCard}>
      <span className={styles.errorTitle}>
        <Icon name="triangle-alert" size={18} color="var(--color-danger)" />
        Jira에 연결하지 못했습니다
      </span>
      <p className={styles.errorBody}>
        MCP Server 인증이 만료되었습니다 (401 Unauthorized). 설정 &gt; MCP에서 Jira 연결을 다시 확인해 주세요. 정리된
        업무와 근거는 위에 그대로 남아 있으니, 연결을 고친 뒤 재시도하면 됩니다.
      </p>
      <div className={styles.errorActions}>
        <Button size="sm" variant="outline">
          설정에서 연결 확인
        </Button>
        <Button size="sm">다시 시도</Button>
      </div>
      <code className={styles.errorRaw}>error · mcp_jira · 401 Unauthorized · run_id 8f31c2</code>
    </section>
  );
}

/** ⑥ 문서 선택 카드 — E2E STEP 2 되묻기. 기준 문서 1건만 고른다. */
export function DocPickCard() {
  const [selected, setSelected] = useState(MOCK_DOC_CANDIDATES.findIndex((doc) => doc.selected));

  return (
    <section className={styles.cardFlush}>
      <div className={styles.docHead}>
        <Icon name="file-text" size={15} color="var(--color-primary)" />
        <strong>기준 문서 후보 3건</strong>
        <span className={styles.muted}>
          기준 문서 1건만 고르면 나머지 근거는 팀 문서 전체에서 찾습니다 · 아직 안 읽은 문서는 고르는 순간 읽습니다
        </span>
      </div>

      {MOCK_DOC_CANDIDATES.map((doc, index) => (
        <label key={doc.name} className={[styles.docRow, selected === index ? styles.docRowOn : ''].join(' ')}>
          <input
            type="radio"
            name="primary-doc"
            checked={selected === index}
            onChange={() => setSelected(index)}
            className={styles.radio}
          />
          <span className={styles.docBody}>
            <strong>{doc.name}</strong>
            <span className={styles.muted}>{doc.meta}</span>
          </span>
          <Badge tone={doc.state === '준비됨' ? 'success' : 'neutral'}>{doc.state}</Badge>
        </label>
      ))}

      <div className={styles.confirmActions}>
        <span className={styles.muted}>다른 문서를 쓰려면 채팅으로 파일명을 알려 주세요.</span>
        <Button size="sm">이 문서로 진행</Button>
      </div>
    </section>
  );
}
