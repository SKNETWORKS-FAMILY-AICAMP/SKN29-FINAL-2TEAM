import { useMemo, useState } from 'react';
import {
  Button,
  Modal,
  OpsDataTable,
  OpsDetailPanel,
  OpsFilterBar,
  OpsPageHeader,
  OpsSearchField,
  OpsStatusBadge,
  OpsSummaryCard,
  OpsSummaryGrid,
  useToast,
} from '../../components';
import { OPS_INVITATIONS } from '../../data/opsMockData';
import type { OpsInvitation } from '../../data/opsMockData';
import styles from '../OpsShared/OpsPages.module.css';

function inviteTone(status: OpsInvitation['status']) {
  if (status === '수락 완료') return 'success';
  if (status === '수락 대기') return 'info';
  if (status === '연결 실패') return 'danger';
  return 'neutral';
}

export default function OpsMappingsPage() {
  const { showToast } = useToast();
  const [invitations, setInvitations] = useState(OPS_INVITATIONS);
  const [query, setQuery] = useState('');
  const [organization, setOrganization] = useState('전체');
  const [status, setStatus] = useState('전체');
  const [selectedId, setSelectedId] = useState('초대 21');
  const [confirmOpen, setConfirmOpen] = useState(false);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return invitations.filter((invitation) => {
      const matchesQuery = !normalized || [invitation.id, invitation.employeeId, invitation.inviterEmail]
        .some((value) => value.toLowerCase().includes(normalized));
      const matchesOrganization = organization === '전체' || invitation.organization === organization;
      const matchesStatus = status === '전체' || invitation.status === status;
      return matchesQuery && matchesOrganization && matchesStatus;
    });
  }, [invitations, organization, query, status]);

  const selected = filtered.find((invitation) => invitation.id === selectedId) ?? filtered[0] ?? null;
  const canDiscard = selected?.status === '수락 대기';
  const canUnlink = selected?.status === '연결 실패' && selected.accountResult.includes('중복 연결');

  function applyAction() {
    if (!selected) return;
    if (canDiscard) {
      setInvitations((current) => current.map((invitation) =>
        invitation.id === selected.id ? { ...invitation, status: '운영자 폐기' } : invitation,
      ));
      showToast('이상 초대 기록을 폐기했습니다.', 'success');
    } else if (canUnlink) {
      setInvitations((current) => current.map((invitation) =>
        invitation.id === selected.id ? { ...invitation, accountResult: '연결 해제됨' } : invitation,
      ));
      showToast('계정과 직원의 연결을 해제했습니다.', 'success');
    }
    setConfirmOpen(false);
  }

  return (
    <div className={styles.page}>
      <OpsPageHeader
        title="계정 연결·초대 현황"
        description="연결 조직별 일회성 초대 발급·수락 결과와 계정–직원 매핑 이상을 추적합니다."
      />

      <OpsSummaryGrid>
        <OpsSummaryCard label="전체" value={24} detail="전체 초대 기록" />
        <OpsSummaryCard label="수락 대기" value={7} detail="만료 전 확인 필요" tone="info" />
        <OpsSummaryCard label="수락 완료" value={14} detail="계정 연결 완료" tone="success" />
        <OpsSummaryCard label="연결 오류" value={2} detail="운영자 검토 필요" tone="danger" />
      </OpsSummaryGrid>

      <div className={styles.notice}>
        원문 초대 코드는 발급 순간 한 번만 노출되며 서버에 저장하지 않습니다. 운영 화면에서는 초대 기록 ID와 발급·수락 결과만 확인합니다.
      </div>

      <OpsFilterBar>
        <OpsSearchField value={query} onChange={setQuery} placeholder="초대 기록 ID 또는 직원 ID 검색" />
        <select value={organization} onChange={(event) => setOrganization(event.target.value)} aria-label="연결 팀·조직">
          <option>전체</option>
          <option>플랫폼팀</option>
          <option>영업기획팀</option>
          <option>디자인팀</option>
        </select>
        <select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="초대 상태">
          <option>전체</option>
          <option>수락 완료</option>
          <option>수락 대기</option>
          <option>만료</option>
          <option>운영자 폐기</option>
          <option>연결 실패</option>
        </select>
      </OpsFilterBar>

      <OpsDataTable minWidth={1100}>
        <thead>
          <tr>
            <th>초대 기록 ID</th>
            <th>직원 ID</th>
            <th>연결 팀·조직</th>
            <th>초대자 이메일</th>
            <th>발급·수락 상태</th>
            <th>계정 연결 결과</th>
            <th>작업</th>
          </tr>
        </thead>
        <tbody>
          {filtered.length > 0 ? filtered.map((invitation) => (
            <tr key={invitation.id} aria-selected={selected?.id === invitation.id} onClick={() => setSelectedId(invitation.id)}>
              <td>{invitation.id}</td>
              <td>{invitation.employeeId}</td>
              <td>{invitation.organization}</td>
              <td>{invitation.inviterEmail}</td>
              <td><OpsStatusBadge tone={inviteTone(invitation.status)}>{invitation.status} · {invitation.issuedAt}</OpsStatusBadge></td>
              <td>{invitation.accountResult}</td>
              <td><button type="button" onClick={(event) => { event.stopPropagation(); setSelectedId(invitation.id); }}>상세 보기</button></td>
            </tr>
          )) : (
            <tr><td className={styles.emptyCell} colSpan={7}>조건에 맞는 초대 기록이 없습니다.</td></tr>
          )}
        </tbody>
      </OpsDataTable>

      {selected ? <OpsDetailPanel title={`선택 초대 · ${selected.id} · ${selected.status}`}>
        <p className={styles.detailText}>
          {selected.employeeId} · {selected.organization} · 초대자 {selected.inviterEmail} · {selected.accountResult}
        </p>
        {(canDiscard || canUnlink) && (
          <div className={styles.rowActions}>
            <Button variant="danger" onClick={() => setConfirmOpen(true)}>
              {canDiscard ? '이상 초대 폐기' : '중복 직원 연결 해제'}
            </Button>
          </div>
        )}
      </OpsDetailPanel> : (
        <div className={styles.inlineEmpty}>검색 조건을 변경하면 초대 상세를 확인할 수 있습니다.</div>
      )}

      <Modal
        open={confirmOpen && selected !== null}
        onClose={() => setConfirmOpen(false)}
        title={canDiscard ? '이상 초대 폐기' : '중복 직원 연결 해제'}
        footer={(
          <>
            <Button variant="secondary" onClick={() => setConfirmOpen(false)}>취소</Button>
            <Button variant="danger" onClick={applyAction}>처리하기</Button>
          </>
        )}
      >
        <p className={styles.modalCopy}>
          {selected?.id} 기록에 작업을 적용합니다. 초대와 연결 이력은 삭제하지 않고 상태 변경 내역을 남깁니다.
        </p>
      </Modal>
    </div>
  );
}
