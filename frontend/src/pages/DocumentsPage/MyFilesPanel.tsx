import { useEffect, useMemo, useRef, useState } from 'react';
import type { DragEvent } from 'react';
import { Badge, Button, Icon, Modal, ToggleSwitch, useToast } from '../../components';
import type { BadgeTone } from '../../components';
import {
  ApiError,
  deletePersonalFile,
  downloadPersonalFile,
  listPersonalFiles,
  listSharedFiles,
  reindexPersonalFile,
  setPersonalFileFlags,
  uploadPersonalFile,
} from '../../api/personalFiles';
import type { PersonalFile } from '../../api/personalFiles';
import { loadSessionToken } from '../../utils/session';
import { notifyIndexingStarted } from '../../utils/indexingSignal';
import { josa } from '../../utils/josa';
import styles from './DocumentsPage.module.css';

/**
 * 「문서」 화면의 **내가 올린 것** 자리 (M④ · 2026-08-18 멘토링).
 *
 * **커넥터 문서와 갈리는 것은 「누구 것이냐」다.** 팀 문서는 폴더를 정하면
 * 시스템이 알아서 받아들이고, 여기 올린 파일은 내 것이라 **내가 켜고 끈다.**
 *
 * **에이전트에 붙이는 조작은 없다.** toggle 이 곧 그 선택이라, 켠 파일은 모든
 * 에이전트가 검색에서 쓴다. 붙이는 표를 따로 두면 같은 파일을 두 번 골라야 하고
 * 「켜져 있는데 안 나오는」 상태가 정상이 되는데, 그건 설명할 수 없는 화면이다.
 *
 * ## 설정에서 옮겨 오며 표로 바꿨다 (2026-08-25)
 *
 * 원래 설정의 한 탭(`MyFilesTab`)이었고 카드 목록이었다. 「문서」 화면으로
 * 들어오면서 **같은 페이지 안에서 화면 언어가 갈렸다** — 트리에서 폴더를 고르면
 * 표인데 내 파일을 고르면 카드에다 제목까지 따로 달았다. 팀 문서 쪽과 같은
 * 표·검색·쪽 넘김을 쓴다(`DocumentsPage.module.css` 를 함께 쓰는 이유).
 *
 * 옮기면서 설정 밑에 있던 파일이 문서 폴더로 왔다. 쓰는 곳이 여기 하나뿐이라
 * 페이지를 건너 import 하던 것도 없어졌다.
 */

/** 쪽당 표시 개수. 팀 문서 표와 같은 값을 쓴다 — 한 화면에서 다르면 안 된다. */
const PAGE_SIZES = [10, 25, 50, 100];

//: 파서가 읽는 것과 같아야 한다. 더 받으면 색인에서 반드시 실패한다.
const ACCEPT = '.pdf,.docx,.txt,.md';

/**
 * 어느 목록을 보는가. **트리가 정해서 넘겨준다**(2026-08-26).
 *
 * **한 목록에 섞지 않는다.** 내 것과 남이 준 것은 할 수 있는 일이 다르다 —
 * 내 것은 지우고 공유할 수 있고, 받은 것은 볼 수만 있다. 한 줄씩 배지로
 * 구분하면 목록을 훑을 때마다 그 판단을 다시 해야 한다.
 *
 * 전에는 이 패널이 안쪽 탭으로 직접 갈랐다. 그러면 **「내 파일」 안에 「공유
 * 받은 파일」이 들어앉는다** — 받은 것은 내 것의 하위가 아니라 나란한 것인데
 * 트리의 이름이 반대로 말했다. 이제 둘 다 「개인 문서」 아래 형제 노드다.
 */
export type PersonalTab = 'mine' | 'shared';

/**
 * 상태 칩. 팀 문서 표(`DocumentsPage`의 `statusChip`)와 **같은 말을 쓴다** —
 * 같은 파이프라인의 같은 상태라 다른 낱말을 쓰면 사람이 두 번 배운다.
 */
function statusChip(file: PersonalFile): { tone: BadgeTone; label: string; hint: string } {
  // **에이전트가 만든 파일은 색인을 안 탄다**(2026-08-26 · `table_export`). 아래
  // 기본값으로 떨어지면 「읽는 중」이 영영 걸려 있다 — 끝나지 않는 진행 표시다.
  //
  // 「내보낸 파일」은 새로 지은 말이다. 저장소에 받기·내려받기 문구가 한 곳도
  // 없었고(2026-08-26 확인), 이 파일을 만드는 도구 이름이 「표 내보내기」라
  // 거기서 그대로 따왔다 — 사용자가 같은 것을 두 이름으로 배우지 않게.
  if (file.origin === 'generated') {
    return { tone: 'neutral', label: '내보낸 파일', hint: '' };
  }
  // **서버가 사유를 주면 그것을 쓴다.** 화면이 짐작해 쓰던 뭉뚱그린 문구보다
  // 언제나 정확하다. 사유가 없는 옛 행은 아래 기본 문구로 떨어진다.
  if (file.index_status === 'FAILED') {
    return {
      tone: 'warning',
      label: '읽기 실패',
      hint: file.index_detail ?? '읽을 수 없는 형식이거나, 글자를 뽑을 수 없는 파일일 수 있습니다.',
    };
  }
  if (file.search_ready) {
    return { tone: 'success', label: '사용 가능', hint: '' };
  }
  return { tone: 'info', label: '읽는 중', hint: '' };
}

function formatDate(iso: string | null): string {
  if (!iso) return '-';
  return iso.slice(0, 10).replace(/-/g, '.');
}

export function MyFilesPanel({ tab }: { tab: PersonalTab }) {
  const { showToast } = useToast();
  const token = loadSessionToken();

  const [files, setFiles] = useState<PersonalFile[]>([]);
  const [shared, setShared] = useState<PersonalFile[]>([]);
  const [error, setError] = useState<string | null>(null);
  /**
   * 올리다 거절당한 이유. **목록 오류와 한 칸을 쓰면 안 된다** — `upload()` 가
   * 사유를 적자마자 뒤이어 도는 `load()` 가 성공하면서 그 칸을 비웠고, 그래서
   * 20MB 넘는 파일을 놓았을 때 **화면이 아무 말도 안 했다**(2026-08-26).
   * 사람은 드래그가 안 먹은 줄로 읽는다.
   */
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  /** 지우려는 파일. 되돌릴 수 없어 한 번 묻는다. */
  const [confirming, setConfirming] = useState<PersonalFile | null>(null);
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const inputRef = useRef<HTMLInputElement>(null);
  /**
   * 아직 색인되지 않은 파일이 있는 동안만 목록을 다시 받는다.
   *
   * **내보낸 파일은 세지 않는다**(2026-08-26). 색인을 아예 안 타서 `search_ready`
   * 가 영영 false 이고 `FAILED` 도 안 되는데, 빼지 않으면 그 파일 하나 때문에
   * **5초 폴링이 영원히 돈다.**
   */
  const pending = files.some(
    (file) => file.origin !== 'generated' && !file.search_ready && file.index_status !== 'FAILED',
  );

  async function load() {
    if (!token) return;
    try {
      // 둘을 함께 받는다. 탭을 바꿀 때마다 부르면 넘어갈 때 빈 화면이 번쩍인다.
      const [mine, given] = await Promise.all([listPersonalFiles(token), listSharedFiles(token)]);
      setFiles(mine);
      setShared(given);
      setError(null);
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : '목록을 불러오지 못했습니다.');
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  /**
   * 처리가 끝날 때까지 목록을 다시 받는다.
   *
   * 올리는 즉시 파싱이 끝나지 않는다(RunPod 라 몇 분이다). 새로고침해야 상태가
   * 바뀌면 사람은 「안 되는 것」으로 읽는다. **끝난 뒤에는 안 돈다** — 볼 것이
   * 없는데 계속 두드릴 이유가 없다.
   */
  useEffect(() => {
    if (!pending) return;
    const timer = setInterval(load, 5_000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending, token]);

  async function upload(picked: FileList | null) {
    if (!token || !picked || picked.length === 0) return;
    setUploadError(null);
    for (const file of Array.from(picked)) {
      setBusy(file.name);
      try {
        await uploadPersonalFile(token, file);
        // 올린 파일도 커넥터 문서와 같은 색인을 탄다. 전역 카드가 곧바로 잡게 한다.
        notifyIndexingStarted();
        showToast(`${file.name} · 업로드했습니다. 읽는 중입니다.`, 'success');
      } catch (exc) {
        // 형식·크기 거절은 서버가 이유를 준다. 그 문장이 가장 정확하다.
        setUploadError(exc instanceof ApiError ? exc.message : `${file.name} · 올리지 못했습니다.`);
      }
    }
    setBusy(null);
    await load();
  }

  /**
   * 스위치 둘을 같은 방식으로 다룬다 — 눌린 즉시 반영하고 실패하면 되돌린다.
   *
   * 서버를 기다리면 스위치가 늦게 움직여 안 눌린 것처럼 보이고, 실패했는데
   * 켜진 채로 두면 **쓰이는 줄 알게 된다.**
   */
  async function toggle(file: PersonalFile, key: 'search_enabled' | 'shared', next: boolean) {
    if (!token) return;
    setFiles((prev) => prev.map((item) => (item.doc_id === file.doc_id ? { ...item, [key]: next } : item)));
    try {
      await setPersonalFileFlags(token, file.doc_id, { [key]: next });
      // 공유를 켜고 끄면 팀원 목록이 달라진다. 내 화면의 「공유 받은」 탭에는
      // 내 것이 안 나오지만, 남이 같은 순간에 켠 것이 있을 수 있어 다시 받는다.
      if (key === 'shared') void load();
    } catch (exc) {
      setFiles((prev) => prev.map((item) => (item.doc_id === file.doc_id ? { ...item, [key]: !next } : item)));
      showToast(exc instanceof ApiError ? exc.message : '바꾸지 못했습니다.', 'error');
    }
  }

  /**
   * 다시 읽힌다. 팀 문서 표(`DocumentsPage` 의 `retry`)와 같은 방식이다.
   *
   * **지우고 다시 올릴 이유가 없다.** 실패는 대개 그때 워커가 못 돌았다는
   * 뜻이라 같은 파일을 다시 읽히면 된다.
   */
  async function retry(file: PersonalFile) {
    if (!token) return;
    setBusy(file.doc_id);
    try {
      await reindexPersonalFile(token, file.doc_id);
      // 한 건이어도 워커가 도는 것은 같다. 전역 카드에도 잡히게 알린다.
      notifyIndexingStarted();
      // 낙관적으로 「읽는 중」으로 바꾼다. 서버도 곧 같은 값을 주지만, 폴링
      // 간격만큼은 버튼이 아무 반응 없어 보인다.
      setFiles((prev) =>
        prev.map((row) =>
          row.doc_id === file.doc_id ? { ...row, index_status: 'RUNNING', index_detail: null } : row,
        ),
      );
      showToast(`${file.file_name} · 다시 읽습니다.`, 'success');
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '다시 시작하지 못했습니다.', 'error');
    } finally {
      setBusy(null);
    }
  }

  /**
   * 내려받는다(2026-08-26). 인증이 Bearer 토큰이라 `<a href>` 로는 안 되고,
   * 받아 온 blob 을 임시 URL 로 만들어 사람이 저장하게 한다.
   *
   * **URL 을 반드시 되돌려준다** — 안 하면 blob 이 탭을 떠날 때까지 메모리에
   * 남는다. 파일 하나가 몇 MB 라 목록에서 여러 번 누르면 쌓인다.
   */
  async function download(file: PersonalFile) {
    if (!token) return;
    setBusy(file.doc_id);
    try {
      const blob = await downloadPersonalFile(token, file.doc_id);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = file.file_name;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '내려받지 못했습니다.', 'error');
    } finally {
      setBusy(null);
    }
  }

  /**
   * 지운다. **`window.confirm` 을 안 쓴다** — 브라우저 확인창은 「halil-ai.site
   * 내용:」 같은 제목이 붙어 이 제품의 화면으로 안 보인다. 프로젝트 삭제가
   * 쓰는 `Modal` 과 같은 모양으로 묻는다.
   */
  async function remove(file: PersonalFile) {
    if (!token) return;
    setConfirming(null);
    setBusy(file.doc_id);
    try {
      await deletePersonalFile(token, file.doc_id);
      setFiles((prev) => prev.filter((item) => item.doc_id !== file.doc_id));
      showToast('파일을 삭제했습니다.', 'success');
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '삭제하지 못했습니다.', 'error');
    } finally {
      setBusy(null);
    }
  }

  const rows = tab === 'mine' ? files : shared;

  const matched = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter((file) => file.file_name.toLowerCase().includes(needle));
  }, [rows, query]);

  const pageCount = Math.max(1, Math.ceil(matched.length / pageSize));
  const safePage = Math.min(page, pageCount);
  const paged = useMemo(
    () => matched.slice((safePage - 1) * pageSize, safePage * pageSize),
    [matched, safePage, pageSize],
  );

  // 자리·검색어·쪽당 개수가 바뀌면 첫 쪽으로. 보던 쪽 번호를 물고 가면 빈 표가 뜬다.
  useEffect(() => {
    setPage(1);
  }, [tab, query, pageSize]);

  useEffect(() => {
    if (page !== safePage) setPage(safePage);
  }, [page, safePage]);

  /**
   * 놓는 자리는 **패널 전체다**(2026-08-27). 얇은 막대만 받으면 파일을 든 채로
   * 그 한 줄을 겨눠야 했다 — 표 위에 놓쳐 떨어뜨리면 브라우저가 그 파일을
   * 열어 버려 보던 화면에서 아예 튕겨 나간다.
   *
   * 받은 파일 탭에서는 받지 않는다. 막지 않으면 남의 것을 모아 둔 자리에
   * 내 파일이 올라간다.
   */
  function onDrop(event: DragEvent<HTMLDivElement>) {
    if (tab !== 'mine') return;
    event.preventDefault();
    setDragging(false);
    upload(event.dataTransfer.files);
  }

  function onDragOver(event: DragEvent<HTMLDivElement>) {
    if (tab !== 'mine') return;
    // 막지 않으면 브라우저가 「여기엔 못 놓는다」로 표시하고 drop 도 안 온다.
    event.preventDefault();
    setDragging(true);
  }

  /**
   * 안쪽 요소를 지날 때마다 dragleave 가 뜬다. **정말 상자를 벗어났을 때만**
   * 끈다 — 아니면 덮개가 표 위를 지나는 내내 깜빡인다. 창 밖으로 나가면
   * relatedTarget 이 null 이라 `contains` 가 false 를 준다.
   */
  function onDragLeave(event: DragEvent<HTMLDivElement>) {
    if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
    setDragging(false);
  }

  // 실패한 것은 「읽는 중」이 아니다 — 팀 문서 표와 같은 규칙을 쓴다.
  //
  // **내보낸 파일도 아니다**(2026-08-26). 색인을 아예 안 타서 `search_ready` 가
  // 영영 false 인데, 빼지 않으면 머리말이 「읽는 중 1」로 굳는다 — 위 `pending`
  // (폴링 조건)과 **같은 규칙을 써야 한다.** 한쪽만 고치면 폴링은 멈췄는데
  // 화면은 계속 읽는 중이라고 말하는, 서로 어긋난 상태가 된다.
  const notReady = matched.filter(
    (file) =>
      file.origin !== 'generated' && !file.search_ready && file.index_status !== 'FAILED',
  ).length;
  const failed = matched.filter((file) => file.index_status === 'FAILED').length;

  return (
    <div className={styles.panelDrop} onDragOver={onDragOver} onDragLeave={onDragLeave} onDrop={onDrop}>
      <div className={styles.panelHead}>
        <h2 className={styles.panelTitle}>{tab === 'mine' ? '내 파일' : '공유 받은 파일'}</h2>
        <span className={styles.panelCount}>
          {query.trim() ? `${matched.length} / ${rows.length}건` : `${rows.length}건`}
          {notReady > 0 && <span className={styles.panelWarn}> · 읽는 중 {notReady}</span>}
          {failed > 0 && <span className={styles.panelWarn}> · 읽기 실패 {failed}</span>}
        </span>
      </div>

      {error && <p className={styles.error}>{error}</p>}

      {/* drag & drop. **누르는 것으로도 된다** — 드래그가 안 되는 환경(모바일)이
          있고, 되는 곳에서도 파일 고르기를 더 편하게 여기는 사람이 있다.
          받은 파일 탭에서는 안 보인다 — 거기 올릴 수는 없다. */}
      {tab === 'mine' && (
        <div
          className={styles.dropZone}
          onClick={() => inputRef.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') inputRef.current?.click();
          }}
        >
          <Icon name="plus" size={18} color="var(--color-primary)" />
          {/* 안내 문구를 뺐다(2026-08-27). 끌어다 놓는 것은 이제 패널 전체가
              받고 덮개가 그때 말해 준다 — 「여기로」라고 적힌 막대는 받는 곳을
              오히려 좁게 가리켰다. **올리는 중 표시는 남긴다** — 올라가고 있다는
              것을 아는 자리가 여기밖에 없다. */}
          {busy && <span className={styles.dropTitle}>{busy} 올리는 중…</span>}
          <span className={styles.dropHint}>
            PDF · Word(docx) · 텍스트(txt·md) · 한 개에 50MB까지 · 여러 개 한 번에
          </span>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept={ACCEPT}
            className={styles.fileInput}
            onChange={(event) => {
              upload(event.target.files);
              // 같은 파일을 다시 고를 수 있게 비운다 — 안 비우면 change 가 안 뜬다.
              event.target.value = '';
            }}
          />
        </div>
      )}

      {/* 거절 사유는 **놓은 자리 바로 아래**에 붙인다. 위쪽 목록 오류 자리에
          두면 방금 한 동작과 멀어져 눈에 안 들어온다. */}
      {tab === 'mine' && uploadError && <p className={styles.error}>{uploadError}</p>}

      <div className={styles.toolbar}>
        <div className={styles.searchBox}>
          <Icon name="search" size={15} color="var(--color-placeholder)" />
          <input
            type="text"
            className={styles.searchInput}
            placeholder="파일 이름 검색..."
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          {query && (
            <button type="button" className={styles.searchClear} onClick={() => setQuery('')} aria-label="검색어 지우기">
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

      {/* **비어 있어도 표는 남긴다**(2026-08-27). 표가 통째로 사라지면 문장
          한 줄만 뜬 채 화면이 무너져 보이고, 어떤 열이 담기는 자리인지도 함께
          사라진다 — 처음 온 사람이 가장 알고 싶어 하는 것이다. */}
      <div className={styles.table}>
        {/* 열이 탭마다 다르다. **받은 파일에는 조작이 없다** — 남의 것이라
            지울 수도 공유를 거둘 수도 없고, 검색에는 공유한 순간부터 이미
            쓰인다. 그 자리에 스위치를 두면 「꺼도 쓰이는」 상태가 생긴다.
            대신 **누가 올렸는지**가 온다 — 팀 문서는 「우리 폴더에서 왔다」가
            믿을 근거인데 여기는 사람이 그 근거다. */}
        <div className={tab === 'mine' ? styles.myFileHead : styles.sharedHead}>
          <span>문서</span>
          {tab === 'shared' && <span>공유한 사람</span>}
          <span>상태</span>
          <span>올림</span>
          {tab === 'mine' && (
            <>
              <span>검색에 사용</span>
              <span>팀에 공유</span>
              <span />
            </>
          )}
        </div>

        {/* 검색으로 0건인 것과 원래 빈 것은 다른 상태다. */}
        {matched.length === 0 && (
          <p className={styles.tableEmpty}>
            {rows.length > 0
              ? '검색 결과가 없습니다.'
              : tab === 'mine'
                ? '아직 올린 파일이 없습니다.'
                : '팀원이 공유한 파일이 아직 없습니다.'}
          </p>
        )}

        {paged.map((file) => {
          const chip = statusChip(file);
          return (
            <div key={file.doc_id} className={tab === 'mine' ? styles.myFileRow : styles.sharedRow}>
              <span className={styles.cellName}>
                <Icon name="file-text" size={15} color="var(--color-primary)" />
                <span className={styles.cellNameText}>
                  <span className={styles.fileName}>{file.file_name}</span>
                  {/* **문서 내용은 목록에 안 찍는다**(2026-08-18 PM). 요약을
                      그대로 얹었더니 줄마다 기획서 본문이 문단째로 쏟아졌다 —
                      파일 목록은 어느 파일인지 고르는 자리지 읽는 자리가 아니다. */}
                  {chip.hint && (
                    <span className={`${styles.cellHint} ${styles.rowDetail}`} title={chip.hint}>
                      {chip.hint}
                    </span>
                  )}
                </span>
              </span>

              {tab === 'shared' && (
                <span className={styles.cellPath} data-label="공유한 사람">
                  {file.owner_name ?? '알 수 없음'}
                </span>
              )}

              <span className={styles.cellStatus} data-label="상태">
                <Badge tone={chip.tone}>{chip.label}</Badge>
              </span>

              <span className={styles.cellDate} data-label="올림">
                {formatDate(file.uploaded_at)}
              </span>

              {tab === 'mine' && (
                <>
                  {/* 색인이 끝나기 전에도 켤 수 있다 — 끝나는 대로 쓰인다.
                      끝나야 켜지게 하면 「올려 뒀는데 왜 안 쓰지」가 된다. */}
                  <span className={styles.cellToggle}>
                    <ToggleSwitch
                      checked={file.search_enabled}
                      onChange={(next) => toggle(file, 'search_enabled', next)}
                    />
                  </span>
                  <span className={styles.cellToggle}>
                    <ToggleSwitch checked={file.shared} onChange={(next) => toggle(file, 'shared', next)} />
                  </span>
                  <span className={styles.cellActions}>
                    {/* 「읽는 중」에는 안 보인다 — 돌고 있는 것을 다시 시키라고
                        권하면 기다리면 될 일을 사람이 의심하게 된다. 팀 문서
                        표와 같은 조건이다. */}
                    {(file.search_ready || file.index_status === 'FAILED') && (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={busy === file.doc_id}
                        onClick={() => void retry(file)}
                      >
                        다시 읽기
                      </Button>
                    )}
                    {/* 「다운로드」는 새로 지은 말이다 — 저장소에 받기·내려받기
                        문구가 한 곳도 없었다(2026-08-26 확인). 「삭제」·「수정」
                        처럼 이미 쓰는 한자어 명사와 결이 같은 쪽을 골랐다. */}
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy === file.doc_id}
                      onClick={() => void download(file)}
                    >
                      다운로드
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={busy === file.doc_id}
                      onClick={() => setConfirming(file)}
                    >
                      삭제
                    </Button>
                  </span>
                </>
              )}
            </div>
          );
        })}
      </div>

      {pageCount > 1 && (
        <div className={styles.pager}>
          <span className={styles.pagerRange}>
            {(safePage - 1) * pageSize + 1}–{Math.min(safePage * pageSize, matched.length)} / {matched.length}
          </span>
          <div className={styles.pagerButtons}>
            <Button size="sm" variant="outline" disabled={safePage <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
              <Icon name="arrow-left" size={14} />
              이전
            </Button>
            <span className={styles.pagerPage}>
              {safePage} / {pageCount}
            </span>
            <Button
              size="sm"
              variant="outline"
              disabled={safePage >= pageCount}
              onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
            >
              다음
              <Icon name="arrow-right" size={14} />
            </Button>
          </div>
        </div>
      )}

      {/* 되돌릴 수 없다. 무엇이 사라지는지 먼저 말한다 — 문구는 프로젝트 삭제
          (`ProjectDetailPage`)와 같은 꼴로 맞춘다. */}
      <Modal
        open={confirming !== null}
        onClose={() => setConfirming(null)}
        title="파일 삭제"
        footer={
          <>
            <Button variant="outline" onClick={() => setConfirming(null)}>
              취소
            </Button>
            <Button variant="primary" disabled={busy !== null} onClick={() => confirming && void remove(confirming)}>
              {busy ? '삭제하는 중…' : '삭제'}
            </Button>
          </>
        }
      >
        <p className={styles.confirmText}>
          <strong>{confirming?.file_name}</strong>
          {josa(confirming?.file_name ?? '', '을/를')} 삭제합니다. <strong>되돌릴 수 없습니다.</strong>
        </p>
        <p className={styles.confirmText}>
          읽어 둔 내용과 원본 파일이 함께 삭제됩니다. 팀에 공유한 파일이면 팀원 목록에서도 제거됩니다.
        </p>
      </Modal>

      {/* 드래그하는 동안에만 덮는다. 표를 가리지만, 지금 놓아도 되는지가
          그 순간에는 표에 무엇이 있는지보다 중요하다. */}
      {dragging && (
        <div className={styles.panelDropOverlay}>
          <Icon name="plus" size={20} color="var(--color-primary)" />
          <span className={styles.dropTitle}>여기로 끌어다 놓으세요</span>
        </div>
      )}
    </div>
  );
}

export default MyFilesPanel;
