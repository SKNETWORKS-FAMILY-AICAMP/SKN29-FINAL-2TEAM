import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Badge, Icon, TopNav, useToast } from '../../components';
import { MAIN_NAV_TABS } from '../../routes';
import { FileRegistrationTable, FILE_ROWS, DEFAULT_SELECTED_IDS } from './FileRegistrationTable';
import styles from './NewFilesPage.module.css';

type DemoState = 'empty' | 'reviewA' | 'reviewB';

interface HistoryItem {
  date: string;
  label: string;
  status: '완료' | 'PARTIAL_RESULT';
}

const HISTORY: HistoryItem[] = [
  { date: '2025.01.18', label: '문서 3건 등록', status: '완료' },
  { date: '2025.01.15', label: '문서 5건 등록 · 업무 분배', status: '완료' },
  { date: '2025.01.12', label: '문서 2건 등록', status: 'PARTIAL_RESULT' },
];

const TOGGLE_OPTIONS: Array<{ target: DemoState; label: string }> = [
  { target: 'empty', label: '빈 상태 (new-files-empty)' },
  { target: 'reviewA', label: '검토 상태 · 신규 파일 (new-files-review A)' },
  { target: 'reviewB', label: '검토 상태 · 업무 분배 미리보기 (new-files-review B)' },
];

export default function NewFilesPage() {
  const [demoState, setDemoState] = useState<DemoState>('empty');
  const [selected, setSelected] = useState<Set<string>>(new Set(DEFAULT_SELECTED_IDS));
  const { showToast } = useToast();
  const navigate = useNavigate();

  const supportedIds = useMemo(() => FILE_ROWS.filter((row) => row.supported).map((row) => row.id), []);

  function toggleRow(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  function toggleAll() {
    setSelected((prev) => {
      const allChecked = supportedIds.every((id) => prev.has(id));
      return allChecked ? new Set() : new Set(supportedIds);
    });
  }

  function handleSubmit() {
    showToast(`선택한 ${selected.size}개 파일 등록이 완료되었습니다.`, 'success');
    setTimeout(() => {
      navigate('/projects');
    }, 900);
  }

  return (
    <div className={styles.page}>
      <div className={styles.demoToggleBar}>
        <span className={styles.demoLabel}>미리보기 상태 전환</span>
        {TOGGLE_OPTIONS.map((option) => (
          <button
            key={option.target}
            type="button"
            className={[styles.toggleBtn, demoState === option.target ? styles.toggleBtnActive : '']
              .filter(Boolean)
              .join(' ')}
            onClick={() => setDemoState(option.target)}
          >
            {option.label}
          </button>
        ))}
      </div>

      <TopNav tabs={MAIN_NAV_TABS} activeTo="/files/new" userLabel="관리자" />

      <div className={styles.contentContainer}>
        {demoState === 'empty' && (
          <>
            <div className={styles.pageHeading}>
              <h1>신규 파일</h1>
              <p>새로 추가된 문서를 검토하고 등록하세요</p>
            </div>

            <div className={styles.tableCard}>
              <div className={styles.tableHeader}>
                <div className={styles.colSelect}>
                  <span className={styles.disabledCheckbox} aria-hidden="true" />
                  <span className={styles.thMuted}>전체선택</span>
                </div>
                <span className={styles.thMuted}>파일명</span>
                <span className={styles.thMuted}>소속 폴더</span>
                <span className={styles.thMuted}>감지일</span>
                <span className={styles.thMuted}>역할</span>
                <span className={styles.thMuted}>지원 여부</span>
              </div>

              <div className={styles.emptyBody}>
                <div className={styles.iconCircle}>
                  <Icon name="folder-open" size={24} color="var(--color-placeholder)" />
                </div>
                <div className={styles.emptyText}>
                  <p>새로 추가된 파일이 없어요</p>
                  <p>다음 동기화까지 기다려주세요</p>
                </div>
              </div>

              <div className={styles.actionBar}>
                <span className={[styles.summaryCount, styles.isDisabled].join(' ')}>0개 파일 선택됨</span>
                <button type="button" className={styles.disabledSubmitBtn} disabled>
                  <span>선택 파일 등록</span>
                  <Icon name="arrow-right" size={14} />
                </button>
              </div>
            </div>

            <HistoryBlock />
          </>
        )}

        {demoState === 'reviewA' && (
          <>
            <div className={styles.pageHeading}>
              <h1>신규 파일</h1>
              <p>새로 추가된 문서를 검토하고 등록하세요</p>
            </div>

            <FileRegistrationTable
              rows={FILE_ROWS}
              selected={selected}
              onToggleRow={toggleRow}
              onToggleAll={toggleAll}
              mode="submit"
              onSubmit={handleSubmit}
            />

            <HistoryBlock />
          </>
        )}

        {demoState === 'reviewB' && (
          <>
            <div className={styles.pageHeading}>
              <h1>업무 분배</h1>
              <p>현재 등록된 파일</p>
            </div>

            <FileRegistrationTable
              rows={FILE_ROWS}
              selected={selected}
              onToggleRow={toggleRow}
              onToggleAll={toggleAll}
              mode="readonly"
            />
          </>
        )}
      </div>

      <p className={styles.footnote}>halil · AI 기반 업무 배정 코파일럿 — 데모용 정적 목업 (실제 데이터 아님)</p>
    </div>
  );
}

function HistoryBlock() {
  return (
    <div className={styles.historyBlock}>
      <h2>최근 처리 이력</h2>
      <div className={styles.historyCard}>
        {HISTORY.map((item) => (
          <div key={item.date} className={styles.historyRow}>
            <div className={styles.historyLeft}>
              <span className={styles.historyDate}>{item.date}</span>
              <span className={styles.historyLabel}>{item.label}</span>
            </div>
            <Badge tone={item.status === '완료' ? 'success' : 'warning'}>{item.status}</Badge>
          </div>
        ))}
      </div>
    </div>
  );
}
