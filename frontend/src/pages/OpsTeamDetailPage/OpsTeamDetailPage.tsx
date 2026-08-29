import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Button,
  Modal,
  OpsDataTable,
  OpsEmpty,
  OpsPageHeader,
  OpsSectionCard,
  OpsStatusBadge,
  useToast,
} from '../../components';
import type { OpsTone } from '../../components';
import {
  fetchOpsTeams,
  fetchTeamContent,
  fetchTeamOwnerCandidates,
  fetchTeamPurgePreview,
  purgeTeam,
  transferTeamOwner,
} from '../../api/opsTeams';
import type {
  OpsPurgePreview,
  OpsTeam,
  OpsTeamAgent,
  OpsTeamCandidate,
  OpsTeamRun,
} from '../../api/opsTeams';
import { ApiError } from '../../api/client';
import { loadOpsSession } from '../../utils/opsSession';
import { PurgeDialog } from '../OpsShared/PurgeDialog';
import { TeamUsageSections } from './TeamUsageSections';
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

const AGENT_LABELS: Record<string, string> = {
  ACTIVE: '사용 중',
  DRAFT: '초안',
  DISABLED: '사용 안 함',
};

const RUN_LABELS: Record<string, string> = {
  DONE: '완료',
  FAILED: '실패',
  RUNNING: '실행 중',
  CANCELLED: '취소됨',
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
  const [selectedAgentId, setSelectedAgentId] = useState('');

  const { showToast } = useToast();
  const [transferOpen, setTransferOpen] = useState(false);
  const [purgeOpen, setPurgeOpen] = useState(false);
  const [purgePreview, setPurgePreview] = useState<OpsPurgePreview | null>(null);
  const [candidates, setCandidates] = useState<OpsTeamCandidate[] | null>(null);
  const [nextOwner, setNextOwner] = useState('');
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const selectedAgent = agents.find((agent) => agent.agent_id === selectedAgentId) ?? null;

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

  /**
   * 후보는 **그 팀의 살아 있는 계정**만이다. 계정 전체에서 고르게 하면 남의 팀
   * 사람을 고를 수 있고, 서버가 거절하더라도 고를 수 있게 보여 주는 것 자체가
   * 잘못된 안내다.
   */
  async function openTransfer() {
    const session = loadOpsSession();
    if (!session || !teamId) return;
    setTransferOpen(true);
    setCandidates(null);
    setNextOwner('');
    setReason('');
    try {
      setCandidates(await fetchTeamOwnerCandidates(session.token, teamId));
    } catch (thrown) {
      showToast(thrown instanceof ApiError ? thrown.message : '후보를 불러오지 못했습니다.', 'error');
      setCandidates([]);
    }
  }

  /** 무엇이 사라지는지 **먼저 보여준 다음** 이름을 받는다. 순서가 반대면 경고가 늦다. */
  async function openPurge() {
    const session = loadOpsSession();
    if (!session || !teamId) return;
    setPurgeOpen(true);
    setPurgePreview(null);
    try {
      setPurgePreview(await fetchTeamPurgePreview(session.token, teamId));
    } catch (thrown) {
      showToast(thrown instanceof ApiError ? thrown.message : '삭제 대상을 확인하지 못했습니다.', 'error');
      setPurgeOpen(false);
    }
  }

  async function confirmPurge() {
    const session = loadOpsSession();
    if (!session || !teamId || !team || submitting) return;
    setSubmitting(true);
    try {
      const result = await purgeTeam(session.token, teamId, team.name);
      const total = result.removed.reduce((sum, item) => sum + item.count, 0);
      showToast(`${team.name}을(를) 삭제했습니다. 관련 데이터 ${total}건이 함께 사라졌습니다.`);
      navigate('/ops/teams');
    } catch (thrown) {
      showToast(thrown instanceof ApiError ? thrown.message : '삭제하지 못했습니다.', 'error');
      setSubmitting(false);
    }
  }

  async function confirmTransfer() {
    const session = loadOpsSession();
    if (!session || !teamId || !nextOwner || submitting) return;
    setSubmitting(true);
    try {
      const result = await transferTeamOwner(session.token, teamId, nextOwner, reason.trim());
      // 옮겨진 모델 수를 함께 말한다 — 소유자만 바뀐 줄 알았는데 모델이 따라간
      // 것을 나중에 알면 그게 더 놀랍다.
      showToast(
        result.moved_models > 0
          ? `소유자를 넘겼습니다. 등록된 모델 ${result.moved_models}건도 함께 옮겼습니다.`
          : '소유자를 넘겼습니다.',
        'success',
      );
      setTransferOpen(false);
      await load();
    } catch (thrown) {
      showToast(thrown instanceof ApiError ? thrown.message : '넘기지 못했습니다.', 'error');
    } finally {
      setSubmitting(false);
    }
  }

  const header = (
    <OpsPageHeader
      title="팀 상세"
      actions={(
        <Button variant="secondary" onClick={() => navigate('/ops/teams')} aria-label="팀 목록으로">← 목록으로</Button>
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

      {/* 조치는 목록이 아니라 여기가 자리다. 표의 「작업」 열에 셋을 가운뎃점으로
          이어 붙였더니 무엇을 눌러야 할지 안 보였다(2026-08-13 PM 지적). */}
      <OpsSectionCard title="조치">
        <div className={styles.rowActions}>
          <Button variant="outline" onClick={() => navigate(`/ops/accounts?team=${teamId}`)}>
            소속 계정
          </Button>
          <Button variant="outline" onClick={openTransfer}>소유자 이전</Button>
          {/* 되돌릴 수 없는 것은 **다른 색**으로, 그리고 줄 끝에 둔다 —
              「소속 계정」 옆에 같은 모양으로 있으면 손이 먼저 간다. */}
          <Button variant="danger" onClick={openPurge}>팀 삭제</Button>
        </div>
      </OpsSectionCard>

      {/* **읽기만 한다.** 등록은 각자의 페이지에 있다(`/ops/models`·`/ops/mcp`) —
          등록은 「무엇을 새로 붙이나」라 주제로 시작하는 일이고, 여기는 「이 팀이
          지금 무엇을 들고 있나」다. 아래 에이전트·실행 기록과 같은 성격이다. */}
      <TeamUsageSections teamId={team.team_id} onFailure={team.guardrail_on_failure} />

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
                      {AGENT_LABELS[agent.status] ?? agent.status}
                    </OpsStatusBadge>
                  </td>
                  <td>{agent.model ?? '-'}</td>
                  <td>{agent.tool_refs.length}</td>
                  <td className={styles.cellEllipsis} title={agent.description ?? ''}>
                    {agent.description || '-'}
                  </td>
                  <td>
                    <button
                      data-button
                      type="button"
                      onClick={() => setSelectedAgentId(agent.agent_id)}
                    >
                      구성 보기
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </OpsDataTable>
        )}

      </OpsSectionCard>

      <OpsSectionCard title={`빌더 에이전트 최근 실행 ${runs.length}건`}>
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
                    <OpsStatusBadge tone={RUN_TONES[run.status] ?? 'neutral'}>
                      {RUN_LABELS[run.status] ?? run.status}
                    </OpsStatusBadge>
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

      <Modal
        open={selectedAgent !== null}
        onClose={() => setSelectedAgentId('')}
        title={selectedAgent ? `${selectedAgent.name} 구성` : '에이전트 구성'}
        width={680}
        footer={<Button variant="secondary" onClick={() => setSelectedAgentId('')}>닫기</Button>}
      >
        {selectedAgent && (
          <table className={[styles.detailTable, styles.modalDetailTable].join(' ')}>
            <tbody>
              <tr>
                <th scope="row">상태</th>
                <td>{AGENT_LABELS[selectedAgent.status] ?? selectedAgent.status}</td>
              </tr>
              <tr>
                <th scope="row">모델</th>
                <td>{selectedAgent.model ?? '-'}</td>
              </tr>
              <tr>
                <th scope="row">도구</th>
                <td>{selectedAgent.tool_refs.join(' · ') || '없음'}</td>
              </tr>
              <tr>
                <th scope="row">응답 방식 · 반복 상한</th>
                <td>{selectedAgent.reasoning_effort ?? '-'} · {selectedAgent.max_iterations ?? '-'}</td>
              </tr>
              <tr>
                <th scope="row">지시문</th>
                <td style={{ whiteSpace: 'pre-wrap' }}>{selectedAgent.instruction || '없음'}</td>
              </tr>
            </tbody>
          </table>
        )}
      </Modal>

      <Modal
        open={transferOpen}
        onClose={() => (submitting ? null : setTransferOpen(false))}
        title="팀 소유자 이전"
        footer={(
          <>
            <Button variant="secondary" onClick={() => setTransferOpen(false)} disabled={submitting}>
              취소
            </Button>
            <Button onClick={confirmTransfer} disabled={!nextOwner || submitting}>
              {submitting ? '넘기는 중…' : '넘기기'}
            </Button>
          </>
        )}
      >
        <div className={styles.formGrid}>
          <div className={styles.fieldGroup}>
            <label htmlFor="next-owner">새 소유자 · {team.name}</label>
            {candidates === null ? (
              <p className={styles.inlineEmpty}>불러오는 중…</p>
            ) : candidates.length === 0 ? (
              <p className={styles.inlineEmpty}>넘길 수 있는 계정이 없습니다.</p>
            ) : (
              <select id="next-owner" value={nextOwner} onChange={(event) => setNextOwner(event.target.value)}>
                <option value="">선택하세요</option>
                {candidates.map((candidate) => (
                  <option key={candidate.account_id} value={candidate.account_id}>
                    {candidate.display_name} · {candidate.email}
                    {candidate.account_id === team.owner_account_id ? ' (현재 소유자)' : ''}
                  </option>
                ))}
              </select>
            )}
          </div>
          <div className={styles.fieldGroup}>
            <label htmlFor="transfer-reason">사유 (선택)</label>
            <textarea
              id="transfer-reason"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="예: 팀장 퇴사"
            />
          </div>
        </div>
      </Modal>

      <PurgeDialog
        open={purgeOpen}
        onClose={() => (submitting ? null : setPurgeOpen(false))}
        kind="팀"
        label={team.name}
        confirmValue={team.name}
        preview={purgePreview}
        busy={submitting}
        onConfirm={confirmPurge}
      />
    </div>
  );
}
