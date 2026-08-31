import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { AppShell, Badge, Button, Icon, InfoNote, useToast } from '../../components';
import type { BadgeTone, IconName } from '../../components';
import { ApiError } from '../../api/client';
import { fetchDocumentLibrary, reindexTeamDocument } from '../../api/documentLibrary';
import type { DocumentLibrary, LibraryDocument, LibraryFolder } from '../../api/documentLibrary';
import { notifyIndexingStarted } from '../../utils/indexingSignal';
import { useSession } from '../../utils/session';
import { MyFilesPanel } from './MyFilesPanel';
import type { PersonalTab } from './MyFilesPanel';
import { DocumentPagination } from './DocumentPagination';
import styles from './DocumentsPage.module.css';

/**
 * 「문서」 — 에이전트가 검색하는 것이 지금 어떤 상태인가.
 *
 * 좌측이 탐색기의 트리, 우측이 그 자리의 파일이다. 저장소(커넥터 연결)로 먼저
 * 묶고 그 아래에 사람이 고른 폴더, 다시 그 아래에 하위 경로가 온다.
 *
 * ## 왜 이 화면이 다시 생겼나
 *
 * `ac64372` 에서 한 번 지웠던 화면이다. 그때 이유는 「본문은 필요해질 때 읽는다 —
 * 사람이 문서 상태를 들여다볼 자리가 따로 있을 이유가 없다」였고, 그 시절엔
 * 맞는 말이었다. **2026-08-24 에 전량 색인으로 바뀌면서 전제가 만료됐다** —
 * 이제 폴더를 저장하는 순간 문서당 100초씩 색인이 돌고, 그동안 사람은 기다린다.
 * 기다림과 실패가 「파이프라인의 사정」에서 **사용자의 시간**이 됐는데 그것을
 * 보여줄 자리가 없었다(2026-08-25 에 평가 문서 8종이 조용히 안 들어온 것을
 * 로그를 뒤져서야 알았다).
 *
 * ## 여기서 하는 일은 둘뿐이다
 *
 * **무엇이 어떤 상태인가**와 **안 된 것을 다시 시킨다.** 정렬·필터·삭제 같은
 * 관리 기능은 넣지 않는다 — 지울 때의 판단("목록·상태·필터는 우리 파이프라인의
 * 사정이지 사용자가 할 일이 아니다")이 그 부분은 여전히 옳다. 문서를 내리는
 * 것은 폴더 설정이 하고, 여기는 **왜 안 되는지 보고 다시 시키는** 자리다.
 *
 * ## 트리는 어디서 오나
 *
 * 폴더 표를 따로 두지 않았다. 뿌리는 `team_folder`(사람이 고른 폴더)이고 그
 * 아래 가지는 문서들이 들고 있는 `src_folder_path` 의 서로 다른 값이다. Drive
 * 에서 폴더가 바뀌어도 다음 수집이 문서와 함께 갱신하므로 맞춰 줄 두 번째
 * 자리가 없다.
 */

/** 저장소 이름. 지금 붙는 것은 Drive 뿐이지만 자리는 연결마다 하나씩이다. */
const STORE_LABEL: Record<string, string> = {
  GOOGLE_DRIVE: 'Google Drive',
  JIRA: 'Jira',
  PEOPLE_DB: '인사 시스템',
};

/**
 * 쪽당 표시 개수. 기본 25 는 1080 높이에서 한 화면에 거의 들어가는 수다 —
 * 더 크게 잡으면 표가 페이지 스크롤을 타고, 그러면 트리를 고정한 의미가 없다.
 */
const PAGE_SIZES = [10, 25, 50, 100];

/** 「개인 문서」 아래 두 갈래. 순서가 곧 화면 순서다. */
const PERSONAL_NODES = [
  { tab: 'mine', label: '내 파일', icon: 'file-text' },
  { tab: 'shared', label: '공유 받은 파일', icon: 'users' },
] as const satisfies readonly { tab: PersonalTab; label: string; icon: IconName }[];

/** 날짜만 쓴다. 문서가 언제 고쳐졌는지에 분·초는 판단에 안 쓰인다. */
function formatDate(iso: string | null): string {
  if (!iso) return '-';
  return iso.slice(0, 10).replace(/-/g, '.');
}

/**
 * 트리에서 고른 자리. 개인 문서는 폴더가 아니라 별도 갈래다.
 *
 * **「내 파일」 안에 탭으로 「공유 받은 파일」이 들어 있었다**(2026-08-26 정리).
 * 받은 파일은 내 파일의 하위가 아니라 나란한 것인데 이름이 그것을 뒤집어
 * 말했다. 둘을 「개인 문서」 아래 형제로 세우고, 고르는 일은 트리가 한다 —
 * 왼쪽에서 자리를 고르는 화면에서 오른쪽이 또 탭으로 자리를 고르면 지금 어디를
 * 보고 있는지가 두 곳에 적힌다.
 */
type Selection =
  | { kind: 'folder'; folderId: string | null; path: string | null }
  | { kind: 'personal'; tab: PersonalTab };

/**
 * 상태 칩. **사용자가 알고 싶은 것은 「이 문서를 쓸 수 있나」 하나다.**
 *
 * 「검색 준비됨」·「색인 대기」·「원문 대기」로 넷을 갈랐던 것을 셋으로 줄였다.
 * 그 넷은 우리 파이프라인의 단계이지 사람이 구별해서 할 일이 아니다 — 원문을
 * 아직 못 받았든 워커 차례를 기다리든, 할 수 있는 것은 기다리는 것 하나다.
 * 「검색」도 우리 쪽 말이라 걷었다: 사용자는 "무슨 검색?"이라고 되묻는다.
 *
 * 「내 파일」(`MyFilesPanel`)과 **같은 말을 쓴다** — 같은 파이프라인의 같은
 * 상태라 다른 낱말을 쓰면 사람이 두 번 배운다.
 */
function statusChip(doc: LibraryDocument): { tone: BadgeTone; label: string; hint: string } {
  if (doc.index_status === 'FAILED') {
    return {
      tone: 'warning',
      label: '읽기 실패',
      hint: doc.index_detail ?? '읽을 수 없는 형식이거나, 글자를 뽑을 수 없는 파일일 수 있습니다.',
    };
  }
  if (doc.search_ready) {
    return { tone: 'success', label: '사용 가능', hint: '' };
  }
  return { tone: 'info', label: '읽는 중', hint: '' };
}

/** 한 폴더 아래에 실제로 존재하는 하위 경로들. 문서가 들고 있는 값에서 나온다. */
function pathsOf(documents: LibraryDocument[], folderId: string): string[] {
  const seen = new Set<string>();
  for (const doc of documents) {
    // `null` 은 「모른다」라 가지로 세우지 않는다. 그 문서들은 폴더 자신에 매단다.
    if (doc.team_folder_id === folderId && doc.src_folder_path) seen.add(doc.src_folder_path);
  }
  return [...seen].sort((a, b) => a.localeCompare(b, 'ko'));
}

export default function DocumentsPage() {
  const session = useSession();
  const token = session?.token;
  const { showToast } = useToast();

  const [library, setLibrary] = useState<DocumentLibrary>({ folders: [], documents: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  /**
   * 어느 자리를 보고 있는가. **처음에는 정하지 못한다** — 무엇이 있는지 받아
   * 봐야 안다. 고정 기본값을 두면(예: 「미분류」) 수집이 제대로 돈 팀은 그
   * 갈래가 아예 없어서 **빈 화면으로 열린다.**
   */
  const [selection, setSelection] = useState<Selection | null>(null);
  /** 접힌 폴더. 기본은 펼침 — 처음 열었을 때 무엇이 있는지 보여야 한다. */
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  /**
   * 채팅의 「근거」 링크로 들어오면 `?file=<doc_id>` 가 붙는다(2026-08-28).
   * 그 파일이 있는 「내 파일」로 자리를 옮기고, 목록이 그 줄을 강조하게 한다.
   */
  const [searchParams, setSearchParams] = useSearchParams();
  const focusFileId = searchParams.get('file');
  useEffect(() => {
    if (!focusFileId) return;
    setSelection({ kind: 'personal', tab: 'mine' });
  }, [focusFileId]);
  /**
   * 파일 이름으로 좁힌다. **고른 자리 안에서만 찾는다** — 트리로 자리를 고르는
   * 화면에서 검색이 그 자리를 무시하면, 보고 있는 폴더와 결과가 어긋나 어느
   * 쪽이 진짜인지 알 수 없게 된다. 폴더를 고르면 하위 경로까지 포함하므로
   * 탐색기에서 폴더 안을 찾는 것과 같은 범위다.
   */
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      setLibrary(await fetchDocumentLibrary(token));
      setError('');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '문서를 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  /**
   * 아직 끝나지 않은 문서가 있는 동안만 다시 받는다. 「내 파일」이 쓰는 방식과
   * 같다 — 색인은 몇 분짜리라 새로고침해야 상태가 바뀌면 사람은 「안 되는 것」
   * 으로 읽는다. **끝난 뒤에는 안 돈다.**
   */
  const pending = useMemo(
    () =>
      library.documents.some(
        (doc) => doc.index_status === 'RUNNING' || (doc.downloaded && !doc.search_ready && doc.index_status !== 'FAILED'),
      ),
    [library.documents],
  );

  useEffect(() => {
    if (!pending) return;
    const timer = setInterval(() => void load(), 5_000);
    return () => clearInterval(timer);
  }, [pending, load]);

  async function retry(doc: LibraryDocument) {
    if (!token) return;
    setBusy(doc.doc_id);
    try {
      await reindexTeamDocument(token, doc.doc_id);
      // 한 건이어도 워커가 도는 것은 같다. 전역 카드에도 잡히게 알린다.
      notifyIndexingStarted();
      // 낙관적으로 「읽는 중」으로 바꾼다. 서버도 곧 같은 값을 주지만, 폴링
      // 간격만큼은 버튼이 아무 반응 없어 보인다.
      setLibrary((prev) => ({
        ...prev,
        documents: prev.documents.map((row) =>
          row.doc_id === doc.doc_id ? { ...row, index_status: 'RUNNING', index_detail: null } : row,
        ),
      }));
      showToast(`${doc.file_name ?? doc.doc_id} · 다시 읽습니다.`, 'success');
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : '다시 시작하지 못했습니다.', 'error');
    } finally {
      setBusy(null);
    }
  }

  /** 저장소별로 묶은 폴더. 연결 하나에 폴더 여럿이다. */
  const stores = useMemo(() => {
    const grouped = new Map<string, { conn: LibraryFolder; folders: LibraryFolder[] }>();
    for (const folder of library.folders) {
      const bucket = grouped.get(folder.conn_id);
      if (bucket) bucket.folders.push(folder);
      else grouped.set(folder.conn_id, { conn: folder, folders: [folder] });
    }
    return [...grouped.values()];
  }, [library.folders]);

  /** 폴더를 모르는 문서가 있는가. 있으면 트리에 「미분류」 갈래를 세운다. */
  const hasUnfiled = useMemo(
    () => library.documents.some((doc) => doc.team_folder_id === null),
    [library.documents],
  );

  /**
   * 처음 받아 온 뒤 **한 번만** 자리를 정한다. 첫 폴더 → 미분류 → 내 파일 순이다.
   * 사람이 고른 뒤에는 다시 안 건드린다(폴링이 목록을 갱신해도 보던 자리가
   * 튀면 안 된다).
   */
  useEffect(() => {
    if (selection !== null || loading) return;
    const first = library.folders[0];
    if (first) setSelection({ kind: 'folder', folderId: first.team_folder_id, path: null });
    else if (hasUnfiled) setSelection({ kind: 'folder', folderId: null, path: null });
    else setSelection({ kind: 'personal', tab: 'mine' });
  }, [loading, library.folders, hasUnfiled, selection]);

  const visibleDocuments = useMemo(() => {
    if (selection === null || selection.kind === 'personal') return [];
    return library.documents.filter((doc) => {
      if (doc.team_folder_id !== selection.folderId) return false;
      // 폴더 자신을 고르면 그 아래 전부를 보여준다. 경로를 고르면 그것만.
      if (selection.path === null) return true;
      return doc.src_folder_path === selection.path;
    });
  }, [library.documents, selection]);

  /** 이름으로 좁힌 결과. 페이지네이션의 모수이기도 하다. */
  const matched = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return visibleDocuments;
    return visibleDocuments.filter((doc) => {
      // 경로도 함께 본다 — 「기획」으로 찾으면 그 폴더 안의 파일이 나와야
      // 사람이 기대한 대로다. 이름만 보면 폴더명으로는 아무것도 안 걸린다.
      const haystack = `${doc.file_name ?? doc.doc_id} ${doc.src_folder_path ?? ''}`.toLowerCase();
      return haystack.includes(needle);
    });
  }, [visibleDocuments, query]);

  const pageCount = Math.max(1, Math.ceil(matched.length / pageSize));
  /**
   * **현재 쪽이 범위를 넘으면 마지막 쪽으로 당긴다.** 3쪽을 보다가 검색을 걸어
   * 결과가 한 쪽으로 줄면 빈 표가 뜬다 — 그 자리에서 계산으로 막고, 상태를
   * 고치는 것은 아래 effect 가 한다(렌더 중에 setState 하지 않는다).
   */
  const safePage = Math.min(page, pageCount);
  const paged = useMemo(
    () => matched.slice((safePage - 1) * pageSize, safePage * pageSize),
    [matched, safePage, pageSize],
  );

  /** 자리를 옮기거나 검색어가 바뀌면 첫 쪽으로. 보던 쪽 번호를 물고 가면 빈 표가 뜬다. */
  useEffect(() => {
    setPage(1);
  }, [selection, query, pageSize]);

  useEffect(() => {
    if (page !== safePage) setPage(safePage);
  }, [page, safePage]);

  function countIn(folderId: string | null): number {
    return library.documents.filter((doc) => doc.team_folder_id === folderId).length;
  }

  function toggleCollapse(folderId: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(folderId)) next.delete(folderId);
      else next.add(folderId);
      return next;
    });
  }

  function isSelected(folderId: string | null, path: string | null): boolean {
    return (
      selection?.kind === 'folder' && selection.folderId === folderId && selection.path === path
    );
  }

  /** 우측 제목. 지금 보고 있는 자리가 어디인지 한 줄로 말한다. */
  const heading = useMemo(() => {
    if (selection === null) return '';
    if (selection.kind === 'personal') return selection.tab === 'mine' ? '내 파일' : '공유 받은 파일';
    if (selection.folderId === null) return '미분류';
    const folder = library.folders.find((row) => row.team_folder_id === selection.folderId);
    const name = folder?.display_name ?? folder?.external_folder_id ?? selection.folderId;
    return selection.path ? `${name} / ${selection.path}` : name;
  }, [selection, library.folders]);

  /**
   * 아직 못 쓰는 문서 수. **좁힌 결과를 센다** — 한 줄에 나란히 붙는
   * 「15 / 45건」과 같은 모수를 봐야 한다. 전체를 세면 15건을 걸러 놓고
   * 그 뒤 숫자가 따라붙어, 보이는 15건 안에 있는 줄로 읽힌다.
   *
   * **실패한 것을 「읽는 중」에 넣지 않는다.** `search_ready` 만 보면 실패도
   * 거짓이라 같이 세어졌고, 줄에는 「읽기 실패」라고 적혀 있는데 머리말은
   * 「읽는 중 2」라고 말했다(2026-08-26). 한 화면이 같은 문서를 두고 서로 다른
   * 말을 하면 사람은 올린 것 자체가 안 됐다고 읽는다.
   */
  const notReady = matched.filter(
    (doc) => !doc.search_ready && doc.index_status !== 'FAILED',
  ).length;
  const failed = matched.filter((doc) => doc.index_status === 'FAILED').length;

  return (
    <AppShell>
      <div className={styles.page}>
        <header className={styles.pageHeader}>
          <h1>문서</h1>
          <div className={styles.pageHelp}>
            <InfoNote title="문서">
              {/* **네 문단이었다.** 파이프라인 사정을 문단마다 설명하고 있었는데,
                  읽는 사람이 알아야 할 것은 「무엇을 쓰는가」와 「어디서 정하는가」
                  둘뿐이다. 나머지는 상태 칩이 이미 말한다. */}
              <p>
                에이전트가 답을 찾을 때 보는 문서입니다. <strong>사용 가능</strong>인 문서만 씁니다.
              </p>
              <p>어떤 폴더를 읽을지는 설정 &gt; 커넥터에서 정합니다.</p>
            </InfoNote>
          </div>
        </header>

        {error && <p className={styles.error}>{error}</p>}

        <div className={styles.split}>
          {/* ── 좌측: 탐색기 트리 ───────────────────────────────── */}
          <nav className={styles.tree} aria-label="문서 위치">
            {stores.map((store) => (
              <div key={store.conn.conn_id} className={styles.store}>
                <div className={styles.storeHead}>
                  <Icon name="database" size={14} color="var(--color-muted)" />
                  <span>{STORE_LABEL[store.conn.connector_type ?? ''] ?? '알 수 없는 저장소'}</span>
                  {/* 연결이 만료·해제됐으면 그 사실이 이 트리 전체의 전제다.
                      새 문서가 안 들어오는 이유가 여기 있는데 안 보이면
                      「왜 그대로지」가 된다. */}
                  {store.conn.auth_status && store.conn.auth_status !== 'CONNECTED' && (
                    <Badge tone="warning">연결 확인 필요</Badge>
                  )}
                </div>

                {store.folders.map((folder) => {
                  const paths = pathsOf(library.documents, folder.team_folder_id);
                  const open = !collapsed.has(folder.team_folder_id);
                  return (
                    <div key={folder.team_folder_id}>
                      <div className={styles.folderRow}>
                        {paths.length > 0 ? (
                          <button
                            type="button"
                            className={styles.twisty}
                            onClick={() => toggleCollapse(folder.team_folder_id)}
                            aria-label={open ? '접기' : '펼치기'}
                            aria-expanded={open}
                          >
                            <Icon name={open ? 'chevron-down' : 'chevron-right'} size={13} />
                          </button>
                        ) : (
                          <span className={styles.twistySpacer} />
                        )}
                        <button
                          type="button"
                          className={[
                            styles.node,
                            isSelected(folder.team_folder_id, null) ? styles.nodeOn : '',
                          ]
                            .filter(Boolean)
                            .join(' ')}
                          onClick={() =>
                            setSelection({ kind: 'folder', folderId: folder.team_folder_id, path: null })
                          }
                        >
                          <Icon name={open ? 'folder-open' : 'folder'} size={15} />
                          <span className={styles.nodeName}>
                            {folder.display_name ?? folder.external_folder_id}
                          </span>
                          <span className={styles.nodeCount}>{countIn(folder.team_folder_id)}</span>
                        </button>
                      </div>

                      {open &&
                        paths.map((path) => (
                          <div key={path} className={styles.childRow}>
                            <button
                              type="button"
                              className={[
                                styles.node,
                                isSelected(folder.team_folder_id, path) ? styles.nodeOn : '',
                              ]
                                .filter(Boolean)
                                .join(' ')}
                              onClick={() =>
                                setSelection({ kind: 'folder', folderId: folder.team_folder_id, path })
                              }
                            >
                              <Icon name="folder" size={14} />
                              <span className={styles.nodeName}>{path}</span>
                            </button>
                          </div>
                        ))}
                    </div>
                  );
                })}
              </div>
            ))}

            {/* 폴더를 모르는 문서. **숨기지 않는다** — 이 칸이 생기기 전에 등록된
                문서라 어디에도 안 매달리는데, 안 보이면 목록에서 사라진 것이 된다.
                다음 수집이 제자리를 찾아 준다. */}
            {hasUnfiled && (
              <div className={styles.store}>
                <div className={styles.storeHead}>
                  <Icon name="circle-help" size={14} color="var(--color-muted)" />
                  <span>미분류</span>
                </div>
                <div className={styles.folderRow}>
                  <span className={styles.twistySpacer} />
                  <button
                    type="button"
                    className={[styles.node, isSelected(null, null) ? styles.nodeOn : ''].filter(Boolean).join(' ')}
                    onClick={() => setSelection({ kind: 'folder', folderId: null, path: null })}
                  >
                    <Icon name="folder" size={15} />
                    <span className={styles.nodeName}>폴더를 모르는 문서</span>
                    <span className={styles.nodeCount}>{countIn(null)}</span>
                  </button>
                </div>
              </div>
            )}

            {/* 저장소가 아니라 사람이 들고 있는 것이라 갈래를 따로 세운다.
                내 것과 받은 것은 **나란한 둘**이다 — 받은 파일이 「내 파일」
                안쪽 탭에 있던 것을 여기로 끌어냈다(2026-08-26). */}
            <div className={styles.store}>
              <div className={styles.storeHead}>
                <Icon name="user" size={14} color="var(--color-muted)" />
                <span>개인 문서</span>
              </div>
              {PERSONAL_NODES.map((node) => (
                <div key={node.tab} className={styles.folderRow}>
                  <span className={styles.twistySpacer} />
                  <button
                    type="button"
                    className={[
                      styles.node,
                      selection?.kind === 'personal' && selection.tab === node.tab ? styles.nodeOn : '',
                    ]
                      .filter(Boolean)
                      .join(' ')}
                    onClick={() => setSelection({ kind: 'personal', tab: node.tab })}
                  >
                    <Icon name={node.icon} size={15} />
                    <span className={styles.nodeName}>{node.label}</span>
                  </button>
                </div>
              ))}
            </div>

            {!loading && stores.length === 0 && !hasUnfiled && (
              <p className={styles.treeEmpty}>
                아직 읽을 폴더가 없습니다. 설정 &gt; 커넥터에서 문서 저장소를 연결하고 폴더를 고르세요.
              </p>
            )}
          </nav>

          {/* ── 우측: 그 자리의 파일 ────────────────────────────── */}
          <section className={styles.panel}>
            {selection?.kind === 'personal' ? (
              <MyFilesPanel
                tab={selection.tab}
                focusDocId={selection.tab === 'mine' ? focusFileId : null}
                onFocusHandled={() => {
                  const next = new URLSearchParams(searchParams);
                  next.delete('file');
                  setSearchParams(next, { replace: true });
                }}
              />
            ) : (
              <>
                <div className={styles.panelHead}>
                  <h2 className={styles.panelTitle}>{heading}</h2>
                  <span className={styles.panelCount}>
                    {/* 검색 중이면 「몇 중 몇」을 말한다 — 결과 수만 보이면
                        사라진 문서가 지워진 것인지 걸러진 것인지 알 수 없다. */}
                    {query.trim() ? `${matched.length} / ${visibleDocuments.length}건` : `${visibleDocuments.length}건`}
                    {notReady > 0 && <span className={styles.panelWarn}> · 읽는 중 {notReady}</span>}
                    {failed > 0 && <span className={styles.panelWarn}> · 읽기 실패 {failed}</span>}
                  </span>
                </div>

                <div className={styles.toolbar}>
                  <div className={styles.searchBox}>
                    <Icon name="search" size={15} color="var(--color-placeholder)" />
                    <input
                      type="text"
                      className={styles.searchInput}
                      placeholder="이 폴더에서 파일 이름 검색..."
                      value={query}
                      onChange={(event) => setQuery(event.target.value)}
                    />
                    {query && (
                      <button
                        type="button"
                        className={styles.searchClear}
                        onClick={() => setQuery('')}
                        aria-label="검색어 지우기"
                      >
                        <Icon name="x" size={13} />
                      </button>
                    )}
                  </div>
                  <label className={styles.pageSize}>
                    <span>쪽당</span>
                    <select
                      value={pageSize}
                      onChange={(event) => setPageSize(Number(event.target.value))}
                      aria-label="쪽당 표시 개수"
                    >
                      {PAGE_SIZES.map((size) => (
                        <option key={size} value={size}>
                          {size}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                {/* **비어 있어도 표는 남긴다**(2026-08-27) — 「내 파일」
                    (`MyFilesPanel`)·팀원 목록(`TeamTab`)·업무 목록
                    (`ProjectDetailPage`)과 같은 방식이다. 표가 통째로 사라지면
                    같은 페이지인데 트리에서 무엇을 고르느냐에 따라 빈 화면
                    모양이 갈렸다. */}
                <div className={styles.table}>
                  {/* 헤더를 스크롤 컨테이너 **안에** 둔다. 밖에 두면 목록에
                      스크롤바가 생길 때 행만 좁아져 열이 어긋난다
                      (`ProjectDetailPage` 업무 목록과 같은 이유). */}
                  <div className={styles.tableHead}>
                    <span>문서</span>
                    <span>위치</span>
                    <span>상태</span>
                    <span>수정</span>
                    <span />
                  </div>

                  {loading && (
                    <div className={styles.tableEmpty}>
                      <span className={styles.tableEmptyIcon}>
                        <Icon name="loader" size={22} color="var(--color-primary)" spin />
                      </span>
                      <p className={styles.tableEmptyTitle}>문서를 불러오는 중…</p>
                    </div>
                  )}

                  {/* 검색으로 0건인 것과 폴더가 원래 빈 것은 다른 상태다.
                      아이콘도 그 둘을 갈라 준다 — 「내 파일」과 같은 꼴이다. */}
                  {!loading && matched.length === 0 && (
                    <div className={styles.tableEmpty}>
                      <span className={styles.tableEmptyIcon}>
                        <Icon
                          name={visibleDocuments.length > 0 ? 'search' : 'folder-open'}
                          size={22}
                          color="var(--color-primary)"
                        />
                      </span>
                      <p className={styles.tableEmptyTitle}>
                        {visibleDocuments.length > 0
                          ? '검색 결과가 없습니다.'
                          : '이 폴더에서 읽어 온 문서가 없습니다.'}
                      </p>
                    </div>
                  )}

                  {paged.map((doc) => {
                    const chip = statusChip(doc);
                    return (
                      <div key={doc.doc_id} className={styles.tableRow}>
                        <span className={styles.cellName}>
                          <Icon name="file-text" size={15} color="var(--color-primary)" />
                          <span className={styles.cellNameText}>
                            <span className={styles.fileName}>{doc.file_name ?? doc.doc_id}</span>
                            {/* 실패 사유는 이름 아래에 붙인다. 열로 만들면 표가
                                못 읽을 만큼 좁아지고, 성공한 행은 그 열이 늘 빈다. */}
                            {chip.hint && (
                              <span className={`${styles.cellHint} ${styles.rowDetail}`} title={chip.hint}>
                                {chip.hint}
                              </span>
                            )}
                          </span>
                        </span>

                        {/* 하위 폴더에서 온 문서는 어디서 왔는지 밝힌다 —
                            폴더를 고르면 아래 전부가 나오므로 필요하다. */}
                        <span className={styles.cellPath} data-label="위치">
                          {doc.src_folder_path ? doc.src_folder_path : <span className={styles.dim}>—</span>}
                        </span>

                        <span className={styles.cellStatus} data-label="상태">
                          <Badge tone={chip.tone}>{chip.label}</Badge>
                          {/* 기준 문서는 지우거나 바꿀 때 파장이 다르다. */}
                          {doc.doc_role === 'PRIMARY' && <Badge tone="info">기준 문서</Badge>}
                          {doc.access_revoked && <Badge tone="warning">접근 권한 없음</Badge>}
                        </span>

                        <span className={styles.cellDate} data-label="수정">
                          {formatDate(doc.src_modified_at)}
                        </span>

                        <span className={styles.cellActions} data-label="작업">
                          {/* **「읽는 중」에는 안 보여준다.** 상태를 셋으로 합치면서
                              차례를 기다리는 문서(`index_status` 가 아직 null 인 것)에도
                              버튼이 뜨고 있었다 — 칩은 「읽는 중」이라고 하는데 옆에서
                              다시 읽으라고 권하는 꼴이라, 사람은 뭔가 잘못된 줄 안다.

                              눌러야 하는 상황이 있지 않을까 싶지만 없다. 워커가 죽어
                              `RUNNING` 인 채로 멈춘 문서도 **다음 수집이 다시 집는다**
                              (`list_pending_index` 는 `FAILED` 만 뺀다). 원문을 아직
                              못 받은 것도 같은 이유로 여기 안 걸린다.

                              남는 것은 둘 — 다 읽은 것을 새로 읽히거나, 실패한 것을
                              다시 시키거나. */}
                          {(doc.search_ready || doc.index_status === 'FAILED') && (
                            <Button
                              size="sm"
                              variant="outline"
                              aria-label={`${doc.file_name ?? doc.doc_id} 다시 읽기`}
                              disabled={busy === doc.doc_id}
                              onClick={() => void retry(doc)}
                            >
                              다시 읽기
                            </Button>
                          )}
                        </span>
                      </div>
                    );
                  })}
                </div>

                {/* 한 쪽에 다 들어가면 안 그린다 — 누를 수 없는 컨트롤이 자리만
                    차지한다. 번호는 현재 쪽 주변 최대 5개를 중앙에 모아 보여 준다. */}
                <DocumentPagination page={safePage} pageCount={pageCount} onPageChange={setPage} />
              </>
            )}
          </section>
        </div>
      </div>
    </AppShell>
  );
}
