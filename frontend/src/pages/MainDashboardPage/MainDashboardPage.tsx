import { useCallback, useEffect, useState } from 'react';
import { TopNav } from '../../components';
import { ApiError } from '../../api/client';
import { listConnectors } from '../../api/connectors';
import type { ConnectorConnection } from '../../api/connectors';
import {
  findOnboardingProject,
  getProjectWorkload,
  listProjectDocuments,
  listProjectSources,
} from '../../api/projects';
import type { ProjectDocument, ProjectSource, WorkloadResult } from '../../api/projects';
import { fetchMyTeam } from '../../api/teams';
import type { Team } from '../../api/teams';
import { MAIN_NAV_TABS } from '../../routes';
import { useSession } from '../../utils/session';
import { TeamDataPanel } from './TeamDataPanel';
import { TeamWorkloadPanel } from './TeamWorkloadPanel';
import styles from './MainDashboardPage.module.css';
import tiles from './TeamDashboard.module.css';

/**
 * 팀 대시보드.
 *
 * 우리 플랫폼을 쓰는 단위는 회사가 아니라 **회사 안의 팀**이라, 여기 보이는 것은
 * 전부 로그인한 사람이 속한 팀의 데이터다(`team_member` 범위). 조직 전체 조직도나
 * 회사 부서별 집계는 이 화면의 일이 아니다.
 *
 * 숫자는 모두 실제 조회 결과다. 값이 없으면 0이나 임의값으로 채우지 않고 "없음"으로
 * 둔다 — 목업 숫자가 실제처럼 보이는 것이 이 화면에서 가장 나쁜 실패다.
 */
export default function MainDashboardPage() {
  const session = useSession();
  const token = session?.token;

  const [team, setTeam] = useState<Team | null>(null);
  const [workload, setWorkload] = useState<WorkloadResult | null>(null);
  const [connectors, setConnectors] = useState<ConnectorConnection[]>([]);
  const [sources, setSources] = useState<ProjectSource[]>([]);
  const [documents, setDocuments] = useState<ProjectDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError('');
    try {
      const [myTeam, connectorRows, project] = await Promise.all([
        fetchMyTeam(token).catch(() => null),
        listConnectors(token).catch(() => []),
        findOnboardingProject(token),
      ]);
      setTeam(myTeam);
      setConnectors(connectorRows);

      if (!project) {
        setWorkload(null);
        setSources([]);
        setDocuments([]);
        return;
      }

      const [workloadResult, sourceRows, documentRows] = await Promise.all([
        getProjectWorkload(token, project.proj_id),
        listProjectSources(token, project.proj_id),
        listProjectDocuments(token, project.proj_id),
      ]);
      setWorkload(workloadResult);
      setSources(sourceRows);
      setDocuments(documentRows);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '대시보드를 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  const people = workload?.people ?? [];
  const rated = people.filter((person) => person.load_rate !== null);
  const overloaded = rated.filter((person) => (person.load_rate ?? 0) > 100).length;
  const away = people.filter((person) => person.absent_days > 0).length;
  const averageRate = rated.length
    ? Math.round(rated.reduce((sum, person) => sum + (person.load_rate ?? 0), 0) / rated.length)
    : null;

  return (
    <div className={styles.page}>
      {/* 아바타 이름은 TopNav가 로그인 세션에서 직접 읽는다. */}
      <TopNav tabs={MAIN_NAV_TABS} activeTo="/dashboard" />

      <div className={styles.header}>
        <p className={styles.teamName}>{team?.name ?? '내 팀'}</p>
        <p className={styles.teamNote}>
          {workload
            ? `팀원 ${people.length}명 · ${workload.period_start} ~ ${workload.period_end} 기준`
            : '팀 데이터를 불러오는 중입니다.'}
        </p>
      </div>

      {error && <div className={styles.error}>{error}</div>}
      {loading && <div className={styles.state}>불러오는 중…</div>}

      {!loading && !error && (
        <>
          <div className={styles.summary}>
            <div className={tiles.tiles}>
              <div className={tiles.tile}>
                <span className={tiles.tileValue}>{people.length}명</span>
                <span className={tiles.tileLabel}>팀원</span>
              </div>
              <div className={tiles.tile}>
                <span className={`${tiles.tileValue} ${overloaded > 0 ? tiles.tileValueDanger : ''}`}>
                  {overloaded}명
                </span>
                <span className={tiles.tileLabel}>과부하 (100% 초과)</span>
              </div>
              <div className={tiles.tile}>
                <span className={tiles.tileValue}>{averageRate === null ? '—' : `${averageRate}%`}</span>
                <span className={tiles.tileLabel}>평균 부하율</span>
                {rated.length !== people.length && (
                  <span className={tiles.tileSub}>계산 불가 {people.length - rated.length}명 제외</span>
                )}
              </div>
              <div className={tiles.tile}>
                <span className={tiles.tileValue}>{away}명</span>
                <span className={tiles.tileLabel}>기간 내 부재</span>
              </div>
              <div className={tiles.tile}>
                <span
                  className={`${tiles.tileValue} ${
                    (workload?.missing_estimate_count ?? 0) > 0 ? tiles.tileValueWarn : ''
                  }`}
                >
                  {workload?.missing_estimate_count ?? 0}건
                </span>
                <span className={tiles.tileLabel}>공수 미입력</span>
                <span className={tiles.tileSub}>부하율에 안 들어감</span>
              </div>
              <div className={tiles.tile}>
                <span
                  className={`${tiles.tileValue} ${
                    (workload?.unmapped_assignee_count ?? 0) > 0 ? tiles.tileValueWarn : ''
                  }`}
                >
                  {workload?.unmapped_assignee_count ?? 0}건
                </span>
                <span className={tiles.tileLabel}>담당자 미매핑</span>
                <span className={tiles.tileSub}>부하율에 안 들어감</span>
              </div>
            </div>
          </div>

          <div className={styles.content}>
            <div className={styles.leftPanel}>
              {workload ? (
                <TeamWorkloadPanel workload={workload} />
              ) : (
                <div className={tiles.card}>
                  <p className={tiles.cardTitle}>팀원 업무 부하</p>
                  <p className={tiles.empty}>
                    연결된 프로젝트가 없습니다. 온보딩에서 Drive 폴더와 Jira 프로젝트를 먼저
                    선택해 주세요.
                  </p>
                </div>
              )}
            </div>

            <div className={styles.rightPanel}>
              <TeamDataPanel connectors={connectors} sources={sources} documents={documents} />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
