import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Button,
  OpsDataTable,
  OpsFilterBar,
  OpsPageHeader,
  OpsSearchField,
  OpsStatusBadge,
} from '../../components';
import { fetchAccounts } from '../../api/opsAccounts';
import type { OpsAccount } from '../../api/opsAccounts';
import { ApiError } from '../../api/client';
import { loadOpsSession } from '../../utils/opsSession';
import {
  MAPPING_LABELS,
  MAPPING_TONES,
  serviceLabels,
  statusLabel,
  statusTone,
} from '../OpsShared/accountLabels';
import styles from '../OpsShared/OpsPages.module.css';



/**
 * 계정 목록 — **「누가 있는가」만 맡는다.**
 *
 * 예전에는 이 화면 아래에 상세 섹션이 붙어 있었다. 표와 상세가 한 화면을 나눠
 * 쓰느라 둘 다 좁았고 조치 버튼이 스크롤 아래에 숨었다. 상세와 조치는
 * `/ops/accounts/:accountId` 로 갈랐다(2026-08-13 PM).
 */
export default function OpsAccountsPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [accounts, setAccounts] = useState<OpsAccount[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState(searchParams.get('status') ?? '전체');
  // 팀 현황에서 팀을 눌러 넘어온 경우 그 팀으로 좁혀 보여준다.
  const teamFilter = searchParams.get('team');

  async function load() {
    const currentSession = loadOpsSession();
    if (!currentSession) {
      navigate('/ops/login', { replace: true });
      return;
    }

    setLoading(true);
    setError('');
    try {
      setAccounts(await fetchAccounts(currentSession.token));
    } catch (thrown) {
      if (thrown instanceof ApiError && thrown.status === 401) {
        navigate('/ops/login', { replace: true });
        return;
      }
      setError(thrown instanceof ApiError ? thrown.message : '계정 목록을 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filtered = useMemo(() => {
    const all = accounts ?? [];
    const normalized = query.trim().toLowerCase();
    return all.filter((account) => {
      const matchesQuery = !normalized || [
        account.email,
        account.person?.name ?? '',
        account.person?.org_name ?? '',
      ].some((value) => value.toLowerCase().includes(normalized));

      const matchesTeam = !teamFilter || account.team_id === teamFilter;
      const matchesStatus = statusFilter === '전체'
        || (statusFilter === '확인 필요' && (account.mapping_status !== 'LINKED' || account.account_status === 'LOCKED'))
        || (statusFilter === '정상' && account.account_status === 'ACTIVE')
        || (statusFilter === '잠김' && account.account_status === 'LOCKED')
        || (statusFilter === '탈퇴' && account.account_status === 'WITHDRAWN');

      return matchesQuery && matchesStatus && matchesTeam;
    });
  }, [accounts, query, statusFilter, teamFilter]);


  if (loading && !accounts) {
    return (
      <div className={styles.page}>
        <OpsPageHeader title="계정 관리" />
        <p className={styles.inlineEmpty}>불러오는 중…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.page}>
        <OpsPageHeader title="계정 관리" />
        <p className={styles.inlineEmpty} role="alert">{error}</p>
        <Button variant="outline" onClick={load}>다시 시도</Button>
      </div>
    );
  }

  if ((accounts ?? []).length === 0) {
    return (
      <div className={styles.page}>
        <OpsPageHeader title="계정 관리" />
        <p className={styles.inlineEmpty}>등록된 계정이 없습니다.</p>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <OpsPageHeader
        title="계정 관리"
      />

      <OpsFilterBar>
        <OpsSearchField value={query} onChange={setQuery} placeholder="계정 이메일 또는 직원 이름 검색" />
        <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} aria-label="계정 상태">
          <option>전체</option>
          <option>확인 필요</option>
          <option>정상</option>
          <option>잠김</option>
          <option>탈퇴</option>
        </select>
      </OpsFilterBar>

      <OpsDataTable minWidth={1080}>
        <thead>
          <tr>
            <th>플랫폼 로그인 계정</th>
            <th>연결된 직원</th>
            <th>팀</th>
            <th>HR 조직</th>
            <th>매핑 상태</th>
            <th>계정 상태</th>
            <th>연결 서비스</th>
            <th>작업</th>
          </tr>
        </thead>
        <tbody>
          {filtered.length > 0 ? filtered.map((account) => (
            <tr key={account.account_id} onClick={() => navigate(`/ops/accounts/${account.account_id}`)}>
              <td>
                {account.email}
                {account.is_admin && (
                  <>
                    {' '}
                    <OpsStatusBadge tone="info">운영자</OpsStatusBadge>
                  </>
                )}
              </td>
              <td>{account.person?.name ?? '미연결'}</td>
              <td>{account.team_name ?? '미소속'}</td>
              <td>{account.person?.org_name ?? '-'}</td>
              <td><OpsStatusBadge tone={MAPPING_TONES[account.mapping_status]}>{MAPPING_LABELS[account.mapping_status]}</OpsStatusBadge></td>
              <td><OpsStatusBadge tone={statusTone(account.account_status)}>{statusLabel(account.account_status)}</OpsStatusBadge></td>
              <td>{serviceLabels(account.services) || '없음'}</td>
              <td>
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    navigate(`/ops/accounts/${account.account_id}`);
                  }}
                >
                  상세 보기
                </button>
              </td>
            </tr>
          )) : (
            <tr><td className={styles.emptyCell} colSpan={8}>조건에 맞는 계정이 없습니다.</td></tr>
          )}
        </tbody>
      </OpsDataTable>
    </div>
  );
}
