import { useCallback, useEffect, useMemo, useState } from 'react';
import { Badge, Button, Icon, Modal, TopNav, useToast } from '../../components';
import { ApiError } from '../../api/client';
import {
  listDocumentHistory,
  listNewDocuments,
  removeDocuments,
  listTeamFolders,
  registerDocuments,
} from '../../api/projects';
import type {
  DocumentHistoryEntry,
  MissingDocument,
  NewDocumentCandidate,
} from '../../api/projects';
import { MAIN_NAV_TABS } from '../../routes';
import { useSession } from '../../utils/session';
import { FileRegistrationTable } from './FileRegistrationTable';
import type { FileRow } from './FileRegistrationTable';
import styles from './NewFilesPage.module.css';

const ACTION_LABEL: Record<string, string> = {
  DOCUMENT_REGISTER: '파일 등록',
  DOCUMENT_DOWNLOAD: '원문 저장',
  DOCUMENT_REMOVE: '삭제 파일 정리',
};

/** 서버는 코드로 준다. 화면에 내부 코드를 그대로 내보내지 않는다. */
const STATUS_LABEL: Record<string, string> = {
  OK: '완료',
  PARTIAL: '일부 실패',
};

function formatDate(iso: string | null): string {
  if (!iso) return '-';
  return iso.slice(0, 10).replace(/-/g, '.');
}

function historyLabel(entry: DocumentHistoryEntry): string {
  const action = ACTION_LABEL[entry.action] ?? entry.action;
  const payload = entry.payload as {
    registered?: number;
    downloaded?: number;
    removed?: number;
    chunks?: number;
    failed?: number;
    skipped?: number;
  };
  const count = payload.registered ?? payload.downloaded ?? payload.removed ?? 0;

  // 실패와 제외는 다르다 — 실패는 하려다 안 된 것, 제외는 미지원이라 애초에
  // 대상이 아니었던 것이다. 같은 말로 뭉치면 원인을 오해한다.
  const notes: string[] = [];
  if (payload.failed) notes.push(`실패 ${payload.failed}건`);
  if (payload.skipped) notes.push(`제외 ${payload.skipped}건`);
  // 정리는 파싱 산출물까지 지운다. 문서 건수만 적으면 무엇이 없어졌는지 모른다.
  if (entry.action === 'DOCUMENT_REMOVE' && payload.chunks) {
    notes.push(`청크 ${payload.chunks}건 삭제`);
  }

  return `${action} ${count}건${notes.length > 0 ? ` (${notes.join(' · ')})` : ''}`;
}

/**
 * 문서 관리.
 *
 * 설정된 Drive 폴더와 등록된 문서를 **맞추는** 화면이다. 폴더에는 있는데 `doc`에
 * 없는 파일을 등록하고, `doc`에는 있는데 폴더에서 사라진 문서를 내린다.
 *
 * 「신규 파일」이라는 이름이었는데 사라진 문서까지 다루게 되면서 반쪽만 가리키는
 * 말이 됐다(2026-08-04). 네비게이션의 「문서 등록」과도 어긋나 있었다.
 *
 * 등록은 `doc` 행을 만드는 데까지다 — 원문 다운로드는 따로다.
 */
export default function NewFilesPage() {
  const session = useSession();
  const token = session?.token;
  const { showToast } = useToast();

  // 폴더가 설정돼 있어야 스캔할 곳이 있다. 프로젝트와는 무관하다.
  const [configured, setConfigured] = useState(false);
  const [candidates, setCandidates] = useState<NewDocumentCandidate[]>([]);
  // Drive 스캔에 더 이상 안 잡히는 등록 문서. 자동으로 내리지 않고 보여만 준다.
  const [missing, setMissing] = useState<MissingDocument[]>([]);
  const [removing, setRemoving] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [history, setHistory] = useState<DocumentHistoryEntry[]>([]);
  const [historyHasMore, setHistoryHasMore] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [registering, setRegistering] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError('');
    try {
      const folders = await listTeamFolders(token);
      setConfigured(folders.length > 0);
      if (folders.length === 0) {
        setCandidates([]);
        setMissing([]);
        setHistory([]);
        setHistoryHasMore(false);
        return;
      }

      const [scan, historyPage] = await Promise.all([
        listNewDocuments(token),
        listDocumentHistory(token).catch(() => ({ entries: [], has_more: false })),
      ]);
      setCandidates(scan.candidates);
      setMissing(scan.missing);
      setConfirming(false);
      setHistory(historyPage.entries);
      setHistoryHasMore(historyPage.has_more);
      // 등록 가능한 것만 미리 골라 둔다.
      setSelected(
        new Set(scan.candidates.filter((row) => row.supported).map((row) => row.file_id)),
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '폴더를 확인하지 못했습니다.');
      setCandidates([]);
      setMissing([]);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  /** 이미 받은 것 뒤부터 이어 받는다. 처음부터 다시 읽으면 스크롤이 튄다. */
  async function handleLoadMoreHistory() {
    if (!token || historyLoading) return;
    setHistoryLoading(true);
    try {
      const page = await listDocumentHistory(token, history.length);
      setHistory((prev) => [...prev, ...page.entries]);
      setHistoryHasMore(page.has_more);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : '이력을 더 불러오지 못했습니다', 'error');
    } finally {
      setHistoryLoading(false);
    }
  }

  // 신규 파일과 사라진 문서를 한 표에 둔다. 「이 폴더의 지금 상태」가 한 화면에
  // 있어야 하고, 사라진 문서만 경고 카드로 세우면 신규 파일 검토보다 시선을
  // 끌어간다.
  const rows: FileRow[] = useMemo(
    () => [
      ...candidates.map((item) => ({
        id: item.file_id,
        name: item.file_name,
        folder: item.folder_name,
        date: formatDate(item.modified_at),
        supported: item.supported,
        kind: 'new' as const,
      })),
      ...missing.map((doc) => ({
        id: doc.doc_id,
        name: doc.file_name ?? doc.doc_id,
        // 사라진 파일이라 소속 폴더도 감지일도 Drive 에서 다시 알 수 없다.
        folder: '—',
        date: '—',
        supported: false,
        kind: 'missing' as const,
        note: doc.proj_id
          ? `${doc.project_name ?? doc.proj_id} ${doc.doc_role === 'PRIMARY' ? '기준 문서' : '근거 문서'}`
          : undefined,
      })),
    ],
    [candidates, missing],
  );

  const supportedIds = useMemo(
    () => candidates.filter((item) => item.supported).map((item) => item.file_id),
    [candidates],
  );

  function toggleRow(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    setSelected((prev) =>
      supportedIds.every((id) => prev.has(id)) ? new Set() : new Set(supportedIds),
    );
  }

  async function handleRegister() {
    if (!token || !configured) return;
    const files = supportedIds.filter((id) => selected.has(id)).map((id) => ({ file_id: id }));
    if (files.length === 0) return;

    setRegistering(true);
    setError('');
    try {
      const result = await registerDocuments(token, files);
      const ok = result.registered.length;
      const skipped = result.skipped.length;
      if (skipped > 0) {
        showToast(`${ok}건 등록, ${skipped}건 제외됨`, 'info');
      } else {
        showToast(`${ok}건을 등록했습니다.`, 'success');
      }
      // 등록한 파일은 더 이상 신규가 아니다. 목록과 이력을 함께 다시 읽는다.
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '파일을 등록하지 못했습니다.');
    } finally {
      setRegistering(false);
    }
  }

  /**
   * Drive 에서 사라진 문서를 내린다.
   *
   * 확인을 한 번 받는다. 휴지통·완전삭제·폴더 밖 이동이 우리 쪽에서 전부 똑같이
   * 「안 잡힘」으로 보여서, 잠깐 옮겨 둔 문서를 실수로 내릴 수 있다.
   */
  async function handleRemoveMissing() {
    if (!token || removing || missing.length === 0) return;

    setConfirming(false);
    setRemoving(true);
    try {
      const result = await removeDocuments(
        token,
        missing.map((doc) => doc.doc_id),
      );
      showToast(
        `${result.removed}건 정리 · 청크 ${result.chunks}건과 벡터 ${result.vectors}건을 지웠습니다.`,
        'success',
      );
      await load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : '문서를 내리지 못했습니다.', 'error');
    } finally {
      setRemoving(false);
    }
  }

  return (
    <div className={styles.page}>
      <TopNav tabs={MAIN_NAV_TABS} activeTo="/files/new" />

      <div className={styles.contentContainer}>
        <div className={styles.pageHeading}>
          <h1>문서 관리</h1>
          <p>설정된 폴더와 비교해 새 파일을 등록하고, 사라진 문서를 정리합니다</p>
        </div>

        {error && <p className={styles.stateRow}>{error}</p>}

        {/*
          Drive를 폴더 수만큼, 폴더 안 파일 수만큼 왕복한다. 지금 시연 데이터로는
          2초지만 파일이 수백 개면 그만큼 늘어나므로 미리 알린다.
        */}
        {loading && (
          <div className={styles.scanCard}>
            <Icon name="loader" size={22} color="var(--color-primary)" spin />
            <div className={styles.scanText}>
              <p className={styles.scanTitle}>Google Drive 폴더를 확인하고 있어요</p>
              <p className={styles.scanDetail}>파일이 많으면 수 분이 소요될 수 있습니다</p>
            </div>
          </div>
        )}

        {!loading && !error && !configured && (
          <p className={styles.stateRow}>
            연결된 프로젝트가 없습니다. 온보딩에서 폴더를 먼저 선택해 주세요.
          </p>
        )}

        {!loading && !error && configured && rows.length === 0 && (
          <div className={styles.tableCard}>
            <div className={styles.emptyBody}>
              <div className={styles.iconCircle}>
                <Icon name="folder-open" size={24} color="var(--color-placeholder)" />
              </div>
              <div className={styles.emptyText}>
                <p>모두 최신 상태입니다</p>
                <p>등록할 새 파일도, 정리할 문서도 없습니다</p>
              </div>
            </div>
          </div>
        )}

        {!loading && !error && configured && rows.length > 0 && (
          <FileRegistrationTable
            rows={rows}
            selected={selected}
            onToggleRow={toggleRow}
            onToggleAll={toggleAll}
            mode="submit"
            submitting={registering}
            onSubmit={handleRegister}
            onRemoveMissing={() => setConfirming(true)}
            removing={removing}
          />
        )}

        {!loading && configured && (
          <HistoryBlock
            entries={history}
            hasMore={historyHasMore}
            loading={historyLoading}
            onLoadMore={handleLoadMoreHistory}
          />
        )}
      </div>

      {/* 되돌릴 수 있는 동작이지만 한 번 묻는다. Drive 휴지통·완전삭제·폴더 밖
          이동이 우리 쪽에서 전부 똑같이 보여서, 잠깐 옮겨 둔 문서를 실수로
          내릴 수 있다. */}
      <Modal
        open={confirming}
        onClose={() => setConfirming(false)}
        title="삭제 파일 정리"
        footer={
          <>
            <Button variant="outline" onClick={() => setConfirming(false)}>
              취소
            </Button>
            <Button variant="primary" disabled={removing} onClick={() => void handleRemoveMissing()}>
              {removing ? '정리하는 중…' : `${missing.length}건 정리`}
            </Button>
          </>
        }
      >
        <p className={styles.confirmText}>
          Drive에서 삭제된 문서 <strong>{missing.length}건</strong>을 목록에서 내리고,
          <strong> 파싱해 둔 본문·청크·벡터를 함께 지웁니다.</strong> 청크에는 문서 원문이
          그대로 들어 있어 Drive에서 지운 내용을 계속 보관할 수 없습니다.
        </p>
        <p className={styles.confirmNote}>
          Drive에 파일을 되돌리면 문서는 되살아나지만, 기준 문서로 쓰려면 다시 처리해야
          합니다.
        </p>

        {/* 기준 문서가 사라지면 그 프로젝트의 업무 추출 근거가 없어진다. */}
        {missing.some((doc) => doc.proj_id) && (
          <div className={styles.confirmLinked}>
            <p>프로젝트에 묶인 문서가 포함됩니다</p>
            <ul>
              {missing
                .filter((doc) => doc.proj_id)
                .map((doc) => (
                  <li key={doc.doc_id}>
                    {doc.file_name}
                    <span>
                      {doc.project_name} {doc.doc_role === 'PRIMARY' ? '기준 문서' : '근거 문서'}
                    </span>
                  </li>
                ))}
            </ul>
          </div>
        )}
      </Modal>
    </div>
  );
}

interface HistoryBlockProps {
  entries: DocumentHistoryEntry[];
  hasMore: boolean;
  loading: boolean;
  onLoadMore: () => void;
}

function HistoryBlock({ entries, hasMore, loading, onLoadMore }: HistoryBlockProps) {
  return (
    <div className={styles.historyBlock}>
      <h2>최근 처리 이력</h2>
      <div className={styles.historyCard}>
        {entries.map((entry) => (
          <div key={entry.audit_id} className={styles.historyRow}>
            <div className={styles.historyLeft}>
              <span className={styles.historyDate}>{formatDate(entry.occurred_at)}</span>
              <span className={styles.historyLabel}>{historyLabel(entry)}</span>
            </div>
            <Badge tone={entry.status === 'OK' ? 'success' : 'warning'}>
              {STATUS_LABEL[entry.status] ?? entry.status}
            </Badge>
          </div>
        ))}
        {entries.length === 0 && <p className={styles.historyEmpty}>최근 처리 이력이 없습니다.</p>}
        {hasMore && (
          <button
            type="button"
            className={styles.historyMore}
            onClick={onLoadMore}
            disabled={loading}
          >
            {loading ? '불러오는 중…' : '더 보기'}
          </button>
        )}
      </div>
    </div>
  );
}
