import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Button, Modal, OpsPageHeader, OpsSectionCard, OpsStatusBadge, useToast } from '../../components';
import { fetchConnector, revokeConnector } from '../../api/opsConnectors';
import type { OpsConnector } from '../../api/opsConnectors';
import { ApiError } from '../../api/client';
import { loadOpsSession } from '../../utils/opsSession';
import { formatConnectedAt, sourceNoun, statusLabel, statusTone, typeLabel } from '../OpsShared/connectorLabels';
import styles from '../OpsShared/OpsPages.module.css';

/**
 * 연결 상세 — **끊을 수 있는 유일한 자리.**
 *
 * 이 화면은 오래 읽기 전용이었고, 그래서 목록 아래 패널로 충분했다. 조치가
 * 생기면서 나머지 네 화면과 같은 모양으로 옮긴다(2026-08-13 PM).
 *
 * 토큰 원문은 여기서도 안 보여준다. 끊는 것과 보는 것은 다른 권한이다.
 */
export default function OpsConnectorDetailPage() {
  const navigate = useNavigate();
  const { connId } = useParams();
  const { showToast } = useToast();

  const [connector, setConnector] = useState<OpsConnector | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [revokeOpen, setRevokeOpen] = useState(false);
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    const session = loadOpsSession();
    if (!session || !connId) {
      navigate('/ops/login', { replace: true });
      return;
    }
    setLoading(true);
    setError('');
    try {
      setConnector(await fetchConnector(session.token, connId));
    } catch (thrown) {
      if (thrown instanceof ApiError && thrown.status === 401) {
        navigate('/ops/login', { replace: true });
        return;
      }
      setError(thrown instanceof ApiError ? thrown.message : '연결을 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }, [connId, navigate]);

  useEffect(() => {
    void load();
  }, [load]);

  async function confirmRevoke() {
    const session = loadOpsSession();
    if (!session || !connector || submitting) return;
    setSubmitting(true);
    try {
      const result = await revokeConnector(session.token, connector.conn_id, reason.trim());
      // 끊은 것으로 끝이 아니다 — 무엇이 같이 섰는지 함께 말한다.
      showToast(
        result.affected_sources > 0
          ? `연결을 해제했습니다. ${sourceNoun(result.connector_type)} ${result.affected_sources}건이 함께 멈춥니다.`
          : '연결을 해제했습니다.',
        'success',
      );
      setRevokeOpen(false);
      setReason('');
      await load();
    } catch (thrown) {
      if (thrown instanceof ApiError && thrown.status === 401) {
        navigate('/ops/login', { replace: true });
        return;
      }
      showToast(thrown instanceof ApiError ? thrown.message : '해제하지 못했습니다.', 'error');
    } finally {
      setSubmitting(false);
    }
  }

  const header = (
    <OpsPageHeader
      title="연결 상세"
      actions={(
        <Button variant="secondary" onClick={() => navigate('/ops/connectors')}>연결 목록으로</Button>
      )}
    />
  );

  if (loading && !connector) {
    return (
      <div className={styles.page}>
        {header}
        <p className={styles.inlineEmpty}>불러오는 중…</p>
      </div>
    );
  }

  if (error || !connector) {
    return (
      <div className={styles.page}>
        {header}
        <p className={styles.inlineEmpty} role="alert">{error || '연결을 찾을 수 없습니다.'}</p>
        <Button variant="outline" onClick={load}>다시 시도</Button>
      </div>
    );
  }

  const revoked = connector.auth_status === 'REVOKED';

  return (
    <div className={styles.page}>
      {header}

      <table className={styles.detailTable}>
        <tbody>
          <tr>
            <th scope="row">유형</th>
            <td>{typeLabel(connector.connector_type)}</td>
          </tr>
          <tr>
            <th scope="row">상태</th>
            <td>
              <OpsStatusBadge tone={statusTone(connector.auth_status)}>
                {statusLabel(connector.auth_status)}
              </OpsStatusBadge>
            </td>
          </tr>
          <tr>
            <th scope="row">소유 계정</th>
            <td>{connector.owner_email ?? '알 수 없음'}</td>
          </tr>
          <tr>
            <th scope="row">연결 조직</th>
            <td>{connector.person?.org_name ?? '미지정'}</td>
          </tr>
          <tr>
            <th scope="row">최근 확인</th>
            <td>{formatConnectedAt(connector.connected_at)}</td>
          </tr>
          <tr>
            <th scope="row">진단</th>
            <td>{connector.diagnosis}</td>
          </tr>
          <tr>
            <th scope="row">다음 조치</th>
            <td>{connector.next_action}</td>
          </tr>
        </tbody>
      </table>

      <OpsSectionCard title="조치">
        {revoked ? (
          <p className={styles.detailText}>
            이미 해제된 연결입니다. 다시 연결하는 것은 계정 소유자가 설정 화면에서 합니다.
          </p>
        ) : (
          <div className={styles.rowActions}>
            <Button variant="danger" onClick={() => setRevokeOpen(true)}>연결 강제 해제</Button>
          </div>
        )}
      </OpsSectionCard>

      <Modal
        open={revokeOpen}
        onClose={() => (submitting ? null : setRevokeOpen(false))}
        title="연결 강제 해제"
        footer={(
          <>
            <Button variant="secondary" onClick={() => setRevokeOpen(false)} disabled={submitting}>취소</Button>
            <Button variant="danger" onClick={confirmRevoke} disabled={submitting}>
              {submitting ? '해제하는 중…' : '해제하기'}
            </Button>
          </>
        )}
      >
        {/* **무엇이 멈추는지 먼저 말한다.** 끊는 것은 한 번에 되지만 그 팀의 문서
            수집이나 Jira 동기화가 같이 선다. */}
        <p className={styles.modalCopy}>
          {connector.owner_email ?? '이 계정'}의 {typeLabel(connector.connector_type)} 연결을 끊습니다.
          저장된 인증 정보를 삭제하므로 이 연결로 읽던 것이 멈추고, 계정 소유자가 설정에서 다시 연결해야
          복구됩니다. 폴더·프로젝트 선택은 삭제하지 않습니다.
        </p>
        <div className={styles.fieldGroup}>
          <label htmlFor="revoke-reason">사유 (선택)</label>
          <textarea
            id="revoke-reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="예: 토큰 유출 의심"
          />
        </div>
      </Modal>
    </div>
  );
}
