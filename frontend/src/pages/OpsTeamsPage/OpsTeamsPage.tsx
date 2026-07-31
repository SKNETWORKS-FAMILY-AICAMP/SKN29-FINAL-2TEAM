import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Button,
  OpsDataTable,
  OpsFilterBar,
  OpsPageHeader,
  OpsSearchField,
  OpsStatusBadge,
} from '../../components';
import { fetchOpsTeams } from '../../api/opsTeams';
import type { OpsTeam } from '../../api/opsTeams';
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
              </td>
            </tr>
          )) : (
            <tr><td className={styles.emptyCell} colSpan={8}>조건에 맞는 팀이 없습니다.</td></tr>
          )}
        </tbody>
      </OpsDataTable>
    </div>
  );
}
