import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Button, Modal, OpsPageHeader, OpsSectionCard, OpsStatusBadge, useToast } from '../../components';
import {
  fetchAccount,
  lockAccount,
  setAccountAdmin,
  unlinkAccountPerson,
  unlockAccount,
} from '../../api/opsAccounts';
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
 * 계정 상세.
 *
 * 예전에는 목록 화면 아래에 붙은 섹션이었다. 표를 훑다가 한 줄을 고르면 그 아래에
 * 상세가 나오는 구조라, **표와 상세가 화면을 나눠 쓰느라 둘 다 좁았고** 조치
 * 버튼이 스크롤 아래에 숨었다. 주소로 바로 들어올 수도 없었다(2026-08-13 PM).
 *
 * 조치는 전부 이쪽으로 옮겼다 — 목록은 「누가 있는가」, 상세는 「이 계정을 어떻게
 * 할 것인가」로 역할이 갈린다.
 */

type PendingAction = 'lock' | 'unlock' | 'unlink' | 'grant-admin' | 'revoke-admin' | null;

const MODAL_TITLES: Record<Exclude<PendingAction, null>, string> = {
  lock: '계정 정지',
  unlock: '계정 재활성',
  unlink: '직원 연결 해제',
  'grant-admin': '운영자로 지정',
  'revoke-admin': '운영자 권한 회수',
};

export default function OpsAccountDetailPage() {
  const navigate = useNavigate();
  const { accountId } = useParams();
  const { showToast } = useToast();

  const [account, setAccount] = useState<OpsAccount | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [pendingAction, setPendingAction] = useState<PendingAction>(null);
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    const session = loadOpsSession();
    if (!session || !accountId) {
      navigate('/ops/login', { replace: true });
      return;
    }
    setLoading(true);
    setError('');
    try {
      setAccount(await fetchAccount(session.token, accountId));
    } catch (thrown) {
      if (thrown instanceof ApiError && thrown.status === 401) {
        navigate('/ops/login', { replace: true });
        return;
      }
      setError(thrown instanceof ApiError ? thrown.message : '계정을 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }, [accountId, navigate]);

  useEffect(() => {
    void load();
  }, [load]);

  function closeModal() {
    if (submitting) return;
    setPendingAction(null);
    setReason('');
  }

  async function confirmAction() {
    const session = loadOpsSession();
    if (!session || !account || !pendingAction || submitting) return;

    setSubmitting(true);
    try {
      if (pendingAction === 'lock') {
        await lockAccount(session.token, account.account_id);
        showToast('계정을 정지했습니다.', 'success');
      } else if (pendingAction === 'unlock') {
        await unlockAccount(session.token, account.account_id);
        showToast('계정을 재활성했습니다.', 'success');
      } else if (pendingAction === 'grant-admin' || pendingAction === 'revoke-admin') {
        const grant = pendingAction === 'grant-admin';
        await setAccountAdmin(session.token, account.account_id, grant, reason.trim());
        showToast(grant ? '운영자 권한을 부여했습니다.' : '운영자 권한을 회수했습니다.', 'success');
      } else {
        await unlinkAccountPerson(session.token, account.account_id);
        showToast('직원 연결을 해제했습니다.', 'success');
      }
      setPendingAction(null);
      setReason('');
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

  const back = (
    <Button variant="secondary" onClick={() => navigate('/ops/accounts')}>
      계정 목록으로
    </Button>
  );

  if (loading && !account) {
    return (
      <div className={styles.page}>
        <OpsPageHeader title="계정 상세" description="이 계정의 상태와 직원 연결을 확인하고 조치합니다." />
        <p className={styles.inlineEmpty}>불러오는 중…</p>
      </div>
    );
  }

  if (error || !account) {
    return (
      <div className={styles.page}>
        <OpsPageHeader title="계정 상세" description="이 계정의 상태와 직원 연결을 확인하고 조치합니다." />
        <p className={styles.inlineEmpty} role="alert">{error || '계정을 찾을 수 없습니다.'}</p>
        <div className={styles.rowActions}>
          <Button variant="outline" onClick={load}>다시 시도</Button>
          {back}
        </div>
      </div>
    );
  }

  const session = loadOpsSession();
  const isSelf = account.account_id === session?.admin.account_id;
  const isWithdrawn = account.account_status === 'WITHDRAWN';
  const canLock = account.account_status === 'ACTIVE' && !isSelf;
  const canUnlock = account.account_status === 'LOCKED';
  const canUnlink = account.mapping_status === 'DUPLICATE';
  const canGrantAdmin = !account.is_admin && !isWithdrawn;
  const canRevokeAdmin = account.is_admin && !isSelf;
  const asksReason = pendingAction === 'grant-admin' || pendingAction === 'revoke-admin';

  return (
    <div className={styles.page}>
      <OpsPageHeader title="계정 상세" description="이 계정의 상태와 직원 연결을 확인하고 조치합니다." />

      <div className={styles.rowActions}>
        {back}
        <OpsStatusBadge tone={statusTone(account.account_status)}>
          {statusLabel(account.account_status)}
        </OpsStatusBadge>
        <OpsStatusBadge tone={MAPPING_TONES[account.mapping_status]}>
          {MAPPING_LABELS[account.mapping_status]}
        </OpsStatusBadge>
        {account.is_admin && <OpsStatusBadge tone="info">운영자</OpsStatusBadge>}
      </div>

      {/* **이메일을 제목으로 쓰지 않는다.** 제목은 이 화면이 무엇인지 말하는
          자리이고, 이메일은 이 계정의 값 중 하나다 — 다른 값과 같은 모양으로
          둔다(2026-08-13 PM 지적).

          `detailGrid`·`infoCard` 는 CSS 에만 있고 쓰는 곳이 없던 관용구다.
          라벨 위·값 아래의 정의형 배치라 이 화면이 원하던 모양 그대로다. */}
      <div className={styles.detailGrid}>
        <div className={styles.infoCard}>
          <span>이메일</span>
          <strong>{account.email}</strong>
        </div>
        <div className={styles.infoCard}>
          <span>이름</span>
          <strong>{account.display_name || '-'}</strong>
        </div>
        <div className={styles.infoCard}>
          <span>소속 팀</span>
          <strong>{account.team_name ?? '미소속'}</strong>
        </div>
        <div className={styles.infoCard}>
          <span>직원 매핑</span>
          <strong>
            {account.person
              ? `${account.person.name ?? '직원 정보 없음'} · ${account.person.org_name ?? '조직 미지정'}`
              : '미연결'}
            {account.mapping_status === 'DUPLICATE' ? ` · 연결 ${account.link_count}건` : ''}
          </strong>
        </div>
        <div className={styles.infoCard}>
          <span>연결 서비스</span>
          <strong>{serviceLabels(account.services) || '없음'}</strong>
        </div>
      </div>

      <OpsSectionCard title="조치">
        {/* 왜 눌릴 수 없는지는 상태가 이미 말한다. 다만 **눌릴 수 없는 이유가
            상태 뱃지로 안 드러나는 두 가지**는 적어 둔다. */}
        {isWithdrawn && <p className={styles.detailText}>탈퇴한 계정은 상태를 변경할 수 없습니다.</p>}
        {isSelf && !isWithdrawn && (
          <p className={styles.detailText}>본인 계정은 정지하거나 권한을 내릴 수 없습니다.</p>
        )}
        <div className={styles.rowActions}>
          {canLock && <Button variant="danger" onClick={() => setPendingAction('lock')}>계정 정지</Button>}
          {canUnlock && <Button variant="primary" onClick={() => setPendingAction('unlock')}>계정 재활성</Button>}
          {canUnlink && (
            <Button variant="outline" onClick={() => setPendingAction('unlink')}>직원 연결 해제</Button>
          )}
          {canGrantAdmin && (
            <Button variant="outline" onClick={() => setPendingAction('grant-admin')}>운영자로 지정</Button>
          )}
          {canRevokeAdmin && (
            <Button variant="danger" onClick={() => setPendingAction('revoke-admin')}>운영자 권한 회수</Button>
          )}
        </div>
      </OpsSectionCard>

      <Modal
        open={pendingAction !== null}
        onClose={closeModal}
        title={MODAL_TITLES[pendingAction ?? 'lock']}
        footer={(
          <>
            <Button variant="secondary" onClick={closeModal} disabled={submitting}>취소</Button>
            <Button
              variant={pendingAction === 'unlock' || pendingAction === 'grant-admin' ? 'primary' : 'danger'}
              onClick={confirmAction}
              disabled={submitting}
            >
              {submitting ? '처리 중…' : '변경 적용'}
            </Button>
          </>
        )}
      >
        <p className={styles.modalCopy}>
          {account.email} 계정에 이 작업을 적용합니다. 변경 내역은 운영 감사 대상으로 기록됩니다.
        </p>
        {asksReason && (
          <div className={styles.fieldGroup}>
            <label htmlFor="admin-reason">사유 (선택)</label>
            <textarea
              id="admin-reason"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="예: 운영 인수인계"
            />
          </div>
        )}
      </Modal>
    </div>
  );
}
