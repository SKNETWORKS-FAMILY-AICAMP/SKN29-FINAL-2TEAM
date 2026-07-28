import { useState } from 'react';
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Icon, Select } from '../../components';
import styles from './FolderRoleAssignmentPage.module.css';

const ROLE_OPTIONS = [
  { label: '기획서', value: 'plan' },
  { label: '회의록', value: 'meeting' },
  { label: '일일보고서', value: 'daily-report' },
  { label: '기타', value: 'etc' },
];

function inheritedRoleOptions(folderRoleLabel: string, folderRoleValue: string) {
  return [
    { label: `폴더 역할 상속 (${folderRoleLabel})`, value: `inherit:${folderRoleValue}` },
    ...ROLE_OPTIONS.filter((opt) => opt.value !== folderRoleValue),
  ];
}

interface RoleFile {
  id: string;
  name: string;
  defaultValue: string;
}

interface RoleFolder {
  id: string;
  name: string;
  fileCount: number;
  icon: ReactNode;
  defaultRole: string;
  expandable: boolean;
  files?: RoleFile[];
}

const FOLDERS: RoleFolder[] = [
  {
    id: 'folder-1',
    name: '2025_프로젝트_기획',
    fileCount: 12,
    icon: <Icon name="folder" size={20} color="var(--color-primary)" />,
    defaultRole: 'plan',
    expandable: false,
  },
  {
    id: 'folder-2',
    name: '회의록_모음',
    fileCount: 8,
    icon: <Icon name="folder-open" size={20} color="var(--color-primary)" />,
    defaultRole: 'meeting',
    expandable: true,
    files: [
      { id: 'file-2-1', name: '주간회의_0106.docx', defaultValue: 'inherit:meeting' },
      { id: 'file-2-2', name: '킥오프_회의록.docx', defaultValue: 'inherit:meeting' },
      { id: 'file-2-3', name: '스프린트_리뷰.docx', defaultValue: 'plan' },
      { id: 'file-2-4', name: '데일리_스크럼_0108.docx', defaultValue: 'inherit:meeting' },
    ],
  },
  {
    id: 'folder-3',
    name: '일일보고서_2025',
    fileCount: 23,
    icon: <Icon name="folder" size={20} color="var(--color-primary)" />,
    defaultRole: 'daily-report',
    expandable: false,
  },
];

export default function FolderRoleAssignmentPage() {
  const navigate = useNavigate();
  const [folderRoles, setFolderRoles] = useState<Record<string, string>>(() =>
    Object.fromEntries(FOLDERS.map((f) => [f.id, f.defaultRole])),
  );
  const [fileRoles, setFileRoles] = useState<Record<string, string>>(() => {
    const entries: [string, string][] = [];
    FOLDERS.forEach((folder) => {
      folder.files?.forEach((file) => entries.push([file.id, file.defaultValue]));
    });
    return Object.fromEntries(entries);
  });
  const [expandedFolders, setExpandedFolders] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(FOLDERS.map((f) => [f.id, f.expandable])),
  );

  function toggleExpanded(folderId: string) {
    setExpandedFolders((prev) => ({ ...prev, [folderId]: !prev[folderId] }));
  }

  function handleFolderRoleChange(folderId: string, value: string) {
    setFolderRoles((prev) => ({ ...prev, [folderId]: value }));
  }

  function handleFileRoleChange(fileId: string, value: string) {
    setFileRoles((prev) => ({ ...prev, [fileId]: value }));
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
          {FOLDERS.map((folder) => {
            const isExpanded = expandedFolders[folder.id];
            const currentRole = folderRoles[folder.id];
            return (
              <div key={folder.id}>
                <div
                  className={[styles.rowCollapsed, folder.expandable ? styles.clickable : '']
                    .filter(Boolean)
                    .join(' ')}
                  onClick={folder.expandable ? () => toggleExpanded(folder.id) : undefined}
                >
                  <div
                    className={[styles.rowLeft, isExpanded ? styles.expanded : ''].filter(Boolean).join(' ')}
                  >
                    {folder.expandable ? (
                      <Icon name="chevron-right" size={12} className={styles.chevron} />
                    ) : (
                      <span className={styles.chevronSpacer} />
                    )}
                    {folder.icon}
                    <span className={styles.folderName}>{folder.name}</span>
                    <span className={styles.folderCount}>{folder.fileCount}개 파일</span>
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

                {folder.expandable && folder.files && (
                  <div className={[styles.children, isExpanded ? styles.open : ''].filter(Boolean).join(' ')}>
                    {folder.files.map((file) => (
                      <div key={file.id} className={styles.fileRow}>
                        <div className={styles.fileLeft}>
                          <Icon name="file-text" size={16} color="var(--color-heading)" />
                          <span className={styles.fileName}>{file.name}</span>
                        </div>
                        <Select
                          size="sm"
                          className={styles.fileSelect}
                          options={inheritedRoleOptions(roleLabel(currentRole), currentRole)}
                          value={fileRoles[file.id]}
                          onChange={(e) => handleFileRoleChange(file.id, e.target.value)}
                        />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        <div className={styles.footer}>
          <Button
            variant="outline"
            className={styles.prevButton}
            iconLeft={<Icon name="arrow-left" size={16} />}
            onClick={() => navigate('/onboarding/folders?mode=demo')}
          >
            이전 단계
          </Button>
          <Button
            variant="primary"
            iconRight={<Icon name="arrow-right" size={16} />}
            onClick={() => navigate('/onboarding/jira-project?mode=demo')}
          >
            다음: Jira 프로젝트 선택
          </Button>
        </div>
      </div>
    </div>
  );
}
