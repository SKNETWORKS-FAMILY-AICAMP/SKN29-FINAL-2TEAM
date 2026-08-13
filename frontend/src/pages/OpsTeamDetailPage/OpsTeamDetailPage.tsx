import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Button,
  OpsDataTable,
  OpsEmpty,
  OpsPageHeader,
  OpsSectionCard,
  OpsStatusBadge,
} from '../../components';
import type { OpsTone } from '../../components';
import { fetchOpsTeams, fetchTeamContent } from '../../api/opsTeams';
import type { OpsTeam, OpsTeamAgent, OpsTeamRun } from '../../api/opsTeams';
import { ApiError } from '../../api/client';
import { loadOpsSession } from '../../utils/opsSession';
import styles from '../OpsShared/OpsPages.module.css';

/**
 * 팀 상세 — **「에이전트가 이상해요」에 답하는 자리.**
 *
 * 여태 운영자가 고객의 것을 볼 방법이 하나도 없었다. 어떤 에이전트가 어떤 도구를
 * 들고 어떤 모델로 도는지, 실제로 무슨 일이 있었는지를 모르니 문의가 오면 할 수
 * 있는 말이 없었다(2026-08-13 PM 지적).
 *
 * **대화 내용과 문서 원문은 보지 않는다.** 그건 고객의 업무 내용이고 열람을 통제할
 * 장치가 아직 없다. 실행 기록은 애초에 내용을 안 담게 설계돼 있어서(`tool_call`
 * 은 원본 인자가 아니라 요약을 남긴다) 그 경계를 이미 지킨다.
 */

const RUN_TONES: Record<string, OpsTone> = {
  DONE: 'success',
  FAILED: 'danger',
  RUNNING: 'info',
  CANCELLED: 'neutral',
};

const AGENT_TONES: Record<string, OpsTone> = {
  ACTIVE: 'success',
  DRAFT: 'neutral',
  DISABLED: 'warning',
};

function at(iso: string | null): string {
  if (!iso) return '-';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(date.getMonth() + 1)}.${p(date.getDate())} ${p(date.getHours())}:${p(date.getMinutes())}`;
}

export default function OpsTeamDetailPage() {
  const navigate = useNavigate();
  const { teamId } = useParams();

  const [team, setTeam] = useState<OpsTeam | null>(null);
  const [agents, setAgents] = useState<OpsTeamAgent[]>([]);
  const [runs, setRuns] = useState<OpsTeamRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  /** 지시문은 길다. 펼친 것만 보여준다. */
  const [openAgent, setOpenAgent] = useState('');

  const load = useCallback(async () => {
    const session = loadOpsSession();
    if (!session || !teamId) {
      navigate('/ops/login', { replace: true });
      return;
    }
    setLoading(true);
    setError('');
    try {
      const [teams, content] = await Promise.all([
        fetchOpsTeams(session.token),
        fetchTeamContent(session.token, teamId),
      ]);
      setTeam(teams.find((row) => row.team_id === teamId) ?? null);
      setAgents(content.agents);
      setRuns(content.runs);
    } catch (thrown) {
      if (thrown instanceof ApiError && thrown.status === 401) {
        navigate('/ops/login', { replace: true });
        return;
      }
      setError(thrown instanceof ApiError ? thrown.message : '팀을 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }, [teamId, navigate]);

  useEffect(() => {
    void load();
  }, [load]);

  const header = (
    <OpsPageHeader
      title="팀 상세"
      description="이 팀이 무엇을 들고 있고 실제로 무슨 일이 있었는지 확인합니다."
      actions={(
        <Button variant="secondary" onClick={() => navigate('/ops/teams')}>팀 목록으로</Button>
      )}
    />
  );

  if (loading && !team) {
    return (
      <div className={styles.page}>
        {header}
        <p className={styles.inlineEmpty}>불러오는 중…</p>
      </div>
    );
  }

  if (error || !team) {
    return (
      <div className={styles.page}>
        {header}
        <p className={styles.inlineEmpty} role="alert">{error || '팀을 찾을 수 없습니다.'}</p>
        <Button variant="outline" onClick={load}>다시 시도</Button>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      {header}

      <table className={styles.detailTable}>
        <tbody>
          <tr>
            <th scope="row">팀</th>
            <td>{team.name}</td>
          </tr>
          <tr>
            <th scope="row">팀장</th>
            <td>{team.owner_email ?? '-'}</td>
          </tr>
          <tr>
            <th scope="row">출처 조직</th>
            <td>{team.src_org_name ?? '-'}</td>
          </tr>
          <tr>
            <th scope="row">팀원 · 가입 계정</th>
            <td>
              {team.member_count}명 · {team.account_count}개
              {team.unregistered_count > 0 && (
                <span className={styles.warningText}> (미가입 {team.unregistered_count})</span>
              )}
            </td>
          </tr>
        </tbody>
      </table>

      <OpsSectionCard title={`에이전트 ${agents.length}개`}>
        {agents.length === 0 ? (
          <OpsEmpty message="이 팀에는 아직 에이전트가 없습니다." />
        ) : (
          <OpsDataTable minWidth={900}>
            <thead>
              <tr>
                <th style={{ width: 200 }}>이름</th>
                <th style={{ width: 100 }}>상태</th>
                <th style={{ width: 200 }}>모델</th>
                <th style={{ width: 80 }}>도구</th>
                <th>설명</th>
                <th style={{ width: 90 }} />
              </tr>
            </thead>
            <tbody>
              {agents.map((agent) => (
                <tr key={agent.agent_id}>
                  <td>{agent.name}</td>
                  <td>
                    <OpsStatusBadge tone={AGENT_TONES[agent.status] ?? 'neutral'}>
                      {agent.status}
                    </OpsStatusBadge>
                  </td>
                  <td>{agent.model ?? '-'}</td>
                  <td>{agent.tool_refs.length}</td>
                  <td className={styles.cellEllipsis} title={agent.description ?? ''}>
                    {agent.description || '-'}
                  </td>
                  <td>
                    <button
                      type="button"
                      onClick={() => setOpenAgent(openAgent === agent.agent_id ? '' : agent.agent_id)}
                    >
                      {openAgent === agent.agent_id ? '접기' : '구성 보기'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </OpsDataTable>
        )}

        {/* 도구 목록과 지시문은 길어서 표 칸에 안 들어간다. 고른 하나만 아래에 편다. */}
        {agents
          .filter((agent) => agent.agent_id === openAgent)
          .map((agent) => (
            <table key={agent.agent_id} className={styles.detailTable} style={{ marginTop: 16 }}>
              <tbody>
                <tr>
                  <th scope="row">도구</th>
                  <td>{agent.tool_refs.join(' · ') || '없음'}</td>
                </tr>
                <tr>
                  <th scope="row">응답 방식 · 반복 상한</th>
                  <td>{agent.reasoning_effort ?? '-'} · {agent.max_iterations ?? '-'}</td>
                </tr>
                <tr>
                  <th scope="row">지시문</th>
                  <td style={{ whiteSpace: 'pre-wrap' }}>{agent.instruction || '없음'}</td>
                </tr>
              </tbody>
            </table>
          ))}
      </OpsSectionCard>

      <OpsSectionCard title={`최근 실행 ${runs.length}건`} subtitle="대화 내용은 담기지 않습니다 — 무엇을 언제 돌렸고 어떤 도구가 실패했는지만 남습니다.">
        {runs.length === 0 ? (
          <OpsEmpty message="아직 실행 기록이 없습니다." />
        ) : (
          <OpsDataTable minWidth={900}>
            <thead>
              <tr>
                <th style={{ width: 120 }}>시각</th>
                <th style={{ width: 180 }}>에이전트</th>
                <th style={{ width: 90 }}>결과</th>
                <th style={{ width: 70 }}>반복</th>
                <th style={{ width: 80 }}>도구</th>
                <th style={{ width: 120 }}>토큰(입·출)</th>
                <th>실패한 도구</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.run_id}>
                  <td>{at(run.started_at)}</td>
                  <td>{run.agent_name}</td>
                  <td>
                    <OpsStatusBadge tone={RUN_TONES[run.status] ?? 'neutral'}>{run.status}</OpsStatusBadge>
                  </td>
                  <td>{run.iterations}</td>
                  <td>{run.tool_calls}</td>
                  <td>{run.token_in ?? '-'} · {run.token_out ?? '-'}</td>
                  <td className={styles.cellEllipsis} title={run.failed_tools.join(' · ')}>
                    {run.failed_tools.join(' · ') || '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </OpsDataTable>
        )}
      </OpsSectionCard>
    </div>
  );
}
