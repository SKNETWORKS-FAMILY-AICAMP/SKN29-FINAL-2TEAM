import { useCallback, useEffect, useState } from 'react';
import { Button, Icon, TopNav } from '../../components';
import { ApiError } from '../../api/client';
import {
  findOnboardingProject,
  getProjectWorkload,
  syncProjectTasks,
} from '../../api/projects';
import type { PersonWorkload, WorkloadResult } from '../../api/projects';
import { MAIN_NAV_TABS } from '../../routes';
import { useSession } from '../../utils/session';
import styles from './WorkloadPage.module.css';

const BLOCKED_LABEL: Record<string, string> = {
  NO_SCHEDULE: '근무조건 없음',
  ON_LEAVE: '휴직·휴가',
  NO_EFFECTIVE_CAPACITY: '가용시간 0',
};

/** 막대 색은 Jira 프로젝트 순서를 따른다 — 두 개까지가 지금 시연 범위다. */
const SEGMENT_CLASS = [styles.segmentPrimary, styles.segmentSecondary];

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function fourWeeksFrom(start: string): string {
  const date = new Date(`${start}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + 28);
  return date.toISOString().slice(0, 10);
}

function rateClass(rate: number | null): string {
  if (rate === null) return styles.rateBlocked;
  if (rate > 100) return styles.rateOver;
  if (rate >= 80) return styles.rateHigh;
  return styles.rateNormal;
}

function PersonRow({ person, scale }: { person: PersonWorkload; scale: number }) {
  const blocked = person.blocked_reason !== null;

  return (
    <div className={styles.personRow}>
      <div className={styles.personHead}>
        <p className={styles.personName}>{person.name ?? person.person_id}</p>
        {person.job_role && <span className={styles.personRole}>{person.job_role}</span>}
        <span className={styles.personNumbers}>
          {blocked
            ? `할당 ${person.current_allocation}h`
            : `${person.current_allocation}h / ${person.effective_capacity}h · 잔여 ${person.remaining_capacity}h`}
        </span>
        <span className={`${styles.personRate} ${rateClass(person.load_rate)}`}>
          {blocked ? BLOCKED_LABEL[person.blocked_reason!] ?? person.blocked_reason : `${person.load_rate}%`}
        </span>
      </div>

      <div className={styles.trackWrap}>
        <div className={styles.track}>
          {/*
            프로젝트별로 쪼개 쌓는다. 한 칸만 보면 90%인데 합치면 122%라는 것을
            같은 막대에서 보여주는 것이 이 화면의 목적이다.
          */}
          {!blocked &&
            person.by_project.map((entry, index) => (
              <div
                key={entry.project_key}
                className={`${styles.segment} ${SEGMENT_CLASS[index % SEGMENT_CLASS.length]}`}
                style={{ width: `${((entry.load_rate ?? 0) / scale) * 100}%` }}
                title={`${entry.project_key} ${entry.hours}h (${entry.load_rate}%)`}
              />
            ))}
        </div>
        {/* 100% 지점을 눈금으로 세운다. 막대를 100%에서 자르면 122%와 300%가 같아 보인다. */}
        <div className={styles.fullMark} style={{ left: `${(100 / scale) * 100}%` }} />
      </div>

      {!blocked && person.by_project.length > 0 && (
        <div className={styles.breakdown}>
          {person.by_project.map((entry, index) => (
            <span key={entry.project_key} className={styles.chip}>
              <span
                className={`${styles.chipDot} ${SEGMENT_CLASS[index % SEGMENT_CLASS.length]}`}
              />
              {entry.project_key} {entry.hours}h ({entry.load_rate}%)
            </span>
          ))}
          {person.unscheduled_backlog_count > 0 && (
            <span className={styles.chip}>
              미일정 Backlog {person.unscheduled_backlog_hours}h / {person.unscheduled_backlog_count}건
            </span>
          )}
          {person.missing_estimate_count > 0 && (
            <span className={styles.chip}>공수 미입력 {person.missing_estimate_count}건</span>
          )}
        </div>
      )}
    </div>
  );
}

export default function WorkloadPage() {
  const session = useSession();
  const token = session?.token;

  const [from, setFrom] = useState(today);
  const [to, setTo] = useState(() => fourWeeksFrom(today()));
  const [result, setResult] = useState<WorkloadResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError('');
    try {
      const project = await findOnboardingProject(token);
      if (!project) {
        setError('연결된 프로젝트가 없습니다. 온보딩에서 소스를 먼저 선택해 주세요.');
        setResult(null);
        return;
      }
      setResult(await getProjectWorkload(token, project.proj_id, from, to));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '부하율을 불러오지 못했습니다.');
      setResult(null);
    } finally {
      setLoading(false);
    }
  }, [token, from, to]);

  useEffect(() => {
    void load();
  }, [load]);

  /** Jira를 다시 읽어 `exist_task`를 교체한 뒤 같은 기간으로 다시 계산한다. */
  const resync = async () => {
    if (!token) return;
    setSyncing(true);
    setError('');
    try {
      const project = await findOnboardingProject(token);
      if (project) await syncProjectTasks(token, project.proj_id);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Jira 동기화에 실패했습니다.');
    } finally {
      setSyncing(false);
    }
  };

  // 최대 부하율까지 담는 축이라 100%를 넘는 사람도 얼마나 넘었는지 보인다.
  const maxRate = Math.max(100, ...(result?.people ?? []).map((p) => p.load_rate ?? 0));
  const scale = Math.ceil(maxRate / 10) * 10;

  return (
    <div className={styles.page}>
      <TopNav tabs={MAIN_NAV_TABS} activeTo="/dashboard" />

      <div className={styles.workspace}>
        <div className={styles.heading}>
          <h1>기간별 업무 부하</h1>
          <p>
            Jira에 기록된 잔여 공수와 HR 근무조건으로 계산한 <strong>계획 공수 기준 배정률</strong>입니다.
            난이도·스트레스처럼 데이터로 확인할 수 없는 것은 반영하지 않습니다.
          </p>
        </div>

        <div className={styles.controls}>
          <div className={styles.field}>
            <label htmlFor="workload-from">시작</label>
            <input
              id="workload-from"
              type="date"
              value={from}
              onChange={(event) => setFrom(event.target.value)}
            />
          </div>
          <div className={styles.field}>
            <label htmlFor="workload-to">종료</label>
            <input
              id="workload-to"
              type="date"
              value={to}
              onChange={(event) => setTo(event.target.value)}
            />
          </div>
          <Button variant="secondary" onClick={resync} disabled={syncing || loading}>
            {syncing ? 'Jira 동기화 중…' : 'Jira 다시 읽기'}
          </Button>
        </div>

        {error && <div className={styles.error}>{error}</div>}
        {loading && <div className={styles.state}>불러오는 중…</div>}

        {!loading && result && (
          <>
            <div className={styles.card}>
              <div>
                <p className={styles.cardTitle}>인원별 부하율</p>
                <p className={styles.cardNote}>
                  {result.period_start} ~ {result.period_end} · 근무일 {result.workdays}일 · 세로선이 100%
                </p>
              </div>

              <div className={styles.personList}>
                {result.people.map((person) => (
                  <PersonRow key={person.person_id} person={person} scale={scale} />
                ))}
                {result.people.length === 0 && (
                  <p className={styles.cardNote}>팀원이 없습니다. 설정에서 팀을 먼저 만들어 주세요.</p>
                )}
              </div>
            </div>

            {/* 제외한 것을 제외했다고 보여준다. 숨기면 신뢰를 잃는다. */}
            <div className={styles.card}>
              <p className={styles.cardTitle}>부하율에 넣지 않은 것</p>
              <div className={styles.diagnostics}>
                <div className={styles.diagnostic}>
                  <span
                    className={`${styles.diagnosticValue} ${
                      result.missing_estimate_count > 0 ? styles.diagnosticValueWarn : ''
                    }`}
                  >
                    {result.missing_estimate_count}건
                  </span>
                  <span className={styles.diagnosticLabel}>공수 미입력</span>
                </div>
                <div className={styles.diagnostic}>
                  <span
                    className={`${styles.diagnosticValue} ${
                      result.unmapped_assignee_count > 0 ? styles.diagnosticValueWarn : ''
                    }`}
                  >
                    {result.unmapped_assignee_count}건
                  </span>
                  <span className={styles.diagnosticLabel}>담당자 미매핑</span>
                </div>
                <div className={styles.diagnostic}>
                  <span className={styles.diagnosticValue}>{result.unscheduled_backlog_hours}h</span>
                  <span className={styles.diagnosticLabel}>미일정 Backlog</span>
                </div>
              </div>

              <div className={styles.limitations}>
                {result.limitations.map((line) => (
                  <p key={line}>
                    <Icon name="triangle-alert" size={12} /> {line}
                  </p>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
