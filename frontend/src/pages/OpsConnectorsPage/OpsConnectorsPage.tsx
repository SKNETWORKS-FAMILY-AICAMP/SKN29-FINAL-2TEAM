import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Button,
  OpsDataTable,
  OpsDetailPanel,
  OpsFilterBar,
  OpsPageHeader,
  OpsSearchField,
  OpsStatusBadge,
  OpsSummaryCard,
  OpsSummaryGrid,
} from '../../components';
import type { OpsTone } from '../../components';
import { fetchConnectors } from '../../api/opsConnectors';
import type { OpsConnector } from '../../api/opsConnectors';
import { ApiError } from '../../api/client';
import { loadOpsSession } from '../../utils/opsSession';
import styles from '../OpsShared/OpsPages.module.css';

// People DB는 본인 확인용 내부 커넥터라 이 화면(외부 데이터 소스 연결 상태 점검)
// 대상이 아니다 — API 응답 자체에서 제외된다(OpsConnectorRepository.list()).
const TYPE_LABELS: Record<string, string> = {
  GOOGLE_DRIVE: '구글 드라이브',
  JIRA: 'Jira',
};

const STATUS_LABELS: Record<string, string> = {
  CONNECTED: '연결됨',
  EXPIRED: '확인 필요',
  ERROR: '오류',
};

const STATUS_TONES: Record<string, OpsTone> = {
  CONNECTED: 'success',
  EXPIRED: 'warning',
  ERROR: 'danger',
};

function typeLabel(type: string) {
  return TYPE_LABELS[type] ?? type;
}

function statusLabel(status: string) {
  return STATUS_LABELS[status] ?? status;
}

function statusTone(status: string): OpsTone {
  return STATUS_TONES[status] ?? 'neutral';
}

function formatConnectedAt(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const mm = String(date.getMonth() + 1).padStart(2, '0');
  const dd = String(date.getDate()).padStart(2, '0');
  const hh = String(date.getHours()).padStart(2, '0');
  const min = String(date.getMinutes()).padStart(2, '0');
  return `${mm}.${dd} ${hh}:${min}`;
}

export default function OpsConnectorsPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [connectors, setConnectors] = useState<OpsConnector[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('전체');
  const [statusFilter, setStatusFilter] = useState(searchParams.get('status') ?? '전체');
  const [selectedId, setSelectedId] = useState('');

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

  const selected = filtered.find((connector) => connector.conn_id === selectedId) ?? filtered[0] ?? null;

  function applyTypeFilter(type: string) {
    setTypeFilter(type);
    setStatusFilter('전체');
  }

  if (loading && !connectors) {
    return (
      <div className={styles.page}>
        <OpsPageHeader title="연결 서비스 현황" description="플랫폼에 연결된 구글 드라이브·Jira의 상태와 오류 원인을 확인합니다." />
        <p className={styles.inlineEmpty}>불러오는 중…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.page}>
        <OpsPageHeader title="연결 서비스 현황" description="플랫폼에 연결된 구글 드라이브·Jira의 상태와 오류 원인을 확인합니다." />
        <p className={styles.inlineEmpty} role="alert">{error}</p>
        <Button variant="outline" onClick={load}>다시 시도</Button>
      </div>
    );
  }

  const all = connectors ?? [];
  const countByType = (type: string) => all.filter((c) => c.connector_type === type).length;
  const countByStatus = (list: OpsConnector[], status: string) => list.filter((c) => c.auth_status === status).length;
  const summaryDetail = (list: OpsConnector[]) =>
    `정상 ${countByStatus(list, 'CONNECTED')} · 확인 필요 ${countByStatus(list, 'EXPIRED')} · 오류 ${countByStatus(list, 'ERROR')}`;

  if (all.length === 0) {
    return (
      <div className={styles.page}>
        <OpsPageHeader title="연결 서비스 현황" description="플랫폼에 연결된 구글 드라이브·Jira의 상태와 오류 원인을 확인합니다." />
        <p className={styles.inlineEmpty}>연결된 서비스가 없습니다.</p>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <OpsPageHeader
        title="연결 서비스 현황"
        description="플랫폼에 연결된 구글 드라이브·Jira의 상태와 오류 원인을 확인합니다."
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
          <option>확인 필요</option>
          <option>오류</option>
        </select>
      </OpsFilterBar>

      <OpsDataTable minWidth={1050}>
        <thead>
          <tr>
            <th>유형</th>
            <th>소유 계정</th>
            <th>연결 팀·조직</th>
            <th>상태</th>
            <th>최근 확인</th>
            <th>진단</th>
          </tr>
        </thead>
        <tbody>
          {filtered.length > 0 ? filtered.map((connector) => (
            <tr key={connector.conn_id} aria-selected={selected?.conn_id === connector.conn_id} onClick={() => setSelectedId(connector.conn_id)}>
              <td>{typeLabel(connector.connector_type)}</td>
              <td>{connector.owner_email ?? '알 수 없음'}</td>
              <td>{connector.person?.org_name ?? '-'}</td>
              <td><OpsStatusBadge tone={statusTone(connector.auth_status)}>{statusLabel(connector.auth_status)}</OpsStatusBadge></td>
              <td>{formatConnectedAt(connector.connected_at)}</td>
              <td>{connector.diagnosis}</td>
            </tr>
          )) : (
            <tr><td className={styles.emptyCell} colSpan={7}>조건에 맞는 연결 서비스가 없습니다.</td></tr>
          )}
        </tbody>
      </OpsDataTable>

      {selected ? <OpsDetailPanel title={`선택 연결 · ${typeLabel(selected.connector_type)} · ${statusLabel(selected.auth_status)}`}>
        <div className={styles.detailCards}>
          <div className={styles.detailCard}>
            <strong>연결 계정</strong>
            <p>{selected.owner_email ?? '알 수 없음'}<br />{selected.person?.org_name ?? '연결 조직 미지정'}</p>
          </div>
          <div className={styles.detailCard}>
            <strong>오류 진단</strong>
            <p>{selected.diagnosis}<br />최근 확인 {formatConnectedAt(selected.connected_at)}</p>
          </div>
          <div className={styles.detailCard}>
            <strong>다음 조치</strong>
            <p>{selected.next_action}<br />운영자는 원인과 영향만 확인</p>
          </div>
        </div>
        <p className={styles.detailText}>
          구성원 이름과 인증 원문은 표시하지 않습니다. 실제 재연결은 계정 소유자가 설정에서 진행합니다.
        </p>
      </OpsDetailPanel> : (
        <div className={styles.inlineEmpty}>검색 조건을 변경하면 연결 상세를 확인할 수 있습니다.</div>
      )}
    </div>
  );
}
