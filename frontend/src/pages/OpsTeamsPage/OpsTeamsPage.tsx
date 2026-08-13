import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Button,
  Modal,
  OpsDataTable,
  OpsFilterBar,
  OpsPageHeader,
  OpsSearchField,
  OpsStatusBadge,
  useToast,
} from '../../components';
import { fetchOpsTeams, fetchTeamOwnerCandidates, transferTeamOwner } from '../../api/opsTeams';
import type { OpsTeam, OpsTeamCandidate } from '../../api/opsTeams';
import { ApiError } from '../../api/client';
import { loadOpsSession } from '../../utils/opsSession';
import styles from '../OpsShared/OpsPages.module.css';

const TITLE = '팀 현황';
const DESCRIPTION = '우리 플랫폼을 사용 중인 팀과 그 안의 계정 현황을 확인합니다.';

/**
 * 확인이 필요한 팀인가.
 *
 * 잠긴 계정이 있거나, 팀원으로 담겼는데 아직 계정을 만들지 않은 사람이 있는
 * 경우다. 후자는 초대가 안 갔거나 코드가 방치된 상태라 운영자가 볼 이유가 있다.
 */
function needsReview(team: OpsTeam) {
  return team.locked_count > 0 || team.unregistered_count > 0;
}

export default function OpsTeamsPage() {
  const navigate = useNavigate();
  const [teams, setTeams] = useState<OpsTeam[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const { showToast } = useToast();
  /** 소유자를 넘기려는 팀. null 이면 모달이 닫혀 있다. */
  const [transferTeam, setTransferTeam] = useState<OpsTeam | null>(null);
  const [candidates, setCandidates] = useState<OpsTeamCandidate[] | null>(null);
  const [nextOwner, setNextOwner] = useState('');
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);

  /**
   * 후보는 **그 팀의 살아 있는 계정**만이다. 계정 전체에서 고르게 하면 남의 팀
   * 사람을 고를 수 있고, 서버가 거절하더라도 고를 수 있게 보여 주는 것 자체가
   * 잘못된 안내다.
   */
  async function openTransfer(team: OpsTeam) {
    const session = loadOpsSession();
    if (!session) return;
    setTransferTeam(team);
    setCandidates(null);
    setNextOwner('');
    setReason('');
    try {
      setCandidates(await fetchTeamOwnerCandidates(session.token, team.team_id));
    } catch (thrown) {
      showToast(thrown instanceof ApiError ? thrown.message : '후보를 불러오지 못했습니다.', 'error');
      setCandidates([]);
    }
  }

  async function confirmTransfer() {
    const session = loadOpsSession();
    if (!session || !transferTeam || !nextOwner || submitting) return;
    setSubmitting(true);
    try {
      const result = await transferTeamOwner(session.token, transferTeam.team_id, nextOwner, reason.trim());
      // 옮겨진 모델 수를 함께 말한다 — 소유자만 바뀐 줄 알았는데 모델이 따라간
      // 것을 나중에 알면 그게 더 놀랍다.
      showToast(
        result.moved_models > 0
          ? `소유자를 넘겼습니다. 등록된 모델 ${result.moved_models}건도 함께 옮겼습니다.`
          : '소유자를 넘겼습니다.',
        'success',
      );
      setTransferTeam(null);
      await load();
    } catch (thrown) {
      showToast(thrown instanceof ApiError ? thrown.message : '넘기지 못했습니다.', 'error');
    } finally {
      setSubmitting(false);
    }
  }

  const load = useCallback(async () => {
    const session = loadOpsSession();
    if (!session) return;

    setLoading(true);
    setError('');
    try {
      setTeams(await fetchOpsTeams(session.token));
    } catch (thrown) {
      // 401은 opsRequest가 세션을 비우고 라우트 가드가 로그인으로 보낸다.
      if (thrown instanceof ApiError && thrown.status === 401) return;
      setError(thrown instanceof ApiError ? thrown.message : '팀 목록을 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return teams ?? [];
    return (teams ?? []).filter((team) =>
      [team.name, team.owner_email, team.src_org_name]
        .some((value) => value?.toLowerCase().includes(keyword)),
    );
  }, [teams, query]);

  const totals = useMemo(() => {
    const all = teams ?? [];
    return {
      teams: all.length,
      accounts: all.reduce((sum, t) => sum + t.account_count, 0),
      review: all.filter(needsReview).length,
    };
  }, [teams]);

  function openAccounts(team: OpsTeam) {
    // 계정 관리 화면이 team 쿼리로 필터를 받는다.
    navigate(`/ops/accounts?team=${encodeURIComponent(team.team_id)}`);
  }

  if (loading && !teams) {
    return (
      <div className={styles.page}>
        <OpsPageHeader title={TITLE} description={DESCRIPTION} />
        <p className={styles.inlineEmpty}>불러오는 중…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.page}>
        <OpsPageHeader title={TITLE} description={DESCRIPTION} />
        <p className={styles.inlineEmpty} role="alert">{error}</p>
        <Button variant="outline" onClick={load}>다시 시도</Button>
      </div>
    );
  }

  if ((teams ?? []).length === 0) {
    return (
      <div className={styles.page}>
        <OpsPageHeader title={TITLE} description={DESCRIPTION} />
        <div className={styles.notice}>
          팀은 팀장이 온보딩에서 직접 만듭니다. 운영자가 만들지 않습니다.
        </div>
        <p className={styles.inlineEmpty}>아직 만들어진 팀이 없습니다.</p>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <OpsPageHeader title={TITLE} description={DESCRIPTION} />

      <div className={styles.notice}>
        팀은 HR 조직과 다릅니다. 회사 전체가 아니라 그 안의 그룹이 플랫폼을 쓰므로, 팀장이
        온보딩에서 직접 만든 팀이 사용 단위입니다. 팀 {totals.teams}개 · 가입 계정{' '}
        {totals.accounts}개
        {totals.review > 0 ? ` · 확인 필요 ${totals.review}개 팀` : ' · 확인 필요 없음'}
      </div>

      <OpsFilterBar>
        <OpsSearchField value={query} onChange={setQuery} placeholder="팀 이름, 팀장 이메일, 출처 조직 검색" />
      </OpsFilterBar>

      <OpsDataTable minWidth={1080}>
        <thead>
          <tr>
            <th>팀</th>
            <th>팀장</th>
            <th>출처 조직</th>
            <th>팀원</th>
            <th>가입 계정</th>
            <th>대기 중 초대</th>
            <th>상태</th>
            <th>작업</th>
          </tr>
        </thead>
        <tbody>
          {filtered.length > 0 ? filtered.map((team) => (
            <tr key={team.team_id} onClick={() => openAccounts(team)}>
              <td>{team.name}</td>
              <td>{team.owner_email ?? '-'}</td>
              <td>{team.src_org_name ?? '-'}</td>
              <td>{team.member_count}</td>
              <td>
                {team.account_count}
                {team.unregistered_count > 0 && (
                  <span className={styles.warningText}> (미가입 {team.unregistered_count})</span>
                )}
              </td>
              <td>{team.pending_invite_count > 0 ? team.pending_invite_count : '-'}</td>
              <td>
                <OpsStatusBadge tone={needsReview(team) ? 'warning' : 'success'}>
                  {needsReview(team) ? '확인 필요' : '정상'}
                </OpsStatusBadge>
              </td>
              <td>
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    openAccounts(team);
                  }}
                >
                  계정 보기
                </button>
                {' · '}
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    void openTransfer(team);
                  }}
                >
                  소유자 이전
                </button>
              </td>
            </tr>
          )) : (
            <tr><td className={styles.emptyCell} colSpan={8}>조건에 맞는 팀이 없습니다.</td></tr>
          )}
        </tbody>
      </OpsDataTable>

      <Modal
        open={transferTeam !== null}
        onClose={() => (submitting ? null : setTransferTeam(null))}
        title="팀 소유자 이전"
        footer={(
          <>
            <Button variant="secondary" onClick={() => setTransferTeam(null)} disabled={submitting}>취소</Button>
            <Button onClick={confirmTransfer} disabled={!nextOwner || submitting}>
              {submitting ? '넘기는 중…' : '넘기기'}
            </Button>
          </>
        )}
      >
        <div className={styles.formGrid}>
          <div className={styles.fieldGroup}>
            <label htmlFor="next-owner">새 소유자 · {transferTeam?.name}</label>
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
                    {candidate.account_id === transferTeam?.owner_account_id ? ' (현재 소유자)' : ''}
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
    </div>
  );
}
