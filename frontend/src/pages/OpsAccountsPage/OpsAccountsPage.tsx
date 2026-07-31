import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Button,
  Modal,
  OpsDataTable,
  OpsDetailPanel,
  OpsFilterBar,
  OpsPageHeader,
  OpsSearchField,
  OpsStatusBadge,
  useToast,
} from '../../components';
import type { OpsTone } from '../../components';
import {
  fetchAccounts,
  lockAccount,
  unlinkAccountPerson,
  unlockAccount,
} from '../../api/opsAccounts';
import type { OpsAccount, OpsMappingStatus } from '../../api/opsAccounts';
import { ApiError } from '../../api/client';
import { loadOpsSession } from '../../utils/opsSession';
import styles from '../OpsShared/OpsPages.module.css';

const STATUS_LABELS: Record<string, string> = {
  ACTIVE: '정상',
  LOCKED: '잠김',
  WITHDRAWN: '탈퇴',
};

const STATUS_TONES: Record<string, OpsTone> = {
  ACTIVE: 'success',
  LOCKED: 'danger',
  WITHDRAWN: 'neutral',
};

const MAPPING_LABELS: Record<OpsMappingStatus, string> = {
  UNMAPPED: '미연결',
  LINKED: '연결됨',
  DUPLICATE: '중복 연결',
};

const MAPPING_TONES: Record<OpsMappingStatus, OpsTone> = {
  UNMAPPED: 'neutral',
  LINKED: 'success',
  DUPLICATE: 'danger',
};

function statusLabel(status: string) {
  return STATUS_LABELS[status] ?? status;
}

function statusTone(status: string): OpsTone {
  return STATUS_TONES[status] ?? 'neutral';
}

type PendingAction = 'lock' | 'unlock' | 'unlink' | null;

export default function OpsAccountsPage() {
  const { showToast } = useToast();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [accounts, setAccounts] = useState<OpsAccount[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState(searchParams.get('status') ?? '전체');
  // 팀 현황에서 팀을 눌러 넘어온 경우 그 팀으로 좁혀 보여준다.
  const teamFilter = searchParams.get('team');
  const [selectedId, setSelectedId] = useState('');
  const [pendingAction, setPendingAction] = useState<PendingAction>(null);
  const [submitting, setSubmitting] = useState(false);

  const session = loadOpsSession();
  const myAccountId = session?.admin.account_id ?? null;

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

  const selected = filtered.find((account) => account.account_id === selectedId) ?? filtered[0] ?? null;

  async function confirmAction() {
    if (!pendingAction || !selected || submitting) return;
    const currentSession = loadOpsSession();
    if (!currentSession) {
      navigate('/ops/login', { replace: true });
      return;
    }

    setSubmitting(true);
    try {
      if (pendingAction === 'lock') {
        await lockAccount(currentSession.token, selected.account_id);
        showToast('계정을 정지했습니다.', 'success');
      } else if (pendingAction === 'unlock') {
        await unlockAccount(currentSession.token, selected.account_id);
        showToast('계정을 재활성했습니다.', 'success');
      } else {
        await unlinkAccountPerson(currentSession.token, selected.account_id);
        showToast('직원 연결을 해제했습니다.', 'success');
      }
      setPendingAction(null);
      await load();
    } catch (thrown) {
      if (thrown instanceof ApiError && thrown.status === 401) {
        navigate('/ops/login', { replace: true });
        return;
      }
      showToast(thrown instanceof ApiError ? thrown.message : '요청을 처리하지 못했습니다.', 'error');
    } finally {
      setSubmitting(false);
    }
  }

  if (loading && !accounts) {
    return (
      <div className={styles.page}>
        <OpsPageHeader title="계정 관리" description="플랫폼 로그인 계정의 상태와 직원 연결 이상을 확인하고 정지·재활성·연결 해제를 수행합니다." />
        <p className={styles.inlineEmpty}>불러오는 중…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.page}>
        <OpsPageHeader title="계정 관리" description="플랫폼 로그인 계정의 상태와 직원 연결 이상을 확인하고 정지·재활성·연결 해제를 수행합니다." />
        <p className={styles.inlineEmpty} role="alert">{error}</p>
        <Button variant="outline" onClick={load}>다시 시도</Button>
      </div>
    );
  }

  if ((accounts ?? []).length === 0) {
    return (
      <div className={styles.page}>
        <OpsPageHeader title="계정 관리" description="플랫폼 로그인 계정의 상태와 직원 연결 이상을 확인하고 정지·재활성·연결 해제를 수행합니다." />
        <p className={styles.inlineEmpty}>등록된 계정이 없습니다.</p>
      </div>
    );
  }

  const canLock = selected?.account_status === 'ACTIVE' && selected.account_id !== myAccountId;
  const canUnlock = selected?.account_status === 'LOCKED';
  const canUnlink = selected?.mapping_status === 'DUPLICATE';
  const isSelf = selected?.account_id === myAccountId;
  const isWithdrawn = selected?.account_status === 'WITHDRAWN';

  return (
    <div className={styles.page}>
      <OpsPageHeader
        title="계정 관리"
        description="플랫폼 로그인 계정의 상태와 직원 연결 이상을 확인하고 정지·재활성·연결 해제를 수행합니다."
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
            <tr
              key={account.account_id}
              aria-selected={account.account_id === selected?.account_id}
              onClick={() => setSelectedId(account.account_id)}
            >
              <td>{account.email}</td>
              <td>{account.person?.name ?? '미연결'}</td>
              <td>{account.team_name ?? '미소속'}</td>
              <td>{account.person?.org_name ?? '-'}</td>
              <td><OpsStatusBadge tone={MAPPING_TONES[account.mapping_status]}>{MAPPING_LABELS[account.mapping_status]}</OpsStatusBadge></td>
              <td><OpsStatusBadge tone={statusTone(account.account_status)}>{statusLabel(account.account_status)}</OpsStatusBadge></td>
              <td>{account.services.join(' · ') || '없음'}</td>
              <td><button type="button" onClick={(event) => { event.stopPropagation(); setSelectedId(account.account_id); }}>상세 보기</button></td>
            </tr>
          )) : (
            <tr><td className={styles.emptyCell} colSpan={8}>조건에 맞는 계정이 없습니다.</td></tr>
          )}
        </tbody>
      </OpsDataTable>

      {selected ? <OpsDetailPanel title={`선택 계정 · ${selected.email} · ${MAPPING_LABELS[selected.mapping_status]}`}>
        <div className={styles.detailCards}>
          <div className={styles.detailCard}>
            <strong>직원 매핑</strong>
            <p>
              {selected.person
                ? `${selected.person.name ?? '직원 정보 없음(연결 대상이 삭제됨)'} · ${selected.person.org_name ?? '조직 미지정'}`
                : '미연결'}
              {selected.mapping_status === 'DUPLICATE' ? ` · 연결 ${selected.link_count}건` : ''}
            </p>
          </div>
          <div className={styles.detailCard}>
            <strong>연결 서비스</strong>
            <p>{selected.services.join(' · ') || '연결된 서비스 없음'}</p>
          </div>
        </div>
        <p className={styles.detailText}>
          운영자는 오류 조사에 필요한 최소 정보만 확인하고, 잘못된 직원 연결 해제 또는 계정 상태 변경을 수행합니다.
        </p>
        {isWithdrawn && (
          <p className={styles.detailText}>탈퇴한 계정은 상태를 변경할 수 없습니다.</p>
        )}
        {isSelf && !isWithdrawn && (
          <p className={styles.detailText}>본인 계정은 이 화면에서 잠글 수 없습니다.</p>
        )}
        <div className={styles.rowActions}>
          {canLock && (
            <Button variant="danger" onClick={() => setPendingAction('lock')}>계정 정지</Button>
          )}
          {canUnlock && (
            <Button variant="primary" onClick={() => setPendingAction('unlock')}>계정 재활성</Button>
          )}
          {canUnlink && (
            <Button variant="outline" onClick={() => setPendingAction('unlink')}>직원 연결 해제</Button>
          )}
        </div>
      </OpsDetailPanel> : (
        <div className={styles.inlineEmpty}>검색 조건을 변경하면 계정 상세를 확인할 수 있습니다.</div>
      )}

      <Modal
        open={pendingAction !== null && selected !== null}
        onClose={() => (submitting ? null : setPendingAction(null))}
        title={pendingAction === 'unlink' ? '직원 연결 해제' : pendingAction === 'unlock' ? '계정 재활성' : '계정 정지'}
        footer={(
          <>
            <Button variant="secondary" onClick={() => setPendingAction(null)} disabled={submitting}>취소</Button>
            <Button
              variant={pendingAction === 'unlock' ? 'primary' : 'danger'}
              onClick={confirmAction}
              disabled={submitting}
            >
              {submitting ? '처리 중…' : '변경 적용'}
            </Button>
          </>
        )}
      >
        <p className={styles.modalCopy}>
          {selected?.email} 계정에 이 작업을 적용합니다. 변경 내역은 운영 감사 대상으로 기록됩니다.
        </p>
      </Modal>
    </div>
  );
}
