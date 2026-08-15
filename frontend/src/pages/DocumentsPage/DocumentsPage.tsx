import { useEffect, useMemo, useState } from 'react';
import { AppShell, Badge, Button, Icon, useToast } from '../../components';
import type { BadgeTone } from '../../components';
import { buildDocumentMeta, listTeamDocuments } from '../../api/documents';
import type { DocState, TeamDocument } from '../../api/documents';
import { ApiError } from '../../api/client';
import { loadSessionToken } from '../../utils/session';
import styles from './DocumentsPage.module.css';

/**
 * 문서 — 팀 범위. 2단계 검색(메타 coarse → 온디맨드 fine)으로 전환되면서
 * "고르고 등록하는" 화면이 아니라 "무엇이 어디까지 준비됐는지 보는" 상태
 * 화면이 됐다. 근거: 2_아키텍처_초안 §5(8/11 개정), 9_Figma_검증 v3.
 *
 * 문서는 팀 소속이라 프로젝트로 범위를 좁히지 않는다 — 좁히면 기준 문서 외에
 * 보여줄 것이 없고, 같은 회의록이 여러 프로젝트의 근거가 되는 현실과 어긋난다.
 */
const STATE_TONE: Record<DocState, BadgeTone> = {
  '준비됨': 'success',
  '메타만': 'neutral',
  '대기': 'info',
  '실패': 'danger',
  '미지원 형식': 'neutral',
};

/** 상태가 뜻하는 것 — 목록 위 범례. 서버의 `state` 매핑과 같은 말을 쓴다. */
const STATE_LEGEND: { state: DocState; desc: string }[] = [
  { state: '준비됨', desc: '본문까지 읽어 근거로 쓸 수 있습니다' },
  { state: '메타만', desc: '요약으로 후보에 잡히고, 쓸 때 본문을 읽습니다' },
  { state: '대기', desc: '원문은 받았고 아직 요약을 만들지 않았습니다' },
  { state: '실패', desc: '읽지 못했습니다 — 다시 처리할 수 있습니다' },
  { state: '미지원 형식', desc: '파서가 없어 다시 시도해도 같습니다' },
];

type FilterId = '전체' | '준비됨' | '메타만' | '대기' | '실패';

const FILTERS: FilterId[] = ['전체', '준비됨', '메타만', '대기', '실패'];

export default function DocumentsPage() {
  const token = loadSessionToken();
  const { showToast } = useToast();
  const [filter, setFilter] = useState<FilterId>('전체');
  const [documents, setDocuments] = useState<TeamDocument[]>([]);
  const [removed, setRemoved] = useState<{ doc_id: string; file_name: string }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function load() {
    if (!token) return;
    try {
      const data = await listTeamDocuments(token);
      setDocuments(data.documents);
      setRemoved(data.removed);
      setError(null);
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : '문서를 불러오지 못했습니다.');
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  /** 메타 생성. 대상 없이 부르면 아직 메타가 없는 문서 전부를 만든다. */
  async function build(docId?: string) {
    if (!token) return;
    setBusy(docId ?? 'all');
    try {
      const result = await buildDocumentMeta(token, docId ? [docId] : undefined);
      const ok = result.built.filter((row) => row.extract_status === 'OK').length;
      // 실패를 성공에 섞지 않는다 — 몇 건이 왜 안 됐는지 함께 말한다.
      showToast(
        `${result.built.length}건 처리 · 읽기 성공 ${ok}건` +
          (result.failed.length ? ` · 오류 ${result.failed.length}건` : ''),
        result.failed.length ? 'error' : 'success',
      );
      await load();
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '처리하지 못했습니다.', 'error');
    } finally {
      setBusy(null);
    }
  }

  const counts = useMemo(() => {
    const map: Record<string, number> = { 전체: documents.length };
    for (const doc of documents) map[doc.state] = (map[doc.state] ?? 0) + 1;
    return map;
  }, [documents]);

  const rows = useMemo(
    () => (filter === '전체' ? documents : documents.filter((doc) => doc.state === filter)),
    [filter, documents],
  );

  const pending = documents.filter((doc) => doc.state === '대기').length;

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
          {/* **「자동으로 등록됩니다」는 사실이 아니었다.** 자동으로 등록하는 경로가
              없고, `registerDocuments` 를 부르는 곳은 사람이 파일을 고르는 「문서
              등록」 화면 하나뿐이다. 기다리면 되는 줄 알고 기다리게 만드는 문장이었다.

              고르게 두는 것이 맞다 — 폴더에 있는 것을 전부 읽어 두면 쓰지도 않을
              문서까지 파싱·임베딩한다. 그 비용을 쓰는 이유는 내용을 보고 무언가
              하기 위해서인데, 안 쓸 문서에는 그 이유가 없다. */}
          <p className={styles.subtitle}>
            쓸 문서를 「문서 등록」에서 골라 추가합니다. 내용은 에이전트가 실제로 사용할 때 읽어 준비하고, 한 번 준비된
            문서는 다시 읽지 않습니다.
          </p>
        </header>

        {error && <p className={styles.error}>{error}</p>}

        <div className={styles.stats}>
          {[
            // 「자동으로 잡힌」도 같은 거짓말이었다 — 고른 것만 들어온다.
            { label: '등록', value: counts['전체'] ?? 0, desc: '골라서 추가한 전체 문서', tone: styles.statNeutral },
            { label: '준비됨', value: counts['준비됨'] ?? 0, desc: '본문까지 읽어 근거로 쓸 수 있는 문서', tone: styles.statSuccess },
            { label: '대기', value: counts['대기'] ?? 0, desc: '아직 요약을 만들지 않은 문서', tone: styles.statInfo },
            { label: '실패', value: counts['실패'] ?? 0, desc: '읽지 못해 근거로 쓸 수 없는 문서', tone: styles.statDanger },
          ].map((stat) => (
            <div key={stat.label} className={styles.stat}>
              <span className={styles.statLabel}>{stat.label}</span>
              <strong className={[styles.statValue, stat.tone].join(' ')}>{stat.value}건</strong>
              <span className={styles.statDesc}>{stat.desc}</span>
            </div>
          ))}
        </div>

        {pending > 0 && (
          <div className={styles.bulk}>
            <span>아직 요약을 만들지 않은 문서가 {pending}건 있습니다. 만들어 두면 검색 후보에 잡힙니다.</span>
            <Button size="sm" disabled={busy !== null} onClick={() => build()}>
              {busy === 'all' ? '처리하는 중…' : `${pending}건 처리`}
            </Button>
          </div>
        )}

        <div className={styles.filters}>
          {FILTERS.map((id) => (
            <button
              key={id}
              type="button"
              className={[styles.filter, filter === id ? styles.filterActive : ''].filter(Boolean).join(' ')}
              onClick={() => setFilter(id)}
            >
              {id}
              <span className={styles.filterCount}>{counts[id] ?? 0}</span>
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
            {/* 값은 `doc_meta.doc_type`(제안요청서·회의록…)이다. 「폴더」라고
                써 있었는데 `doc` 에는 Drive 폴더가 아예 없어서, 실제 폴더(01_기획)
                와 다른 값을 폴더라고 부르고 있었다(2026-08-12 QA §C). */}
            <span className={styles.colFolder}>유형</span>
            <span className={styles.colDate}>수정일</span>
            <span className={styles.colSummary}>요약 (자동 생성)</span>
            <span className={styles.colState}>상태</span>
          </div>

          {rows.map((doc) => (
            <div
              key={doc.doc_id}
              className={[styles.tableRow, doc.state === '미지원 형식' ? styles.rowDim : ''].filter(Boolean).join(' ')}
            >
              <span className={styles.colName}>
                <Icon name="file-text" size={16} color="var(--color-body)" />
                <span className={styles.docName}>{doc.file_name}</span>
              </span>
              <span className={styles.colFolder}>{doc.doc_type ?? '-'}</span>
              <span className={styles.colDate}>
                {doc.src_modified_at ? new Date(doc.src_modified_at).toLocaleDateString('ko-KR') : '-'}
              </span>
              {/* 요약이 없으면 지어내지 않는다. 왜 없는지는 상태 칩이 말한다. */}
              <span className={[styles.colSummary, doc.summary ? '' : styles.summaryMuted].join(' ')}>
                {doc.summary ?? '요약 없음'}
              </span>
              <span className={styles.colState}>
                <span className={styles.stateChipRow}>
                  <Badge tone={STATE_TONE[doc.state]}>{doc.state}</Badge>
                  {/* 다시 시도해서 달라질 수 있는 상태에만 버튼을 준다.
                      미지원 형식은 파서가 없어 몇 번을 눌러도 같다. */}
                  {doc.state !== '미지원 형식' && doc.state !== '준비됨' && doc.has_source && (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy !== null}
                      onClick={() => build(doc.doc_id)}
                    >
                      {busy === doc.doc_id ? '처리 중…' : '다시 처리'}
                    </Button>
                  )}
                </span>
                {!doc.has_source && <span className={styles.stateNote}>원문을 아직 받지 않았습니다</span>}
              </span>
            </div>
          ))}

          {rows.length === 0 && <p className={styles.stateNote}>이 상태의 문서가 없습니다.</p>}
        </section>

        {removed.length > 0 && (
          <section className={styles.removed}>
            <div className={styles.removedHead}>
              <Icon name="triangle-alert" size={16} color="var(--color-warning-text)" />
              <div className={styles.removedText}>
                <strong>Drive에서 사라진 문서 {removed.length}건</strong>
                <span>목록에서 내려간 문서입니다. 저장된 청크와 요약은 정리 시 함께 지워집니다.</span>
              </div>
            </div>

            {removed.map((item) => (
              <div key={item.doc_id} className={styles.removedRow}>
                <div className={styles.removedInfo}>
                  <strong>{item.file_name}</strong>
                  <span>{item.doc_id}</span>
                </div>
              </div>
            ))}
          </section>
        )}

      </div>
    </AppShell>
  );
}
