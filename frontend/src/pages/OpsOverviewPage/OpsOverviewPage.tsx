import { useNavigate } from 'react-router-dom';
import {
  OpsPageHeader,
  OpsStatusBadge,
  OpsSummaryCard,
  OpsSummaryGrid,
} from '../../components';
import styles from '../OpsShared/OpsPages.module.css';

const ACTIONS = [
  { tone: 'warning', badge: '확인', title: '구글 드라이브 인증 만료', meta: '제품전략팀 · 인증 만료 · 2시간 전', action: '연결 보기', to: '/ops/connectors' },
  { tone: 'danger', badge: '긴급', title: '계정과 직원 연결 충돌', meta: '직원 18 · 중복 연결 감지', action: '계정 보기', to: '/ops/accounts' },
  { tone: 'info', badge: '예정', title: '오늘 만료되는 초대 2건', meta: '오늘 만료되는 초대 2건', action: '초대 보기', to: '/ops/mappings' },
] as const;

const ACTIVITIES = [
  ['운영자 · 계정 18 재활성', '10분 전'],
  ['운영자 · 만료 초대 폐기', '25분 전'],
  ['운영자 · 직원 연결 해제', '1시간 전'],
  ['시스템 · 구글 인증 만료', '2시간 전'],
];

export default function OpsOverviewPage() {
  const navigate = useNavigate();

  return (
    <div className={styles.page}>
      <OpsPageHeader
        title="운영 현황"
        description="플랫폼에 연결된 범위와 운영상 확인이 필요한 항목을 한눈에 확인합니다."
      />

      <OpsSummaryGrid>
        <OpsSummaryCard label="연결 조직 범위" value={12} detail="플랫폼에 연결된 범위" onClick={() => navigate('/ops/organizations')} />
        <OpsSummaryCard label="전체 계정" value={89} detail="정상 86 · 확인 필요 3" tone="danger" onClick={() => navigate('/ops/accounts')} />
        <OpsSummaryCard label="연결 확인 필요" value={5} detail="확인 필요 2 · 오류 3" tone="warning" onClick={() => navigate('/ops/connectors')} />
        <OpsSummaryCard label="수락 대기 초대" value={7} detail="오늘 만료 예정 2개" tone="info" onClick={() => navigate('/ops/mappings')} />
      </OpsSummaryGrid>

      <div className={styles.overviewVisuals}>
        <section className={styles.panel}>
          <h2>계정 운영 상태</h2>
          <div className={styles.largeValue}>
            <strong>89</strong>
            <span>전체 계정</span>
          </div>
          <div className={styles.stackedBar} aria-label="정상 계정 86개, 확인 필요 계정 3개">
            <span className={styles.barSuccess} style={{ width: '96.6%' }} />
            <span className={styles.barDanger} style={{ width: '3.4%' }} />
          </div>
          <div className={styles.legend}>
            <button type="button" className={styles.statusLink} onClick={() => navigate('/ops/accounts?status=정상')}>
              <span className={styles.successText}>● 정상 86개</span>
            </button>
            <button type="button" className={styles.statusLink} onClick={() => navigate('/ops/accounts?status=확인 필요')}>
              <span className={styles.dangerText}>● 확인 필요 3개</span>
            </button>
          </div>
          <p className={styles.panelSubtitle}>상태를 누르면 계정 관리의 해당 목록으로 이동합니다.</p>
        </section>

        <section className={styles.panel}>
          <h2>연결 서비스 상태</h2>
          <p className={styles.panelSubtitle}>플랫폼 연결 31개의 최근 확인 결과</p>
          <div className={styles.barRows}>
            {[
              ['연결됨', 84, '26개', styles.barSuccess, styles.successText],
              ['확인 필요', 7, '2개', styles.barWarning, styles.warningText],
              ['오류', 9, '3개', styles.barDanger, styles.dangerText],
            ].map(([label, width, count, barClass, textClass]) => (
              <button
                type="button"
                className={[styles.barRow, styles.barRowButton].join(' ')}
                key={String(label)}
                onClick={() => navigate(`/ops/connectors?status=${encodeURIComponent(String(label))}`)}
              >
                <span>{label}</span>
                <div className={styles.barTrack}>
                  <span className={String(barClass)} style={{ width: `${width}%` }} />
                </div>
                <strong className={String(textClass)}>{count}</strong>
              </button>
            ))}
          </div>
        </section>
      </div>

      <div className={styles.overviewBottom}>
        <section className={styles.panel}>
          <h2>오늘 확인할 일 · 3건</h2>
          <p className={styles.panelSubtitle}>관련 화면에서 원인과 현재 상태를 확인하세요.</p>
          <div className={styles.actionList}>
            {ACTIONS.map((item) => (
              <div key={item.title} className={[styles.actionItem, styles[`action_${item.tone}`]].join(' ')}>
                <OpsStatusBadge tone={item.tone}>{item.badge}</OpsStatusBadge>
                <div className={styles.actionCopy}>
                  <strong>{item.title}</strong>
                  <span>{item.meta}</span>
                </div>
                <button type="button" className={styles.outlineAction} onClick={() => navigate(item.to)}>
                  {item.action}
                </button>
              </div>
            ))}
          </div>
        </section>

        <section className={styles.panel}>
          <h2>최근 운영 활동</h2>
          <div className={styles.activityList}>
            {ACTIVITIES.map(([label, time]) => (
              <div className={styles.activityItem} key={label}>
                <span className={styles.activityDot} />
                <strong>{label}</strong>
                <span>{time}</span>
              </div>
            ))}
          </div>
          <button type="button" className={styles.linkAction} onClick={() => navigate('/ops/audit?view=operations')}>
            감사 로그에서 전체 보기 →
          </button>
        </section>
      </div>
    </div>
  );
}
