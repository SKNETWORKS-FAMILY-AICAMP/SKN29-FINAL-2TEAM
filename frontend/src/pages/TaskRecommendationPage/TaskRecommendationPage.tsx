import { useEffect, useRef, useState } from 'react';
import { Badge, Button, Icon, TopNav, useToast } from '../../components';
import type { BadgeTone } from '../../components';
import { MAIN_NAV_TABS } from '../../routes';
import styles from './TaskRecommendationPage.module.css';

type FilterKey = 'all' | 'verify' | 'unconfirmed';

interface AltCandidate {
  name: string;
  initial: string;
  avatarColor: string;
  score: number;
}

interface TaskCard {
  id: string;
  fileName: string;
  title: string;
  assigneeName: string;
  assigneeInitial: string;
  avatarColor: string;
  fitTone: BadgeTone;
  fitLabel: string;
  reasons: string[];
  duration: string;
  flags: FilterKey[];
  needsVerify: boolean;
  altCandidates: AltCandidate[];
}

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: 'all', label: '전체' },
  { key: 'verify', label: '근거 확인 필요' },
  { key: 'unconfirmed', label: '미확정 정보 포함' },
];

const NOTIFICATIONS = [
  '새로운 업무 추천 결과가 도착했어요.',
  '김민수님이 배정을 확인했어요.',
  '스프린트3 회의록이 업데이트됐어요.',
];

const TASKS: TaskCard[] = [
  {
    id: 'task-1',
    fileName: '프로젝트_기획.docx',
    title: 'API 인증 모듈 리팩토링',
    assigneeName: '김민수',
    assigneeInitial: '김',
    avatarColor: 'var(--color-primary)',
    fitTone: 'success',
    fitLabel: '높음',
    reasons: ['최근 유사 업무 3건 처리 이력', '이번 주 가용 시간 14시간', '인증 모듈 도메인 전문성 보유'],
    duration: '3일',
    flags: [],
    needsVerify: false,
    altCandidates: [
      { name: '이지은', initial: '이', avatarColor: 'var(--color-info)', score: 78 },
      { name: '박서준', initial: '박', avatarColor: 'var(--color-placeholder)', score: 65 },
    ],
  },
  {
    id: 'task-2',
    fileName: '스프린트3_회의록.docx',
    title: '결제 시스템 에러 핸들링 개선',
    assigneeName: '이지은',
    assigneeInitial: '이',
    avatarColor: 'var(--color-info)',
    fitTone: 'warning',
    fitLabel: '보통',
    reasons: ['결제 도메인 경험 2년', '현재 진행 업무 2건으로 여유 있음'],
    duration: '5일',
    flags: ['verify'],
    needsVerify: true,
    altCandidates: [
      { name: '김민수', initial: '김', avatarColor: 'var(--color-primary)', score: 71 },
      { name: '최도현', initial: '최', avatarColor: 'var(--color-placeholder)', score: 58 },
    ],
  },
];

export default function TaskRecommendationPage() {
  const { showToast } = useToast();
  const [activeFilter, setActiveFilter] = useState<FilterKey>('all');
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [notifOpen, setNotifOpen] = useState(false);
  const notifRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!notifOpen) return;

    function handleOutsideClick(event: MouseEvent) {
      if (notifRef.current && !notifRef.current.contains(event.target as Node)) {
        setNotifOpen(false);
      }
    }

    window.addEventListener('click', handleOutsideClick);
    return () => window.removeEventListener('click', handleOutsideClick);
  }, [notifOpen]);

  const visibleTasks = activeFilter === 'all' ? TASKS : TASKS.filter((task) => task.flags.includes(activeFilter));

  function toggleCandidates(taskId: string) {
    setExpanded((prev) => ({ ...prev, [taskId]: !prev[taskId] }));
  }

  return (
    <div className={styles.screen}>
      <div className={styles.topSection}>
        <TopNav tabs={MAIN_NAV_TABS} activeTo="/projects" onBellClick={() => setNotifOpen((open) => !open)} />

        {notifOpen && (
          <div className={styles.notifDropdown} ref={notifRef}>
            <h3>알림</h3>
            {NOTIFICATIONS.map((message) => (
              <div className={styles.notifItem} key={message}>
                {message}
              </div>
            ))}
          </div>
        )}

        <main className={styles.mainBody}>
          <div className={styles.pageHeading}>
            <h1>업무 추천 결과</h1>
            <p>4개 업무 후보에 대한 배정 추천이에요</p>
          </div>

          <div className={styles.filterBar}>
            {FILTERS.map((filter) => (
              <button
                key={filter.key}
                type="button"
                className={[styles.filterChip, activeFilter === filter.key ? styles.filterChipActive : ''].join(' ')}
                onClick={() => setActiveFilter(filter.key)}
              >
                {filter.label}
              </button>
            ))}
          </div>

          <div className={styles.taskList}>
            {visibleTasks.length === 0 && <p className={styles.emptyState}>해당 조건에 맞는 업무 후보가 없어요.</p>}

            {visibleTasks.map((task) => {
              const isExpanded = Boolean(expanded[task.id]);
              return (
                <article className={styles.taskCard} key={task.id}>
                  <div className={styles.cardHeader}>
                    <div className={styles.cardHeaderLeft}>
                      <div className={styles.fileChip}>
                        <Icon name="file-text" size={14} />
                        <span>{task.fileName}</span>
                      </div>
                      <h2 className={styles.taskTitle}>{task.title}</h2>
                    </div>
                  </div>

                  <hr className={styles.divider} />

                  <div className={styles.assigneeSection}>
                    <div className={styles.assigneeRow}>
                      <span className={styles.assigneeLabel}>추천 배정자:</span>
                      <div className={styles.assignee}>
                        <div
                          className={`${styles.avatar} ${styles.avatarSm}`}
                          style={{ background: task.avatarColor }}
                        >
                          {task.assigneeInitial}
                        </div>
                        <span className={styles.assigneeName}>{task.assigneeName}</span>
                      </div>
                      <Badge tone={task.fitTone}>{task.fitLabel}</Badge>
                    </div>
                    <ul className={styles.reasonList}>
                      {task.reasons.map((reason) => (
                        <li key={reason}>
                          <span className={styles.dot} />
                          {reason}
                        </li>
                      ))}
                    </ul>
                  </div>

                  <hr className={styles.divider} />

                  <div className={styles.cardFooter}>
                    <button
                      type="button"
                      className={[styles.toggleCandidates, isExpanded ? styles.toggleCandidatesExpanded : ''].join(
                        ' ',
                      )}
                      onClick={() => toggleCandidates(task.id)}
                    >
                      다른 후보 보기
                      <Icon name="chevron-down" size={14} className={styles.chevron} />
                    </button>
                    <div className={styles.footerRight}>
                      <span className={styles.duration}>
                        예상 소요: <strong>{task.duration}</strong>
                      </span>
                      {task.needsVerify && (
                        <span className={styles.verifyBadge} tabIndex={0}>
                          <Icon name="circle-help" size={12} />
                          확인 필요
                          <span className={styles.tooltip} role="tooltip">
                            이 추천은 미확정 정보(예상 일정, 최근 성과 데이터)를 기반으로 계산됐어요. 배정 전에
                            근거를 확인해 주세요.
                          </span>
                        </span>
                      )}
                    </div>
                  </div>

                  {isExpanded && (
                    <div className={styles.altCandidates}>
                      {task.altCandidates.map((candidate) => (
                        <div className={styles.altCandidate} key={candidate.name}>
                          <div
                            className={`${styles.avatar} ${styles.avatarXs}`}
                            style={{ background: candidate.avatarColor }}
                          >
                            {candidate.initial}
                          </div>
                          <span>{candidate.name}</span>
                          <span className={styles.altScore}>적합도 {candidate.score}%</span>
                        </div>
                      ))}
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        </main>
      </div>

      <footer className={styles.bottomBar}>
        <Button variant="secondary" onClick={() => showToast('이전 단계로 이동합니다.')}>
          이전 단계
        </Button>
        <Button variant="primary" onClick={() => showToast('검증 결과 확인 단계로 이동합니다.')}>
          다음: 검증 결과 확인
        </Button>
      </footer>
    </div>
  );
}
