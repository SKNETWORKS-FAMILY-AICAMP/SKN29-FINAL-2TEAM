import { useMemo, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Badge, Button, Icon, TopNav } from '../../components';
import type { ExtractedTask, Project, TaskExtractionResult } from '../../api/projects';
import { MAIN_NAV_TABS } from '../../routes';
import styles from './TaskExtractionPage.module.css';

const FIELD_LABEL: Record<string, string> = {
  required_role: '담당 역할',
  required_skills: '필요 기술',
  effort_hours: '공수',
  start_date: '시작',
  due_date: '마감',
  priority: '우선순위',
  dependencies: '선행 업무',
  constraints: '제약',
  risks: '위험',
  acceptance_criteria: '완료 기준',
  deliverables: '산출물',
};

const INTENT_LABEL: Record<string, string> = {
  TASK_DISCOVERY: '업무 후보 찾기',
  TASK_CORE: '요구사항·산출물',
  ASSIGNMENT_REQUIREMENT: '역할·기술',
  EXECUTION_CONDITION: '공수·일정·제약',
};

function hours(value: number | null): string {
  if (value === null) return '—';
  return `${Number.isInteger(value) ? value : value.toFixed(1)}h`;
}

function date(value: string | null): string {
  if (!value) return '—';
  return value.slice(0, 10).replace(/-/g, '.');
}

/** 값이 있는 것만 보여준다. 빈 항목은 아래 「근거 없음」이 따로 말한다. */
function Facts({ task }: { task: ExtractedTask }) {
  const facts: [string, string][] = [];
  if (task.required_role) facts.push(['담당 역할', task.required_role]);
  if (task.required_skills.length) facts.push(['필요 기술', task.required_skills.join(' · ')]);
  if (task.effort_hours !== null) facts.push(['공수', hours(task.effort_hours)]);
  if (task.start_date) facts.push(['시작', date(task.start_date)]);
  if (task.due_date) facts.push(['마감', date(task.due_date)]);
  if (task.priority) facts.push(['우선순위', task.priority]);

  if (facts.length === 0) return null;

  return (
    <div className={styles.facts}>
      {facts.map(([label, value]) => (
        <span key={label} className={styles.fact}>
          <span className={styles.factLabel}>{label}</span>
          <span className={styles.factValue}>{value}</span>
        </span>
      ))}
    </div>
  );
}

function TaskCard({
  task,
  index,
  evidenceById,
}: {
  task: ExtractedTask;
  index: number;
  evidenceById: Map<string, TaskExtractionResult['evidence'][number]>;
}) {
  const [openEvidence, setOpenEvidence] = useState(false);
  const cited = task.evidence_chunk_ids
    .map((id) => evidenceById.get(id))
    .filter((row): row is TaskExtractionResult['evidence'][number] => row !== undefined);

  return (
    <article className={styles.task}>
      <div className={styles.taskHead}>
        <span className={styles.taskNo}>{index + 1}</span>
        <h2 className={styles.taskTitle}>{task.title}</h2>
      </div>

      {task.description && <p className={styles.taskDesc}>{task.description}</p>}

      <Facts task={task} />

      {(task.acceptance_criteria.length > 0 || task.deliverables.length > 0) && (
        <div className={styles.lists}>
          {task.acceptance_criteria.length > 0 && (
            <div>
              <span className={styles.listLabel}>완료 기준</span>
              <ul>
                {task.acceptance_criteria.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}
          {task.deliverables.length > 0 && (
            <div>
              <span className={styles.listLabel}>산출물</span>
              <ul>
                {task.deliverables.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* 비어 있는 항목을 숨기지 않고 이름으로 적는다. 근거가 없어 안 채운 것과
          모델이 놓친 것을 사람이 구분할 수 있어야 한다. */}
      {task.missing_fields.length > 0 && (
        <p className={styles.missing}>
          근거 없어 비움 · {task.missing_fields.map((f) => FIELD_LABEL[f] ?? f).join(' · ')}
        </p>
      )}

      <div className={styles.evidence}>
        <button
          type="button"
          className={styles.evidenceToggle}
          onClick={() => setOpenEvidence((prev) => !prev)}
          aria-expanded={openEvidence}
        >
          <Icon name="chevron-down" size={14} className={openEvidence ? styles.rotated : ''} />
          <span>원문 근거 {cited.length}건</span>
        </button>

        {openEvidence && (
          <div className={styles.quotes}>
            {cited.map((row) => (
              <blockquote key={row.chunk_id} className={styles.quote}>
                <p>{row.text}</p>
                <footer>
                  {row.doc_id} · {INTENT_LABEL[row.intent] ?? row.intent} · 유사도{' '}
                  {Math.round(row.retrieval_score * 100)}%
                  <span className={styles.query}>「{row.query}」로 찾음</span>
                </footer>
              </blockquote>
            ))}
            {cited.length === 0 && (
              <p className={styles.noQuote}>이 업무에 연결된 근거 문장이 없습니다.</p>
            )}
          </div>
        )}
      </div>
    </article>
  );
}

/**
 * 추출된 업무를 사람이 처음 확인하는 화면.
 *
 * 중간발표의 완료 지점이다 — P3 기준 그대로 **"기획서에서 추출된 Task가 원문 근거와
 * 함께 화면에 표시"**된다. 팀원 배정과 추천은 이 다음 단계다.
 *
 * 근거를 접어 두되 없애지 않는다. AI가 만든 문장을 그대로 믿게 하지 않으려면
 * 「어느 문서의 어느 문장에서 나왔나」를 한 번의 클릭 안에 둬야 한다.
 *
 * 결과는 앞 화면에서 router state 로 받는다. 서버가 추출 결과를 저장하지 않기
 * 때문인데(`task`·`task_source` 적재는 다음 단계다), 그래서 새로고침하면 사라진다.
 * 지어낸 값을 대신 보여주는 대신 「다시 추출해 주세요」라고 말한다.
 */
export default function TaskExtractionPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const state = location.state as { result?: TaskExtractionResult; project?: Project } | null;
  const result = state?.result;
  const project = state?.project;

  const evidenceById = useMemo(
    () => new Map((result?.evidence ?? []).map((row) => [row.chunk_id, row])),
    [result],
  );

  const [copied, setCopied] = useState(false);

  async function copyJson() {
    if (!result) return;
    await navigator.clipboard.writeText(JSON.stringify(result, null, 2));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  }

  if (!result) {
    return (
      <div className={styles.page}>
        <TopNav tabs={MAIN_NAV_TABS} activeTo="/projects" />
        <main className={styles.main}>
          <p className={styles.empty}>
            추출 결과가 없습니다. 결과는 아직 저장되지 않아 새로고침하면 사라집니다.
          </p>
          <Button variant="primary" onClick={() => navigate('/tasks/distribution/documents')}>
            다시 추출하기
          </Button>
        </main>
      </div>
    );
  }

  const totalHours = result.tasks.reduce((sum, task) => sum + (task.effort_hours ?? 0), 0);
  const noEstimate = result.tasks.filter((task) => task.effort_hours === null).length;

  return (
    <div className={styles.page}>
      <TopNav tabs={MAIN_NAV_TABS} activeTo="/projects" />

      <main className={styles.main}>
        <button
          type="button"
          className={styles.back}
          onClick={() => navigate('/tasks/distribution/documents')}
        >
          <Icon name="arrow-left" size={16} />
          <span>문서 다시 고르기</span>
        </button>

        <div className={styles.header}>
          <div>
            <h1>{project?.name ?? '추출된 업무'}</h1>
            <p className={styles.meta}>
              업무 {result.tasks.length}건 · 공수 합계 {hours(totalHours)}
              {noEstimate > 0 && ` · 공수 미상 ${noEstimate}건`} · 근거{' '}
              {result.evidence.length}개 문단
            </p>
          </div>
          {project && (
            <Badge tone="neutral">
              {project.status === 'DRAFT' ? '작성 중' : project.status}
            </Badge>
          )}
        </div>

        {result.warnings.length > 0 && (
          <div className={styles.warnings}>
            {result.warnings.map((warning) => (
              <p key={warning}>{warning}</p>
            ))}
          </div>
        )}

        <div className={styles.tasks}>
          {result.tasks.map((task, index) => (
            <TaskCard
              key={`${task.title}-${index}`}
              task={task}
              index={index}
              evidenceById={evidenceById}
            />
          ))}
          {result.tasks.length === 0 && (
            <p className={styles.empty}>
              기준 문서에서 업무를 찾지 못했습니다. 근거가 없는 업무를 지어내지 않습니다.
            </p>
          )}
        </div>

        {/* 어떤 질의로 무엇을 몇 건 찾았는지. 결과가 빈약할 때 어느 단계가 비었는지
            알아야 문서를 더 넣을지 판단할 수 있다. */}
        <details className={styles.trace}>
          <summary>검색 단계 {result.trace.length}단계</summary>
          <div className={styles.traceBody}>
            {result.trace.map((step) => {
              const [intent, hits] = step.split(':');
              return (
                <div key={step} className={styles.traceRow}>
                  <span className={styles.traceIntent}>{INTENT_LABEL[intent] ?? intent}</span>
                  <span className={styles.traceHits}>{hits}건</span>
                </div>
              );
            })}
          </div>
          <p className={styles.model}>
            {result.model} · reasoning {result.reasoning_effort}
          </p>
        </details>

        <div className={styles.actions}>
          <span className={styles.note}>
            팀원 배정과 추천은 다음 단계입니다. 이 결과는 아직 저장되지 않습니다.
          </span>
          {/* 결과가 브라우저 메모리에만 있어 새로고침하면 사라진다. 저장이 들어오기
              전까지 이것이 결과를 밖으로 꺼내는 유일한 방법이다. */}
          <button type="button" className={styles.copyBtn} onClick={() => void copyJson()}>
            {copied ? '복사됨' : 'JSON 복사'}
          </button>
          <Link to="/projects" className={styles.doneLink}>
            프로젝트 목록으로
          </Link>
        </div>
      </main>
    </div>
  );
}
