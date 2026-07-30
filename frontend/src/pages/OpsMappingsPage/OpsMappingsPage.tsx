import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
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
import type { OpsTone } from '../../components';
import { discardInvite, fetchInvites, unlinkInvite } from '../../api/opsInvites';
import type { OpsInvite, OpsInviteStatus } from '../../api/opsInvites';
import { ApiError } from '../../api/client';
import { loadOpsSession } from '../../utils/opsSession';
import styles from '../OpsShared/OpsPages.module.css';

const STATUS_LABELS: Record<OpsInviteStatus, string> = {
  PENDING: '수락 대기',
  ACCEPTED: '수락 완료',
  EXPIRED: '만료',
  REVOKED: '취소됨',
};

const STATUS_TONES: Record<OpsInviteStatus, OpsTone> = {
  PENDING: 'info',
  ACCEPTED: 'success',
  EXPIRED: 'neutral',
  REVOKED: 'neutral',
};

function statusLabel(status: OpsInviteStatus) {
  return STATUS_LABELS[status] ?? status;
}

function statusTone(status: OpsInviteStatus): OpsTone {
  return STATUS_TONES[status] ?? 'neutral';
}

type PendingAction = 'discard' | 'unlink' | null;

export default function OpsMappingsPage() {
  const { showToast } = useToast();
  const navigate = useNavigate();
  const [invites, setInvites] = useState<OpsInvite[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [organization, setOrganization] = useState('전체');
  const [status, setStatus] = useState('전체');
  const [selectedId, setSelectedId] = useState('');
  const [pendingAction, setPendingAction] = useState<PendingAction>(null);
  const [submitting, setSubmitting] = useState(false);

  async function load() {
    const session = loadOpsSession();
    if (!session) {
      navigate('/ops/login', { replace: true });
      return;
    }

    setLoading(true);
    setError('');
    try {
      setInvites(await fetchInvites(session.token));
    } catch (thrown) {
      if (thrown instanceof ApiError && thrown.status === 401) {
        navigate('/ops/login', { replace: true });
        return;
      }
      setError(thrown instanceof ApiError ? thrown.message : '초대 현황을 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const organizations = useMemo(() => {
    const names = new Set<string>();
    for (const invite of invites ?? []) {
      if (invite.org_name) names.add(invite.org_name);
    }
    return ['전체', ...[...names].sort()];
  }, [invites]);

  const filtered = useMemo(() => {
    const all = invites ?? [];
    const normalized = query.trim().toLowerCase();
    return all.filter((invite) => {
      const matchesQuery = !normalized || [
        invite.invite_id,
        invite.person_id,
        invite.person_name ?? '',
        invite.inviter_email ?? '',
      ].some((value) => value.toLowerCase().includes(normalized));
      const matchesOrganization = organization === '전체' || invite.org_name === organization;
      const matchesStatus = status === '전체' || statusLabel(invite.status) === status;
      return matchesQuery && matchesOrganization && matchesStatus;
    });
  }, [invites, organization, query, status]);

  const selected = filtered.find((invite) => invite.invite_id === selectedId) ?? filtered[0] ?? null;
  const canDiscard = selected?.status === 'PENDING' || selected?.status === 'EXPIRED';
  const canUnlink = selected?.linked_account_duplicate === true;

  async function confirmAction() {
    if (!pendingAction || !selected || submitting) return;
    const session = loadOpsSession();
    if (!session) {
      navigate('/ops/login', { replace: true });
      return;
    }

    setSubmitting(true);
    try {
      if (pendingAction === 'discard') {
        await discardInvite(session.token, selected.invite_id);
        showToast('이상 초대 기록을 폐기했습니다.', 'success');
      } else {
        await unlinkInvite(session.token, selected.invite_id);
        showToast('계정과 직원의 연결을 해제했습니다.', 'success');
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

  if (loading && !invites) {
    return (
      <div className={styles.page}>
        <OpsPageHeader title="계정 연결·초대 현황" description="연결 조직별 일회성 초대 발급·수락 결과와 계정–직원 매핑 이상을 추적합니다." />
        <p className={styles.inlineEmpty}>불러오는 중…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.page}>
        <OpsPageHeader title="계정 연결·초대 현황" description="연결 조직별 일회성 초대 발급·수락 결과와 계정–직원 매핑 이상을 추적합니다." />
        <p className={styles.inlineEmpty} role="alert">{error}</p>
        <Button variant="outline" onClick={load}>다시 시도</Button>
      </div>
    );
  }

  const all = invites ?? [];
  const countByStatus = (target: OpsInviteStatus) => all.filter((i) => i.status === target).length;
  const duplicateCount = all.filter((i) => i.linked_account_duplicate).length;

  return (
    <div className={styles.page}>
      <OpsPageHeader
        title="계정 연결·초대 현황"
        description="연결 조직별 일회성 초대 발급·수락 결과와 계정–직원 매핑 이상을 추적합니다."
      />

      <OpsSummaryGrid>
        <OpsSummaryCard label="전체" value={all.length} detail="전체 초대 기록" />
        <OpsSummaryCard label="수락 대기" value={countByStatus('PENDING')} detail="만료 전 확인 필요" tone="info" />
        <OpsSummaryCard label="수락 완료" value={countByStatus('ACCEPTED')} detail="계정 연결 완료" tone="success" />
        <OpsSummaryCard label="중복 연결" value={duplicateCount} detail="운영자 검토 필요" tone="danger" />
      </OpsSummaryGrid>

      <div className={styles.notice}>
        원문 초대 코드는 발급 순간 한 번만 노출되며 서버에 저장하지 않습니다. 운영 화면에서는 초대 기록 ID와 발급·수락 결과만 확인합니다.
      </div>

      {all.length === 0 ? (
        <p className={styles.inlineEmpty}>발급된 초대 기록이 없습니다.</p>
      ) : (
        <>
          <OpsFilterBar>
            <OpsSearchField value={query} onChange={setQuery} placeholder="초대 기록 ID 또는 직원 ID 검색" />
            <select value={organization} onChange={(event) => setOrganization(event.target.value)} aria-label="연결 팀·조직">
              {organizations.map((name) => <option key={name}>{name}</option>)}
            </select>
            <select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="초대 상태">
              <option>전체</option>
              {(Object.keys(STATUS_LABELS) as OpsInviteStatus[]).map((key) => (
                <option key={key}>{STATUS_LABELS[key]}</option>
              ))}
            </select>
          </OpsFilterBar>

          <OpsDataTable minWidth={1100}>
            <thead>
              <tr>
                <th>초대 기록 ID</th>
                <th>직원 ID</th>
                <th>연결 팀·조직</th>
                <th>초대자 이메일</th>
                <th>상태</th>
                <th>계정 연결 결과</th>
                <th>작업</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length > 0 ? filtered.map((invite) => (
                <tr key={invite.invite_id} aria-selected={selected?.invite_id === invite.invite_id} onClick={() => setSelectedId(invite.invite_id)}>
                  <td>{invite.invite_id}</td>
                  <td>{invite.person_id}</td>
                  <td>{invite.org_name ?? '-'}</td>
                  <td>{invite.inviter_email ?? '-'}</td>
                  <td><OpsStatusBadge tone={statusTone(invite.status)}>{statusLabel(invite.status)}</OpsStatusBadge></td>
                  <td>
                    {invite.linked_account_id
                      ? `${invite.linked_account_id}${invite.linked_account_duplicate ? ' · 중복 연결' : ' · 연결됨'}`
                      : '연결 안 됨'}
                  </td>
                  <td><button type="button" onClick={(event) => { event.stopPropagation(); setSelectedId(invite.invite_id); }}>상세 보기</button></td>
                </tr>
              )) : (
                <tr><td className={styles.emptyCell} colSpan={7}>조건에 맞는 초대 기록이 없습니다.</td></tr>
              )}
            </tbody>
          </OpsDataTable>

          {selected ? <OpsDetailPanel title={`선택 초대 · ${selected.invite_id} · ${statusLabel(selected.status)}`}>
            <p className={styles.detailText}>
              {selected.person_id} · {selected.person_name ?? '이름 미상'} · {selected.org_name ?? '조직 미지정'} · 초대자 {selected.inviter_email ?? '-'}
            </p>
            <p className={styles.detailText}>
              {selected.linked_account_id
                ? `연결된 계정 ${selected.linked_account_id}${selected.linked_account_duplicate ? ' (이 계정에 직원이 중복으로 연결되어 있습니다)' : ''}`
                : '아직 계정에 연결되지 않았습니다.'}
            </p>
            {(canDiscard || canUnlink) && (
              <div className={styles.rowActions}>
                {canDiscard && (
                  <Button variant="danger" onClick={() => setPendingAction('discard')}>이상 초대 폐기</Button>
                )}
                {canUnlink && (
                  <Button variant="outline" onClick={() => setPendingAction('unlink')}>중복 직원 연결 해제</Button>
                )}
              </div>
            )}
          </OpsDetailPanel> : (
            <div className={styles.inlineEmpty}>검색 조건을 변경하면 초대 상세를 확인할 수 있습니다.</div>
          )}
        </>
      )}

      <Modal
        open={pendingAction !== null && selected !== null}
        onClose={() => (submitting ? null : setPendingAction(null))}
        title={pendingAction === 'unlink' ? '중복 직원 연결 해제' : '이상 초대 폐기'}
        footer={(
          <>
            <Button variant="secondary" onClick={() => setPendingAction(null)} disabled={submitting}>취소</Button>
            <Button variant="danger" onClick={confirmAction} disabled={submitting}>
              {submitting ? '처리 중…' : '처리하기'}
            </Button>
          </>
        )}
      >
        <p className={styles.modalCopy}>
          {selected?.invite_id} 기록에 작업을 적용합니다. 초대와 연결 이력은 삭제하지 않고 상태 변경 내역을 남깁니다.
        </p>
      </Modal>
    </div>
  );
}
