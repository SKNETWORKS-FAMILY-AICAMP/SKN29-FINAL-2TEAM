import { Badge, Button, Checkbox, Icon, Select } from '../../components';
import type { SelectOption } from '../../components';
import styles from './FileRegistrationTable.module.css';

export interface FileRow {
  id: string;
  name: string;
  folder: string;
  date: string;
  role: string;
  supported: boolean;
}

interface FileRegistrationTableProps {
  rows: FileRow[];
  selected: Set<string>;
  onToggleRow: (id: string) => void;
  onToggleAll: () => void;
  mode: 'submit' | 'readonly';
  onSubmit?: () => void;
  showSupport?: boolean;
  submitLabel?: string;
  submitting?: boolean;
  /**
   * 주면 「역할」 열이 Select가 된다. 신규 파일은 폴더 역할을 물려받되 행마다
   * 바꿀 수 있어야 해서, 읽기 전용 목록과 같은 컴포넌트를 쓰되 여기서 갈린다.
   */
  roleOptions?: SelectOption[];
  onRoleChange?: (id: string, role: string) => void;
}

export function FileRegistrationTable({
  rows,
  selected,
  onToggleRow,
  onToggleAll,
  mode,
  onSubmit,
  showSupport = true,
  submitLabel = '선택 파일 등록',
  submitting = false,
  roleOptions,
  onRoleChange,
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

      {/*
        파일이 많으면 표가 화면을 넘어가 아래의 "선택 파일 등록"이 안 보인다.
        헤더와 액션바는 고정하고 행만 스크롤한다.
      */}
      <div className={styles.rowList}>
        {rows.length === 0 && <p className={styles.emptyRow}>표시할 파일이 없습니다.</p>}
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
                {roleOptions && onRoleChange ? (
                  <Select
                    size="sm"
                    options={roleOptions}
                    value={row.role}
                    // 미지원 파일은 등록 자체가 안 되므로 역할을 고를 이유가 없다.
                    disabled={!row.supported}
                    onChange={(event) => onRoleChange(row.id, event.target.value)}
                  />
                ) : (
                  <Badge tone="neutral">{row.role}</Badge>
                )}
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
            disabled={checkedCount === 0 || submitting}
            // 등록도 Drive를 다시 읽어 확인하므로 즉시 끝나지 않는다.
            iconRight={
              submitting ? (
                <Icon name="loader" size={14} color="currentColor" spin />
              ) : (
                <Icon name="arrow-right" size={14} color="currentColor" />
              )
            }
            onClick={onSubmit}
          >
            {submitting ? 'Drive에서 확인하는 중…' : submitLabel}
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
