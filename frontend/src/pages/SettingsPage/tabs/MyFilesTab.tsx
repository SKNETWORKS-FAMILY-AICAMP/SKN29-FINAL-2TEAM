import { useEffect, useRef, useState } from 'react';
import type { DragEvent } from 'react';
import { Badge, Button, Icon, InfoNote, ToggleSwitch, useToast } from '../../../components';
import type { BadgeTone } from '../../../components';
import {
  ApiError,
  deletePersonalFile,
  listPersonalFiles,
  listSharedFiles,
  setPersonalFileFlags,
  uploadPersonalFile,
} from '../../../api/personalFiles';
import type { PersonalFile } from '../../../api/personalFiles';
import { loadSessionToken } from '../../../utils/session';
import styles from './tabs.module.css';

/**
 * 「내 파일」 탭 — 내가 올린 문서 (M④ · 2026-08-18 멘토링).
 *
 * **커넥터 문서와 갈리는 것은 「누구 것이냐」다.** 팀 문서는 폴더를 정하면
 * 시스템이 알아서 받아들이고(Connector 탭), 여기 올린 파일은 내 것이라 **내가
 * 켜고 끈다.** 그 경계를 화면이 말해 주지 않으면 「어떤 문서는 자동이고 어떤
 * 문서는 내가 켜야 한다」가 뒤섞인다 — 그래서 InfoNote 가 그 말을 먼저 한다.
 *
 * **에이전트에 붙이는 조작은 없다.** toggle 이 곧 그 선택이라, 켠 파일은 모든
 * 에이전트가 검색에서 쓴다. 붙이는 표를 따로 두면 같은 파일을 두 번 골라야 하고
 * 「켜져 있는데 안 나오는」 상태가 정상이 되는데, 그건 설명할 수 없는 화면이다.
 */

/** 처리 상태 칩. **넷을 뭉개지 않는다** — 사람이 할 행동이 각각 다르다. */
function statusChip(file: PersonalFile): { tone: BadgeTone; label: string; hint: string } {
  if (file.search_ready) {
    return { tone: 'success', label: '검색 준비됨', hint: '' };
  }
  if (file.extract_status === 'UNSUPPORTED') {
    return {
      tone: 'warning',
      label: '읽을 수 없는 형식',
      hint: '이 형식은 본문을 뽑을 수 없습니다. 다른 형식으로 저장해 다시 올려 주세요.',
    };
  }
  if (file.extract_status === 'FAILED') {
    return {
      tone: 'warning',
      label: '본문 추출 실패',
      hint: '글자가 없는 스캔 이미지일 수 있습니다. 텍스트가 들어 있는 파일로 다시 올려 주세요.',
    };
  }
  // 요약은 됐는데 청크가 아직 없는 상태와, 막 올라온 상태를 같이 본다 —
  // 사람이 할 일이 「기다린다」로 같다.
  return {
    tone: 'neutral',
    label: file.summary ? '본문 읽는 중' : '읽는 중',
    hint: '읽고 색인하는 중입니다. 몇 분 걸릴 수 있고, 끝나면 검색에 쓰입니다.',
  };
}

const ACCEPT = '.pdf,.docx,.pptx,.xlsx,.txt,.md,.csv';

/**
 * 안쪽 탭 둘.
 *
 * **한 목록에 섞지 않는다.** 내 것과 남이 준 것은 할 수 있는 일이 다르다 —
 * 내 것은 지우고 공유할 수 있고, 받은 것은 볼 수만 있다. 한 줄씩 배지로
 * 구분하면 목록을 훑을 때마다 그 판단을 다시 해야 한다.
 */
type Inner = 'mine' | 'shared';

export function MyFilesTab() {
  const { showToast } = useToast();
  const token = loadSessionToken();

  const [inner, setInner] = useState<Inner>('mine');
  const [files, setFiles] = useState<PersonalFile[]>([]);
  const [shared, setShared] = useState<PersonalFile[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  /** 처리 중인 파일이 있는 동안만 목록을 다시 받는다. */
  const pending = files.some((file) => !file.search_ready && file.extract_status !== 'UNSUPPORTED'
    && file.extract_status !== 'FAILED');

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
    const timer = setInterval(load, 10_000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending, token]);

  async function upload(picked: FileList | null) {
    if (!token || !picked || picked.length === 0) return;
    setError(null);
    for (const file of Array.from(picked)) {
      setBusy(file.name);
      try {
        await uploadPersonalFile(token, file);
        showToast(`${file.name} 을 올렸습니다. 읽는 중입니다.`, 'success');
      } catch (exc) {
        // 형식·크기 거절은 서버가 이유를 준다. 그 문장이 가장 정확하다.
        setError(exc instanceof ApiError ? exc.message : '올리지 못했습니다.');
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
    setFiles((prev) =>
      prev.map((item) => (item.doc_id === file.doc_id ? { ...item, [key]: next } : item)),
    );
    try {
      await setPersonalFileFlags(token, file.doc_id, { [key]: next });
      // 공유를 켜고 끄면 팀원 목록이 달라진다. 내 화면의 「공유 받은」 탭에는
      // 내 것이 안 나오지만, 남이 같은 순간에 켠 것이 있을 수 있어 다시 받는다.
      if (key === 'shared') void load();
    } catch (exc) {
      setFiles((prev) =>
        prev.map((item) => (item.doc_id === file.doc_id ? { ...item, [key]: !next } : item)),
      );
      showToast(exc instanceof ApiError ? exc.message : '바꾸지 못했습니다.', 'error');
    }
  }

  async function remove(file: PersonalFile) {
    if (!token) return;
    // **되살릴 수 없다.** 커넥터 문서와 달리 원본이 우리뿐이라, 묻지 않고
    // 지우면 사람이 되찾을 방법이 없다.
    const confirmed = window.confirm(
      `${file.file_name} 을 지웁니다.\n\n올린 파일은 우리 쪽에만 있어 되살릴 수 없습니다.`,
    );
    if (!confirmed) return;

    setBusy(file.doc_id);
    try {
      await deletePersonalFile(token, file.doc_id);
      setFiles((prev) => prev.filter((item) => item.doc_id !== file.doc_id));
      showToast(`${file.file_name} 을 지웠습니다.`, 'success');
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '지우지 못했습니다.', 'error');
    } finally {
      setBusy(null);
    }
  }

  const rows = inner === 'mine' ? files : shared;

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    upload(event.dataTransfer.files);
  }

  return (
    <div className={styles.tab}>
      {error && <p className={`${styles.notice} ${styles.noticeDanger}`}>{error}</p>}

      <section className={styles.card}>
        <div className={styles.cardHead}>
          <h2 className={styles.cardTitle}>
            내 파일
            <InfoNote title="내 파일">
              <p>
                <strong>내 컴퓨터에서 올린 문서</strong>입니다. Connector 탭의 팀 문서와는{' '}
                <strong>누구 것이냐</strong>로 갈립니다 — 팀 문서는 폴더를 정해 두면 시스템이 알아서
                가져오고, 여기 올린 파일은 <strong>내 것이라 내가 켜고 끕니다.</strong>
              </p>
              <p>
                켜 두면 대화에서 답을 찾을 때 이 문서도 함께 봅니다. <strong>에이전트마다 따로
                고를 필요는 없습니다</strong> — 켠 파일은 내가 쓰는 모든 에이전트가 씁니다.
              </p>
              <p>
                끄면 검색에서만 빠지고 <strong>읽어 둔 내용은 그대로 남습니다.</strong> 다시 켤 때
                기다리지 않아도 됩니다.
              </p>
              <p>
                <strong>지우면 되살릴 수 없습니다.</strong> 팀 문서는 원본이 Drive에 있어 다시
                가져오지만, 올린 파일은 여기에만 있습니다.
              </p>
            </InfoNote>
          </h2>
          <p className={styles.cardSub}>
            PDF · Word · PowerPoint · Excel · 텍스트 파일을 올릴 수 있습니다. 한 개에 20MB까지입니다.
          </p>
        </div>

        {/* drag & drop. **누르는 것으로도 된다** — 드래그가 안 되는 환경(모바일)이
            있고, 되는 곳에서도 파일 고르기를 더 편하게 여기는 사람이 있다. */}
        <div
          className={[styles.dropZone, dragging ? styles.dropZoneOn : ''].filter(Boolean).join(' ')}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => inputRef.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') inputRef.current?.click();
          }}
        >
          <Icon name="plus" size={22} color="var(--color-primary)" />
          <span className={styles.dropTitle}>
            {busy ? `${busy} 올리는 중…` : '여기로 끌어다 놓거나 눌러서 고르세요'}
          </span>
          <span className={styles.dropHint}>여러 개를 한 번에 올릴 수 있습니다.</span>
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
      </section>

      <section className={styles.card}>
        <div className={styles.cardHead}>
          {/* 안쪽 탭. **내 것과 받은 것을 한 목록에 섞지 않는다** — 할 수 있는
              일이 달라서(지우기·공유 vs 보기만), 섞으면 줄마다 그 판단을 다시
              해야 한다. */}
          <div className={styles.innerTabs} role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={inner === 'mine'}
              className={[styles.innerTab, inner === 'mine' ? styles.innerTabOn : '']
                .filter(Boolean)
                .join(' ')}
              onClick={() => setInner('mine')}
            >
              내 파일 {files.length}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={inner === 'shared'}
              className={[styles.innerTab, inner === 'shared' ? styles.innerTabOn : '']
                .filter(Boolean)
                .join(' ')}
              onClick={() => setInner('shared')}
            >
              공유 받은 파일 {shared.length}
            </button>
          </div>
        </div>

        <div className={styles.list}>
          {rows.length === 0 && (
            <p className={styles.cardSub}>
              {inner === 'mine'
                ? '아직 올린 파일이 없습니다.'
                : '팀원이 공유한 파일이 아직 없습니다.'}
            </p>
          )}

          {rows.map((file) => {
            const chip = statusChip(file);
            return (
              <div key={file.doc_id} className={`${styles.row} ${styles.rowTall}`}>
                <span className={styles.rowIcon}>
                  <Icon name="file-text" size={20} color="var(--color-primary)" />
                </span>
                <div className={styles.rowBody}>
                  <span className={styles.rowName}>
                    {file.file_name}
                    <Badge tone={chip.tone}>{chip.label}</Badge>
                  </span>
                  {/* 받은 파일은 **누가 올렸는지가 먼저다.** 팀 문서는 「우리
                      폴더에서 왔다」가 믿을 근거인데, 여기는 사람이 그 근거다. */}
                  {inner === 'shared' && (
                    <span className={styles.rowMeta}>{file.owner_name ?? '알 수 없음'} 님이 공유</span>
                  )}
                  {file.summary && <span className={styles.rowMeta}>{file.summary}</span>}
                  {chip.hint && <span className={styles.rowMeta}>{chip.hint}</span>}
                  {file.keywords.length > 0 && (
                    <span className={styles.chips}>
                      {file.keywords.map((word) => (
                        <span key={word} className={styles.chip}>
                          {word}
                        </span>
                      ))}
                    </span>
                  )}
                </div>
                {/* **받은 파일에는 조작이 없다.** 남의 것이라 지울 수도 공유를
                    거둘 수도 없고, 검색에는 공유한 순간부터 이미 쓰인다 —
                    여기에 스위치를 두면 「꺼도 쓰이는」 상태가 생긴다. */}
                {inner === 'mine' && (
                  <div className={styles.rowActions}>
                    {/* 색인이 끝나기 전에도 켤 수 있다 — 끝나는 대로 쓰인다.
                        끝나야 켜지게 하면 「올려 뒀는데 왜 안 쓰지」가 된다. */}
                    <ToggleSwitch
                      checked={file.search_enabled}
                      onChange={(next) => toggle(file, 'search_enabled', next)}
                      label="검색에 사용"
                    />
                    <ToggleSwitch
                      checked={file.shared}
                      onChange={(next) => toggle(file, 'shared', next)}
                      label="팀에 공유"
                    />
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={busy === file.doc_id}
                      onClick={() => remove(file)}
                    >
                      지우기
                    </Button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
