import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Icon, Select, useToast } from '../../components';
import { ApiError } from '../../api/client';
import { getDriveFolders, listDriveFiles } from '../../api/connectors';
import type { DriveFile } from '../../api/connectors';
import { listTeamDocuments, listTeamFolders, saveDocumentRoles } from '../../api/projects';
import type { DocRole } from '../../api/projects';
import { markConnectorConnected } from '../../utils/connectorStatus';
import { useSession } from '../../utils/session';
import styles from './FolderRoleAssignmentPage.module.css';

/** `doc.doc_role` 코드값을 그대로 쓴다. 화면 전용 값을 따로 두면 매핑이 하나 늘어난다. */
const ROLE_OPTIONS: { label: string; value: DocRole }[] = [
  { label: '기획서', value: 'PLAN' },
  { label: '회의록', value: 'MEETING_NOTE' },
  { label: '일일보고서', value: 'DAILY_REPORT' },
  { label: '기타', value: 'OTHER' },
];

const DEFAULT_ROLE: DocRole = 'PLAN';

/** 파일별 역할은 폴더 역할을 물려받는 것이 기본이고, 필요할 때만 덮어쓴다. */
const INHERIT = 'inherit';

function inheritedRoleOptions(folderRoleLabel: string) {
  return [{ label: `폴더 역할 상속 (${folderRoleLabel})`, value: INHERIT }, ...ROLE_OPTIONS];
}

interface RoleFolder {
  id: string;
  name: string;
  files: DriveFile[];
}

export default function FolderRoleAssignmentPage() {
  const navigate = useNavigate();
  const session = useSession();
  const { showToast } = useToast();
  const [folders, setFolders] = useState<RoleFolder[]>([]);
  const [folderRoles, setFolderRoles] = useState<Record<string, DocRole>>({});
  const [fileRoles, setFileRoles] = useState<Record<string, DocRole | typeof INHERIT>>({});
  const [expandedFolders, setExpandedFolders] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const token = session?.token;

  // 저장된 폴더를 읽어 이름과 그 안의 파일을 채운다. 이전에 지정한 역할이 있으면
  // 폴더 역할은 team_folder에서, 파일별 덮어쓰기는 doc에서 되살린다.
  useEffect(() => {
    if (!token) return;

    let cancelled = false;
    void (async () => {
      try {
        const savedFolders = await listTeamFolders(token);
        if (savedFolders.length === 0) {
          if (!cancelled) setLoading(false);
          return;
        }

        const named = await getDriveFolders(
          token,
          savedFolders.map((folder) => folder.external_folder_id),
        );
        // 폴더를 저장할 때 정한 탐색 깊이로 읽는다. 저장될 문서와 같아야 한다.
        const depthByFolder = new Map(
          savedFolders.map((folder) => [folder.external_folder_id, folder.max_depth]),
        );
        const fileLists = await Promise.all(
          named.map((folder) =>
            listDriveFiles(token, folder.folder_id, depthByFolder.get(folder.folder_id) ?? 1),
          ),
        );
        const documents = await listTeamDocuments(token);
        if (cancelled) return;

        const savedFolderRoles: Record<string, DocRole> = {};
        for (const folder of savedFolders) {
          savedFolderRoles[folder.external_folder_id] = folder.default_doc_role ?? DEFAULT_ROLE;
        }

        const rows = named.map((folder, index) => ({
          id: folder.folder_id,
          name: folder.name,
          files: fileLists[index],
        }));

        // 폴더 역할과 다른 문서만 덮어쓴 것으로 본다.
        const savedFileRoles: Record<string, DocRole | typeof INHERIT> = {};
        for (const row of rows) {
          for (const file of row.files) {
            const saved = documents.find((doc) => doc.src_file_id === file.file_id);
            savedFileRoles[file.file_id] =
              saved?.doc_role && saved.doc_role !== savedFolderRoles[row.id] ? saved.doc_role : INHERIT;
          }
        }

        setFolders(rows);
        setFolderRoles(savedFolderRoles);
        setFileRoles(savedFileRoles);
        setExpandedFolders(Object.fromEntries(rows.map((row) => [row.id, false])));
      } catch (error) {
        if (!cancelled) {
          showToast(error instanceof ApiError ? error.message : '폴더를 불러오지 못했습니다.', 'error');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [token, showToast]);

  async function handleSaveAndFinish() {
    if (!token || folders.length === 0) return;

    // 상속을 고른 파일은 보내지 않는다. 서버가 폴더 역할을 적용한다.
    const overrides: Record<string, DocRole> = {};
    for (const [fileId, role] of Object.entries(fileRoles)) {
      if (role !== INHERIT) overrides[fileId] = role;
    }

    setSaving(true);
    try {
      await saveDocumentRoles(token, folderRoles, overrides);
      markConnectorConnected('google-drive');
      navigate('/onboarding/connectors');
    } catch (error) {
      showToast(error instanceof ApiError ? error.message : '역할을 저장하지 못했습니다.', 'error');
      setSaving(false);
    }
  }

  function toggleExpanded(folderId: string) {
    setExpandedFolders((prev) => ({ ...prev, [folderId]: !prev[folderId] }));
  }

  function handleFolderRoleChange(folderId: string, value: string) {
    setFolderRoles((prev) => ({ ...prev, [folderId]: value as DocRole }));
  }

  function handleFileRoleChange(fileId: string, value: string) {
    setFileRoles((prev) => ({ ...prev, [fileId]: value as DocRole | typeof INHERIT }));
  }

  function roleLabel(value: string) {
    return ROLE_OPTIONS.find((opt) => opt.value === value)?.label ?? value;
  }

  return (
    <div className={styles.page}>
      <div className={styles.panel}>
        <div className={styles.header}>
          <div className={styles.logo}>
            <span className={styles.mark}>h</span>
            <span className={styles.wordmark}>halil</span>
          </div>
          <span className={styles.stepPill}>스텝 3 / 4</span>
        </div>

        <div className={styles.titles}>
          <h1>폴더 역할 지정</h1>
          <p>각 폴더가 어떤 문서를 담고 있는지 알려주세요. 지정된 역할은 내부 파일에 자동으로 상속됩니다.</p>
        </div>

        <div className={styles.folderTree}>
          {loading && <p className={styles.emptyNote}>폴더와 파일을 불러오는 중…</p>}
          {!loading && folders.length === 0 && (
            <p className={styles.emptyNote}>
              지정할 폴더가 없습니다. 이전 단계에서 Drive 폴더를 먼저 선택해 주세요.
            </p>
          )}
          {folders.map((folder) => {
            const isExpanded = expandedFolders[folder.id];
            const currentRole = folderRoles[folder.id] ?? DEFAULT_ROLE;
            const supportedCount = folder.files.filter((file) => file.supported).length;
            return (
              <div key={folder.id}>
                <div
                  className={[styles.rowCollapsed, styles.clickable].join(' ')}
                  onClick={() => toggleExpanded(folder.id)}
                >
                  <div
                    className={[styles.rowLeft, isExpanded ? styles.expanded : ''].filter(Boolean).join(' ')}
                  >
                    <Icon name="chevron-right" size={12} className={styles.chevron} />
                    <Icon name="folder" size={16} color="var(--color-primary)" />
                    <span className={styles.folderName}>{folder.name}</span>
                    <span className={styles.folderCount}>
                      {supportedCount}개 파일
                      {folder.files.length > supportedCount &&
                        ` · 미지원 ${folder.files.length - supportedCount}개 제외`}
                    </span>
                  </div>
                  <Select
                    size="sm"
                    className={styles.roleSelect}
                    options={ROLE_OPTIONS}
                    value={currentRole}
                    onClick={(e) => e.stopPropagation()}
                    onChange={(e) => handleFolderRoleChange(folder.id, e.target.value)}
                  />
                </div>

                <div className={[styles.children, isExpanded ? styles.open : ''].filter(Boolean).join(' ')}>
                  {folder.files.length === 0 && (
                    <p className={styles.emptyNote}>이 폴더에는 파일이 없습니다.</p>
                  )}
                  {folder.files.map((file) => (
                    <div key={file.file_id} className={styles.fileRow}>
                      <div className={styles.fileLeft}>
                        <Icon name="file-text" size={16} color="var(--color-heading)" />
                        <span className={styles.fileName}>
                          {file.folder_path && `${file.folder_path}/`}
                          {file.name}
                        </span>
                      </div>
                      {file.supported ? (
                        <Select
                          size="sm"
                          className={styles.fileSelect}
                          options={inheritedRoleOptions(roleLabel(currentRole))}
                          value={fileRoles[file.file_id] ?? INHERIT}
                          onChange={(e) => handleFileRoleChange(file.file_id, e.target.value)}
                        />
                      ) : (
                        <span className={styles.folderCount}>미지원 형식</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>

        <div className={styles.footer}>
          <Button
            variant="outline"
            className={styles.prevButton}
            iconLeft={<Icon name="arrow-left" size={16} />}
            onClick={() => navigate('/onboarding/folders')}
          >
            이전 단계
          </Button>
          <Button
            variant="primary"
            iconRight={<Icon name="arrow-right" size={16} />}
            disabled={loading || saving || folders.length === 0}
            onClick={() => void handleSaveAndFinish()}
          >
            {saving ? '저장 중…' : 'Drive 설정 완료'}
          </Button>
        </div>
      </div>
    </div>
  );
}
