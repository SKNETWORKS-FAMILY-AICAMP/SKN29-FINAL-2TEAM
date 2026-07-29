import { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Badge, Button, Icon, TopNav } from '../../components';
import type { BadgeTone } from '../../components';
import { MAIN_NAV_TABS } from '../../routes';
import styles from './AssignmentResultPage.module.css';

type Mode = 'dashboard' | 'reassigned';
type StatusFilter = 'all' | 'assigned' | 'review' | 'unassigned';

interface TaskRow {
  id: string;
  taskId: string;
  title: string;
  statusTone: BadgeTone;
  statusLabel: string;
  assigneeName: string | null;
  highlight?: boolean;
}

const ASSIGNEE_OPTIONS: string[] = [];
const FILTER_ORDER: StatusFilter[] = ['all', 'assigned', 'review', 'unassigned'];
const FILTER_LABEL: Record<StatusFilter, string> = {
  all: '전체',
  assigned: '배정완료',
  review: '검토·변경',
  unassigned: '미배정',
};
const STATUS_ORDER: Record<string, number> = {
  미배정: 0,
  검토중: 1,
  배정완료: 2,
  변경됨: 3,
};

function sortByStatusThenTitle(rows: TaskRow[]): TaskRow[] {
  return [...rows].sort((a, b) => {
    const orderA = STATUS_ORDER[a.statusLabel] ?? Number.MAX_SAFE_INTEGER;
    const orderB = STATUS_ORDER[b.statusLabel] ?? Number.MAX_SAFE_INTEGER;
    if (orderA !== orderB) return orderA - orderB;
    return a.title.localeCompare(b.title, 'ko');
  });
}

const DASHBOARD_ROWS: TaskRow[] = [];

const REASSIGNED_ROWS: TaskRow[] = [];

function ReassignIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
      <path d="M3 3v5h5" />
      <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" />
      <path d="M16 16h5v5" />
    </svg>
  );
}

function FilterIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <line x1="21" x2="14" y1="4" y2="4" />
      <line x1="10" x2="3" y1="4" y2="4" />
      <line x1="21" x2="12" y1="12" y2="12" />
      <line x1="8" x2="3" y1="12" y2="12" />
      <line x1="21" x2="16" y1="20" y2="20" />
      <line x1="12" x2="3" y1="20" y2="20" />
      <line x1="14" x2="14" y1="2" y2="6" />
      <line x1="8" x2="8" y1="10" y2="14" />
      <line x1="16" x2="16" y1="18" y2="22" />
    </svg>
  );
}

export default function AssignmentResultPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const initiallyAdjusted = new URLSearchParams(location.search).get('adjusted') === '1';
  const [mode, setMode] = useState<Mode>(initiallyAdjusted ? 'reassigned' : 'dashboard');
  const [rows, setRows] = useState<TaskRow[]>(initiallyAdjusted ? REASSIGNED_ROWS : DASHBOARD_ROWS);
  const [openRowId, setOpenRowId] = useState<string | null>(null);
  const [selectedRowId, setSelectedRowId] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const tableRef = useRef<HTMLDivElement | null>(null);
  const filteredRows = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    const matches = rows.filter((row) => {
      const matchesQuery =
        !query || row.title.toLowerCase().includes(query) || row.taskId.toLowerCase().includes(query);
      const matchesStatus =
        statusFilter === 'all' ||
        (statusFilter === 'assigned' && row.statusLabel === '배정완료') ||
        (statusFilter === 'review' && (row.statusLabel === '검토중' || row.statusLabel === '변경됨')) ||
        (statusFilter === 'unassigned' && row.statusLabel === '미배정');
      return matchesQuery && matchesStatus;
    });
    return sortByStatusThenTitle(matches);
  }, [rows, searchQuery, statusFilter]);
  const selectedRow = rows.find((row) => row.id === selectedRowId) ?? rows[0] ?? null;

  useEffect(() => {
    if (!openRowId) return;

    function handleOutsideClick(event: MouseEvent) {
      if (tableRef.current && !tableRef.current.contains(event.target as Node)) {
        setOpenRowId(null);
      }
    }

    window.addEventListener('click', handleOutsideClick);
    return () => window.removeEventListener('click', handleOutsideClick);
  }, [openRowId]);

  function switchMode(next: Mode) {
    const nextRows = next === 'dashboard' ? DASHBOARD_ROWS : REASSIGNED_ROWS;
    setMode(next);
    setRows(nextRows);
    setSelectedRowId(nextRows[0]?.id ?? '');
    setOpenRowId(null);
  }

  function selectAssignee(rowId: string, name: string) {
    setRows((prev) =>
      prev.map((row) =>
        row.id === rowId
          ? { ...row, assigneeName: name, statusLabel: '변경됨', statusTone: 'danger', highlight: true }
          : row,
      ),
    );
    setMode('reassigned');
    setSelectedRowId(rowId);
    setOpenRowId(null);
  }

  function cycleStatusFilter() {
    setStatusFilter((current) => {
      const index = FILTER_ORDER.indexOf(current);
      return FILTER_ORDER[(index + 1) % FILTER_ORDER.length];
    });
  }

  return (
    <div className={styles.page}>
      <TopNav tabs={MAIN_NAV_TABS} activeTo="/projects" />

      <div className={styles.mainContainer}>
        <div className={styles.pageHeader}>
          <h1>업무 배정 결과 대시보드</h1>
          <p>UI 흐름 검증용 정적 예시이며 실제 배정 결과가 아닙니다.</p>
        </div>

        <div className={styles.gridSplit}>
          <div className={styles.leftColumn} ref={tableRef}>
            <div className={styles.tableActionHeader}>
              <h2>Assignment Table</h2>
              <div className={styles.tableControls}>
                <div className={styles.searchBox}>
                  <Icon name="search" size={16} />
                  <input
                    type="text"
                    placeholder="업무 검색..."
                    value={searchQuery}
                    onChange={(event) => setSearchQuery(event.target.value)}
                  />
                </div>
                <button className={styles.filterBtn} type="button" onClick={cycleStatusFilter}>
                  <FilterIcon />
                  필터: {FILTER_LABEL[statusFilter]}
                </button>
              </div>
            </div>

            <div className={styles.taskTable}>
              <div className={styles.theadRow}>
                <div className={styles.colTask}>Task</div>
                <div className={styles.colId}>작업 ID</div>
                <div className={styles.colStatus}>배정현황</div>
                <div className={styles.colAssignee}>배정 인원</div>
              </div>

              <div className={styles.tableScrollBody}>
                {filteredRows.map((row) => (
                  <div
                    className={[
                      styles.trow,
                      row.highlight || selectedRowId === row.id ? styles.trowHighlight : '',
                    ].join(' ')}
                    key={row.id}
                    onClick={() => setSelectedRowId(row.id)}
                  >
                    <div className={styles.colTask}>{row.title}</div>
                    <div className={styles.colId}>{row.taskId}</div>
                    <div className={styles.colStatus}>
                      <Badge tone={row.statusTone}>{row.statusLabel}</Badge>
                    </div>
                    <div className={styles.colAssignee}>
                      <div className={styles.assigneePillWrap}>
                        <button
                          type="button"
                          className={[styles.assigneePill, row.assigneeName ? '' : styles.assigneePillEmpty].join(
                            ' ',
                          )}
                          onClick={(event) => {
                            event.stopPropagation();
                            setOpenRowId((prev) => (prev === row.id ? null : row.id));
                          }}
                        >
                          {row.assigneeName ? (
                            <>
                              <div className={styles.pillAvatar}>{row.assigneeName.charAt(0)}</div>
                              <span className={styles.pillName}>{row.assigneeName}</span>
                            </>
                          ) : (
                            <span className={styles.pillPlaceholder}>-</span>
                          )}
                          <Icon
                            name="chevron-down"
                            size={14}
                            className={[styles.pillChevron, openRowId === row.id ? styles.pillChevronOpen : ''].join(
                              ' ',
                            )}
                          />
                        </button>
                        {openRowId === row.id && (
                          <div className={styles.assigneeDropdown}>
                            {ASSIGNEE_OPTIONS.map((name) => (
                              <div
                                key={name}
                                onClick={() => selectAssignee(row.id, name)}
                                className={styles.assigneeOption}
                              >
                                {name}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
                {filteredRows.length === 0 && (
                  <p className={styles.emptyTableRow}>검색·필터 조건에 맞는 업무가 없습니다.</p>
                )}
              </div>
            </div>

            <p className={styles.totalCount}>총 {filteredRows.length}건</p>
          </div>

          <div className={styles.rightColumn}>
            <div className={styles.rightHeader}>
              <h3>Assignment Rationale &amp; Controls</h3>
              <p>선택된 업무에 대한 배정 근거입니다</p>
            </div>

            {selectedRow ? (
              <>
                <div className={styles.selectedTaskCard}>
                  <div className={styles.selectedTaskTitle}>{selectedRow.title}</div>
                  <hr />
                  <div className={styles.assigneeDetailRow}>
                    <div className={styles.bigAvatar}>{selectedRow.assigneeName?.charAt(0) ?? '-'}</div>
                    <div className={styles.assigneeMeta}>
                      <span className={styles.aName}>{selectedRow.assigneeName ?? '미배정'}</span>
                      <span className={styles.aRole}>{selectedRow.statusLabel}</span>
                    </div>
                  </div>
                </div>

                {mode === 'dashboard' ? (
                  <div className={styles.rationaleSection}>
                    <h4>추천 배정 사유</h4>
                    <div className={styles.rationaleBullets}>
                      <p className={styles.emptyTableRow}>배정 근거가 없습니다.</p>
                    </div>
                  </div>
                ) : (
                  <div className={styles.reassignmentNotice}>
                    <div className={styles.noticeHeader}>
                      <div className={styles.noticeIcon}>
                        <Icon name="info" size={16} />
                      </div>
                      <p>배정이 수동으로 변경되었습니다</p>
                    </div>
                    <p className={styles.diffLine}>수동 변경 후: {selectedRow.assigneeName ?? '미배정'}</p>
                    <p className={styles.disclaimer}>수동 변경된 업무는 AI 추천 근거를 제공하지 않습니다</p>
                  </div>
                )}
              </>
            ) : (
              <p className={styles.emptyTableRow}>선택된 업무가 없습니다.</p>
            )}
          </div>
        </div>
      </div>

      <div className={styles.bottomBar}>
        <Button
          variant="secondary"
          iconLeft={<Icon name="arrow-left" size={16} />}
          onClick={() => navigate(`/tasks/recommendation${location.search}`)}
        >
          이전 단계
        </Button>
        <div className={styles.bottomBarRight}>
          <Button variant="outline" iconLeft={<ReassignIcon />} onClick={() => switchMode('reassigned')}>
            업무 재배정
          </Button>
          <Button
            variant="primary"
            iconRight={<Icon name="arrow-right" size={16} />}
            onClick={() => navigate('/dashboard')}
          >
            검토 완료 · 대시보드로
          </Button>
        </div>
      </div>
    </div>
  );
}
