import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Badge, Button, Icon, TopNav, useToast } from '../../components';
import { MAIN_NAV_TABS } from '../../routes';
import { FileRegistrationTable, FILE_ROWS, DEFAULT_SELECTED_IDS } from './FileRegistrationTable';
import styles from './NewFilesPage.module.css';

type DemoState = 'empty' | 'reviewB';

interface HistoryItem {
  date: string;
  label: string;
  status: '완료' | 'PARTIAL_RESULT';
}

const HISTORY: HistoryItem[] = [];

export default function NewFilesPage() {
  const [searchParams] = useSearchParams();
  const isDistributionPreview =
    searchParams.get('preview') === 'distribution' || searchParams.get('view') === 'review';
  const [demoState, setDemoState] = useState<DemoState>(isDistributionPreview ? 'reviewB' : 'empty');
  const [selected, setSelected] = useState<Set<string>>(new Set(DEFAULT_SELECTED_IDS));
  const { showToast } = useToast();
  const navigate = useNavigate();

  useEffect(() => {
    setDemoState(isDistributionPreview ? 'reviewB' : 'empty');
  }, [isDistributionPreview]);

  function handleGoToWorkspace() {
    showToast('팀원 선택 화면으로 이동합니다.', 'info');
    setTimeout(() => {
      navigate('/workspace');
    }, 700);
  }

  const supportedIds = useMemo(() => FILE_ROWS.filter((row) => row.supported).map((row) => row.id), []);
  const registeredRows = useMemo(
    () => FILE_ROWS.filter((row) => DEFAULT_SELECTED_IDS.includes(row.id)),
    [],
  );

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

  function handleRegisterClick() {
    showToast('파일 등록이 완료되었습니다.', 'success');
    setTimeout(() => {
      navigate('/projects');
    }, 900);
  }

  return (
    <div className={styles.page}>
      <TopNav
        tabs={MAIN_NAV_TABS}
        activeTo={demoState === 'reviewB' ? '/projects' : '/files/new'}
        userLabel="관리자"
      />

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
                <span className={styles.summaryCount}>0개 파일 선택됨</span>
                <Button
                  variant="primary"
                  iconRight={<Icon name="arrow-right" size={14} color="currentColor" />}
                  onClick={handleRegisterClick}
                >
                  선택 파일 등록
                </Button>
              </div>
            </div>

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
              rows={registeredRows}
              selected={selected}
              onToggleRow={toggleRow}
              onToggleAll={toggleAll}
              mode="readonly"
              showSupport={false}
            />

            <div className={styles.nextStepRow}>
              <Button
                variant="primary"
                iconRight={<Icon name="arrow-right" size={14} color="currentColor" />}
                onClick={handleGoToWorkspace}
              >
                다음: 팀원 선택
              </Button>
            </div>
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
        {HISTORY.length === 0 && <p className={styles.historyEmpty}>최근 처리 이력이 없습니다.</p>}
      </div>
    </div>
  );
}
