import { useMemo, useState } from 'react';
import { Badge, Button, Checkbox, Icon } from '../../components';
import styles from './FileRegistrationTable.module.css';

export interface FileRow {
  id: string;
  name: string;
  folder: string;
  date: string;
  supported: boolean;
  /**
   * `new`  — Drive 에 새로 생긴 파일. 고르면 등록된다.
   * `missing` — 등록돼 있는데 Drive 스캔에 안 잡히는 문서. 정리하면 목록에서 빠진다.
   *
   * 한 표에 같이 둔다. 「이 폴더의 지금 상태」가 한 화면에 있어야 하고, 사라진
   * 문서만 따로 경고 카드로 세우면 신규 파일 검토보다 시선을 끌어간다.
   */
  kind: 'new' | 'missing';
  /** `missing` 행이 프로젝트에 묶여 있으면 그 표시. 정리하기 전에 알아야 한다. */
  note?: string;
}

type SortKey = 'name' | 'folder' | 'date' | 'supported';
type SortDirection = 'asc' | 'desc';

/** 한글·영문·숫자가 섞인 파일명을 사람이 기대하는 순서로 비교한다. */
const collator = new Intl.Collator('ko', { numeric: true, sensitivity: 'base' });

const SORT_HEADERS: { key: SortKey; label: string; colClass: keyof typeof styles }[] = [
  { key: 'name', label: '파일명', colClass: 'colName' },
  { key: 'folder', label: '소속 폴더', colClass: 'colFolder' },
  { key: 'date', label: '감지일', colClass: 'colDate' },
  { key: 'supported', label: '상태', colClass: 'colSupport' },
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
  /** 주면 「삭제 파일 정리 N건」이 액션바에 붙는다. 확인은 호출자가 모달로 받는다. */
  onRemoveMissing?: () => void;
  removing?: boolean;
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
  onRemoveMissing,
  removing = false,
}: FileRegistrationTableProps) {
  // 등록 대상은 「신규 + 지원됨」뿐이다. 사라진 문서는 고를 수 있지만 하는 일이
  // 반대라(등록이 아니라 내림) 집계도 버튼도 따로 센다.
  const newRows = rows.filter((row) => row.kind === 'new');
  const supportedRows = newRows.filter((row) => row.supported);
  const checkedCount = supportedRows.filter((row) => selected.has(row.id)).length;
  const excludedCount = newRows.length - supportedRows.length;
  const allChecked = supportedRows.length > 0 && checkedCount === supportedRows.length;
  const missingRows = rows.filter((row) => row.kind === 'missing');

  // 기본은 소속 폴더 오름차순이고, 같은 폴더 안에서는 파일명 순이다(아래 2차 기준).
  const [sortKey, setSortKey] = useState<SortKey>('folder');
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc');

  const sortedRows = useMemo(() => {
    const compare = (a: FileRow, b: FileRow) => {
      let result = 0;
      if (sortKey === 'supported') {
        // 등록할 수 있는 파일을 위로. 사라진 문서는 손댈 일이 적어 아래로 보낸다.
        result =
          Number(a.kind === 'missing') - Number(b.kind === 'missing') ||
          Number(b.supported) - Number(a.supported);
      } else {
        result = collator.compare(a[sortKey], b[sortKey]);
      }
      if (result !== 0) return sortDirection === 'asc' ? result : -result;

      // 1차 기준이 같으면 늘 폴더·파일명 순이다. 방향을 뒤집어도 이 순서는
      // 그대로 둔다 — 안 그러면 같은 값끼리 자리가 흔들려 읽기 어렵다.
      return collator.compare(a.folder, b.folder) || collator.compare(a.name, b.name);
    };
    return [...rows].sort(compare);
  }, [rows, sortKey, sortDirection]);

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
                  name={row.kind === 'missing' || !row.supported ? 'triangle-alert' : 'file-text'}
                  size={16}
                  color={
                    row.kind === 'missing'
                      ? 'var(--color-warning)'
                      : row.supported
                        ? 'var(--color-body)'
                        : 'var(--color-placeholder)'
                  }
                />
                <span>{row.name}</span>
                {row.note && <span className={styles.rowNote}>{row.note}</span>}
              </div>
              <div className={styles.rowFolder}>
                <Icon name="folder" size={14} color="var(--color-placeholder)" />
                <span>{row.folder}</span>
              </div>
              <div className={styles.rowDate}>{row.date}</div>
              {showSupport && (
                <div className={styles.rowSupport}>
                  {row.kind === 'missing' ? (
                    <Badge tone="warning">Drive에서 삭제됨</Badge>
                  ) : (
                    <Badge tone={row.supported ? 'success' : 'neutral'}>
                      {row.supported ? '지원됨' : '미지원'}
                    </Badge>
                  )}
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
            {/* 등록과 내림은 반대 방향이라 한 버튼에 묶지 않는다. */}
            {missingRows.length > 0 && onRemoveMissing && (
              <button
                type="button"
                className={styles.removeLink}
                disabled={removing}
                onClick={onRemoveMissing}
              >
                {removing ? '정리하는 중…' : `삭제 파일 정리 ${missingRows.length}건`}
              </button>
            )}
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
