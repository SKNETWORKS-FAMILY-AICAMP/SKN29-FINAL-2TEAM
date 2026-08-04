import { useCallback, useEffect, useState } from 'react';
import { Icon, TopNav, useToast } from '../../components';
import { ApiError } from '../../api/client';
import {
  getTeamWorkload,
  listMyProjects,
  listTeamDeadlines,
  syncTeamTasks,
} from '../../api/projects';
import type { DeadlineResult, Project, WorkloadResult } from '../../api/projects';
import { fetchMyTeam } from '../../api/teams';
import type { Team } from '../../api/teams';
import { MAIN_NAV_TABS } from '../../routes';
import { useSession } from '../../utils/session';
import { OverduePanel } from './OverduePanel';
import { ProjectProgressPanel } from './ProjectProgressPanel';
import { TeamWeekPanel } from './TeamWeekPanel';
import { UpcomingPanel } from './UpcomingPanel';
import styles from './MainDashboardPage.module.css';
import tiles from './TeamDashboard.module.css';

const WEEKDAY = ['일', '월', '화', '수', '목', '금', '토'];

function today(): string {
  const now = new Date();
  return `${now.getMonth() + 1}/${now.getDate()}(${WEEKDAY[now.getDay()]})`;
}

/**
 * 팀 대시보드.
 *
 * 우리 플랫폼을 쓰는 단위는 회사가 아니라 **회사 안의 팀**이라, 여기 보이는 것은
 * 전부 로그인한 사람이 속한 팀의 데이터다(`team_member` 범위). 조직 전체 조직도나
 * 회사 부서별 집계는 이 화면의 일이 아니다.
 *
 * 숫자는 모두 실제 조회 결과다. 값이 없으면 0이나 임의값으로 채우지 않고 "없음"으로
 * 둔다 — 목업 숫자가 실제처럼 보이는 것이 이 화면에서 가장 나쁜 실패다.
 *
 * **배치는 크기가 위계다.** 타일을 전부 같은 크기로 깔면 「시간 부족 1명」과 「계산
 * 불가 0명」이 같은 무게로 놓여, 무엇부터 봐야 할지를 화면이 말해 주지 못한다.
 * 눈이 먼저 닿는 좌상단에 가장 급한 것(지연)을 크게 두고, 아래로 갈수록 작아진다.
 *
 * 올라온 값은 전부 "보고 뭘 할지"가 있는 것만 남겼다. 커넥터 상태나 미매핑 건수는
 * 정상일 때 아무 행동도 낳지 않아서 맨 아래 각주 한 줄로 내렸다.
 */
export default function MainDashboardPage() {
  const { showToast } = useToast();
  const session = useSession();
  const token = session?.token;

  const [team, setTeam] = useState<Team | null>(null);
  const [workload, setWorkload] = useState<WorkloadResult | null>(null);
  const [deadlines, setDeadlines] = useState<DeadlineResult | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError('');
    try {
      // 전부 팀 단위다. 프로젝트를 하나 골라서 그것만 보여 주면, 사람의 실제
      // 부하(모든 프로젝트의 합)보다 낮은 숫자를 보고 여유가 있다고 판단하게 된다.
      const [myTeam, workloadResult, deadlineResult, projectRows] = await Promise.all([
        fetchMyTeam(token).catch(() => null),
        getTeamWorkload(token),
        listTeamDeadlines(token).catch(() => null),
        listMyProjects(token).catch(() => []),
      ]);
      setTeam(myTeam);
      setWorkload(workloadResult);
      setDeadlines(deadlineResult);
      setProjects(projectRows);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '대시보드를 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleRefresh() {
    if (!token || syncing) return;
    setSyncing(true);
    try {
      await syncTeamTasks(token);
      await load();
      showToast('Jira 업무를 다시 읽었습니다', 'success');
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : 'Jira 갱신에 실패했습니다', 'error');
    } finally {
      setSyncing(false);
    }
  }

  const people = workload?.people ?? [];
  const overdue = deadlines?.overdue ?? [];

  // 마감별 누적으로 판정한다. 부하율은 조회 기간에 따라 흔들려서 — 2주로 보면
  // 과부하 0명, 4주면 1명 — 한 화면에 세울 값이 못 된다.
  const short = people.filter((person) => (person.tightest?.slack_hours ?? 0) < 0);
  const worst = short.reduce<(typeof short)[number] | null>(
    (acc, person) =>
      acc === null || (person.tightest?.slack_hours ?? 0) < (acc.tightest?.slack_hours ?? 0)
        ? person
        : acc,
    null,
  );

  // 프로젝트 하나하나의 진행률을 평균 내지 않는다. 20시간짜리와 200시간짜리가
  // 같은 무게가 되어, 작은 프로젝트를 끝내면 팀 전체가 앞선 것처럼 보인다.
  const rated = projects.filter((project) => project.progress && project.status !== 'ARCHIVED');
  const totalHours = rated.reduce((sum, p) => sum + (p.progress?.total_hours ?? 0), 0);
  const doneHours = rated.reduce((sum, p) => sum + (p.progress?.completed_hours ?? 0), 0);
  const teamProgress = totalHours > 0 ? Math.round((doneHours / totalHours) * 100) : null;

  // 진행률 분모에서 빠진 몫. 「계산 불가」와 「담당자 미매핑」은 각각 주간 격자의
  // 사람 행과 카드 설명에 이미 나와 있어 여기서 따로 세지 않는다.
  const missingEstimate = workload?.missing_estimate_count ?? 0;

  return (
    <div className={styles.page}>
      {/* 아바타 이름은 TopNav가 로그인 세션에서 직접 읽는다. */}
      <TopNav tabs={MAIN_NAV_TABS} activeTo="/dashboard" />

      <div className={styles.header}>
        <div>
          <p className={styles.teamName}>{team?.name ?? '내 팀'}</p>
          <p className={styles.teamNote}>
            {workload
              ? `팀원 ${people.length}명 · 오늘 ${today()} · ${workload.workload_weeks}주 기준`
              : '팀 데이터를 불러오는 중입니다.'}
          </p>
        </div>
        {/* 다른 화면에 들어가지 않고 여기서 바로 다시 읽는다. */}
        <button
          type="button"
          className={styles.refreshBtn}
          onClick={() => void handleRefresh()}
          disabled={syncing}
        >
          <Icon name="refresh" size={15} spin={syncing} />
          <span>{syncing ? '갱신 중…' : '갱신'}</span>
        </button>
      </div>

      {error && <div className={styles.error}>{error}</div>}
      {loading && <div className={styles.state}>불러오는 중…</div>}

      {!loading && !error && (
        <div className={styles.bento}>
          {/* 1행 — 눈이 먼저 닿는 자리. 지연이 가장 크다. */}
          <div className={styles.spanHero}>
            <OverduePanel tasks={overdue} />
          </div>

          <div className={styles.spanQuarter}>
            <div className={tiles.tile}>
              <span
                className={`${tiles.tileValue} ${short.length > 0 ? tiles.tileValueDanger : ''}`}
              >
                {short.length}명
              </span>
              <span className={tiles.tileLabel}>시간 부족</span>
              <span className={tiles.tileSub}>
                {worst
                  ? `${worst.name ?? worst.person_id} · ${worst.tightest?.due_at.slice(5).replace('-', '/')}까지 ${Math.round(-(worst.tightest?.slack_hours ?? 0))}h`
                  : '마감까지 모두 여유가 있습니다'}
              </span>
            </div>
          </div>

          <div className={styles.spanQuarter}>
            <div className={tiles.tile}>
              <span className={tiles.tileValue}>
                {teamProgress === null ? '—' : `${teamProgress}%`}
              </span>
              <span className={tiles.tileLabel}>전체 진행률</span>
              {/* 분모에서 빠진 몫을 이 줄에 붙여 둔다. 따로 떼어 각주로 두면 30%만
                  읽은 사람이 그게 무엇을 뺀 값인지 모른 채 지나간다. */}
              <span className={tiles.tileSub}>
                {teamProgress === null
                  ? '집계할 공수가 없습니다'
                  : `진행 중 ${rated.length}개 · ${Math.round(totalHours)}h 기준${
                      missingEstimate > 0 ? ` · 공수 없음 ${missingEstimate}건 제외` : ''
                    }`}
              </span>
            </div>
          </div>

          {/* 2행 — 전폭. 누가 언제 몰려 있고, 누구에게 여유가 있는가. */}
          <div className={styles.spanFull}>
            {workload ? (
              <TeamWeekPanel workload={workload} />
            ) : (
              <div className={tiles.card}>
                <p className={tiles.cardTitle}>팀원별 주간 업무 시간</p>
                <p className={tiles.empty}>
                  연결된 프로젝트가 없습니다. 온보딩에서 Drive 폴더와 Jira 프로젝트를 먼저
                  선택해 주세요.
                </p>
              </div>
            )}
          </div>

          {/* 3행 — 반반. 어디까지 갔나 / 곧 무엇이 오나. */}
          <div className={styles.spanHalf}>
            <ProjectProgressPanel projects={projects} overdue={overdue} />
          </div>
          <div className={styles.spanHalf}>
            <UpcomingPanel tasks={deadlines?.soon ?? []} />
          </div>
        </div>
      )}
    </div>
  );
}
