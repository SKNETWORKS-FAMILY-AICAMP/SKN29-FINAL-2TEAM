import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
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
import { OPS_ACCOUNTS } from '../../data/opsMockData';
import type { OpsAccount } from '../../data/opsMockData';
import styles from '../OpsShared/OpsPages.module.css';

function statusTone(status: OpsAccount['status']) {
  return status === '정상' ? 'success' : 'danger';
}

function mappingTone(status: OpsAccount['mappingStatus']) {
  if (status === '연결됨') return 'success';
  if (status === '중복 연결') return 'danger';
  return 'neutral';
}

export default function OpsAccountsPage() {
  const { showToast } = useToast();
  const [searchParams] = useSearchParams();
  const [accounts, setAccounts] = useState(OPS_ACCOUNTS);
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState(searchParams.get('status') ?? '전체');
  const [selectedId, setSelectedId] = useState('계정 18');
  const [pendingAction, setPendingAction] = useState<'toggle' | 'unlink' | null>(null);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return accounts.filter((account) => {
      const matchesQuery = !normalized || [account.email, account.id, account.employeeId ?? '', account.organization]
        .some((value) => value.toLowerCase().includes(normalized));
      const matchesStatus = statusFilter === '전체'
        || (statusFilter === '확인 필요' && (account.mappingStatus !== '연결됨' || account.status === '잠김'))
        || account.status === statusFilter;
      return matchesQuery && matchesStatus;
    });
  }, [accounts, query, statusFilter]);

  const selected = filtered.find((account) => account.id === selectedId) ?? filtered[0] ?? null;

  function confirmAction() {
    if (!pendingAction || !selected) return;

    setAccounts((current) => current.map((account) => {
      if (account.id !== selected.id) return account;
      if (pendingAction === 'toggle') {
        return { ...account, status: account.status === '정상' ? '잠김' : '정상' };
      }
      return { ...account, employeeId: null, mappingStatus: '미연결' };
    }));

    showToast(
      pendingAction === 'toggle'
        ? `계정 상태를 ${selected.status === '정상' ? '잠김' : '정상'}으로 변경했습니다.`
        : '직원 연결을 해제했습니다.',
      'success',
    );
    setPendingAction(null);
  }

  return (
    <div className={styles.page}>
      <OpsPageHeader
        title="계정 관리"
        description="플랫폼 로그인 계정의 상태와 직원 연결 이상을 확인하고 정지·재활성·연결 해제를 수행합니다."
      />

      <OpsFilterBar>
        <OpsSearchField value={query} onChange={setQuery} placeholder="계정 이메일 또는 직원 ID 검색" />
        <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} aria-label="계정 상태">
          <option>전체</option>
          <option>확인 필요</option>
          <option>정상</option>
          <option>잠김</option>
        </select>
      </OpsFilterBar>

      <OpsDataTable minWidth={1080}>
        <thead>
          <tr>
            <th>플랫폼 로그인 계정</th>
            <th>직원 ID</th>
            <th>연결 팀·조직</th>
            <th>매핑 상태</th>
            <th>계정 상태</th>
            <th>연결 서비스</th>
            <th>작업</th>
          </tr>
        </thead>
        <tbody>
          {filtered.length > 0 ? filtered.map((account) => (
            <tr key={account.id} aria-selected={account.id === selected.id} onClick={() => setSelectedId(account.id)}>
              <td>{account.email}</td>
              <td>{account.employeeId ?? '미연결'}</td>
              <td>{account.organization}</td>
              <td><OpsStatusBadge tone={mappingTone(account.mappingStatus)}>{account.mappingStatus}</OpsStatusBadge></td>
              <td><OpsStatusBadge tone={statusTone(account.status)}>{account.status}</OpsStatusBadge></td>
              <td>{account.services.join(' · ') || '없음'}</td>
              <td><button type="button" onClick={(event) => { event.stopPropagation(); setSelectedId(account.id); }}>상세 보기</button></td>
            </tr>
          )) : (
            <tr><td className={styles.emptyCell} colSpan={7}>조건에 맞는 계정이 없습니다.</td></tr>
          )}
        </tbody>
      </OpsDataTable>

      {selected ? <OpsDetailPanel title={`선택 계정 · ${selected.email} · ${selected.mappingStatus}`}>
        <div className={styles.detailCards}>
          <div className={styles.detailCard}>
            <strong>직원 매핑</strong>
            <p>{selected.employeeId ?? '미연결'} · {selected.organization} · {selected.mappingStatus}</p>
          </div>
          <div className={styles.detailCard}>
            <strong>확인용 인사 정보</strong>
            <p>{selected.employeeName ? `이름 ${selected.employeeName} · 오류 조사 시에만 표시` : '추가 확인 정보 없음'}</p>
          </div>
          <div className={styles.detailCard}>
            <strong>연결 서비스</strong>
            <p>{selected.services.join(' · ') || '연결된 서비스 없음'}</p>
          </div>
        </div>
        <p className={styles.detailText}>
          운영자는 오류 조사에 필요한 최소 정보만 확인하고, 잘못된 직원 연결 해제 또는 계정 상태 변경을 수행합니다.
        </p>
        <div className={styles.rowActions}>
          <Button variant={selected.status === '정상' ? 'danger' : 'primary'} onClick={() => setPendingAction('toggle')}>
            {selected.status === '정상' ? '계정 정지' : '계정 재활성'}
          </Button>
          {selected.mappingStatus === '중복 연결' && (
            <Button variant="outline" onClick={() => setPendingAction('unlink')}>
              직원 연결 해제
            </Button>
          )}
        </div>
      </OpsDetailPanel> : (
        <div className={styles.inlineEmpty}>검색 조건을 변경하면 계정 상세를 확인할 수 있습니다.</div>
      )}

      <Modal
        open={pendingAction !== null && selected !== null}
        onClose={() => setPendingAction(null)}
        title={pendingAction === 'unlink' ? '직원 연결 해제' : selected?.status === '정상' ? '계정 정지' : '계정 재활성'}
        footer={(
          <>
            <Button variant="secondary" onClick={() => setPendingAction(null)}>취소</Button>
            <Button variant={pendingAction === 'unlink' || selected?.status === '정상' ? 'danger' : 'primary'} onClick={confirmAction}>
              변경 적용
            </Button>
          </>
        )}
      >
        <p className={styles.modalCopy}>
          {selected?.email} 계정에 이 작업을 적용합니다. 변경 내역은 운영 감사 대상으로 기록되어야 합니다.
        </p>
      </Modal>
    </div>
  );
}
