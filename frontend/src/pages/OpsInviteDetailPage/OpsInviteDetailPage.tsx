import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Button, Modal, OpsPageHeader, OpsSectionCard, OpsStatusBadge, useToast } from '../../components';
import { discardInvite, fetchInvite, unlinkInvite } from '../../api/opsInvites';
import type { OpsInvite } from '../../api/opsInvites';
import { ApiError } from '../../api/client';
import { loadOpsSession } from '../../utils/opsSession';
import { statusLabel, statusTone } from '../OpsShared/inviteLabels';
import styles from '../OpsShared/OpsPages.module.css';

/**
 * 초대 상세.
 *
 * 계정 상세와 같은 이유로 목록에서 갈랐다 — 표와 상세가 한 화면을 나눠 쓰느라
 * 조치 두 개가 스크롤 아래에 숨었다(2026-08-13 PM).
 *
 * 이 화면의 조치는 **되돌릴 수 없는 쪽**이다. 초대를 폐기하면 그 코드는 다시 못
 * 쓰고, 연결을 끊으면 그 사람은 다시 초대를 받아야 한다. 목록에서 한 줄 고르고
 * 바로 누르던 것을 한 단계 떨어뜨려 둔다.
 */

type PendingAction = 'discard' | 'unlink' | null;

const MODAL_TITLES: Record<Exclude<PendingAction, null>, string> = {
  discard: '이상 초대 폐기',
  unlink: '중복 직원 연결 해제',
};

function formatAt(iso: string | null): string {
  if (!iso) return '-';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return `${date.getFullYear()}.${String(date.getMonth() + 1).padStart(2, '0')}.${String(date.getDate()).padStart(2, '0')}`;
}

export default function OpsInviteDetailPage() {
  const navigate = useNavigate();
  const { inviteId } = useParams();
  const { showToast } = useToast();

  const [invite, setInvite] = useState<OpsInvite | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [pendingAction, setPendingAction] = useState<PendingAction>(null);
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    const session = loadOpsSession();
    if (!session || !inviteId) {
      navigate('/ops/login', { replace: true });
      return;
    }
    setLoading(true);
    setError('');
    try {
      setInvite(await fetchInvite(session.token, inviteId));
    } catch (thrown) {
      if (thrown instanceof ApiError && thrown.status === 401) {
        navigate('/ops/login', { replace: true });
        return;
      }
      setError(thrown instanceof ApiError ? thrown.message : '초대를 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }, [inviteId, navigate]);

  useEffect(() => {
    void load();
  }, [load]);

  async function confirmAction() {
    const session = loadOpsSession();
    if (!session || !invite || !pendingAction || submitting) return;

    setSubmitting(true);
    try {
      if (pendingAction === 'discard') {
        await discardInvite(session.token, invite.invite_id);
        showToast('초대를 폐기했습니다.', 'success');
      } else {
        await unlinkInvite(session.token, invite.invite_id);
        showToast('중복 직원 연결을 해제했습니다.', 'success');
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

  const back = (
    <Button variant="secondary" onClick={() => navigate('/ops/mappings')}>
      초대 목록으로
    </Button>
  );
  const header = (
    <OpsPageHeader
      title="초대 상세"
      description="초대 발급·수락 결과와 계정–직원 연결 상태를 확인하고 조치합니다."
      actions={back}
    />
  );

  if (loading && !invite) {
    return (
      <div className={styles.page}>
        {header}
        <p className={styles.inlineEmpty}>불러오는 중…</p>
      </div>
    );
  }

  if (error || !invite) {
    return (
      <div className={styles.page}>
        {header}
        <p className={styles.inlineEmpty} role="alert">{error || '초대를 찾을 수 없습니다.'}</p>
        <Button variant="outline" onClick={load}>다시 시도</Button>
      </div>
    );
  }

  const canDiscard = invite.status === 'PENDING' || invite.status === 'EXPIRED';
  const canUnlink = invite.linked_account_duplicate;

  return (
    <div className={styles.page}>
      {header}

      <table className={styles.detailTable}>
        <tbody>
          <tr>
            <th scope="row">초대한 직원</th>
            <td>{invite.person_name ?? '이름 미상'}</td>
          </tr>
          <tr>
            <th scope="row">직원 이메일</th>
            <td>{invite.person_email ?? '미상'}</td>
          </tr>
          <tr>
            <th scope="row">조직</th>
            <td>{invite.org_name ?? '미지정'}</td>
          </tr>
          <tr>
            <th scope="row">초대 상태</th>
            <td>
              <OpsStatusBadge tone={statusTone(invite.status)}>{statusLabel(invite.status)}</OpsStatusBadge>
            </td>
          </tr>
          <tr>
            <th scope="row">초대한 사람</th>
            <td>{invite.inviter_email ?? '-'}</td>
          </tr>
          <tr>
            <th scope="row">발급 · 만료</th>
            <td>{formatAt(invite.created_at)} · {formatAt(invite.expires_at)}</td>
          </tr>
          <tr>
            <th scope="row">수락 시각</th>
            <td>{formatAt(invite.accepted_at)}</td>
          </tr>
          <tr>
            <th scope="row">연결된 계정</th>
            <td>
              {invite.linked_account_id ? (
                <>
                  {invite.linked_account_email ?? '(이메일 미상)'}
                  {invite.linked_account_duplicate && (
                    <>
                      {' '}
                      <OpsStatusBadge tone="danger">중복 연결</OpsStatusBadge>
                    </>
                  )}
                </>
              ) : (
                '아직 연결되지 않음'
              )}
            </td>
          </tr>
        </tbody>
      </table>

      <OpsSectionCard title="조치">
        {!canDiscard && !canUnlink && (
          <p className={styles.detailText}>이 초대에 지금 할 수 있는 조치가 없습니다.</p>
        )}
        <div className={styles.rowActions}>
          {canDiscard && (
            <Button variant="danger" onClick={() => setPendingAction('discard')}>이상 초대 폐기</Button>
          )}
          {canUnlink && (
            <Button variant="outline" onClick={() => setPendingAction('unlink')}>중복 직원 연결 해제</Button>
          )}
        </div>
      </OpsSectionCard>

      <Modal
        open={pendingAction !== null}
        onClose={() => (submitting ? null : setPendingAction(null))}
        title={MODAL_TITLES[pendingAction ?? 'discard']}
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
          {invite.person_name ?? '선택한'} 님의 초대 기록에 작업을 적용합니다. 초대와 연결 이력은 삭제하지 않고
          상태 변경 내역을 남깁니다.
        </p>
      </Modal>
    </div>
  );
}
