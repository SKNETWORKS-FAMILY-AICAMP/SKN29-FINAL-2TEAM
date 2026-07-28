import { useState } from 'react';
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { Badge, Button, Icon, Select, ToggleSwitch, TopNav } from '../../components';
import styles from './FolderSelectPage.module.css';

type PageState = 'empty' | 'complete';

interface SelectedFolder {
  id: string;
  name: string;
  fileCount: number;
}

interface PreviewFile {
  id: string;
  name: string;
  icon: ReactNode;
  supported: boolean;
}

const SELECTED_FOLDERS: SelectedFolder[] = [
  { id: 'f1', name: '2025_프로젝트_기획', fileCount: 12 },
  { id: 'f2', name: '회의록_모음', fileCount: 8 },
  { id: 'f3', name: '일일보고서_2025', fileCount: 23 },
];

const PREVIEW_FILES: PreviewFile[] = [
  { id: 'p1', name: '프로젝트_요구사항.docx', icon: <Icon name="file-text" size={18} />, supported: true },
  { id: 'p2', name: '회의록_0112.docx', icon: <Icon name="file-text" size={18} />, supported: true },
  { id: 'p3', name: '일정표.xlsx', icon: <Icon name="file-spreadsheet" size={18} />, supported: true },
  { id: 'p4', name: '디자인시안.psd', icon: <Icon name="file-image" size={18} />, supported: false },
  { id: 'p5', name: 'API_명세서.pdf', icon: <Icon name="file-text" size={18} />, supported: true },
];

const DEPTH_OPTIONS = [
  { label: '1단계까지', value: '1' },
  { label: '2단계까지', value: '2' },
  { label: '3단계까지', value: '3' },
  { label: '제한 없음', value: 'unlimited' },
];

export default function FolderSelectPage() {
  const navigate = useNavigate();
  const [state, setState] = useState<PageState>('empty');
  const [folders, setFolders] = useState<SelectedFolder[]>(SELECTED_FOLDERS);
  const [includeSubfolders, setIncludeSubfolders] = useState(true);
  const [depth, setDepth] = useState('2');

  function handleSelectFromDrive() {
    setState('complete');
  }

  function handleRemoveFolder(id: string) {
    setFolders((prev) => prev.filter((f) => f.id !== id));
  }

  const unsupportedCount = PREVIEW_FILES.filter((f) => !f.supported).length;

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

        {import.meta.env.DEV && (
          <p className={styles.devSwitch}>
            미리보기 상태 전환:{' '}
            <button type="button" onClick={() => setState('empty')}>
              빈 상태
            </button>{' '}
            /{' '}
            <button type="button" onClick={() => setState('complete')}>
              폴더 선택 완료 상태
            </button>
          </p>
        )}

        {state === 'empty' ? (
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
              <Button variant="primary" onClick={handleSelectFromDrive}>
                Google Drive에서 폴더 선택
              </Button>
            </div>

            <div className={styles.stepFooter}>
              <Button variant="outline" onClick={() => navigate('/onboarding/connectors')}>
                이전 단계
              </Button>
              <Button variant="link" onClick={() => navigate('/onboarding/jira-project?mode=demo')}>
                건너뛰기
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
                {folders.map((folder) => (
                  <div key={folder.id} className={styles.folderRow}>
                    <div className={styles.folderInfo}>
                      <div className={styles.folderIcon}>
                        <Icon name="folder" size={24} color="var(--color-primary)" />
                      </div>
                      <div className={styles.folderMeta}>
                        <p className={styles.folderName}>{folder.name}</p>
                        <p className={styles.folderCount}>파일 {folder.fileCount}개</p>
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
              <button type="button" className={styles.addFolderBtn} onClick={handleSelectFromDrive}>
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
                    onChange={(e) => setDepth(e.target.value)}
                  />
                </div>
              </div>

              <div className={styles.filePreviewCard}>
                <div className={styles.filePreviewHeader}>가져올 파일 목록 미리보기</div>
                <div className={styles.fileList}>
                  {PREVIEW_FILES.map((file) => (
                    <div key={file.id} className={styles.fileRow}>
                      <div
                        className={[styles.fileRowLeft, !file.supported ? styles.unsupported : '']
                          .filter(Boolean)
                          .join(' ')}
                      >
                        {file.icon}
                        <span className={styles.fileName}>{file.name}</span>
                      </div>
                      <Badge tone={file.supported ? 'success' : 'neutral'}>
                        {file.supported ? '지원됨' : '미지원'}
                      </Badge>
                    </div>
                  ))}
                </div>
              </div>

              <p className={styles.helperNote}>
                <Icon name="circle-help" size={14} color="var(--color-placeholder)" />
                {unsupportedCount}개 파일은 지원되지 않는 형식이라 제외돼요
              </p>
            </div>

            <div className={styles.stepFooter}>
              <Button variant="outline" onClick={() => navigate('/onboarding/connectors')}>
                이전 단계
              </Button>
              <Button variant="primary" onClick={() => navigate('/onboarding/folder-roles?mode=demo')}>
                다음: 폴더 역할 지정
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
