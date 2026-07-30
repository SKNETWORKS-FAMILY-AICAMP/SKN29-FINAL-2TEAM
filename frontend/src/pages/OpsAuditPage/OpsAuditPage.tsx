import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Button,
  OpsDataTable,
  OpsDetailPanel,
  OpsFilterBar,
  OpsPageHeader,
  OpsSearchField,
  OpsStatusBadge,
} from '../../components';
import type { OpsTone } from '../../components';
import {
  fetchAssignmentRuns,
  fetchDecisions,
  fetchOperationLogs,
  fetchRecommendations,
  fetchValidations,
} from '../../api/opsAudit';
import type {
  OpsAssignmentRun,
  OpsDecision,
  OpsOperationLog,
  OpsRecommendation,
  OpsValidation,
} from '../../api/opsAudit';
import { ApiError } from '../../api/client';
import { actionLabel } from '../../utils/auditActions';
import { loadOpsSession } from '../../utils/opsSession';
import { timeAgo } from '../../utils/relativeTime';
import styles from '../OpsShared/OpsPages.module.css';

type AuditView = 'operations' | 'analysis';
type AnalysisTab = 'assignment' | 'recommendation' | 'validation' | 'decision';

const ANALYSIS_TAB_LABELS: Record<AnalysisTab, string> = {
  assignment: '배정 실행',
  recommendation: '추천 결과',
  validation: '검증 결과',
  decision: '결정 기록',
};

const PM_ACTION_LABELS: Record<string, string> = {
  APPROVE: '승인',
  MODIFY: '수정',
  REJECT: '반려',
};

const PM_ACTION_TONES: Record<string, OpsTone> = {
  APPROVE: 'success',
  MODIFY: 'warning',
  REJECT: 'danger',
};

function pmActionLabel(action: string) {
  return PM_ACTION_LABELS[action] ?? action;
}

function pmActionTone(action: string): OpsTone {
  return PM_ACTION_TONES[action] ?? 'neutral';
}

function statusTone(status: string): OpsTone {
  if (status === 'RUNNING') return 'info';
  if (status === 'PASS' || status === 'CONFIRMED' || status === 'COMPLETED') return 'success';
  if (status === 'CONDITIONAL_PASS' || status === 'PARTIAL') return 'warning';
  if (status === 'REJECT' || status === 'BLOCKED') return 'danger';
  return 'neutral';
}

function hasContent(value: unknown): boolean {
  if (value === null || value === undefined) return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === 'object') return Object.keys(value).length > 0;
  return true;
}

function formatConfidence(value: number | null): string {
  return value === null ? '-' : value.toFixed(2);
}

function csvCell(value: string) {
  return `"${value.replaceAll('"', '""')}"`;
}

function downloadCsv(filename: string, headers: string[], rows: string[][]) {
  const body = rows.map((row) => row.map(csvCell).join(',')).join('\n');
  const blob = new Blob([`﻿${headers.map(csvCell).join(',')}\n${body}`], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

/** 탭을 처음 열 때만 불러오고, 이후에는 다시 불러오지 않는(reload 호출 전까지) 지연 로딩 훅. */
function useLazyList<T>(
  fetcher: (token: string) => Promise<T[]>,
  active: boolean,
  onUnauthorized: () => void,
) {
  const [data, setData] = useState<T[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!active || data !== null) return;
    const session = loadOpsSession();
    if (!session) {
      onUnauthorized();
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError('');
    fetcher(session.token)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((thrown: unknown) => {
        if (cancelled) return;
        if (thrown instanceof ApiError && thrown.status === 401) {
          onUnauthorized();
          return;
        }
        setError(thrown instanceof ApiError ? thrown.message : '데이터를 불러오지 못했습니다.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, data]);

  return { data, loading, error, reload: () => setData(null) };
}

interface PanelShellProps {
  loading: boolean;
  error: string;
  reload: () => void;
  isEmpty: boolean;
  emptyText: string;
  children: React.ReactNode;
}

function PanelShell({ loading, error, reload, isEmpty, emptyText, children }: PanelShellProps) {
  if (loading) return <p className={styles.inlineEmpty}>불러오는 중…</p>;
  if (error) {
    return (
      <>
        <p className={styles.inlineEmpty} role="alert">{error}</p>
        <Button variant="outline" onClick={reload}>다시 시도</Button>
      </>
    );
  }
  if (isEmpty) return <p className={styles.inlineEmpty}>{emptyText}</p>;
  return <>{children}</>;
}

function OperationsPanel({
  loading, error, reload, allCount, actions, query, setQuery, statusFilter, setStatusFilter, rows, selectedId, onSelect,
}: {
  loading: boolean; error: string; reload: () => void; allCount: number; actions: string[];
  query: string; setQuery: (v: string) => void; statusFilter: string; setStatusFilter: (v: string) => void;
  rows: OpsOperationLog[]; selectedId: string | undefined; onSelect: (id: string) => void;
}) {
  const selected = rows.find((r) => r.audit_id === selectedId) ?? rows[0] ?? null;

  function exportRows() {
    downloadCsv(
      '감사로그_운영활동.csv',
      ['기록ID', '시각', '수행자', '작업', '대상'],
      rows.map((r) => [r.audit_id, r.occurred_at, r.actor_display_name ?? r.actor_email ?? r.actor_account_id,
        actionLabel(r.action), [r.target_type, r.target_id].filter(Boolean).join(' · ')]),
    );
  }

  return (
    <PanelShell loading={loading} error={error} reload={reload} isEmpty={allCount === 0} emptyText="운영 활동 기록이 없습니다.">
      <OpsFilterBar>
        <OpsSearchField value={query} onChange={setQuery} placeholder="기록 ID·수행자·대상 검색" />
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} aria-label="작업 종류">
          <option>전체</option>
          {actions.map((a) => <option key={a}>{a}</option>)}
        </select>
        <Button variant="outline" onClick={exportRows}>현재 목록 내보내기</Button>
      </OpsFilterBar>
      <p className={styles.resultSummary}>현재 {rows.length}건 표시 · 전체 기록 {allCount}건</p>
      <OpsDataTable minWidth={1100}>
        <thead>
          <tr><th>기록 ID</th><th>시각</th><th>수행자</th><th>작업</th><th>대상</th></tr>
        </thead>
        <tbody>
          {rows.length > 0 ? rows.map((row) => (
            <tr key={row.audit_id} aria-selected={selected?.audit_id === row.audit_id} onClick={() => onSelect(row.audit_id)}>
              <td>{row.audit_id}</td>
              <td>{timeAgo(row.occurred_at)}</td>
              <td>{row.actor_display_name ?? row.actor_email ?? row.actor_account_id}</td>
              <td>{actionLabel(row.action)}</td>
              <td>{[row.target_type, row.target_id].filter(Boolean).join(' · ') || '-'}</td>
            </tr>
          )) : <tr><td className={styles.emptyCell} colSpan={5}>조건에 맞는 기록이 없습니다.</td></tr>}
        </tbody>
      </OpsDataTable>
      {selected ? (
        <OpsDetailPanel title={`선택 운영 활동 · ${selected.audit_id} · ${actionLabel(selected.action)}`}>
          <p className={styles.detailText}>
            수행자 {selected.actor_display_name ?? selected.actor_email ?? selected.actor_account_id} ·
            {' '}{new Date(selected.occurred_at).toLocaleString('ko-KR')}
          </p>
          {selected.proj_id && <p className={styles.detailText}>프로젝트 {selected.proj_id}</p>}
          <p className={styles.detailText}>
            {hasContent(selected.payload) ? JSON.stringify(selected.payload) : '추가 정보 없음'}
          </p>
        </OpsDetailPanel>
      ) : <div className={styles.inlineEmpty}>검색 조건을 변경하면 기록 상세를 확인할 수 있습니다.</div>}
    </PanelShell>
  );
}

function AssignmentRunsPanel({
  loading, error, reload, allCount, query, setQuery, statusFilter, setStatusFilter, rows, selectedId, onSelect,
}: {
  loading: boolean; error: string; reload: () => void; allCount: number;
  query: string; setQuery: (v: string) => void; statusFilter: string; setStatusFilter: (v: string) => void;
  rows: OpsAssignmentRun[]; selectedId: string | undefined; onSelect: (id: string) => void;
}) {
  const selected = rows.find((r) => r.run_id === selectedId) ?? rows[0] ?? null;
  const statuses = [...new Set(rows.map((r) => r.status))];

  return (
    <PanelShell
      loading={loading} error={error} reload={reload} isEmpty={allCount === 0}
      emptyText="아직 실행된 배정이 없습니다. 업무 분배 기능에서 배정을 실행하면 여기에 기록됩니다."
    >
      <OpsFilterBar>
        <OpsSearchField value={query} onChange={setQuery} placeholder="실행 ID·스냅샷 ID·요청자 검색" />
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} aria-label="상태">
          <option>전체</option>
          {statuses.map((s) => <option key={s}>{s}</option>)}
        </select>
      </OpsFilterBar>
      <p className={styles.resultSummary}>현재 {rows.length}건 표시 · 전체 기록 {allCount}건</p>
      <OpsDataTable minWidth={1100}>
        <thead>
          <tr><th>실행 ID</th><th>스냅샷 ID</th><th>준비도 결과</th><th>모델 버전</th><th>정책 버전</th><th>요청자</th><th>상태</th></tr>
        </thead>
        <tbody>
          {rows.length > 0 ? rows.map((row) => (
            <tr key={row.run_id} aria-selected={selected?.run_id === row.run_id} onClick={() => onSelect(row.run_id)}>
              <td>{row.run_id}</td>
              <td>{row.snapshot_id}</td>
              <td>{row.readiness_id ?? '-'}</td>
              <td>{row.model_version ?? '-'}</td>
              <td>{row.policy_version ?? '-'}</td>
              <td>{row.requester_display_name ?? row.requester_email ?? row.requested_by ?? '-'}</td>
              <td><OpsStatusBadge tone={statusTone(row.status)}>{row.status}</OpsStatusBadge></td>
            </tr>
          )) : <tr><td className={styles.emptyCell} colSpan={7}>조건에 맞는 기록이 없습니다.</td></tr>}
        </tbody>
      </OpsDataTable>
      {selected ? (
        <OpsDetailPanel title={`선택 배정 실행 · ${selected.run_id} · ${selected.status}`}>
          <p className={styles.detailText}>
            스냅샷 {selected.snapshot_id}{selected.proj_id ? ` · 프로젝트 ${selected.proj_id}` : ''} · 준비도 결과 {selected.readiness_id ?? '없음'}
          </p>
          <p className={styles.detailText}>
            모델 버전 {selected.model_version ?? '-'} · 정책 버전 {selected.policy_version ?? '-'} ·
            요청자 {selected.requester_display_name ?? selected.requester_email ?? selected.requested_by ?? '-'}
          </p>
        </OpsDetailPanel>
      ) : <div className={styles.inlineEmpty}>검색 조건을 변경하면 실행 상세를 확인할 수 있습니다.</div>}
    </PanelShell>
  );
}

function RecommendationsPanel({
  loading, error, reload, allCount, query, setQuery, statusFilter, setStatusFilter, rows, selectedId, onSelect,
}: {
  loading: boolean; error: string; reload: () => void; allCount: number;
  query: string; setQuery: (v: string) => void; statusFilter: string; setStatusFilter: (v: string) => void;
  rows: OpsRecommendation[]; selectedId: string | undefined; onSelect: (id: string) => void;
}) {
  const selected = rows.find((r) => r.reco_id === selectedId) ?? rows[0] ?? null;
  const statuses = [...new Set(rows.map((r) => r.status))];

  return (
    <PanelShell
      loading={loading} error={error} reload={reload} isEmpty={allCount === 0}
      emptyText="아직 생성된 추천 결과가 없습니다. 업무 추천 기능이 실행되면 여기에 기록됩니다."
    >
      <OpsFilterBar>
        <OpsSearchField value={query} onChange={setQuery} placeholder="추천 ID·실행 ID·업무 ID 검색" />
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} aria-label="상태">
          <option>전체</option>
          {statuses.map((s) => <option key={s}>{s}</option>)}
        </select>
      </OpsFilterBar>
      <p className={styles.resultSummary}>현재 {rows.length}건 표시 · 전체 기록 {allCount}건</p>
      <OpsDataTable minWidth={1100}>
        <thead>
          <tr><th>추천 ID</th><th>실행 ID</th><th>업무</th><th>신뢰도</th><th>누락 데이터</th><th>제한·가정</th><th>상태</th></tr>
        </thead>
        <tbody>
          {rows.length > 0 ? rows.map((row) => (
            <tr key={row.reco_id} aria-selected={selected?.reco_id === row.reco_id} onClick={() => onSelect(row.reco_id)}>
              <td>{row.reco_id}</td>
              <td>{row.run_id}</td>
              <td>{row.task_name ?? row.task_id}</td>
              <td>{formatConfidence(row.confidence)}</td>
              <td>{hasContent(row.missing_data) ? '있음' : '없음'}</td>
              <td>{hasContent(row.limitations) || hasContent(row.assumptions) ? '있음' : '없음'}</td>
              <td><OpsStatusBadge tone={statusTone(row.status)}>{row.status}</OpsStatusBadge></td>
            </tr>
          )) : <tr><td className={styles.emptyCell} colSpan={7}>조건에 맞는 기록이 없습니다.</td></tr>}
        </tbody>
      </OpsDataTable>
      {selected ? (
        <OpsDetailPanel title={`선택 추천 결과 · ${selected.reco_id} · ${selected.status}`}>
          <p className={styles.detailText}>
            배정 실행 {selected.run_id} · 업무 {selected.task_name ?? selected.task_id} · 신뢰도 {formatConfidence(selected.confidence)}
          </p>
          <p className={styles.detailText}>
            누락 데이터 {hasContent(selected.missing_data) ? JSON.stringify(selected.missing_data) : '없음'}
          </p>
          <p className={styles.detailText}>
            제한사항 {hasContent(selected.limitations) ? JSON.stringify(selected.limitations) : '없음'} ·
            가정 {hasContent(selected.assumptions) ? JSON.stringify(selected.assumptions) : '없음'}
          </p>
        </OpsDetailPanel>
      ) : <div className={styles.inlineEmpty}>검색 조건을 변경하면 추천 상세를 확인할 수 있습니다.</div>}
    </PanelShell>
  );
}

function ValidationsPanel({
  loading, error, reload, allCount, query, setQuery, statusFilter, setStatusFilter, rows, selectedId, onSelect,
}: {
  loading: boolean; error: string; reload: () => void; allCount: number;
  query: string; setQuery: (v: string) => void; statusFilter: string; setStatusFilter: (v: string) => void;
  rows: OpsValidation[]; selectedId: string | undefined; onSelect: (id: string) => void;
}) {
  const selected = rows.find((r) => r.valid_id === selectedId) ?? rows[0] ?? null;
  const statuses = [...new Set(rows.map((r) => r.status))];

  return (
    <PanelShell
      loading={loading} error={error} reload={reload} isEmpty={allCount === 0}
      emptyText="아직 생성된 검증 결과가 없습니다. 추천 결과가 생기면 여기에 기록됩니다."
    >
      <OpsFilterBar>
        <OpsSearchField value={query} onChange={setQuery} placeholder="검증 ID·추천 ID 검색" />
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} aria-label="상태">
          <option>전체</option>
          {statuses.map((s) => <option key={s}>{s}</option>)}
        </select>
      </OpsFilterBar>
      <p className={styles.resultSummary}>현재 {rows.length}건 표시 · 전체 기록 {allCount}건</p>
      <OpsDataTable minWidth={1000}>
        <thead>
          <tr><th>검증 ID</th><th>추천 ID</th><th>실행 ID</th><th>업무 ID</th><th>신뢰도</th><th>누락 데이터</th><th>상태</th></tr>
        </thead>
        <tbody>
          {rows.length > 0 ? rows.map((row) => (
            <tr key={row.valid_id} aria-selected={selected?.valid_id === row.valid_id} onClick={() => onSelect(row.valid_id)}>
              <td>{row.valid_id}</td>
              <td>{row.reco_id}</td>
              <td>{row.run_id ?? '-'}</td>
              <td>{row.task_id ?? '-'}</td>
              <td>{formatConfidence(row.confidence)}</td>
              <td>{hasContent(row.missing_data) ? '있음' : '없음'}</td>
              <td><OpsStatusBadge tone={statusTone(row.status)}>{row.status}</OpsStatusBadge></td>
            </tr>
          )) : <tr><td className={styles.emptyCell} colSpan={7}>조건에 맞는 기록이 없습니다.</td></tr>}
        </tbody>
      </OpsDataTable>
      {selected ? (
        <OpsDetailPanel title={`선택 검증 결과 · ${selected.valid_id} · ${selected.status}`}>
          <p className={styles.detailText}>
            추천 결과 {selected.reco_id} · 신뢰도 {formatConfidence(selected.confidence)}
          </p>
          <p className={styles.detailText}>
            누락 데이터 {hasContent(selected.missing_data) ? JSON.stringify(selected.missing_data) : '없음'}
          </p>
        </OpsDetailPanel>
      ) : <div className={styles.inlineEmpty}>검색 조건을 변경하면 검증 상세를 확인할 수 있습니다.</div>}
    </PanelShell>
  );
}

function DecisionsPanel({
  loading, error, reload, allCount, query, setQuery, statusFilter, setStatusFilter, rows, selectedId, onSelect,
}: {
  loading: boolean; error: string; reload: () => void; allCount: number;
  query: string; setQuery: (v: string) => void; statusFilter: string; setStatusFilter: (v: string) => void;
  rows: OpsDecision[]; selectedId: string | undefined; onSelect: (id: string) => void;
}) {
  const selected = rows.find((r) => r.decision_id === selectedId) ?? rows[0] ?? null;
  const actions = [...new Set(rows.map((r) => r.pm_action))];

  return (
    <PanelShell
      loading={loading} error={error} reload={reload} isEmpty={allCount === 0}
      emptyText="아직 저장된 PM 결정이 없습니다. 검증 결과가 생기면 여기에 기록됩니다."
    >
      <OpsFilterBar>
        <OpsSearchField value={query} onChange={setQuery} placeholder="결정 ID·추천 ID·검증 ID 검색" />
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} aria-label="조치">
          <option>전체</option>
          {actions.map((a) => <option key={a}>{a}</option>)}
        </select>
      </OpsFilterBar>
      <p className={styles.resultSummary}>현재 {rows.length}건 표시 · 전체 기록 {allCount}건</p>
      <OpsDataTable minWidth={1100}>
        <thead>
          <tr><th>결정 ID</th><th>추천 ID</th><th>검증 ID</th><th>수정 후보</th><th>결정자</th><th>결정 시각</th><th>조치</th></tr>
        </thead>
        <tbody>
          {rows.length > 0 ? rows.map((row) => (
            <tr key={row.decision_id} aria-selected={selected?.decision_id === row.decision_id} onClick={() => onSelect(row.decision_id)}>
              <td>{row.decision_id}</td>
              <td>{row.reco_id}</td>
              <td>{row.valid_id ?? '-'}</td>
              <td>{row.modified_cand_id ?? '없음'}</td>
              <td>{row.decider_display_name ?? row.decider_email ?? row.decided_by ?? '-'}</td>
              <td>{new Date(row.decided_at).toLocaleString('ko-KR')}</td>
              <td><OpsStatusBadge tone={pmActionTone(row.pm_action)}>{pmActionLabel(row.pm_action)}</OpsStatusBadge></td>
            </tr>
          )) : <tr><td className={styles.emptyCell} colSpan={7}>조건에 맞는 기록이 없습니다.</td></tr>}
        </tbody>
      </OpsDataTable>
      {selected ? (
        <OpsDetailPanel title={`선택 PM 결정 · ${selected.decision_id} · ${pmActionLabel(selected.pm_action)}`}>
          <p className={styles.detailText}>
            추천 결과 {selected.reco_id} · 검증 결과 {selected.valid_id ?? '없음'} · 수정 후보 {selected.modified_cand_id ?? '없음'}
          </p>
          <p className={styles.detailText}>
            결정자 {selected.decider_display_name ?? selected.decider_email ?? selected.decided_by ?? '-'} ·
            결정 시각 {new Date(selected.decided_at).toLocaleString('ko-KR')}
          </p>
          {selected.reason && <p className={styles.detailText}>사유 {selected.reason}</p>}
        </OpsDetailPanel>
      ) : <div className={styles.inlineEmpty}>검색 조건을 변경하면 결정 상세를 확인할 수 있습니다.</div>}
    </PanelShell>
  );
}

export default function OpsAuditPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialView: AuditView = searchParams.get('view') === 'analysis' ? 'analysis' : 'operations';
  const initialTabParam = searchParams.get('tab');
  const initialTab: AnalysisTab = initialTabParam && initialTabParam in ANALYSIS_TAB_LABELS
    ? (initialTabParam as AnalysisTab)
    : 'assignment';

  const [activeView, setActiveView] = useState<AuditView>(initialView);
  const [activeTab, setActiveTab] = useState<AnalysisTab>(initialTab);
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('전체');
  const [selectedId, setSelectedId] = useState<Record<string, string>>({});

  const onUnauthorized = useCallback(() => navigate('/ops/login', { replace: true }), [navigate]);

  const operations = useLazyList<OpsOperationLog>(fetchOperationLogs, activeView === 'operations', onUnauthorized);
  const assignmentRuns = useLazyList<OpsAssignmentRun>(
    fetchAssignmentRuns, activeView === 'analysis' && activeTab === 'assignment', onUnauthorized,
  );
  const recommendations = useLazyList<OpsRecommendation>(
    fetchRecommendations, activeView === 'analysis' && activeTab === 'recommendation', onUnauthorized,
  );
  const validations = useLazyList<OpsValidation>(
    fetchValidations, activeView === 'analysis' && activeTab === 'validation', onUnauthorized,
  );
  const decisions = useLazyList<OpsDecision>(
    fetchDecisions, activeView === 'analysis' && activeTab === 'decision', onUnauthorized,
  );

  const dataKey = activeView === 'operations' ? 'operations' : activeTab;

  function resetFilters() {
    setQuery('');
    setStatusFilter('전체');
  }

  function changeView(view: AuditView) {
    setActiveView(view);
    resetFilters();
    setSearchParams(view === 'operations' ? { view: 'operations' } : { view: 'analysis', tab: activeTab });
  }

  function changeTab(tab: AnalysisTab) {
    setActiveTab(tab);
    resetFilters();
    setSearchParams({ view: 'analysis', tab });
  }

  const operationActions = useMemo(() => {
    if (!operations.data) return [];
    return [...new Set(operations.data.map((row) => row.action))];
  }, [operations.data]);

  const filteredOperations = useMemo(() => {
    const all = operations.data ?? [];
    const normalized = query.trim().toLowerCase();
    return all.filter((row) => {
      const matchesQuery = !normalized || [
        row.audit_id,
        row.actor_display_name ?? '',
        row.actor_email ?? '',
        row.target_type ?? '',
        row.target_id ?? '',
      ].some((value) => value.toLowerCase().includes(normalized));
      const matchesAction = statusFilter === '전체' || row.action === statusFilter;
      return matchesQuery && matchesAction;
    });
  }, [operations.data, query, statusFilter]);

  const filteredAssignmentRuns = useMemo(() => {
    const all = assignmentRuns.data ?? [];
    const normalized = query.trim().toLowerCase();
    return all.filter((row) => {
      const matchesQuery = !normalized || [row.run_id, row.snapshot_id, row.requester_email ?? '']
        .some((value) => value.toLowerCase().includes(normalized));
      const matchesStatus = statusFilter === '전체' || row.status === statusFilter;
      return matchesQuery && matchesStatus;
    });
  }, [assignmentRuns.data, query, statusFilter]);

  const filteredRecommendations = useMemo(() => {
    const all = recommendations.data ?? [];
    const normalized = query.trim().toLowerCase();
    return all.filter((row) => {
      const matchesQuery = !normalized || [row.reco_id, row.run_id, row.task_id]
        .some((value) => value.toLowerCase().includes(normalized));
      const matchesStatus = statusFilter === '전체' || row.status === statusFilter;
      return matchesQuery && matchesStatus;
    });
  }, [recommendations.data, query, statusFilter]);

  const filteredValidations = useMemo(() => {
    const all = validations.data ?? [];
    const normalized = query.trim().toLowerCase();
    return all.filter((row) => {
      const matchesQuery = !normalized || [row.valid_id, row.reco_id]
        .some((value) => value.toLowerCase().includes(normalized));
      const matchesStatus = statusFilter === '전체' || row.status === statusFilter;
      return matchesQuery && matchesStatus;
    });
  }, [validations.data, query, statusFilter]);

  const filteredDecisions = useMemo(() => {
    const all = decisions.data ?? [];
    const normalized = query.trim().toLowerCase();
    return all.filter((row) => {
      const matchesQuery = !normalized || [row.decision_id, row.reco_id, row.valid_id ?? '']
        .some((value) => value.toLowerCase().includes(normalized));
      const matchesStatus = statusFilter === '전체' || row.pm_action === statusFilter;
      return matchesQuery && matchesStatus;
    });
  }, [decisions.data, query, statusFilter]);

  function selectRow(id: string) {
    setSelectedId((prev) => ({ ...prev, [dataKey]: id }));
  }

  return (
    <div className={styles.page}>
      <OpsPageHeader
        title="감사 로그"
        description="운영자의 조치 이력과 분석·결정 과정의 저장 결과를 조회합니다. 모든 기록은 읽기 전용입니다."
      />

      <div className={styles.auditViewTabs} role="tablist" aria-label="감사 로그 구분">
        <button type="button" role="tab" aria-selected={activeView === 'operations'} onClick={() => changeView('operations')}>
          운영 활동
          <span>계정·초대·연결 서비스 조치</span>
        </button>
        <button type="button" role="tab" aria-selected={activeView === 'analysis'} onClick={() => changeView('analysis')}>
          분석·결정 기록
          <span>배정 실행부터 PM 결정까지</span>
        </button>
      </div>

      {activeView === 'analysis' && (
        <div className={styles.tabs} role="tablist" aria-label="분석·결정 데이터">
          {(Object.keys(ANALYSIS_TAB_LABELS) as AnalysisTab[]).map((key) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={activeTab === key}
              className={[styles.tab, activeTab === key ? styles.tabActive : ''].filter(Boolean).join(' ')}
              onClick={() => changeTab(key)}
            >
              {ANALYSIS_TAB_LABELS[key]}
            </button>
          ))}
        </div>
      )}

      {activeView === 'operations' && (
        <OperationsPanel
          loading={operations.loading}
          error={operations.error}
          reload={operations.reload}
          allCount={operations.data?.length ?? 0}
          actions={operationActions}
          query={query}
          setQuery={setQuery}
          statusFilter={statusFilter}
          setStatusFilter={setStatusFilter}
          rows={filteredOperations}
          selectedId={selectedId.operations}
          onSelect={selectRow}
        />
      )}

      {activeView === 'analysis' && activeTab === 'assignment' && (
        <AssignmentRunsPanel
          loading={assignmentRuns.loading}
          error={assignmentRuns.error}
          reload={assignmentRuns.reload}
          allCount={assignmentRuns.data?.length ?? 0}
          query={query}
          setQuery={setQuery}
          statusFilter={statusFilter}
          setStatusFilter={setStatusFilter}
          rows={filteredAssignmentRuns}
          selectedId={selectedId.assignment}
          onSelect={selectRow}
        />
      )}

      {activeView === 'analysis' && activeTab === 'recommendation' && (
        <RecommendationsPanel
          loading={recommendations.loading}
          error={recommendations.error}
          reload={recommendations.reload}
          allCount={recommendations.data?.length ?? 0}
          query={query}
          setQuery={setQuery}
          statusFilter={statusFilter}
          setStatusFilter={setStatusFilter}
          rows={filteredRecommendations}
          selectedId={selectedId.recommendation}
          onSelect={selectRow}
        />
      )}

      {activeView === 'analysis' && activeTab === 'validation' && (
        <ValidationsPanel
          loading={validations.loading}
          error={validations.error}
          reload={validations.reload}
          allCount={validations.data?.length ?? 0}
          query={query}
          setQuery={setQuery}
          statusFilter={statusFilter}
          setStatusFilter={setStatusFilter}
          rows={filteredValidations}
          selectedId={selectedId.validation}
          onSelect={selectRow}
        />
      )}

      {activeView === 'analysis' && activeTab === 'decision' && (
        <DecisionsPanel
          loading={decisions.loading}
          error={decisions.error}
          reload={decisions.reload}
          allCount={decisions.data?.length ?? 0}
          query={query}
          setQuery={setQuery}
          statusFilter={statusFilter}
          setStatusFilter={setStatusFilter}
          rows={filteredDecisions}
          selectedId={selectedId.decision}
          onSelect={selectRow}
        />
      )}
    </div>
  );
}
