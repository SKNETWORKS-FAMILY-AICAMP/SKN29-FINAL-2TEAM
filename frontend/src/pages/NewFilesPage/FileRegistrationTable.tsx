import { useMemo, useState } from 'react';
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

type SortKey = 'name' | 'folder' | 'date' | 'role' | 'supported';
type SortDirection = 'asc' | 'desc';

/** 한글·영문·숫자가 섞인 파일명을 사람이 기대하는 순서로 비교한다. */
const collator = new Intl.Collator('ko', { numeric: true, sensitivity: 'base' });

const SORT_HEADERS: { key: SortKey; label: string; colClass: keyof typeof styles }[] = [
  { key: 'name', label: '파일명', colClass: 'colName' },
  { key: 'folder', label: '소속 폴더', colClass: 'colFolder' },
  { key: 'date', label: '감지일', colClass: 'colDate' },
  { key: 'role', label: '역할', colClass: 'colRole' },
  { key: 'supported', label: '지원 여부', colClass: 'colSupport' },
];

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

  // 기본은 소속 폴더 오름차순이고, 같은 폴더 안에서는 파일명 순이다(아래 2차 기준).
  const [sortKey, setSortKey] = useState<SortKey>('folder');
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc');

  /** 역할은 코드(`PLAN`)로 들고 있어 그대로 비교하면 화면 순서와 다르다. */
  const roleLabel = (value: string) =>
    roleOptions?.find((option) => option.value === value)?.label ?? value;

  const sortedRows = useMemo(() => {
    const compare = (a: FileRow, b: FileRow) => {
      let result = 0;
      if (sortKey === 'supported') {
        // 지원되는 것이 먼저다 — 등록할 수 있는 파일을 위로 올린다.
        result = Number(b.supported) - Number(a.supported);
      } else if (sortKey === 'role') {
        result = collator.compare(roleLabel(a.role), roleLabel(b.role));
      } else {
        result = collator.compare(a[sortKey], b[sortKey]);
      }
      if (result !== 0) return sortDirection === 'asc' ? result : -result;

      // 1차 기준이 같으면 늘 폴더·파일명 순이다. 방향을 뒤집어도 이 순서는
      // 그대로 둔다 — 안 그러면 같은 값끼리 자리가 흔들려 읽기 어렵다.
      return collator.compare(a.folder, b.folder) || collator.compare(a.name, b.name);
    };
    return [...rows].sort(compare);
  }, [rows, sortKey, sortDirection, roleOptions]);

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDirection((prev) => (prev === 'asc' ? 'desc' : 'asc'));
      return;
    }
    setSortKey(key);
    setSortDirection('asc');
  }

  return (
    <div className={styles.tableCard}>
      <div className={styles.tableHeader}>
        <div className={styles.colSelect}>
          <Checkbox checked={allChecked} onChange={onToggleAll} />
          <span className={styles.thActive}>전체선택</span>
        </div>
        {SORT_HEADERS.filter((header) => header.key !== 'supported' || showSupport).map((header) => {
          const active = sortKey === header.key;
          return (
            <button
              key={header.key}
              type="button"
              className={[styles[header.colClass], styles.thActive, styles.sortHeader].join(' ')}
              onClick={() => toggleSort(header.key)}
              aria-sort={active ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'}
            >
              {header.label}
              <Icon
                name="chevron-down"
                size={13}
                className={[
                  styles.sortIcon,
                  active ? styles.sortIconActive : '',
                  active && sortDirection === 'asc' ? styles.sortIconUp : '',
                ]
                  .filter(Boolean)
                  .join(' ')}
              />
            </button>
          );
        })}
      </div>

      {/*
        파일이 많으면 표가 화면을 넘어가 아래의 "선택 파일 등록"이 안 보인다.
        헤더와 액션바는 고정하고 행만 스크롤한다.
      */}
      <div className={styles.rowList}>
        {sortedRows.length === 0 && <p className={styles.emptyRow}>표시할 파일이 없습니다.</p>}
        {sortedRows.map((row, idx) => {
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
