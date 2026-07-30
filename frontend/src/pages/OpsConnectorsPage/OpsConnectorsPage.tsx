import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  OpsDataTable,
  OpsDetailPanel,
  OpsFilterBar,
  OpsPageHeader,
  OpsSearchField,
  OpsStatusBadge,
  OpsSummaryCard,
  OpsSummaryGrid,
} from '../../components';
import { OPS_CONNECTORS } from '../../data/opsMockData';
import type { OpsConnector } from '../../data/opsMockData';
import styles from '../OpsShared/OpsPages.module.css';

function connectorTone(status: OpsConnector['status']) {
  if (status === '연결됨') return 'success';
  if (status === '확인 필요') return 'warning';
  return 'danger';
}

export default function OpsConnectorsPage() {
  const [searchParams] = useSearchParams();
  const [query, setQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('전체');
  const [statusFilter, setStatusFilter] = useState(searchParams.get('status') ?? '전체');
  const [selectedId, setSelectedId] = useState('연결 07');

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return OPS_CONNECTORS.filter((connector) => {
      const matchesQuery = !normalized || [connector.id, connector.owner, connector.organization]
        .some((value) => value.toLowerCase().includes(normalized));
      const matchesType = typeFilter === '전체' || connector.type === typeFilter;
      const matchesStatus = statusFilter === '전체' || connector.status === statusFilter;
      return matchesQuery && matchesType && matchesStatus;
    });
  }, [query, statusFilter, typeFilter]);

  const selected = filtered.find((connector) => connector.id === selectedId) ?? filtered[0] ?? null;

  function applyTypeFilter(type: string) {
    setTypeFilter(type);
    setStatusFilter('전체');
  }

  return (
    <div className={styles.page}>
      <OpsPageHeader
        title="연결 서비스 현황"
        description="플랫폼에 연결된 인사 정보·구글 드라이브·Jira의 상태와 오류 원인을 확인합니다."
      />

      <OpsSummaryGrid>
        <OpsSummaryCard label="전체 연결" value={31} detail="정상 26 · 확인 필요 2 · 오류 3" onClick={() => applyTypeFilter('전체')} />
        <OpsSummaryCard label="인사 정보" value={1} detail="연결 조직 범위 동기화" tone="success" onClick={() => applyTypeFilter('인사 정보')} />
        <OpsSummaryCard label="구글 드라이브" value={15} detail="정상 13 · 확인 필요 2" tone="warning" onClick={() => applyTypeFilter('구글 드라이브')} />
        <OpsSummaryCard label="Jira" value={15} detail="정상 12 · 오류 3" tone="danger" onClick={() => applyTypeFilter('Jira')} />
      </OpsSummaryGrid>

      <OpsFilterBar>
        <OpsSearchField value={query} onChange={setQuery} placeholder="계정·연결 조직 검색" />
        <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)} aria-label="연결 유형">
          <option>전체</option>
          <option>인사 정보</option>
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
            <th>연결 번호</th>
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
            <tr key={connector.id} aria-selected={selected?.id === connector.id} onClick={() => setSelectedId(connector.id)}>
              <td>{connector.id}</td>
              <td>{connector.type}</td>
              <td>{connector.owner}</td>
              <td>{connector.organization}</td>
              <td><OpsStatusBadge tone={connectorTone(connector.status)}>{connector.status}</OpsStatusBadge></td>
              <td>{connector.checkedAt}</td>
              <td>{connector.diagnosis}</td>
            </tr>
          )) : (
            <tr><td className={styles.emptyCell} colSpan={7}>조건에 맞는 연결 서비스가 없습니다.</td></tr>
          )}
        </tbody>
      </OpsDataTable>

      {selected ? <OpsDetailPanel title={`선택 연결 · ${selected.id} · ${selected.type} · ${selected.status}`}>
        <div className={styles.detailCards}>
          <div className={styles.detailCard}>
            <strong>연결 계정</strong>
            <p>{selected.owner}<br />{selected.organization}</p>
          </div>
          <div className={styles.detailCard}>
            <strong>오류 진단</strong>
            <p>{selected.diagnosis}<br />최근 확인 {selected.checkedAt}</p>
          </div>
          <div className={styles.detailCard}>
            <strong>다음 조치</strong>
            <p>{selected.nextAction}<br />운영자는 원인과 영향만 확인</p>
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
