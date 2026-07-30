import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
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
import styles from '../OpsShared/OpsPages.module.css';

type AuditView = 'operations' | 'analysis';
type AnalysisTab = 'assignment' | 'recommendation' | 'validation' | 'decision';
type AuditDataKey = AuditView | AnalysisTab;

interface AuditColumn {
  key: string;
  label: string;
}

interface AuditRow {
  id: string;
  values: Record<string, string>;
  status: string;
  tone: OpsTone;
  detailTitle: string;
  detailLines: string[];
}

interface AuditConfig {
  label: string;
  count: number;
  searchPlaceholder: string;
  statusLabel?: string;
  columns: AuditColumn[];
  rows: AuditRow[];
}

const OPERATION_AUDIT: AuditConfig = {
  label: '운영 활동',
  count: 128,
  searchPlaceholder: '기록 ID·수행자·작업·대상 검색',
  columns: [
    { key: 'recordId', label: '기록 ID' },
    { key: 'time', label: '시각' },
    { key: 'actor', label: '수행자' },
    { key: 'action', label: '작업' },
    { key: 'target', label: '대상' },
  ],
  rows: [
    {
      id: 'LOG-128',
      values: { recordId: 'LOG-128', time: '07.30 10:12', actor: '운영자 계정 03', action: '계정 재활성', target: '계정 18' },
      status: '완료',
      tone: 'success',
      detailTitle: '선택 운영 활동 · LOG-128 · 계정 재활성',
      detailLines: ['운영자 계정 03이 계정 18의 상태를 정상으로 변경했습니다.', '변경 전 잠김 · 변경 후 정상 · 처리 시각 07.30 10:12'],
    },
    {
      id: 'LOG-127',
      values: { recordId: 'LOG-127', time: '07.30 09:57', actor: '운영자 계정 03', action: '이상 초대 폐기', target: '초대 18' },
      status: '완료',
      tone: 'success',
      detailTitle: '선택 운영 활동 · LOG-127 · 이상 초대 폐기',
      detailLines: ['수락 전 상태의 초대 18을 운영자 폐기로 전환했습니다.', '초대 기록과 처리 이력은 조회 목적으로 유지됩니다.'],
    },
    {
      id: 'LOG-126',
      values: { recordId: 'LOG-126', time: '07.30 09:22', actor: '운영자 계정 07', action: '직원 연결 해제', target: '계정 42 · 직원 62' },
      status: '완료',
      tone: 'success',
      detailTitle: '선택 운영 활동 · LOG-126 · 직원 연결 해제',
      detailLines: ['중복 연결이 확인된 계정 42와 직원 62의 연결을 해제했습니다.', '연결 상태 변경 사유와 대상 식별자는 운영 감사 대상으로 유지됩니다.'],
    },
    {
      id: 'LOG-125',
      values: { recordId: 'LOG-125', time: '07.30 08:40', actor: '시스템', action: '연결 상태 확인', target: '구글 드라이브 · 연결 07' },
      status: '확인 필요',
      tone: 'warning',
      detailTitle: '선택 운영 활동 · LOG-125 · 연결 상태 확인',
      detailLines: ['연결 07에서 인증 만료가 확인되었습니다.', '운영자는 원인과 영향을 확인하고 실제 재연결은 계정 소유자가 진행합니다.'],
    },
  ],
};

const ANALYSIS_TABS: Record<AnalysisTab, AuditConfig> = {
  assignment: {
    label: '배정 실행',
    count: 24,
    searchPlaceholder: '실행 ID·스냅샷 ID·요청자 검색',
    columns: [
      { key: 'runId', label: '실행 ID' },
      { key: 'snapshotId', label: '스냅샷 ID' },
      { key: 'readinessId', label: '준비도 결과' },
      { key: 'modelVersion', label: '모델 버전' },
      { key: 'policyVersion', label: '정책 버전' },
      { key: 'requester', label: '요청자' },
    ],
    rows: [
      { id: 'A-021', values: { runId: 'A-021', snapshotId: 'S-088', readinessId: 'R-088', modelVersion: 'v1.3', policyVersion: 'P-07', requester: '계정 12' }, status: '완료', tone: 'success', detailTitle: '선택 배정 실행 · A-021 · 완료', detailLines: ['스냅샷 S-088 · 준비도 결과 R-088 · 요청자 계정 12', '모델 버전 v1.3 · 정책 버전 P-07 · 현재 상태 완료'] },
      { id: 'A-022', values: { runId: 'A-022', snapshotId: 'S-089', readinessId: 'R-089', modelVersion: 'v1.3', policyVersion: 'P-07', requester: '계정 18' }, status: '부분 완료', tone: 'warning', detailTitle: '선택 배정 실행 · A-022 · 부분 완료', detailLines: ['스냅샷 S-089 · 준비도 결과 R-089 · 요청자 계정 18', '모델 버전 v1.3 · 정책 버전 P-07 · 현재 상태 부분 완료', '추천 결과 탭에서 실행 ID A-022와 연결된 결과를 이어서 확인할 수 있습니다.'] },
      { id: 'A-023', values: { runId: 'A-023', snapshotId: 'S-090', readinessId: 'R-090', modelVersion: 'v1.3', policyVersion: 'P-07', requester: '계정 07' }, status: '실행 중', tone: 'info', detailTitle: '선택 배정 실행 · A-023 · 실행 중', detailLines: ['스냅샷 S-090 · 요청자 계정 07', '실행이 완료되면 결과를 확인할 수 있습니다.'] },
      { id: 'A-024', values: { runId: 'A-024', snapshotId: 'S-091', readinessId: 'R-091', modelVersion: 'v1.3', policyVersion: 'P-07', requester: '계정 31' }, status: '차단', tone: 'danger', detailTitle: '선택 배정 실행 · A-024 · 차단', detailLines: ['필수 데이터가 부족해 실행이 차단되었습니다.', '준비도 결과 R-091에서 차단 사유를 확인합니다.'] },
    ],
  },
  recommendation: {
    label: '추천 결과',
    count: 68,
    searchPlaceholder: '추천 ID·실행 ID·업무 ID 검색',
    columns: [
      { key: 'recommendationId', label: '추천 ID' },
      { key: 'runId', label: '실행 ID' },
      { key: 'taskId', label: '업무 ID' },
      { key: 'confidence', label: '신뢰도' },
      { key: 'missingData', label: '누락 데이터' },
      { key: 'limitations', label: '제한·가정' },
    ],
    rows: [
      { id: 'RC-064', values: { recommendationId: 'RC-064', runId: 'A-021', taskId: 'T-018', confidence: '0.91', missingData: '없음', limitations: '없음' }, status: '성공', tone: 'success', detailTitle: '선택 추천 결과 · RC-064 · 성공', detailLines: ['배정 실행 A-021 · 신규 업무 T-018 · 신뢰도 0.91', '누락 데이터와 제한사항이 없습니다.'] },
      { id: 'RC-065', values: { recommendationId: 'RC-065', runId: 'A-022', taskId: 'T-021', confidence: '0.72', missingData: 'Jira 업무량', limitations: '일정 가정' }, status: '부분 결과', tone: 'warning', detailTitle: '선택 추천 결과 · RC-065 · 부분 결과', detailLines: ['배정 실행 A-022 · 신규 업무 T-021 · 신뢰도 0.72', '누락 데이터 Jira 업무량 · 제한사항 현재 부하를 완전 반영하지 못함', '가정 최근 동기화 기준 가용시간 사용 · 검증 결과 탭에서 RC-065를 이어서 확인'] },
      { id: 'RC-066', values: { recommendationId: 'RC-066', runId: 'A-022', taskId: 'T-022', confidence: '0.68', missingData: '업무량', limitations: '가용성 제한' }, status: '부분 결과', tone: 'warning', detailTitle: '선택 추천 결과 · RC-066 · 부분 결과', detailLines: ['업무량 데이터 누락으로 조건부 추천이 생성되었습니다.'] },
      { id: 'RC-067', values: { recommendationId: 'RC-067', runId: 'A-024', taskId: 'T-025', confidence: '-', missingData: '필수 기술', limitations: '추천 보류' }, status: '차단', tone: 'danger', detailTitle: '선택 추천 결과 · RC-067 · 차단', detailLines: ['필수 기술 정보가 없어 추천을 생성하지 않았습니다.'] },
    ],
  },
  validation: {
    label: '검증 결과',
    count: 68,
    searchPlaceholder: '검증 ID·추천 ID 검색',
    columns: [
      { key: 'validationId', label: '검증 ID' },
      { key: 'recommendationId', label: '추천 ID' },
      { key: 'confidence', label: '신뢰도' },
      { key: 'missingData', label: '누락 데이터' },
      { key: 'checkCount', label: '검사 항목' },
      { key: 'warnings', label: '실패·경고' },
    ],
    rows: [
      { id: 'V-064', values: { validationId: 'V-064', recommendationId: 'RC-064', confidence: '0.92', missingData: '없음', checkCount: '6건', warnings: '없음' }, status: '통과', tone: 'success', detailTitle: '선택 검증 결과 · V-064 · 통과', detailLines: ['추천 결과 RC-064 · 검사 6건 · 실패와 경고 없음'] },
      { id: 'V-065', values: { validationId: 'V-065', recommendationId: 'RC-065', confidence: '0.74', missingData: 'Jira 업무량', checkCount: '6건', warnings: '경고 2' }, status: '조건부', tone: 'warning', detailTitle: '선택 검증 결과 · V-065 · 조건부', detailLines: ['추천 결과 RC-065 · 신뢰도 0.74 · 누락 데이터 Jira 업무량', '검사 6건 · 경고 2건 · 최고 심각도 주의 · 실제 값과 기대 규칙 비교 가능', '결정 기록 탭에서 검증 ID V-065와 연결된 최종 판단을 이어서 확인'] },
      { id: 'V-066', values: { validationId: 'V-066', recommendationId: 'RC-066', confidence: '0.63', missingData: '업무량', checkCount: '6건', warnings: '경고 1' }, status: '조건부', tone: 'warning', detailTitle: '선택 검증 결과 · V-066 · 조건부', detailLines: ['업무량 누락 경고 1건이 있습니다.'] },
      { id: 'V-067', values: { validationId: 'V-067', recommendationId: 'RC-067', confidence: '-', missingData: '필수 기술', checkCount: '4건', warnings: '실패 1' }, status: '거절', tone: 'danger', detailTitle: '선택 검증 결과 · V-067 · 거절', detailLines: ['필수 기술 조건 위반으로 검증을 통과하지 못했습니다.'] },
    ],
  },
  decision: {
    label: '결정 기록',
    count: 41,
    searchPlaceholder: '결정 ID·추천 ID·검증 ID 검색',
    statusLabel: '조치',
    columns: [
      { key: 'decisionId', label: '결정 ID' },
      { key: 'recommendationId', label: '추천 ID' },
      { key: 'validationId', label: '검증 ID' },
      { key: 'candidateId', label: '수정 후보' },
      { key: 'decider', label: '결정자' },
      { key: 'decidedAt', label: '결정 시각' },
    ],
    rows: [
      { id: 'D-037', values: { decisionId: 'D-037', recommendationId: 'RC-064', validationId: 'V-064', candidateId: '없음', decider: '계정 12', decidedAt: '07.29 11:52' }, status: '승인', tone: 'success', detailTitle: '선택 PM 결정 · D-037 · 승인', detailLines: ['추천 결과 RC-064 · 검증 결과 V-064 · 원안 승인'] },
      { id: 'D-038', values: { decisionId: 'D-038', recommendationId: 'RC-065', validationId: 'V-065', candidateId: 'C-109', decider: '계정 18', decidedAt: '07.29 12:18' }, status: '수정', tone: 'warning', detailTitle: '선택 PM 결정 · D-038 · 수정', detailLines: ['추천 결과 RC-065 · 검증 결과 V-065 · 수정 후보 C-109', '조치 수정 · 사유 Jira 업무량 누락을 반영해 담당자 후보 변경', '결정자 계정 18 · 결정 시각 07.29 12:18'] },
      { id: 'D-039', values: { decisionId: 'D-039', recommendationId: 'RC-066', validationId: 'V-066', candidateId: '없음', decider: '계정 07', decidedAt: '07.29 13:04' }, status: '승인', tone: 'success', detailTitle: '선택 PM 결정 · D-039 · 승인', detailLines: ['조건부 경고를 확인한 뒤 원안을 승인했습니다.'] },
      { id: 'D-040', values: { decisionId: 'D-040', recommendationId: 'RC-067', validationId: 'V-067', candidateId: '없음', decider: '계정 31', decidedAt: '07.29 13:22' }, status: '반려', tone: 'danger', detailTitle: '선택 PM 결정 · D-040 · 반려', detailLines: ['필수 기술 조건 위반을 근거로 추천을 반려했습니다.'] },
    ],
  },
};

function csvCell(value: string) {
  return `"${value.replaceAll('"', '""')}"`;
}

export default function OpsAuditPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialView: AuditView = searchParams.get('view') === 'analysis' ? 'analysis' : 'operations';
  const initialTab = searchParams.get('tab') as AnalysisTab | null;
  const [activeView, setActiveView] = useState<AuditView>(initialView);
  const [activeTab, setActiveTab] = useState<AnalysisTab>(initialTab && initialTab in ANALYSIS_TABS ? initialTab : 'assignment');
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('전체');
  const [selectedIds, setSelectedIds] = useState<Record<AuditDataKey, string>>({
    operations: 'LOG-128',
    analysis: 'A-022',
    assignment: 'A-022',
    recommendation: 'RC-065',
    validation: 'V-065',
    decision: 'D-038',
  });

  const dataKey: AuditDataKey = activeView === 'operations' ? 'operations' : activeTab;
  const config = activeView === 'operations' ? OPERATION_AUDIT : ANALYSIS_TABS[activeTab];
  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return config.rows.filter((row) => {
      const matchesQuery = !normalized || [row.id, ...Object.values(row.values)]
        .some((value) => value.toLowerCase().includes(normalized));
      return matchesQuery && (status === '전체' || row.status === status);
    });
  }, [config, query, status]);
  const selected = filtered.find((row) => row.id === selectedIds[dataKey]) ?? filtered[0] ?? null;
  const statuses = [...new Set(config.rows.map((row) => row.status))];

  function resetFilters() {
    setQuery('');
    setStatus('전체');
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

  function exportRows() {
    const headers = [...config.columns.map((column) => column.label), config.statusLabel ?? '상태'];
    const body = filtered.map((row) => [
      ...config.columns.map((column) => row.values[column.key] ?? ''),
      row.status,
    ].map(csvCell).join(',')).join('\n');
    const blob = new Blob([`\uFEFF${headers.map(csvCell).join(',')}\n${body}`], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `감사로그_${config.label}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
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
          {(Object.entries(ANALYSIS_TABS) as [AnalysisTab, AuditConfig][]).map(([key, tab]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={activeTab === key}
              className={[styles.tab, activeTab === key ? styles.tabActive : ''].filter(Boolean).join(' ')}
              onClick={() => changeTab(key)}
            >
              {tab.label} {tab.count}
            </button>
          ))}
        </div>
      )}

      <OpsFilterBar>
        <OpsSearchField value={query} onChange={setQuery} placeholder={config.searchPlaceholder} />
        <select value={status} onChange={(event) => setStatus(event.target.value)} aria-label={config.statusLabel ?? '상태'}>
          <option>전체</option>
          {statuses.map((item) => <option key={item}>{item}</option>)}
        </select>
        <Button variant="outline" onClick={exportRows}>현재 목록 내보내기</Button>
      </OpsFilterBar>
      <p className={styles.resultSummary}>
        현재 {filtered.length}건 표시 · 전체 기록 {config.count}건
      </p>

      <OpsDataTable minWidth={1120}>
        <thead>
          <tr>
            {config.columns.map((column) => <th scope="col" key={column.key}>{column.label}</th>)}
            <th scope="col">{config.statusLabel ?? '상태'}</th>
            <th scope="col">상세</th>
          </tr>
        </thead>
        <tbody>
          {filtered.length > 0 ? filtered.map((row) => (
            <tr
              key={row.id}
              aria-selected={selected?.id === row.id}
              onClick={() => setSelectedIds((current) => ({ ...current, [dataKey]: row.id }))}
            >
              {config.columns.map((column) => <td key={`${row.id}:${column.key}`}>{row.values[column.key]}</td>)}
              <td><OpsStatusBadge tone={row.tone}>{row.status}</OpsStatusBadge></td>
              <td>
                <button
                  type="button"
                  aria-label={`${row.id} 상세 보기`}
                  onClick={(event) => {
                    event.stopPropagation();
                    setSelectedIds((current) => ({ ...current, [dataKey]: row.id }));
                  }}
                >
                  보기
                </button>
              </td>
            </tr>
          )) : (
            <tr><td className={styles.emptyCell} colSpan={config.columns.length + 2}>조건에 맞는 기록이 없습니다.</td></tr>
          )}
        </tbody>
      </OpsDataTable>

      {selected ? (
        <OpsDetailPanel title={selected.detailTitle}>
          {selected.detailLines.map((line) => <p className={styles.detailText} key={line}>{line}</p>)}
        </OpsDetailPanel>
      ) : (
        <div className={styles.inlineEmpty}>검색 조건을 변경하면 기록 상세를 확인할 수 있습니다.</div>
      )}
    </div>
  );
}
