import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Button, Icon, TopNav } from '../../components';
import { MAIN_NAV_TABS } from '../../routes';
import styles from './TaskDistributionPage.module.css';

type ScreenState = 'loading' | 'partial-fail';
type StepStatus = 'done' | 'active' | 'pending' | 'warning';
type StepWeight = 'medium' | 'semibold' | 'muted';

interface StepItem {
  label: string;
  status: StepStatus;
  weight: StepWeight;
  subnote?: string;
}

interface StateConfig {
  steps: StepItem[];
  progressLabel: string;
  progressPercent: number;
  showAmberBanner: boolean;
}

const STATE_CONFIG: Record<ScreenState, StateConfig> = {
  loading: {
    steps: [
      { label: '문서에서 업무 후보 추출 중', status: 'done', weight: 'medium' },
      { label: '인원별 워크로드 계산 중', status: 'active', weight: 'semibold' },
      { label: '배정 추천 생성 중', status: 'pending', weight: 'muted' },
      { label: '정책 검증 중', status: 'pending', weight: 'muted' },
    ],
    progressLabel: '2/4 단계 (40%)',
    progressPercent: 40,
    showAmberBanner: false,
  },
  'partial-fail': {
    steps: [
      { label: '문서에서 업무 후보 추출 중', status: 'done', weight: 'medium' },
      {
        label: '인원별 워크로드 계산 중',
        status: 'warning',
        weight: 'semibold',
        subnote: '일부 문서 처리에 실패했어요',
      },
      { label: '배정 추천 생성 중', status: 'active', weight: 'semibold' },
      { label: '정책 검증 중', status: 'pending', weight: 'muted' },
    ],
    progressLabel: '3/4 단계 (60%)',
    progressPercent: 60,
    showAmberBanner: true,
  },
};

function StepStatusIcon({ status }: { status: StepStatus }) {
  if (status === 'done') {
    return (
      <span className={`${styles.stepIcon} ${styles.iconDone}`}>
        <Icon name="check-circle" size={15} />
      </span>
    );
  }
  if (status === 'active') {
    return (
      <span className={`${styles.stepIcon} ${styles.iconActive}`}>
        <Icon name="loader" size={13} spin />
      </span>
    );
  }
  if (status === 'warning') {
    return (
      <span className={`${styles.stepIcon} ${styles.iconWarning}`}>
        <Icon name="triangle-alert" size={15} />
      </span>
    );
  }
  return <span className={`${styles.stepIcon} ${styles.iconPending}`} aria-hidden="true" />;
}

function weightClassName(weight: StepWeight): string {
  if (weight === 'medium') return styles.weightMedium;
  if (weight === 'semibold') return styles.weightSemibold;
  return styles.weightMuted;
}

export default function TaskDistributionPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [screenState, setScreenState] = useState<ScreenState>('loading');
  const navigate = useNavigate();
  const config = STATE_CONFIG[screenState];

  useEffect(() => {
    const timer = setTimeout(() => {
      navigate('/tasks/recommendation');
    }, 3000);
    return () => clearTimeout(timer);
  }, [navigate]);

  return (
    <div className={styles.page}>
      <div className={styles.demoBar}>
        <span className={styles.demoLabel}>미리보기 상태 전환</span>
        <button
          type="button"
          className={[styles.demoBtn, screenState === 'loading' ? styles.demoBtnActive : ''].join(' ')}
          onClick={() => setScreenState('loading')}
        >
          진행 중 (task-distribution-loading)
        </button>
        <button
          type="button"
          className={[styles.demoBtn, screenState === 'partial-fail' ? styles.demoBtnActive : ''].join(' ')}
          onClick={() => setScreenState('partial-fail')}
        >
          일부 실패 (task-distribution-partial-fail)
        </button>
      </div>

      <TopNav tabs={MAIN_NAV_TABS} activeTo="/projects" />

      <div className={styles.workspace}>
        <div className={styles.centerCard}>
          <div className={styles.cardHeading}>
            <h1>업무 분배를 진행하고 있어요</h1>
            <p>AI가 문서를 분석하고 배정을 준비하는 중이에요. 몇 분 정도 걸릴 수 있어요.</p>
          </div>

          <div className={styles.stepList}>
            {config.steps.map((step) => (
              <div className={styles.stepRow} key={step.label}>
                <div className={styles.stepRowMain}>
                  <StepStatusIcon status={step.status} />
                  <p className={`${styles.stepLabel} ${weightClassName(step.weight)}`}>{step.label}</p>
                </div>
                {step.subnote && (
                  <div className={styles.stepSubnote}>
                    <p>{step.subnote}</p>
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className={styles.progressBlock}>
            <div className={styles.progressLabels}>
              <span className={styles.pLabel}>전체 진행률</span>
              <span className={styles.pValue}>{config.progressLabel}</span>
            </div>
            <div className={styles.progressTrack}>
              <div className={styles.progressFill} style={{ width: `${config.progressPercent}%` }} />
            </div>
          </div>

          {config.showAmberBanner && (
            <div className={styles.amberBanner}>
              <Icon name="triangle-alert" size={17} />
              <p>일부 문서 처리에 실패했어요, 계속 진행돼요</p>
            </div>
          )}

          <div className={styles.divider} />

          <div className={styles.footnoteRow}>
            <Icon name="circle-help" size={13} />
            <p>이 화면을 벗어나도 진행은 계속돼요</p>
          </div>

          <div className={styles.nextAction}>
            <Button
              variant="primary"
              iconRight={<Icon name="arrow-right" size={14} />}
              onClick={() => navigate(`/tasks/recommendation${location.search}`)}
            >
              데모 분석 완료 · 추천 결과 보기
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
