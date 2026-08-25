import { useEffect, useState } from 'react';
import { Badge, Button, Icon, Modal, Select, ToggleSwitch, useToast } from '../../../components';
import { ApiError } from '../../../api/client';
import { getDriveFolders, listDriveFiles } from '../../../api/connectors';
import type { DriveFile } from '../../../api/connectors';
import { listTeamFolders, replaceTeamFolders } from '../../../api/projects';
import { notifyIndexingStarted } from '../../../utils/indexingSignal';
import { DriveFolderPickerModal } from './DriveFolderPickerModal';
import type { PickedFolder } from './DriveFolderPickerModal';
import styles from './DriveFolderModal.module.css';

/** 미리보기 한 줄. 어느 폴더에서 온 파일인지 알 수 있어야 한다. */
interface PreviewFile extends DriveFile {
  folderName: string;
}

/** `proj_source.max_depth`로 그대로 저장된다. `unlimited`는 null이다. */
const DEPTH_OPTIONS = [
  { label: '2단계까지', value: '2' },
  { label: '3단계까지', value: '3' },
  { label: '제한 없음', value: 'unlimited' },
];

const DEFAULT_DEPTH = '2';

/**
 * 화면의 두 컨트롤을 컬럼 하나로 접는다. "하위 폴더 포함"을 끄는 것이 곧
 * 깊이 1이다 — DB에 불리언을 따로 두면 어느 쪽이 이기는지 모르게 된다.
 */
function toMaxDepth(includeSubfolders: boolean, depth: string): number | null {
  if (!includeSubfolders) return 1;
  return depth === 'unlimited' ? null : Number(depth);
}

function fromMaxDepth(maxDepth: number | null): { includeSubfolders: boolean; depth: string } {
  if (maxDepth === null) return { includeSubfolders: true, depth: 'unlimited' };
  if (maxDepth <= 1) return { includeSubfolders: false, depth: DEFAULT_DEPTH };
  return { includeSubfolders: true, depth: String(maxDepth) };
}

export interface DriveFolderModalProps {
  open: boolean;
  token: string;
  onClose: () => void;
  /** 저장이 끝났다. 부모가 연결 상태 문구를 다시 읽는다. */
  onSaved: () => void;
}

/**
 * 팀이 읽을 Drive 폴더를 지정한다. **옛 `FolderSelectPage`(533줄)가 여기로
 * 들어왔다**(5차 단계 4) — 온보딩 페이지를 없애면서 이 설정만 남았고, 화면
 * 하나를 통째로 쓸 만큼의 일이 아니다.
 *
 * 폴더 트리는 이 안에서 또 한 겹 모달로 연다. 트리를 이 모달에 같이 펴면
 * 「고르는 중」과 「고른 결과」가 한 화면에 섞여, 무엇이 이미 저장된 것인지
 * 알 수 없다.
 */
export function DriveFolderModal({ open, token, onClose, onSaved }: DriveFolderModalProps) {
  const { showToast } = useToast();
  const [folders, setFolders] = useState<PickedFolder[]>([]);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [previewFiles, setPreviewFiles] = useState<PreviewFile[]>([]);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [includeSubfolders, setIncludeSubfolders] = useState(true);
  const [depth, setDepth] = useState(DEFAULT_DEPTH);

  // 저장된 선택을 되살린다. team_folder에는 폴더 id만 남으므로 이름은 Drive에서
  // 다시 가져온다. 모달이 열릴 때마다 읽는다 — 닫혀 있는 동안 다른 곳에서
  // 바뀌었을 수 있고, 닫힌 모달이 Drive를 호출할 이유는 없다.
  useEffect(() => {
    if (!open) return;

    let cancelled = false;
    void (async () => {
      try {
        const saved = await listTeamFolders(token);
        if (cancelled) return;

        const resolved = await getDriveFolders(
          token,
          saved.map((folder) => folder.external_folder_id),
        );
        if (cancelled) return;

        setFolders(resolved.map((folder) => ({ id: folder.folder_id, name: folder.name, path: '' })));
        // 저장된 깊이는 폴더마다 같은 값이므로 첫 행만 보면 된다.
        if (saved.length > 0) {
          const restored = fromMaxDepth(saved[0].max_depth);
          setIncludeSubfolders(restored.includeSubfolders);
          setDepth(restored.depth);
        }
      } catch (error) {
        if (!cancelled) {
          showToast(
            error instanceof ApiError ? error.message : '저장된 폴더를 불러오지 못했습니다.',
            'error',
          );
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [open, token, showToast]);

  // 선택한 폴더와 탐색 깊이로 실제로 가져올 파일을 보여준다. 깊이를 바꿨을 때
  // 결과가 달라지는 것을 확인할 수 없으면 설정이 의미가 없다.
  useEffect(() => {
    if (!open || folders.length === 0) {
      setPreviewFiles([]);
      return;
    }

    let cancelled = false;
    const maxDepth = toMaxDepth(includeSubfolders, depth);
    setPreviewLoading(true);
    void (async () => {
      try {
        const perFolder = await Promise.all(
          folders.map(async (folder) => {
            const files = await listDriveFiles(token, folder.id, maxDepth);
            return files.map((file) => ({ ...file, folderName: folder.name }));
          }),
        );
        if (!cancelled) setPreviewFiles(perFolder.flat());
      } catch (error) {
        if (!cancelled) {
          setPreviewFiles([]);
          showToast(
            error instanceof ApiError ? error.message : '가져올 파일을 확인하지 못했습니다.',
            'error',
          );
        }
      } finally {
        if (!cancelled) setPreviewLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [open, token, folders, includeSubfolders, depth, showToast]);

  async function handleSave() {
    if (folders.length === 0) return;

    setSaving(true);
    try {
      // 폴더를 고르는 것은 **프로젝트를 만드는 것이 아니다.** 폴더는 파일이
      // 어디 있는지 알려주는 경로일 뿐이고, 그 안의 파일이 어느 프로젝트 것인지는
      // 열어 봐야 안다. 그래서 팀에 매단다.
      await replaceTeamFolders(
        token,
        folders.map((folder) => folder.id),
        toMaxDepth(includeSubfolders, depth),
        // 이름을 지금 같이 넘긴다. 나중에 "소속 폴더"를 보여주려고 Drive에 다시
        // 물어보면, 토큰이 만료됐을 때 등록된 문서는 멀쩡한데 폴더 이름만 못 읽는다.
        Object.fromEntries(folders.map((folder) => [folder.id, folder.name])),
      );
      // **저장이 끝이 아니다.** 이 요청이 곧바로 전량 수집을 띄우는데(서버
      // `_start_document_intake`) 응답은 그것을 기다리지 않는다. 시작됐다는 것을
      // 두 가지로 알린다 — 전역 진행 카드에 곧바로(안 그러면 다음 폴링까지 최대
      // 60초 동안 아무 일도 안 일어난 것처럼 보인다), 그리고 토스트로.
      notifyIndexingStarted();
      // 막연한 시간(「몇 분 걸립니다」)은 쓰지 않는다 — 화면문구_정리표 §1-1 이
      // 그것을 걷어낸 자리다. 대신 **무엇을 하는 중인지**와 **어디서 보는지**만
      // 말한다(「내 파일」 토스트 "업로드했습니다. 읽는 중입니다." 와 같은 꼴).
      showToast(
        `폴더 ${folders.length}개를 저장했습니다. 문서를 읽는 중입니다. 진행은 문서 화면에서 확인할 수 있습니다.`,
        'success',
      );
      onSaved();
      onClose();
    } catch (error) {
      showToast(error instanceof ApiError ? error.message : '폴더를 저장하지 못했습니다.', 'error');
    } finally {
      setSaving(false);
    }
  }

  function handlePick(picked: PickedFolder[]) {
    // 같은 폴더를 두 번 고를 수 있으므로 id로 합친다.
    setFolders((prev) => {
      const merged = new Map(prev.map((folder) => [folder.id, folder]));
      for (const folder of picked) merged.set(folder.id, folder);
      return [...merged.values()];
    });
    setPickerOpen(false);
  }

  function handleRemoveFolder(id: string) {
    setFolders((prev) => prev.filter((f) => f.id !== id));
  }

  const unsupportedCount = previewFiles.filter((file) => !file.supported).length;

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title="Drive 폴더 설정"
        width={720}
        footer={
          <>
            <Button variant="outline" onClick={onClose}>
              취소
            </Button>
            <Button
              variant="primary"
              disabled={saving || folders.length === 0}
              onClick={() => void handleSave()}
            >
              {saving ? '저장 중…' : '폴더 저장'}
            </Button>
          </>
        }
      >
        <div className={styles.body}>
          <p className={styles.pageSubtitle}>
            서비스에서 활용할 지식 베이스 폴더를 지정하고 연동할 파일 목록을 확인합니다.
          </p>

          {folders.length === 0 ? (
            <div className={styles.emptyBox}>
              <div className={styles.emptyIconWrap}>
                <Icon name="folder" size={32} color="var(--color-primary)" />
              </div>
              <div>
                <p className={styles.emptyTitle}>문서를 가져올 폴더를 선택하세요</p>
                <p className={styles.emptyDesc}>
                  Google Drive에서 마크다운, PDF, 오피스 문서 등이 보관된 폴더를 연결할 수 있습니다.
                </p>
              </div>
              <Button variant="primary" onClick={() => setPickerOpen(true)}>
                Google Drive에서 폴더 선택
              </Button>
            </div>
          ) : (
            <>
              <div className={styles.selectedFoldersBlock}>
                <p className={styles.sectionLabel}>선택된 폴더</p>
                <div className={styles.folderList}>
                  {folders.map((folder) => (
                    <div key={folder.id} className={styles.folderRow}>
                      <div className={styles.folderInfo}>
                        <div className={styles.folderIcon}>
                          <Icon name="folder" size={24} color="var(--color-primary)" />
                        </div>
                        <div className={styles.folderMeta}>
                          <p className={styles.folderName}>{folder.name}</p>
                          {folder.path && <p className={styles.folderCount}>{folder.path}</p>}
                        </div>
                      </div>
                      <button
                        type="button"
                        className={styles.folderRemove}
                        onClick={() => handleRemoveFolder(folder.id)}
                      >
                        제거
                      </button>
                    </div>
                  ))}
                </div>
                <button type="button" className={styles.addFolderBtn} onClick={() => setPickerOpen(true)}>
                  + 폴더 추가
                </button>
              </div>

              <div className={styles.settingsBlock}>
                <div className={styles.settingsRow}>
                  <div className={styles.settingsItem}>
                    <ToggleSwitch checked={includeSubfolders} onChange={setIncludeSubfolders} />
                    <span className={styles.settingsLabel}>하위 폴더 포함</span>
                  </div>
                  <div className={styles.settingsItem}>
                    <span className={styles.settingsLabel}>탐색 깊이</span>
                    <Select
                      size="sm"
                      className={styles.depthSelect}
                      options={DEPTH_OPTIONS}
                      value={depth}
                      disabled={!includeSubfolders}
                      onChange={(e) => setDepth(e.target.value)}
                    />
                  </div>
                </div>

                <div className={styles.filePreviewCard}>
                  <div className={styles.filePreviewHeader}>
                    가져올 파일 목록 미리보기
                    {previewFiles.length > 0 && ` · ${previewFiles.length}개`}
                  </div>
                  <div className={styles.fileList}>
                    {previewLoading && <p className={styles.emptyNote}>파일을 확인하는 중…</p>}
                    {!previewLoading && previewFiles.length === 0 && (
                      <p className={styles.emptyNote}>가져올 파일이 없습니다.</p>
                    )}
                    {!previewLoading &&
                      previewFiles.map((file) => (
                        <div key={file.file_id} className={styles.fileRow}>
                          <div
                            className={[styles.fileRowLeft, !file.supported ? styles.unsupported : '']
                              .filter(Boolean)
                              .join(' ')}
                          >
                            <Icon name="file-text" size={16} color="var(--color-heading)" />
                            <span className={styles.fileName}>
                              {file.folderName}
                              {file.folder_path && `/${file.folder_path}`} / {file.name}
                            </span>
                          </div>
                          <Badge tone={file.supported ? 'success' : 'neutral'}>
                            {file.supported ? '지원됨' : '미지원'}
                          </Badge>
                        </div>
                      ))}
                  </div>
                </div>

                {unsupportedCount > 0 && (
                  <p className={styles.helperNote}>
                    <Icon name="circle-help" size={14} color="var(--color-placeholder)" />
                    {unsupportedCount}개 파일은 지원되지 않는 형식이라 제외돼요
                  </p>
                )}
              </div>
            </>
          )}
        </div>
      </Modal>

      <DriveFolderPickerModal
        open={pickerOpen}
        token={token}
        onClose={() => setPickerOpen(false)}
        onPick={handlePick}
      />
    </>
  );
}
