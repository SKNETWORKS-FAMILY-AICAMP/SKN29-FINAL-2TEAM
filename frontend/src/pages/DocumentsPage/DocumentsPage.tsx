import { useMemo, useState } from 'react';
import { AppShell, Badge, Button, Icon } from '../../components';
import type { BadgeTone } from '../../components';
import styles from './DocumentsPage.module.css';

/**
 * 문서 — 팀 범위. 2단계 검색(메타 coarse → 온디맨드 fine)으로 전환되면서
 * "고르고 등록하는" 화면이 아니라 "무엇이 어디까지 준비됐는지 보는" 상태
 * 화면이 됐다. 근거: 2_아키텍처_초안 §5(8/11 개정), 9_Figma_검증 v3.
 *
 * 문서는 팀 소속이라 프로젝트로 범위를 좁히지 않는다 — 좁히면 기준 문서 외에
 * 보여줄 것이 없고, 같은 회의록이 여러 프로젝트의 근거가 되는 현실과 어긋난다.
 */
type DocState = '준비됨' | '메타만' | '처리 중' | '실패' | '미지원 형식';

interface DocRow {
  name: string;
  folder: string;
  updated: string;
  summary: string;
  state: DocState;
  note?: string;
  retry?: boolean;
}

const STATE_TONE: Record<DocState, BadgeTone> = {
  '준비됨': 'success',
  '메타만': 'neutral',
  '처리 중': 'info',
  '실패': 'danger',
  '미지원 형식': 'neutral',
};

/** 상태가 뜻하는 것 — 목록 위 범례. 툴팁 문구와 같은 말을 쓴다. */
const STATE_LEGEND: { state: DocState; desc: string }[] = [
  { state: '준비됨', desc: '근거로 사용할 수 있습니다' },
  { state: '메타만', desc: '에이전트가 사용할 때 자동으로 읽습니다' },
  { state: '실패', desc: '읽지 못했습니다 — 다시 처리할 수 있습니다' },
  { state: '미지원 형식', desc: '읽을 수 없는 형식입니다' },
];

const MOCK_DOCS: DocRow[] = [
  {
    name: '2026_상반기_사업계획서.docx',
    folder: '기획 문서',
    updated: '2026.08.03',
    summary: '상반기 통합포털 개편 목표와 단계별 일정, 투입 인력 규모를 정리한 기획서',
    state: '준비됨',
  },
  {
    name: '물류시스템_요구사항정의서_v2.pdf',
    folder: '요구사항',
    updated: '2026.07.30',
    summary: 'SSO·권한 등급·데이터 이관 요구사항과 완료 기준을 항목별로 기술',
    state: '준비됨',
  },
  {
    name: '고객사_제안요청서_RFP_v3.pdf',
    folder: '제안 문서',
    updated: '2026.07.28',
    summary: '발주처 요구 범위와 산출물 목록, 평가 배점 기준',
    state: '처리 중',
    note: '지금 읽는 중 — 잠시 후 근거로 쓸 수 있습니다',
  },
  {
    name: '킥오프_회의록_2026-08-03.md',
    folder: '회의록',
    updated: '2026.08.03',
    summary: '킥오프에서 정한 역할 분담과 8월 마일스톤, 미결 3건',
    state: '메타만',
  },
  {
    name: '통합관제_구축_제안서_스캔.pdf',
    folder: '제안 문서',
    updated: '2026.06.18',
    summary: '요약을 만들지 못했습니다',
    state: '실패',
    note: '스캔본 — 텍스트 추출 실패',
    retry: true,
  },
  {
    name: '회의록_20260728.hwp',
    folder: '회의록',
    updated: '2026.07.28',
    summary: '—',
    state: '미지원 형식',
  },
];

const MOCK_REMOVED = [
  { name: '구_통합관제_제안서.pdf', why: '제안 문서 · 통합관제 플랫폼 고도화 기준 문서로 쓰이던 문서', chunks: '청크 148건' },
  { name: '이전_요구사항_v1.pdf', why: '요구사항 · 2026.07.30 v2로 대체됨', chunks: '청크 96건' },
];

type FilterId = '전체' | '준비됨' | '메타만' | '실패';

const FILTERS: { id: FilterId; count: number }[] = [
  { id: '전체', count: 128 },
  { id: '준비됨', count: 12 },
  { id: '메타만', count: 114 },
  { id: '실패', count: 1 },
];

export default function DocumentsPage() {
  const [filter, setFilter] = useState<FilterId>('전체');

  const rows = useMemo(() => {
    if (filter === '전체') return MOCK_DOCS;
    if (filter === '메타만') return MOCK_DOCS.filter((doc) => doc.state === '메타만' || doc.state === '처리 중');
    return MOCK_DOCS.filter((doc) => doc.state === filter);
  }, [filter]);

  return (
    <AppShell>
      <div className={styles.page}>
        <nav className={styles.breadcrumb}>
          <span>프로젝트</span>
          <Icon name="chevron-right" size={13} color="var(--color-placeholder)" />
          <span className={styles.crumbCurrent}>문서</span>
          <span className={styles.pathGuess}>경로 가안 · PM 확정 대기</span>
        </nav>

        <header className={styles.header}>
          <h1 className={styles.title}>문서</h1>
          <p className={styles.subtitle}>
            폴더의 새 파일은 자동으로 등록됩니다. 내용은 에이전트가 실제로 사용할 때 읽어 준비하고, 한 번 준비된 문서는
            다시 읽지 않습니다.
          </p>
        </header>

        <div className={styles.stats}>
          {[
            { label: '등록', value: '128건', desc: '폴더에서 자동으로 잡힌 전체 문서', tone: styles.statNeutral },
            { label: '준비됨', value: '12건', desc: '내용까지 읽어 근거로 쓸 수 있는 문서', tone: styles.statSuccess },
            { label: '처리 중', value: '1건', desc: '지금 읽고 있는 문서', tone: styles.statInfo },
            { label: '실패', value: '1건', desc: '읽지 못해 근거로 쓸 수 없는 문서', tone: styles.statDanger },
          ].map((stat) => (
            <div key={stat.label} className={styles.stat}>
              <span className={styles.statLabel}>{stat.label}</span>
              <strong className={[styles.statValue, stat.tone].join(' ')}>{stat.value}</strong>
              <span className={styles.statDesc}>{stat.desc}</span>
            </div>
          ))}
        </div>

        <div className={styles.filters}>
          {FILTERS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={[styles.filter, filter === item.id ? styles.filterActive : ''].filter(Boolean).join(' ')}
              onClick={() => setFilter(item.id)}
            >
              {item.id}
              <span className={styles.filterCount}>{item.count}</span>
            </button>
          ))}
        </div>

        <section className={styles.legend}>
          <span className={styles.legendTitle}>상태가 뜻하는 것</span>
          <div className={styles.legendRow}>
            {STATE_LEGEND.map((item) => (
              <span key={item.state} className={styles.legendItem}>
                <Badge tone={STATE_TONE[item.state]}>{item.state}</Badge>
                <span className={styles.legendDesc}>{item.desc}</span>
              </span>
            ))}
          </div>
        </section>

        <section className={styles.table}>
          <div className={styles.tableHead}>
            <span className={styles.colName}>파일명</span>
            <span className={styles.colFolder}>폴더</span>
            <span className={styles.colDate}>수정일</span>
            <span className={styles.colSummary}>요약 (자동 생성)</span>
            <span className={styles.colState}>상태</span>
          </div>

          {rows.map((doc) => (
            <div
              key={doc.name}
              className={[styles.tableRow, doc.state === '미지원 형식' ? styles.rowDim : ''].filter(Boolean).join(' ')}
            >
              <span className={styles.colName}>
                <Icon name="file-text" size={16} color="var(--color-body)" />
                <span className={styles.docName}>{doc.name}</span>
              </span>
              <span className={styles.colFolder}>
                <Icon name="folder" size={14} color="var(--color-placeholder)" />
                {doc.folder}
              </span>
              <span className={styles.colDate}>{doc.updated}</span>
              <span className={[styles.colSummary, doc.state === '실패' ? styles.summaryMuted : ''].join(' ')}>
                {doc.summary}
              </span>
              <span className={styles.colState}>
                <span className={styles.stateChipRow}>
                  <Badge tone={STATE_TONE[doc.state]}>{doc.state}</Badge>
                  {doc.retry && (
                    <Button size="sm" variant="outline">
                      다시 처리
                    </Button>
                  )}
                </span>
                {doc.note && (
                  <span className={[styles.stateNote, doc.state === '실패' ? styles.stateNoteDanger : ''].join(' ')}>
                    {doc.note}
                  </span>
                )}
              </span>
            </div>
          ))}

          <button type="button" className={styles.more}>
            외 122건 보기
          </button>
        </section>

        <section className={styles.removed}>
          <div className={styles.removedHead}>
            <Icon name="triangle-alert" size={16} color="var(--color-warning-text)" />
            <div className={styles.removedText}>
              <strong>Drive에서 사라진 문서 2건, 확인 후 정리</strong>
              <span>정리하면 저장된 청크와 요약도 함께 지워집니다. 되돌릴 수 없습니다.</span>
            </div>
            <Button size="sm" variant="outline">
              확인 후 정리
            </Button>
          </div>

          {MOCK_REMOVED.map((item) => (
            <div key={item.name} className={styles.removedRow}>
              <div className={styles.removedInfo}>
                <strong>{item.name}</strong>
                <span>{item.why}</span>
              </div>
              <span className={styles.removedChunks}>{item.chunks}</span>
            </div>
          ))}
        </section>
      </div>
    </AppShell>
  );
}
