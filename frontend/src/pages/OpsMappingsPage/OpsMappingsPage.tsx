import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Button,
  OpsDataTable,
  OpsFilterBar,
  OpsPageHeader,
  OpsSearchField,
  OpsStatusBadge,
  OpsSummaryCard,
  OpsSummaryGrid,
} from '../../components';
import { fetchInvites } from '../../api/opsInvites';
import type { OpsInvite, OpsInviteStatus } from '../../api/opsInvites';
import { ApiError } from '../../api/client';
import { loadOpsSession } from '../../utils/opsSession';
import { STATUS_LABELS, statusLabel, statusTone } from '../OpsShared/inviteLabels';
import styles from '../OpsShared/OpsPages.module.css';

/**
 * 초대·연결 목록 — **「어떤 초대가 있는가」만 맡는다.**
 *
 * 조치(초대 폐기·중복 연결 해제)와 상세는 `/ops/mappings/:inviteId` 로 갈랐다.
 * 계정 관리와 같은 이유다(2026-08-13 PM).
 */
export default function OpsMappingsPage() {
  const navigate = useNavigate();
  const [invites, setInvites] = useState<OpsInvite[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [organization, setOrganization] = useState('전체');
  const [status, setStatus] = useState('전체');

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
        invite.person_name ?? '',
        invite.inviter_email ?? '',
      ].some((value) => value.toLowerCase().includes(normalized));
      const matchesOrganization = organization === '전체' || invite.org_name === organization;
      const matchesStatus = status === '전체' || statusLabel(invite.status) === status;
      return matchesQuery && matchesOrganization && matchesStatus;
    });
  }, [invites, organization, query, status]);



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
            <OpsSearchField value={query} onChange={setQuery} placeholder="직원 이름 또는 초대자 이메일 검색" />
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
                <th>초대받은 직원</th>
                <th>연결 팀·조직</th>
                <th>초대자 이메일</th>
                <th>상태</th>
                <th>계정 연결 결과</th>
                <th>작업</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length > 0 ? filtered.map((invite) => (
                <tr key={invite.invite_id} onClick={() => navigate(`/ops/mappings/${invite.invite_id}`)}>
                  <td>{invite.person_name ?? '이름 미상'}</td>
                  <td>{invite.org_name ?? '-'}</td>
                  <td>{invite.inviter_email ?? '-'}</td>
                  <td><OpsStatusBadge tone={statusTone(invite.status)}>{statusLabel(invite.status)}</OpsStatusBadge></td>
                  <td>
                    {invite.linked_account_id
                      ? `${invite.linked_account_email ?? '연결된 계정'}${invite.linked_account_duplicate ? ' · 중복 연결' : ''}`
                      : '연결 안 됨'}
                  </td>
                  <td>
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        navigate(`/ops/mappings/${invite.invite_id}`);
                      }}
                    >
                      상세 보기
                    </button>
                  </td>
                </tr>
              )) : (
                <tr><td className={styles.emptyCell} colSpan={7}>조건에 맞는 초대 기록이 없습니다.</td></tr>
              )}
            </tbody>
          </OpsDataTable>

        </>
      )}
    </div>
  );
}
