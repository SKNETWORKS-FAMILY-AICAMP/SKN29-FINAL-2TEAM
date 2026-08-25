import { useCallback, useEffect, useMemo, useState } from 'react';
import { AppShell, Badge, Button, Icon, InfoNote, useToast } from '../../components';
import type { BadgeTone } from '../../components';
import { ApiError } from '../../api/client';
import { fetchDocumentLibrary, reindexTeamDocument } from '../../api/documentLibrary';
import type { DocumentLibrary, LibraryDocument, LibraryFolder } from '../../api/documentLibrary';
import { useSession } from '../../utils/session';
// 「내 파일」은 자리만 옮기고 화면은 그대로 쓴다. 업로드·검색 토글·팀 공유·삭제가
// 이미 붙어 있고 동작이 검증돼 있어서, 여기서 다시 짜면 그 검증을 버리게 된다.
// 파일이 아직 SettingsPage 밑에 있는 것은 `tabs.module.css` 를 커넥터·스킬 탭과
// 함께 쓰기 때문이다 — 옮기면 그 셋이 CSS 를 서로 건너 참조하게 된다.
import { MyFilesTab } from '../SettingsPage/tabs/MyFilesTab';
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

/** 트리에서 고른 자리. 「내 파일」은 폴더가 아니라 별도 갈래다. */
type Selection =
  | { kind: 'folder'; folderId: string | null; path: string | null }
  | { kind: 'mine' };

/**
 * 색인 상태 칩. 「내 파일」의 `statusChip` 과 **같은 말을 쓴다** — 같은 파이프
 * 라인의 같은 상태라 다른 낱말을 쓰면 사람이 두 번 배운다.
 *
 * 넷을 가른다. 원문을 아직 안 받은 것과 받아 놓고 색인을 안 돌린 것은 사람이
 * 할 일이 다르고, 돌고 있는 것과 실패한 것은 말할 것도 없다.
 */
function statusChip(doc: LibraryDocument): { tone: BadgeTone; label: string; hint: string } {
  if (doc.index_status === 'FAILED') {
    return {
      tone: 'warning',
      label: '본문 색인 실패',
      hint: doc.index_detail ?? '읽을 수 없는 형식이거나, 글자를 뽑을 수 없는 파일일 수 있습니다.',
    };
  }
  if (doc.index_status === 'RUNNING') {
    return { tone: 'info', label: '읽는 중', hint: '' };
  }
  if (doc.search_ready) {
    return { tone: 'success', label: '검색 준비됨', hint: '' };
  }
  if (!doc.downloaded) {
    return { tone: 'neutral', label: '원문 대기', hint: '아직 원문을 받지 않아 색인을 시작할 수 없습니다.' };
  }
  return { tone: 'neutral', label: '색인 대기', hint: '' };
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
    const timer = setInterval(() => void load(), 10_000);
    return () => clearInterval(timer);
  }, [pending, load]);

  async function retry(doc: LibraryDocument) {
    if (!token) return;
    setBusy(doc.doc_id);
    try {
      await reindexTeamDocument(token, doc.doc_id);
      // 낙관적으로 「읽는 중」으로 바꾼다. 서버도 곧 같은 값을 주지만, 폴링이
      // 10초라 그때까지 버튼이 아무 반응 없어 보인다.
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
    else setSelection({ kind: 'mine' });
  }, [loading, library.folders, hasUnfiled, selection]);

  const visibleDocuments = useMemo(() => {
    if (selection === null || selection.kind === 'mine') return [];
    return library.documents.filter((doc) => {
      if (doc.team_folder_id !== selection.folderId) return false;
      // 폴더 자신을 고르면 그 아래 전부를 보여준다. 경로를 고르면 그것만.
      if (selection.path === null) return true;
      return doc.src_folder_path === selection.path;
    });
  }, [library.documents, selection]);

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
    if (selection.kind === 'mine') return '내 파일';
    if (selection.folderId === null) return '미분류';
    const folder = library.folders.find((row) => row.team_folder_id === selection.folderId);
    const name = folder?.display_name ?? folder?.external_folder_id ?? selection.folderId;
    return selection.path ? `${name} / ${selection.path}` : name;
  }, [selection, library.folders]);

  /** 이 자리에서 아직 검색에 못 쓰는 문서 수. 제목 옆 요약이 된다. */
  const notReady = visibleDocuments.filter((doc) => !doc.search_ready).length;

  return (
    <AppShell>
      <div className={styles.page}>
        <header className={styles.pageHeader}>
          <h1>
            문서
            <InfoNote title="문서">
              <p>
                에이전트가 답을 찾을 때 보는 문서입니다. <strong>커넥터가 가져온 팀 문서</strong>와
                <strong> 내가 올린 파일</strong>이 함께 있습니다.
              </p>
              <p>
                <strong>검색 준비됨</strong>이라야 문장 근거로 쓰입니다. 폴더를 저장하면 그 안의 문서를
                전부 읽어 들이는데, 문서 하나에 몇 분씩 걸리고 순서대로 돕니다.
              </p>
              <p>
                실패한 문서는 사유와 함께 표시됩니다. <strong>다시 읽기</strong>로 그 문서만 다시 시킬 수
                있습니다.
              </p>
              <p>어떤 폴더를 읽을지 정하는 곳은 설정 &gt; 커넥터입니다.</p>
            </InfoNote>
          </h1>
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

            {/* 내 파일은 저장소가 아니라 내가 올린 것이라 갈래를 따로 세운다. */}
            <div className={styles.store}>
              <div className={styles.storeHead}>
                <Icon name="user" size={14} color="var(--color-muted)" />
                <span>내가 올린 것</span>
              </div>
              <div className={styles.folderRow}>
                <span className={styles.twistySpacer} />
                <button
                  type="button"
                  className={[styles.node, selection?.kind === 'mine' ? styles.nodeOn : ''].filter(Boolean).join(' ')}
                  onClick={() => setSelection({ kind: 'mine' })}
                >
                  <Icon name="file-text" size={15} />
                  <span className={styles.nodeName}>내 파일</span>
                </button>
              </div>
            </div>

            {!loading && stores.length === 0 && !hasUnfiled && (
              <p className={styles.treeEmpty}>
                아직 읽을 폴더가 없습니다. 설정 &gt; 커넥터에서 문서 저장소를 연결하고 폴더를 고르세요.
              </p>
            )}
          </nav>

          {/* ── 우측: 그 자리의 파일 ────────────────────────────── */}
          <section className={styles.panel}>
            {selection?.kind === 'mine' ? (
              // 「내 파일」은 화면을 그대로 쓴다. 업로드·검색 토글·팀 공유·삭제가
              // 이미 붙어 있고, 여기서 다시 짜면 그 검증을 버린다.
              <MyFilesTab />
            ) : (
              <>
                <div className={styles.panelHead}>
                  <h2 className={styles.panelTitle}>{heading}</h2>
                  <span className={styles.panelCount}>
                    {visibleDocuments.length}건
                    {notReady > 0 && <span className={styles.panelWarn}> · 검색 대기 {notReady}</span>}
                  </span>
                </div>

                {loading && <p className={styles.muted}>문서를 불러오는 중…</p>}

                {!loading && visibleDocuments.length === 0 && (
                  <p className={styles.muted}>이 폴더에서 읽어 온 문서가 없습니다.</p>
                )}

                <div className={styles.list}>
                  {visibleDocuments.map((doc) => {
                    const chip = statusChip(doc);
                    return (
                      <div key={doc.doc_id} className={styles.row}>
                        <span className={styles.rowIcon}>
                          <Icon name="file-text" size={18} color="var(--color-primary)" />
                        </span>
                        <div className={styles.rowBody}>
                          <span className={styles.rowName}>
                            {doc.file_name ?? doc.doc_id}
                            <Badge tone={chip.tone}>{chip.label}</Badge>
                            {/* 기준 문서는 지우거나 바꿀 때 파장이 다르다. */}
                            {doc.doc_role === 'PRIMARY' && <Badge tone="info">기준 문서</Badge>}
                            {doc.access_revoked && <Badge tone="warning">접근 권한 없음</Badge>}
                          </span>
                          {/* 하위 폴더에서 온 문서는 어디서 왔는지 밝힌다 —
                              폴더를 고르면 아래 전부가 나오므로 필요하다. */}
                          {selection?.kind === 'folder' && selection.path === null && doc.src_folder_path && (
                            <span className={styles.rowMeta}>{doc.src_folder_path}</span>
                          )}
                          {chip.hint && (
                            <span className={`${styles.rowMeta} ${styles.rowDetail}`} title={chip.hint}>
                              {chip.hint}
                            </span>
                          )}
                        </div>
                        <div className={styles.rowActions}>
                          {/* 원문이 없으면 색인이 시작조차 못 하므로 안 보여준다 —
                              눌러도 서버가 409 로 막는 버튼을 둘 이유가 없다. */}
                          {doc.downloaded && doc.index_status !== 'RUNNING' && (
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={busy === doc.doc_id}
                              onClick={() => void retry(doc)}
                            >
                              {doc.search_ready ? '다시 읽기' : '다시 시도'}
                            </Button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </>
            )}
          </section>
        </div>
      </div>
    </AppShell>
  );
}
