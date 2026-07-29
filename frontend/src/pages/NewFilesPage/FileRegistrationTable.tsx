import { Badge, Button, Checkbox, Icon } from '../../components';
import styles from './FileRegistrationTable.module.css';

export interface FileRow {
  id: string;
  name: string;
  folder: string;
  date: string;
  role: string;
  supported: boolean;
}

export const FILE_ROWS: FileRow[] = [
  { id: '1', name: '프로젝트_요구사항_v2.docx', folder: '2025_프로젝트_기획', date: '2025.01.20', role: '기획서', supported: true },
  { id: '2', name: 'API_설계_초안.docx', folder: '2025_프로젝트_기획', date: '2025.01.20', role: '기획서', supported: true },
  { id: '3', name: '스프린트3_회의록.docx', folder: '회의록_모음', date: '2025.01.19', role: '회의록', supported: true },
  { id: '4', name: '주간보고_0120.docx', folder: '일일보고서_2025', date: '2025.01.20', role: '일일보고서', supported: true },
  { id: '5', name: '디자인_목업.fig', folder: '2025_프로젝트_기획', date: '2025.01.18', role: '기획서', supported: false },
  { id: '6', name: '인프라_구성도.pdf', folder: '2025_프로젝트_기획', date: '2025.01.19', role: '기획서', supported: true },
];

// Rows checked by default in the source mockup (row 4 starts unchecked).
export const DEFAULT_SELECTED_IDS = ['1', '2', '3', '6'];

interface FileRegistrationTableProps {
  rows: FileRow[];
  selected: Set<string>;
  onToggleRow: (id: string) => void;
  onToggleAll: () => void;
  mode: 'submit' | 'readonly';
  onSubmit?: () => void;
  showSupport?: boolean;
}

export function FileRegistrationTable({
  rows,
  selected,
  onToggleRow,
  onToggleAll,
  mode,
  onSubmit,
  showSupport = true,
}: FileRegistrationTableProps) {
  const supportedRows = rows.filter((row) => row.supported);
  const checkedCount = supportedRows.filter((row) => selected.has(row.id)).length;
  const excludedCount = rows.length - supportedRows.length;
  const allChecked = supportedRows.length > 0 && checkedCount === supportedRows.length;

  return (
    <div className={styles.tableCard}>
      <div className={styles.tableHeader}>
        <div className={styles.colSelect}>
          <Checkbox checked={allChecked} onChange={onToggleAll} />
          <span className={styles.thActive}>전체선택</span>
        </div>
        <span className={[styles.colName, styles.thActive].join(' ')}>파일명</span>
        <span className={[styles.colFolder, styles.thActive].join(' ')}>소속 폴더</span>
        <span className={[styles.colDate, styles.thActive].join(' ')}>감지일</span>
        <span className={[styles.colRole, styles.thActive].join(' ')}>역할</span>
        {showSupport && <span className={[styles.colSupport, styles.thActive].join(' ')}>지원 여부</span>}
      </div>

      <div>
        {rows.map((row, idx) => {
          const isChecked = row.supported && selected.has(row.id);
          const rowClasses = [
            styles.fileRow,
            idx % 2 === 1 ? styles.alt : '',
            !row.supported ? styles.rowDisabled : '',
          ]
            .filter(Boolean)
            .join(' ');

          return (
            <div key={row.id} className={rowClasses}>
              <div className={styles.rowSelect}>
                <Checkbox
                  checked={isChecked}
                  disabled={!row.supported}
                  onChange={() => onToggleRow(row.id)}
                />
              </div>
              <div className={styles.rowName}>
                <Icon
                  name={row.supported ? 'file-text' : 'triangle-alert'}
                  size={16}
                  color={row.supported ? 'var(--color-body)' : 'var(--color-placeholder)'}
                />
                <span>{row.name}</span>
              </div>
              <div className={styles.rowFolder}>
                <Icon name="folder" size={14} color="var(--color-placeholder)" />
                <span>{row.folder}</span>
              </div>
              <div className={styles.rowDate}>{row.date}</div>
              <div className={styles.rowRole}>
                <Badge tone="neutral">{row.role}</Badge>
              </div>
              {showSupport && (
                <div className={styles.rowSupport}>
                  <Badge tone={row.supported ? 'success' : 'neutral'}>{row.supported ? '지원됨' : '미지원'}</Badge>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {mode === 'submit' ? (
        <div className={styles.actionBar}>
          <div className={styles.summaryText}>
            <span className={[styles.summaryCount, checkedCount === 0 ? styles.isDisabled : ''].join(' ')}>
              {checkedCount}개 파일 선택됨
            </span>
            {excludedCount > 0 && <span className={styles.summaryExcluded}>(미지원 파일 {excludedCount}개 제외됨)</span>}
          </div>
          <Button
            variant="primary"
            disabled={checkedCount === 0}
            iconRight={<Icon name="arrow-right" size={14} color="currentColor" />}
            onClick={onSubmit}
          >
            선택 파일 등록
          </Button>
        </div>
      ) : (
        <div className={styles.selectionSummary}>
          <span className={[styles.summaryCount, checkedCount === 0 ? styles.isDisabled : ''].join(' ')}>
            {checkedCount}개 파일 선택됨
          </span>
          {excludedCount > 0 && <span className={styles.summaryExcluded}>(미지원 파일 {excludedCount}개 제외됨)</span>}
        </div>
      )}
    </div>
  );
}

export default FileRegistrationTable;
