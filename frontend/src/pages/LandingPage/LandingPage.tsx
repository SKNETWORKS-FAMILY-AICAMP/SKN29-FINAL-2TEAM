import { Link } from 'react-router-dom';
import { Button, Icon } from '../../components';
import styles from './LandingPage.module.css';

export default function LandingPage() {
  return (
    <div className={styles.page}>
      <nav className={styles.nav}>
        <div className={styles.logo}>
          <span className={styles.logoMark}>h</span>
          <span className={styles.logoName}>halil</span>
        </div>
        <div className={styles.navLinks}>
          <a href="#features">기능</a>
          <a href="#connectors">연동 서비스</a>
          <a href="#pricing">요금제</a>
          <a href="#contact">문의하기</a>
        </div>
        <div className={styles.navActions}>
          <Link to="/login" className={styles.loginLink}>
            로그인
          </Link>
          <Link to="/signup">
            <Button variant="primary" size="sm">
              무료로 시작하기
            </Button>
          </Link>
        </div>
      </nav>

      <section className={styles.hero}>
        <span className={styles.badge}>
          <Icon name="sparkles" size={14} />
          AI 기반 업무 배정 코파일럿 halil 출시
        </span>
        <h1 className={styles.heroTitle}>
          흩어진 업무, AI가 정리하고 배정까지
        </h1>
        <p className={styles.heroSubtitle}>
          문서·일정·인력 데이터를 연결하면, halil이 최적의 담당자를 찾아 추천합니다. PM의 승인 한 번으로 Jira 티켓까지 스마트하게 생성하세요.
        </p>
        <div className={styles.heroActions}>
          <Link to="/signup">
            <Button variant="primary" size="lg">
              무료로 시작하기
            </Button>
          </Link>
          <Link to="/dashboard">
            <Button variant="outline" size="lg">
              데모 보기
            </Button>
          </Link>
        </div>
      </section>

      <div className={styles.previewWrap}>
        <div className={styles.browserCard}>
          <div className={styles.browserBar}>
            <div className={styles.trafficLights}>
              <span className={styles.dotRed} />
              <span className={styles.dotYellow} />
              <span className={styles.dotGreen} />
            </div>
            <span className={styles.browserUrl}>workspace.halil.ai</span>
            <span className={styles.connectedBadge}>
              <Icon name="send" size={13} />
              Workspace 연결됨
            </span>
          </div>

          <div className={styles.previewBody}>
            <div>
              <p className={styles.docListTitle}>분석된 문서 목록</p>
              <div className={styles.docList}>
                <div className={styles.docRow}>
                  <Icon name="file-text" size={15} />
                  2024_Q4_마케팅_기획서.gdoc
                </div>
                <div className={styles.docRow}>
                  <Icon name="file-text" size={15} />
                  시스템_성능_개선_요구사항.pdf
                </div>
                <div className={styles.docRow}>
                  <Icon name="file-spreadsheet" size={15} />
                  유저_피드백_스프레드시트.gsheet
                </div>
              </div>
            </div>

            <div className={styles.aiPanel}>
              <div className={styles.aiPanelHeader}>
                <span className={styles.aiPanelHeading}>
                  <Icon name="chart-network" size={15} />
                  AI 추천 배정 제안
                </span>
                <span className={styles.confidence}>신뢰도 98%</span>
              </div>

              <p className={styles.taskLabel}>추출된 업무</p>
              <div className={styles.taskBox}>
                &ldquo;Q4 캠페인용 성과 대시보드 UI 개발 및 API 연동&rdquo;
              </div>

              <div className={styles.assigneeRow}>
                <span className={styles.avatar}>김</span>
                <div className={styles.assigneeInfo}>
                  <div className={styles.assigneeName}>김민수 (Frontend Lead)</div>
                  <div className={styles.assigneeMeta}>현재 워크로드: 여유 (20%)</div>
                </div>
                <Button variant="primary" size="sm" className={styles.approveButton}>
                  승인 후 Jira 생성
                </Button>
              </div>

              <div className={styles.reasonBox}>
                <Icon name="circle-help" size={14} />
                <span>
                  <strong>추천 근거</strong> · 김민수님은 지난 분기 &lsquo;대시보드 연동&rsquo; 모듈을 개발하였으며, 캘린더 분석 결과 이번 주 여유 일정이 12시간 확인됩니다.
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
