import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '../Icon/Icon';
import {
  ApiError,
  SKILL_JOB_STAGES,
  cancelSkillJob,
  getSkillJob,
  getSkillJobFailureCopy,
  isSkillJobOpen,
  isSkillJobTerminal,
  listOpenSkillJobs,
} from '../../api/skillJobs';
import type { SkillJob, SkillJobStage } from '../../api/skillJobs';
import { PATHS } from '../../routes';
import { onSkillJobRemoved, onSkillJobStarted } from '../../utils/skillJobSignal';
import { useStackedCard } from '../../utils/progressStack';
import { subscribeSession, loadSession } from '../../utils/session';
import styles from './SkillJobCenter.module.css';

/**
 * 스킬 검증 job 진행 카드 — `IndexingProgress`("문서를 읽는 중")와 같은 자리,
 * 같은 이유로 전역이다(정본 03_스킬_검증_등록_설계.md §13 "진행·실패 UI").
 *
 * **`IndexingProgress`와 다른 점 — job은 여러 개가 동시에 있을 수 있다.**
 * 문서 색인은 "전체 진행률 하나"만 있으면 됐지만, 스킬은 사람마다 여러
 * 스킬을 동시에 고칠 수 있다. 그래서 job마다 카드 하나씩,
 * `ProgressCardStack`(`utils/progressStack.ts`)에 각자 등록한다 — 실제 등록은
 * 아래 `SkillJobCard`(job 하나당 컴포넌트 인스턴스 하나)가 한다. 컴포넌트
 * 하나가 훅을 매번 다른 횟수로 부르면 안 되므로(Rules of Hooks), "job마다
 * 카드 하나"를 이렇게 별도 컴포넌트로 나눴다 — `.map()` 안에서 직접
 * `useStackedCard()`를 부르면 job 개수가 바뀔 때마다 훅 호출 횟수도 바뀐다.
 */

const STAGE_LABELS: Record<SkillJobStage, string> = {
  WAITING: '검증 대기 중',
  CHECKING: '기본 정보 확인 중',
  PREPARING_TESTS: '테스트 준비 중',
  TESTING: '스킬 테스트 중',
  PUBLISHING: '스킬 등록 중',
};

const POLL_ACTIVE_MS = 3_000;
const POLL_NUDGE_MS = 1_500;
/** 신호를 받은 뒤 이만큼은 짧은 간격을 유지한다 — `IndexingProgress`의
 * `NUDGE_WINDOW_MS`와 같은 이유(서버에 아직 job 행이 안 보일 수 있는 창). */
const NUDGE_WINDOW_MS = 15_000;
/** 성공한 job은 이만큼 더 보여 준 뒤 스스로 사라진다. 실패·취소는 사람이
 * 직접 닫아야 한다 — 실패 이유는 무심코 지나치면 안 된다. */
const SUCCESS_HOLD_MS = 8_000;

interface TrackedJob {
  job: SkillJob;
  /** 이 job이 종료 상태로 바뀐 시각(로컬 시계) — SUCCEEDED 자동 숨김의 기준. */
  terminalAt: number | null;
}

function statusHeadline(job: SkillJob): string {
  switch (job.status) {
    case 'SUCCEEDED':
      return '완료';
    case 'FAILED':
      return '검증 실패';
    case 'CANCEL_REQUESTED':
      return '취소하는 중…';
    case 'CANCELED':
      return '취소됨';
    default:
      return STAGE_LABELS[job.stage];
  }
}

export function SkillJobCenter() {
  const [session, setSession] = useState(loadSession);
  const [jobs, setJobs] = useState<Record<string, TrackedJob>>({});
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [nudgeUntil, setNudgeUntil] = useState(0);
  const timer = useRef<number | null>(null);
  const jobsRef = useRef<Record<string, TrackedJob>>({});
  const token = session?.token;
  const hasTrackedWork = Object.values(jobs).some(
    ({ job, terminalAt }) =>
      isSkillJobOpen(job) || (job.status === 'SUCCEEDED' && terminalAt !== null),
  );

  useEffect(() => {
    jobsRef.current = jobs;
  }, [jobs]);

  useEffect(() => subscribeSession(() => setSession(loadSession())), []);
  useEffect(() => onSkillJobStarted(() => setNudgeUntil(Date.now() + NUDGE_WINDOW_MS)), []);

  useEffect(() => {
    if (nudgeUntil === 0) return;
    const remaining = nudgeUntil - Date.now();
    if (remaining <= 0) {
      setNudgeUntil(0);
      return;
    }
    const t = window.setTimeout(() => setNudgeUntil(0), remaining);
    return () => window.clearTimeout(t);
  }, [nudgeUntil]);

  const applyJob = useCallback((job: SkillJob) => {
    setJobs((prev) => {
      const existing = prev[job.job_id];
      const nowTerminal = isSkillJobTerminal(job);
      // 이미 종료 상태로 기록해 둔 게 있으면(=terminalAt이 이미 찍혀 있으면)
      // 그 시각을 그대로 지킨다 — 폴링마다 다시 지금 시각으로 덮어쓰면
      // SUCCESS_HOLD_MS 카운트다운이 매번 리셋돼 카드가 영원히 안 사라진다.
      const terminalAt = !nowTerminal ? null : (existing?.terminalAt ?? Date.now());
      return {
        ...prev,
        [job.job_id]: { job, terminalAt },
      };
    });
  }, []);

  const removeJob = useCallback((jobId: string) => {
    setJobs((prev) => {
      const next = { ...prev };
      delete next[jobId];
      return next;
    });
    setExpanded((prev) => {
      if (!(jobId in prev)) return prev;
      const next = { ...prev };
      delete next[jobId];
      return next;
    });
  }, []);

  // 설정 화면에서 실패 기록을 삭제하거나 수정 흐름으로 넘기면, 다음 3초
  // 폴링을 기다리지 않고 오른쪽 아래 카드도 같은 순간에 제거한다.
  useEffect(() => onSkillJobRemoved(removeJob), [removeJob]);

  const refreshOpenList = useCallback(
    (currentToken: string) =>
      listOpenSkillJobs(currentToken)
        .then((rows) => rows.forEach(applyJob))
        .catch(() => {
          // 곁다리 정보다 — `IndexingProgress`와 같은 이유로 조용히 넘어간다.
        }),
    [applyJob],
  );

  // 새로고침 후 "내 열린 job" 복원(§13) — 마운트·로그인 시 한 번.
  useEffect(() => {
    if (!token) return;
    void refreshOpenList(token);
  }, [token, refreshOpenList]);

  // 추적 중인 job 각각을 폴링하고, **동시에 열린 job 목록도 다시 받는다.**
  // 후자가 없으면 방금 새로 생긴 job을 영영 못 찾는다 — `jobs`(로컬에 이미
  // 추적 중인 것)만 개별 조회하면, 최초 마운트 이후 생긴 job은 애초에
  // `jobs`에 없어서 이 반복문 자체를 안 탄다. `notifySkillJobStarted()`가
  // 신호만 보내고 job_id를 안 주는 이유(`skillJobSignal.ts`)도 이 목록 재조회로
  // 새 job을 스스로 찾아내기 때문이다.
  useEffect(() => {
    if (!token) return;

    function stop() {
      if (timer.current !== null) {
        window.clearInterval(timer.current);
        timer.current = null;
      }
    }

    function poll() {
      void refreshOpenList(token as string);
      const now = Date.now();
      Object.values(jobsRef.current).forEach(({ job, terminalAt }) => {
        if (isSkillJobTerminal(job)) {
          if (job.status === 'SUCCEEDED' && terminalAt !== null && now - terminalAt >= SUCCESS_HOLD_MS) {
            removeJob(job.job_id);
          }
          return;
        }
        getSkillJob(token as string, job.job_id)
          .then(applyJob)
          .catch((exc) => {
            // job이 사라졌으면(다른 화면에서 지웠거나) 더 이상 쫓지 않는다.
            if (exc instanceof ApiError && exc.status === 404) removeJob(job.job_id);
          });
      });
    }

    function start() {
      stop();
      if (document.hidden) return;
      const hasWork = hasTrackedWork;
      // 추적 중인 job이 없어도 nudge 기간에는 계속 돈다 — 새 job이 아직
      // `jobs`에 안 들어와 있어도, `poll()`의 `refreshOpenList()`가 매 tick
      // 목록을 다시 받아 스스로 찾아낸다.
      if (!hasWork && nudgeUntil === 0) return;
      poll();
      const interval = nudgeUntil !== 0 ? POLL_NUDGE_MS : POLL_ACTIVE_MS;
      timer.current = window.setInterval(poll, interval);
    }

    start();
    document.addEventListener('visibilitychange', start);
    return () => {
      stop();
      document.removeEventListener('visibilitychange', start);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, hasTrackedWork, nudgeUntil, applyJob, removeJob, refreshOpenList]);

  async function handleCancel(jobId: string) {
    if (!token) return;
    try {
      const updated = await cancelSkillJob(token, jobId);
      applyJob(updated);
    } catch {
      // 취소 실패는 조용히 넘어간다 — 다음 폴링이 실제 상태를 다시 보여준다.
    }
  }

  return (
    <>
      {Object.values(jobs).map(({ job }) => (
        <SkillJobCard
          key={job.job_id}
          job={job}
          expanded={Boolean(expanded[job.job_id])}
          onToggleExpand={() =>
            setExpanded((prev) => ({ ...prev, [job.job_id]: !prev[job.job_id] }))
          }
          onDismiss={() => removeJob(job.job_id)}
          onCancel={() => void handleCancel(job.job_id)}
        />
      ))}
    </>
  );
}

interface SkillJobCardProps {
  job: SkillJob;
  expanded: boolean;
  onToggleExpand: () => void;
  onDismiss: () => void;
  onCancel: () => void;
}

/** job 하나당 인스턴스 하나 — `useStackedCard()`를 정확히 한 번 부른다. */
function SkillJobCard({ job, expanded, onToggleExpand, onDismiss, onCancel }: SkillJobCardProps) {
  const navigate = useNavigate();
  const terminal = isSkillJobTerminal(job);
  const failed = job.status === 'FAILED';
  const canceling = job.status === 'CANCEL_REQUESTED';

  const card = (
    <aside
      className={styles.card}
      role="status"
      aria-live="polite"
      aria-label={`${job.skill_name} 스킬 검증 — ${statusHeadline(job)}`}
    >
      <div className={styles.head}>
        {terminal ? (
          failed || job.status === 'CANCELED' ? (
            <Icon
              name={failed ? 'triangle-alert' : 'x'}
              size={15}
              color={failed ? 'var(--color-danger)' : 'var(--color-muted)'}
            />
          ) : (
            <Icon name="check-circle" size={15} color="var(--color-success)" />
          )
        ) : (
          <Icon name="loader" size={15} spin color="var(--color-primary)" />
        )}
        <span className={styles.title}>{job.skill_name}</span>
        <span className={styles.status}>{statusHeadline(job)}</span>
        <button
          type="button"
          className={styles.expandButton}
          onClick={onToggleExpand}
          aria-expanded={expanded}
          aria-label={expanded ? '자세히 접기' : '자세히 보기'}
        >
          <Icon name={expanded ? 'chevron-down' : 'chevron-right'} size={14} />
        </button>
        {terminal && (
          <button type="button" className={styles.close} onClick={onDismiss} aria-label="닫기">
            <Icon name="x" size={13} />
          </button>
        )}
      </div>

      {expanded && (
        <div className={styles.detail}>
          <ol className={styles.steps}>
            {SKILL_JOB_STAGES.map((stage, index) => {
              const state =
                failed && index === job.stage_index
                  ? 'error'
                  : index < job.stage_index || job.status === 'SUCCEEDED'
                    ? 'done'
                    : index === job.stage_index
                      ? 'current'
                      : 'pending';
              return (
                <li key={stage} className={styles.step} data-state={state}>
                  <span className={styles.stepCircle}>
                    {state === 'done' ? (
                      <Icon name="check" size={11} color="var(--color-surface)" />
                    ) : state === 'error' ? (
                      <Icon name="x" size={11} color="var(--color-surface)" />
                    ) : (
                      index + 1
                    )}
                  </span>
                  <span className={styles.stepLabel}>{STAGE_LABELS[stage]}</span>
                </li>
              );
            })}
          </ol>

          {failed && (
            <p className={styles.failureSummary}>{getSkillJobFailureCopy(job).reason}</p>
          )}

          {!terminal && (
            <p className={styles.activity}>
              <Icon name="loader" size={13} spin color="var(--color-primary)" />
              <span>{job.waiting_reason ?? job.progress_message}</span>
              {job.progress_total !== null && job.progress_total > 0 && (
                <strong>{job.progress_current ?? 0}/{job.progress_total}</strong>
              )}
            </p>
          )}

          <div className={styles.actions}>
            {!terminal && !canceling && (
              <button type="button" className={styles.link} onClick={onCancel}>
                취소
              </button>
            )}
            <button
              type="button"
              className={styles.link}
              onClick={() => navigate(`${PATHS.settingsSkills}?job=${encodeURIComponent(job.job_id)}`)}
            >
              자세히보기
            </button>
          </div>
        </div>
      )}
    </aside>
  );

  useStackedCard(`skill-job-${job.job_id}`, card);
  return null;
}

export default SkillJobCenter;
