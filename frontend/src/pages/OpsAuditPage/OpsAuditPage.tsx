import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Button,
  Modal,
  OpsDataTable,
  OpsFilterBar,
  OpsPageHeader,
  OpsSearchField,
} from '../../components';
import { fetchOperationLogs } from '../../api/opsAudit';
import type { OpsOperationLog } from '../../api/opsAudit';
import { ApiError } from '../../api/client';
import { actionLabel, isAuthenticationAction } from '../../utils/auditActions';
import { loadOpsSession } from '../../utils/opsSession';
import { timeAgo } from '../../utils/relativeTime';
import styles from '../OpsShared/OpsPages.module.css';

const PAGE_SIZE = 25;

/**
 * 감사 로그 — **누가 무엇을 했는가.**
 *
 * 「분석·결정 기록」이라는 두 번째 갈래에 탭 4종(배정 실행·추천 결과·검증
 * 결과·PM 결정)이 있었고 **넷 다 항상 0건이었다.** 그 테이블에 쓰는 추천
 * 파이프라인이 이 저장소에 없고 제품도 업무 배정 추천에서 물러났다 — 있지도
 * 않을 것을 기다리는 빈 탭은 화면이 거짓말을 하는 것이다(2026-08-13 지적).
 *
 * 갈래가 하나만 남으면서 위쪽 구분 탭도 같이 걷었다. 탭이 하나면 탭이 아니다.
 */

function hasContent(value: unknown): boolean {
  if (value === null || value === undefined) return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === 'object') return Object.keys(value).length > 0;
  return true;
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

export default function OpsAuditPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [logs, setLogs] = useState<OpsOperationLog[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [actionFilter, setActionFilter] = useState('전체');
  const [categoryFilter, setCategoryFilter] = useState(searchParams.get('view') === 'operations' ? '운영 변경' : '전체');
  const [selectedId, setSelectedId] = useState('');
  const [page, setPage] = useState(1);

  async function load() {
    const session = loadOpsSession();
    if (!session) {
      navigate('/ops/login', { replace: true });
      return;
    }

    setLoading(true);
    setError('');
    try {
      setLogs(await fetchOperationLogs(session.token));
    } catch (thrown) {
      if (thrown instanceof ApiError && thrown.status === 401) {
        navigate('/ops/login', { replace: true });
        return;
      }
      setError(thrown instanceof ApiError ? thrown.message : '기록을 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const actions = useMemo(() => [...new Set((logs ?? [])
    .filter((row) => categoryFilter === '전체'
      || (categoryFilter === '운영 변경' && !isAuthenticationAction(row.action))
      || (categoryFilter === '로그인·인증' && isAuthenticationAction(row.action)))
    .map((row) => row.action))], [categoryFilter, logs]);

  const filtered = useMemo(() => {
    const all = logs ?? [];
    const normalized = query.trim().toLowerCase();
    return all.filter((row) => {
      // 화면에 보이는 값으로만 검색한다 — 고유 번호는 표시하지 않으므로 검색어로 쓸 수 없다.
      const matchesQuery = !normalized || [
        row.actor_display_name ?? '',
        row.actor_email ?? '',
        row.target_type ?? '',
      ].some((value) => value.toLowerCase().includes(normalized));
      const matchesAction = actionFilter === '전체' || row.action === actionFilter;
      const isAuthentication = isAuthenticationAction(row.action);
      const matchesCategory = categoryFilter === '전체'
        || (categoryFilter === '운영 변경' && !isAuthentication)
        || (categoryFilter === '로그인·인증' && isAuthentication);
      return matchesQuery && matchesAction && matchesCategory;
    });
  }, [logs, query, actionFilter, categoryFilter]);

  const selected = filtered.find((row) => row.audit_id === selectedId) ?? null;
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageRows = filtered.slice(
    (currentPage - 1) * PAGE_SIZE,
    currentPage * PAGE_SIZE,
  );

  const header = (
    <OpsPageHeader
      title="감사 로그"
    />
  );

  if (loading && !logs) {
    return (
      <div className={styles.page}>
        {header}
        <p className={styles.inlineEmpty}>불러오는 중…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.page}>
        {header}
        <p className={styles.inlineEmpty} role="alert">{error}</p>
        <Button variant="outline" onClick={load}>다시 시도</Button>
      </div>
    );
  }

  const all = logs ?? [];

  if (all.length === 0) {
    return (
      <div className={styles.page}>
        {header}
        <p className={styles.inlineEmpty}>기록이 없습니다.</p>
      </div>
    );
  }

  function exportRows() {
    downloadCsv(
      '감사로그_운영활동.csv',
      ['기록ID', '시각', '수행자', '작업', '대상'],
      filtered.map((r) => [r.audit_id, r.occurred_at, r.actor_display_name ?? r.actor_email ?? r.actor_account_id,
        actionLabel(r.action), [r.target_type, r.target_id].filter(Boolean).join(' · ')]),
    );
  }

  return (
    <div className={styles.page}>
      {header}

      <OpsFilterBar>
        <OpsSearchField
          value={query}
          onChange={(value) => {
            setQuery(value);
            setPage(1);
          }}
          placeholder="수행자 또는 대상 검색"
        />
        <select
          value={categoryFilter}
          onChange={(e) => {
            setCategoryFilter(e.target.value);
            setActionFilter('전체');
            setPage(1);
          }}
          aria-label="기록 구분"
        >
          <option>전체</option>
          <option>운영 변경</option>
          <option>로그인·인증</option>
        </select>
        <select
          value={actionFilter}
          onChange={(e) => {
            setActionFilter(e.target.value);
            setPage(1);
          }}
          aria-label="작업 종류"
        >
          <option>전체</option>
          {/* 보이는 것은 한글 라벨, 고르는 값은 원본 코드다 — 라벨을 값으로 쓰면
              표의 `action` 과 안 맞아 아무것도 안 걸린다. */}
          {actions.map((a) => <option key={a} value={a}>{actionLabel(a)}</option>)}
        </select>
        <Button variant="outline" onClick={exportRows}>현재 목록 내보내기</Button>
      </OpsFilterBar>

      <p className={styles.resultSummary}>
        필터 결과 {filtered.length}건 · 최근 기록 {all.length === 200 ? '최대 200건' : `${all.length}건`}
      </p>

      <OpsDataTable minWidth={1100}>
        <thead>
          <tr><th>시각</th><th>수행자</th><th>작업</th><th>대상</th></tr>
        </thead>
        <tbody>
          {pageRows.length > 0 ? pageRows.map((row) => (
            <tr
              key={row.audit_id}
              aria-selected={selected?.audit_id === row.audit_id}
              onClick={() => setSelectedId(row.audit_id)}
            >
              <td>{timeAgo(row.occurred_at)}</td>
              <td>{row.actor_display_name ?? row.actor_email ?? '알 수 없음'}</td>
              <td>{actionLabel(row.action)}</td>
              <td>{row.target_type ?? '-'}</td>
            </tr>
          )) : <tr><td className={styles.emptyCell} colSpan={4}>조건에 맞는 기록이 없습니다.</td></tr>}
        </tbody>
      </OpsDataTable>

      {filtered.length > PAGE_SIZE && (
        <div className={styles.pager} aria-label="감사 로그 페이지 이동">
          <span className={styles.pagerInfo}>
            {(currentPage - 1) * PAGE_SIZE + 1}–{Math.min(currentPage * PAGE_SIZE, filtered.length)} / {filtered.length}건
          </span>
          <div className={styles.pagerActions}>
            <Button variant="outline" size="sm" onClick={() => setPage(Math.max(1, currentPage - 1))} disabled={currentPage === 1}>
              이전
            </Button>
            <span className={styles.pagerInfo}>{currentPage} / {totalPages} 페이지</span>
            <Button variant="outline" size="sm" onClick={() => setPage(Math.min(totalPages, currentPage + 1))} disabled={currentPage === totalPages}>
              다음
            </Button>
          </div>
        </div>
      )}

      <Modal
        open={selected !== null}
        onClose={() => setSelectedId('')}
        title={selected ? actionLabel(selected.action) : '감사 기록 상세'}
        width={680}
        footer={<Button variant="secondary" onClick={() => setSelectedId('')}>닫기</Button>}
      >
        {selected && (
          <>
            <dl className={styles.policyMetadata}>
              <div>
                <dt>수행자</dt>
                <dd>{selected.actor_display_name ?? selected.actor_email ?? '알 수 없음'}</dd>
              </div>
              <div>
                <dt>시각</dt>
                <dd>{new Date(selected.occurred_at).toLocaleString('ko-KR')}</dd>
              </div>
              <div>
                <dt>대상</dt>
                <dd className={styles.targetValue}>
                  {selected.target_type ? <span className={styles.targetType}>{selected.target_type}</span> : '-'}
                  {selected.target_id && <span className={styles.targetId}>{selected.target_id}</span>}
                </dd>
              </div>
            </dl>
            {hasContent(selected.payload) ? (
              <pre className={styles.jsonBlock}>{JSON.stringify(selected.payload, null, 2)}</pre>
            ) : (
              <p className={[styles.inlineEmpty, styles.payloadEmpty].join(' ')}>추가 정보가 없습니다.</p>
            )}
          </>
        )}
      </Modal>
    </div>
  );
}
