import { useCallback, useEffect, useState } from 'react';
import { Button, Checkbox, Icon, Modal } from '../../components';
import { ApiError } from '../../api/client';
import { DRIVE_ROOT_ID, listDriveFolders } from '../../api/connectors';
import type { DriveFolder } from '../../api/connectors';
import styles from './DriveFolderPickerModal.module.css';

const MY_DRIVE_LABEL = '내 드라이브';

/** 탐색 중인 위치. 첫 칸은 항상 내 드라이브 최상단이다. */
interface Crumb {
  id: string;
  name: string;
}

export interface PickedFolder {
  id: string;
  name: string;
  /** 이름만으로는 구분이 안 되는 폴더가 많아 상위 경로를 함께 보여준다. */
  path: string;
}

export interface DriveFolderPickerModalProps {
  open: boolean;
  token: string;
  onClose: () => void;
  onPick: (folders: PickedFolder[]) => void;
}

export function DriveFolderPickerModal({
  open,
  token,
  onClose,
  onPick,
}: DriveFolderPickerModalProps) {
  const [crumbs, setCrumbs] = useState<Crumb[]>([{ id: DRIVE_ROOT_ID, name: MY_DRIVE_LABEL }]);
  const [folders, setFolders] = useState<DriveFolder[]>([]);
  const [picked, setPicked] = useState<Map<string, PickedFolder>>(new Map());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [needsReconnect, setNeedsReconnect] = useState(false);

  const currentPath = crumbs.map((crumb) => crumb.name).join(' / ');
  const parentId = crumbs[crumbs.length - 1].id;

  const reset = useCallback(() => {
    setCrumbs([{ id: DRIVE_ROOT_ID, name: MY_DRIVE_LABEL }]);
    setFolders([]);
    setPicked(new Map());
    setError('');
    setNeedsReconnect(false);
  }, []);

  useEffect(() => {
    if (open) reset();
  }, [open, reset]);

  useEffect(() => {
    if (!open) return;

    let cancelled = false;
    setLoading(true);
    setError('');
    listDriveFolders(token, parentId)
      .then((rows) => {
        if (!cancelled) setFolders(rows);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setFolders([]);
        // 404는 아직 연결되지 않은 것, 502는 갱신이 실패해 재연결이 필요한 것.
        // 둘 다 이 화면에서 해결할 수 없으니 커넥터 화면으로 돌려보낸다.
        if (err instanceof ApiError && (err.status === 404 || err.status === 502)) {
          setNeedsReconnect(true);
        }
        setError(err instanceof ApiError ? err.message : '폴더 목록을 불러오지 못했습니다.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [open, token, parentId]);

  function toggle(folder: DriveFolder, checked: boolean) {
    setPicked((prev) => {
      const next = new Map(prev);
      if (checked) {
        next.set(folder.folder_id, { id: folder.folder_id, name: folder.name, path: currentPath });
      } else {
        next.delete(folder.folder_id);
      }
      return next;
    });
  }

  function renderBody() {
    if (needsReconnect) {
      return (
        <div className={styles.notice}>
          <Icon name="triangle-alert" size={24} color="var(--color-danger)" />
          <p>{error}</p>
          <p className={styles.hint}>커넥터 화면에서 Google Drive를 먼저 연결해 주세요.</p>
        </div>
      );
    }

    if (loading) {
      return (
        <div className={styles.notice}>
          <Icon name="loader" size={24} color="var(--color-primary)" spin />
          <p>폴더를 불러오는 중…</p>
        </div>
      );
    }

    if (error) {
      return (
        <div className={styles.notice}>
          <Icon name="triangle-alert" size={24} color="var(--color-danger)" />
          <p>{error}</p>
        </div>
      );
    }

    if (folders.length === 0) {
      return <p className={styles.hint}>이 폴더 안에는 하위 폴더가 없습니다.</p>;
    }

    return (
      <div className={styles.folderList}>
        {folders.map((folder) => (
          <div key={folder.folder_id} className={styles.folderRow}>
            <Checkbox
              checked={picked.has(folder.folder_id)}
              onChange={(checked) => toggle(folder, checked)}
            />
            <button
              type="button"
              className={styles.folderOpen}
              onClick={() => setCrumbs((prev) => [...prev, { id: folder.folder_id, name: folder.name }])}
            >
              <Icon name="folder" size={18} color="var(--color-primary)" />
              <span className={styles.folderName}>{folder.name}</span>
              <Icon name="chevron-right" size={16} color="var(--color-placeholder)" />
            </button>
          </div>
        ))}
      </div>
    );
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Google Drive 폴더 선택"
      width={600}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            취소
          </Button>
          <Button
            variant="primary"
            disabled={picked.size === 0}
            onClick={() => onPick([...picked.values()])}
          >
            {picked.size === 0 ? '폴더 추가' : `선택한 ${picked.size}개 추가`}
          </Button>
        </>
      }
    >
      <div className={styles.body}>
        <nav className={styles.breadcrumb} aria-label="폴더 경로">
          {crumbs.map((crumb, index) => (
            <span key={crumb.id} className={styles.crumbItem}>
              {index > 0 && <span className={styles.crumbSep}>/</span>}
              {index === crumbs.length - 1 ? (
                <span className={styles.crumbCurrent}>{crumb.name}</span>
              ) : (
                <button
                  type="button"
                  className={styles.crumbLink}
                  onClick={() => setCrumbs((prev) => prev.slice(0, index + 1))}
                >
                  {crumb.name}
                </button>
              )}
            </span>
          ))}
        </nav>

        {renderBody()}
      </div>
    </Modal>
  );
}
