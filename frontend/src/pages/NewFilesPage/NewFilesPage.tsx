import { useCallback, useEffect, useMemo, useState } from 'react';
import { Badge, Icon, TopNav, useToast } from '../../components';
import type { SelectOption } from '../../components';
import { ApiError } from '../../api/client';
import {
  findOnboardingProject,
  listDocumentHistory,
  listNewDocuments,
  registerDocuments,
} from '../../api/projects';
import type { DocRole, DocumentHistoryEntry, NewDocumentCandidate } from '../../api/projects';
import { MAIN_NAV_TABS } from '../../routes';
import { useSession } from '../../utils/session';
import { FileRegistrationTable } from './FileRegistrationTable';
import type { FileRow } from './FileRegistrationTable';
import styles from './NewFilesPage.module.css';

/** `doc.doc_role` 코드값을 그대로 쓴다. 온보딩 역할 지정 화면과 같은 목록이다. */
const ROLE_OPTIONS: SelectOption[] = [
  { label: '기획서', value: 'PLAN' },
  { label: '회의록', value: 'MEETING_NOTE' },
  { label: '일일보고서', value: 'DAILY_REPORT' },
  { label: '기타', value: 'OTHER' },
];

const FALLBACK_ROLE: DocRole = 'OTHER';

const ACTION_LABEL: Record<string, string> = {
  DOCUMENT_REGISTER: '파일 등록',
  DOCUMENT_DOWNLOAD: '원문 저장',
};

function formatDate(iso: string | null): string {
  if (!iso) return '-';
  return iso.slice(0, 10).replace(/-/g, '.');
}

function historyLabel(entry: DocumentHistoryEntry): string {
  const action = ACTION_LABEL[entry.action] ?? entry.action;
  const payload = entry.payload as { registered?: number; downloaded?: number; failed?: number };
  const count = payload.registered ?? payload.downloaded ?? 0;
  const failed = payload.failed ?? 0;
  const suffix = failed > 0 ? ` (실패 ${failed}건)` : '';
  return `${action} ${count}건${suffix}`;
}

/**
 * 신규 파일.
 *
 * 설정된 Drive 폴더를 훑어 **아직 `doc`에 없는 파일**을 보여주고, 고른 것만 등록한다.
 * 등록은 온보딩 역할 지정과 같은 범위다 — `doc` 행을 만드는 데까지고 원문 다운로드는
 * 따로다.
 */
export default function NewFilesPage() {
  const session = useSession();
  const token = session?.token;
  const { showToast } = useToast();

  const [projectId, setProjectId] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<NewDocumentCandidate[]>([]);
  const [history, setHistory] = useState<DocumentHistoryEntry[]>([]);
  const [roles, setRoles] = useState<Record<string, string>>({});
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [registering, setRegistering] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError('');
    try {
      const project = await findOnboardingProject(token);
      setProjectId(project?.proj_id ?? null);
      if (!project) {
        setCandidates([]);
        setHistory([]);
        return;
      }

      const [rows, historyRows] = await Promise.all([
        listNewDocuments(token, project.proj_id),
        listDocumentHistory(token, project.proj_id).catch(() => []),
      ]);
      setCandidates(rows);
      setHistory(historyRows);
      // 폴더에 지정된 역할을 기본값으로 채운다. 없으면 '기타'로 두고 사용자가 고른다.
      setRoles(
        Object.fromEntries(rows.map((row) => [row.file_id, row.suggested_role ?? FALLBACK_ROLE])),
      );
      // 등록 가능한 것만 미리 골라 둔다.
      setSelected(new Set(rows.filter((row) => row.supported).map((row) => row.file_id)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '신규 파일을 확인하지 못했습니다.');
      setCandidates([]);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  const rows: FileRow[] = useMemo(
    () =>
      candidates.map((item) => ({
        id: item.file_id,
        name: item.file_name,
        folder: item.folder_name,
        date: formatDate(item.modified_at),
        role: roles[item.file_id] ?? FALLBACK_ROLE,
        supported: item.supported,
      })),
    [candidates, roles],
  );

  const supportedIds = useMemo(
    () => candidates.filter((item) => item.supported).map((item) => item.file_id),
    [candidates],
  );

  function toggleRow(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    setSelected((prev) =>
      supportedIds.every((id) => prev.has(id)) ? new Set() : new Set(supportedIds),
    );
  }

  async function handleRegister() {
    if (!token || !projectId) return;
    const files = supportedIds
      .filter((id) => selected.has(id))
      .map((id) => ({ file_id: id, doc_role: (roles[id] ?? FALLBACK_ROLE) as DocRole }));
    if (files.length === 0) return;

    setRegistering(true);
    setError('');
    try {
      const result = await registerDocuments(token, projectId, files);
      const ok = result.registered.length;
      const skipped = result.skipped.length;
      if (skipped > 0) {
        showToast(`${ok}건 등록, ${skipped}건 제외됨`, 'info');
      } else {
        showToast(`${ok}건을 등록했습니다.`, 'success');
      }
      // 등록한 파일은 더 이상 신규가 아니다. 목록과 이력을 함께 다시 읽는다.
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '파일을 등록하지 못했습니다.');
    } finally {
      setRegistering(false);
    }
  }

  return (
    <div className={styles.page}>
      <TopNav tabs={MAIN_NAV_TABS} activeTo="/files/new" />

      <div className={styles.contentContainer}>
        <div className={styles.pageHeading}>
          <h1>신규 파일</h1>
          <p>설정된 폴더에 새로 추가된 문서를 검토하고 등록하세요</p>
        </div>

        {error && <p className={styles.stateRow}>{error}</p>}
        {loading && <p className={styles.stateRow}>폴더를 확인하는 중…</p>}

        {!loading && !error && !projectId && (
          <p className={styles.stateRow}>
            연결된 프로젝트가 없습니다. 온보딩에서 폴더를 먼저 선택해 주세요.
          </p>
        )}

        {!loading && !error && projectId && rows.length === 0 && (
          <div className={styles.tableCard}>
            <div className={styles.emptyBody}>
              <div className={styles.iconCircle}>
                <Icon name="folder-open" size={24} color="var(--color-placeholder)" />
              </div>
              <div className={styles.emptyText}>
                <p>새로 추가된 파일이 없어요</p>
                <p>설정된 폴더의 파일이 모두 등록되어 있습니다</p>
              </div>
            </div>
          </div>
        )}

        {!loading && !error && projectId && rows.length > 0 && (
          <FileRegistrationTable
            rows={rows}
            selected={selected}
            onToggleRow={toggleRow}
            onToggleAll={toggleAll}
            mode="submit"
            submitting={registering}
            onSubmit={handleRegister}
            roleOptions={ROLE_OPTIONS}
            onRoleChange={(id, role) => setRoles((prev) => ({ ...prev, [id]: role }))}
          />
        )}

        {!loading && projectId && <HistoryBlock entries={history} />}
      </div>
    </div>
  );
}

function HistoryBlock({ entries }: { entries: DocumentHistoryEntry[] }) {
  return (
    <div className={styles.historyBlock}>
      <h2>최근 처리 이력</h2>
      <div className={styles.historyCard}>
        {entries.map((entry) => (
          <div key={entry.audit_id} className={styles.historyRow}>
            <div className={styles.historyLeft}>
              <span className={styles.historyDate}>{formatDate(entry.occurred_at)}</span>
              <span className={styles.historyLabel}>{historyLabel(entry)}</span>
            </div>
            <Badge tone={entry.status === '완료' ? 'success' : 'warning'}>{entry.status}</Badge>
          </div>
        ))}
        {entries.length === 0 && <p className={styles.historyEmpty}>최근 처리 이력이 없습니다.</p>}
      </div>
    </div>
  );
}
