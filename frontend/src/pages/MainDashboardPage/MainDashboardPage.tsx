import { useCallback, useEffect, useState } from 'react';
import { TopNav } from '../../components';
import { ApiError } from '../../api/client';
import { listConnectors } from '../../api/connectors';
import type { ConnectorConnection } from '../../api/connectors';
import {
  getTeamWorkload,
  listMyProjects,
  listTeamDocuments,
  listTeamFolders,
} from '../../api/projects';
import type { Project, TeamDocument, TeamFolder, WorkloadResult } from '../../api/projects';
import { fetchMyTeam } from '../../api/teams';
import type { Team } from '../../api/teams';
import { MAIN_NAV_TABS } from '../../routes';
import { useSession } from '../../utils/session';
import { TeamDataPanel } from './TeamDataPanel';
import { TeamProjectPanel } from './TeamProjectPanel';
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
  const [folders, setFolders] = useState<TeamFolder[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [documents, setDocuments] = useState<TeamDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError('');
    try {
      // 전부 팀 단위다. 프로젝트를 하나 골라서 그것만 보여 주면, 사람의 실제
      // 부하(모든 프로젝트의 합)보다 낮은 숫자를 보고 여유가 있다고 판단하게 된다.
      const [myTeam, connectorRows, workloadResult, folderRows, projectRows, documentRows] =
        await Promise.all([
          fetchMyTeam(token).catch(() => null),
          listConnectors(token).catch(() => []),
          getTeamWorkload(token),
          listTeamFolders(token).catch(() => []),
          listMyProjects(token).catch(() => []),
          listTeamDocuments(token).catch(() => []),
        ]);
      setTeam(myTeam);
      setConnectors(connectorRows);
      setWorkload(workloadResult);
      setFolders(folderRows);
      setProjects(projectRows);
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

  // 개인 부하율의 평균이 아니라 팀 전체 배정 ÷ 팀 전체 용량이다. 평균을 쓰면
  // 용량이 작은 사람의 높은 비율이 팀 전체를 실제보다 과부하로 보이게 한다.
  const allocated = people.reduce((sum, person) => sum + person.current_allocation, 0);
  const capacity = rated.reduce((sum, person) => sum + (person.effective_capacity ?? 0), 0);
  const teamRate = capacity > 0 ? Math.round((allocated / capacity) * 100) : null;

  // 부하율 숫자에 안 들어간 것들. 이게 0이어야 퍼센트를 그대로 믿을 수 있다.
  const needsReview =
    (workload?.missing_estimate_count ?? 0) + (workload?.unmapped_assignee_count ?? 0);
  const blocked = people.length - rated.length;

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
                <span className={`${tiles.tileValue} ${overloaded > 0 ? tiles.tileValueDanger : ''}`}>
                  {overloaded}명
                </span>
                <span className={tiles.tileLabel}>과부하</span>
                <span className={tiles.tileSub}>부하율 100% 초과</span>
              </div>
              <div className={tiles.tile}>
                <span className={tiles.tileValue}>{teamRate === null ? '—' : `${teamRate}%`}</span>
                <span className={tiles.tileLabel}>팀 부하율</span>
                <span className={tiles.tileSub}>
                  {Math.round(allocated)}h / {Math.round(capacity)}h
                </span>
              </div>
              <div className={tiles.tile}>
                <span className={`${tiles.tileValue} ${needsReview > 0 ? tiles.tileValueWarn : ''}`}>
                  {needsReview}건
                </span>
                <span className={tiles.tileLabel}>확인 필요</span>
                <span className={tiles.tileSub}>
                  공수 미입력 {workload?.missing_estimate_count ?? 0} · 미매핑{' '}
                  {workload?.unmapped_assignee_count ?? 0}
                </span>
              </div>
              <div className={tiles.tile}>
                <span className={`${tiles.tileValue} ${blocked > 0 ? tiles.tileValueWarn : ''}`}>
                  {blocked}명
                </span>
                <span className={tiles.tileLabel}>부하율 계산 불가</span>
                <span className={tiles.tileSub}>휴직·근무조건 없음</span>
              </div>
            </div>
          </div>

          {/*
            "무엇이 연결돼 있나"는 매일 보는 값이 아니라 숫자의 출처를 확인하는
            자리다. 카드로 세워 두면 부하 분석보다 시선을 끌어가므로 가로 한 줄로
            깔고, 아래를 분석 두 장에 내준다.
          */}
          <div className={styles.summary}>
            <TeamDataPanel
              connectors={connectors}
              folders={folders}
              projects={projects}
              documents={documents}
            />
          </div>

          <div className={styles.content}>
            <div className={styles.leftPanel}>
              {workload ? (
                <TeamWorkloadPanel workload={workload} />
              ) : (
                <div className={tiles.card}>
                  <p className={tiles.cardTitle}>인원별 업무 부하</p>
                  <p className={tiles.empty}>
                    연결된 프로젝트가 없습니다. 온보딩에서 Drive 폴더와 Jira 프로젝트를 먼저
                    선택해 주세요.
                  </p>
                </div>
              )}
            </div>

            <div className={styles.rightPanel}>
              {workload && <TeamProjectPanel workload={workload} />}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
