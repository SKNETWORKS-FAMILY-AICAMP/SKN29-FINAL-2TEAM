import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
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
import { fetchConnectors } from '../../api/opsConnectors';
import type { OpsConnector } from '../../api/opsConnectors';
import { ApiError } from '../../api/client';
import { loadOpsSession } from '../../utils/opsSession';
import { formatConnectedAt, statusLabel, statusTone, typeLabel } from '../OpsShared/connectorLabels';
import styles from '../OpsShared/OpsPages.module.css';

/**
 * 연결 서비스 목록 — **「무엇이 연결돼 있는가」만 맡는다.**
 *
 * 조치(강제 해제)가 생기면서 상세를 `/ops/connectors/:connId` 로 갈랐다. 계정·
 * 초대·팀과 같은 규칙이다(2026-08-13 PM).
 */
export default function OpsConnectorsPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [connectors, setConnectors] = useState<OpsConnector[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('전체');
  const [statusFilter, setStatusFilter] = useState(searchParams.get('status') ?? '전체');

  async function load() {
    const session = loadOpsSession();
    if (!session) {
      navigate('/ops/login', { replace: true });
      return;
    }

    setLoading(true);
    setError('');
    try {
      setConnectors(await fetchConnectors(session.token));
    } catch (thrown) {
      if (thrown instanceof ApiError && thrown.status === 401) {
        navigate('/ops/login', { replace: true });
        return;
      }
      setError(thrown instanceof ApiError ? thrown.message : '연결 서비스 현황을 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filtered = useMemo(() => {
    const all = connectors ?? [];
    const normalized = query.trim().toLowerCase();
    return all.filter((connector) => {
      const matchesQuery = !normalized || [
        connector.owner_email ?? '',
        connector.person?.org_name ?? '',
      ].some((value) => value.toLowerCase().includes(normalized));
      const matchesType = typeFilter === '전체' || typeLabel(connector.connector_type) === typeFilter;
      const matchesStatus = statusFilter === '전체' || statusLabel(connector.auth_status) === statusFilter;
      return matchesQuery && matchesType && matchesStatus;
    });
  }, [connectors, query, statusFilter, typeFilter]);

  function applyTypeFilter(type: string) {
    setTypeFilter(type);
    setStatusFilter('전체');
  }

  if (loading && !connectors) {
    return (
      <div className={styles.page}>
        <OpsPageHeader title="연결 서비스 현황" />
        <p className={styles.inlineEmpty}>불러오는 중…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.page}>
        <OpsPageHeader title="연결 서비스 현황" />
        <p className={styles.inlineEmpty} role="alert">{error}</p>
        <Button variant="outline" onClick={load}>다시 시도</Button>
      </div>
    );
  }

  const all = connectors ?? [];
  const countByType = (type: string) => all.filter((c) => c.connector_type === type).length;
  const countByStatus = (list: OpsConnector[], status: string) => list.filter((c) => c.auth_status === status).length;
  const summaryDetail = (list: OpsConnector[]) =>
    `연결 ${countByStatus(list, 'CONNECTED')} · 만료 ${countByStatus(list, 'EXPIRED')} · 오류 ${countByStatus(list, 'ERROR')} · 해제 ${countByStatus(list, 'REVOKED')}`;

  if (all.length === 0) {
    return (
      <div className={styles.page}>
        <OpsPageHeader title="연결 서비스 현황" />
        <div className={styles.pageEmptyState}>연결된 서비스가 없습니다.</div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <OpsPageHeader
        title="연결 서비스 현황"
      />

      <OpsSummaryGrid>
        <OpsSummaryCard label="전체 연결" value={all.length} detail={summaryDetail(all)} onClick={() => applyTypeFilter('전체')} />
        <OpsSummaryCard
          label="구글 드라이브"
          value={countByType('GOOGLE_DRIVE')}
          detail={summaryDetail(all.filter((c) => c.connector_type === 'GOOGLE_DRIVE'))}
          onClick={() => applyTypeFilter('구글 드라이브')}
        />
        <OpsSummaryCard
          label="Jira"
          value={countByType('JIRA')}
          detail={summaryDetail(all.filter((c) => c.connector_type === 'JIRA'))}
          onClick={() => applyTypeFilter('Jira')}
        />
      </OpsSummaryGrid>

      <OpsFilterBar>
        <OpsSearchField value={query} onChange={setQuery} placeholder="계정·연결 조직 검색" />
        <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)} aria-label="연결 유형">
          <option>전체</option>
          <option>구글 드라이브</option>
          <option>Jira</option>
        </select>
        <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} aria-label="연결 상태">
          <option>전체</option>
          <option>연결됨</option>
          <option>만료됨</option>
          <option>오류</option>
          <option>해제됨</option>
        </select>
      </OpsFilterBar>

      <OpsDataTable minWidth={1050}>
        <thead>
          <tr>
            <th>유형</th>
            <th>소유 계정</th>
            <th>연결 팀·조직</th>
            <th>상태</th>
            <th>연결 시각</th>
            <th>진단</th>
            <th>작업</th>
          </tr>
        </thead>
        <tbody>
          {filtered.length > 0 ? filtered.map((connector) => (
            <tr key={connector.conn_id} onClick={() => navigate(`/ops/connectors/${connector.conn_id}`)}>
              <td>{typeLabel(connector.connector_type)}</td>
              <td>{connector.owner_email ?? '알 수 없음'}</td>
              <td>{connector.person?.org_name ?? '-'}</td>
              <td><OpsStatusBadge tone={statusTone(connector.auth_status)}>{statusLabel(connector.auth_status)}</OpsStatusBadge></td>
              <td>{formatConnectedAt(connector.connected_at)}</td>
              <td className={styles.cellEllipsis} title={connector.diagnosis}>{connector.diagnosis}</td>
              <td>
                {/* `data-button` — 운영자 표는 안에 든 버튼의 테두리를 벗겨 글씨처럼
                    만든다(`OpsUi.module.css`). 「상세 보기」는 **눌러서 다른 화면으로
                    가는 것**이라 눌리는 것처럼 보여야 한다(2026-08-19 PM). */}
                <button
                  data-button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    navigate(`/ops/connectors/${connector.conn_id}`);
                  }}
                >
                  상세 보기
                </button>
              </td>
            </tr>
          )) : (
            <tr><td className={styles.emptyCell} colSpan={7}>조건에 맞는 연결 서비스가 없습니다.</td></tr>
          )}
        </tbody>
      </OpsDataTable>
    </div>
  );
}
