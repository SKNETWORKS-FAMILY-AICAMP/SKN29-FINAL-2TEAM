import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Badge, Button, Icon, Select, ToggleSwitch, TopNav, useToast } from '../../components';
import { ApiError } from '../../api/client';
import { getDriveFolders, listDriveFiles } from '../../api/connectors';
import type { DriveFile } from '../../api/connectors';
import {
  ensureOnboardingProject,
  findOnboardingProject,
  listProjectSources,
  replaceProjectSources,
} from '../../api/projects';
import { useSession } from '../../utils/session';
import { DriveFolderPickerModal } from './DriveFolderPickerModal';
import type { PickedFolder } from './DriveFolderPickerModal';
import styles from './FolderSelectPage.module.css';

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

export default function FolderSelectPage() {
  const navigate = useNavigate();
  const session = useSession();
  const { showToast } = useToast();
  const [folders, setFolders] = useState<PickedFolder[]>([]);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [previewFiles, setPreviewFiles] = useState<PreviewFile[]>([]);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [includeSubfolders, setIncludeSubfolders] = useState(true);
  const [depth, setDepth] = useState(DEFAULT_DEPTH);

  const token = session?.token;

  // 저장된 선택을 되살린다. proj_source에는 폴더 id만 남으므로 이름은 Drive에서
  // 다시 가져온다. 화면을 열기만 했을 때는 프로젝트를 만들지 않는다.
  useEffect(() => {
    if (!token) return;

    let cancelled = false;
    void (async () => {
      try {
        const project = await findOnboardingProject(token);
        if (!project || cancelled) return;

        const sources = await listProjectSources(token, project.proj_id);
        const driveSources = sources.filter((source) => source.source_type === 'DRIVE_FOLDER');
        const resolved = await getDriveFolders(
          token,
          driveSources.map((source) => source.external_source_id),
        );
        if (cancelled) return;

        setFolders(resolved.map((folder) => ({ id: folder.folder_id, name: folder.name, path: '' })));
        // 저장된 깊이는 폴더마다 같은 값이므로 첫 행만 보면 된다.
        if (driveSources.length > 0) {
          const restored = fromMaxDepth(driveSources[0].max_depth);
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
  }, [token, showToast]);

  // 선택한 폴더와 탐색 깊이로 실제로 가져올 파일을 보여준다. 깊이를 바꿨을 때
  // 결과가 달라지는 것을 확인할 수 없으면 설정이 의미가 없다.
  useEffect(() => {
    if (!token || folders.length === 0) {
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
  }, [token, folders, includeSubfolders, depth, showToast]);

  async function handleSaveAndContinue() {
    if (!token || folders.length === 0) return;

    setSaving(true);
    try {
      // 폴더를 고르는 것이 프로젝트를 만드는 것이다. 이름은 기획서를 읽고 나서
      // 제대로 정할 수 있으므로 지금은 폴더명으로 둔다.
      const project = await ensureOnboardingProject(token, folders[0].name);
      await replaceProjectSources(
        token,
        project.proj_id,
        'DRIVE_FOLDER',
        folders.map((folder) => folder.id),
        toMaxDepth(includeSubfolders, depth),
      );
      navigate('/onboarding/folder-roles');
    } catch (error) {
      showToast(error instanceof ApiError ? error.message : '폴더를 저장하지 못했습니다.', 'error');
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
    <div className={styles.page}>
      <TopNav tabs={[]} stepBadge="단계 2 / 4" />

      <div className={styles.contentContainer}>
        <div className={styles.headerBlock}>
          <h1 className={styles.pageTitle}>데이터 소스 설정</h1>
          <p className={styles.pageSubtitle}>
            서비스에서 활용할 지식 베이스 폴더를 지정하고 연동할 파일 목록을 확인합니다.
          </p>
        </div>

        {folders.length === 0 ? (
          <>
            <div className={styles.emptyBox}>
              <div className={styles.emptyIconWrap}>
                <Icon name="folder" size={32} color="var(--color-primary)" />
              </div>
              <div>
                <p className={styles.emptyTitle}>프로젝트 문서를 가져올 폴더를 선택해주세요</p>
                <p className={styles.emptyDesc}>
                  Google Drive에서 마크다운, PDF, 오피스 문서 등이 보관된 폴더를 연결할 수 있습니다.
                </p>
              </div>
              <Button variant="primary" onClick={() => setPickerOpen(true)}>
                Google Drive에서 폴더 선택
              </Button>
            </div>

            <div className={styles.stepFooter}>
              <Button variant="outline" onClick={() => navigate('/onboarding/connectors')}>
                이전 단계
              </Button>
              <Button variant="primary" disabled>
                다음: 폴더 역할 지정
              </Button>
            </div>
          </>
        ) : (
          <>
            <div className={styles.selectedFoldersBlock}>
              <p className={styles.sectionLabel}>선택된 폴더</p>
              <div className={styles.folderList}>
                {folders.length === 0 && <p className={styles.emptyNote}>선택된 폴더가 없습니다.</p>}
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

            <div className={styles.stepFooter}>
              <Button variant="outline" onClick={() => navigate('/onboarding/connectors')}>
                이전 단계
              </Button>
              <Button variant="primary" disabled={saving} onClick={() => void handleSaveAndContinue()}>
                {saving ? '저장 중…' : '다음: 폴더 역할 지정'}
              </Button>
            </div>
          </>
        )}
      </div>

      {session && (
        <DriveFolderPickerModal
          open={pickerOpen}
          token={session.token}
          onClose={() => setPickerOpen(false)}
          onPick={handlePick}
        />
      )}
    </div>
  );
}
