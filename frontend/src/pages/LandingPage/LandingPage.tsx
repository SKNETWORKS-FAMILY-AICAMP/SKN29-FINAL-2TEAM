import { Link } from 'react-router-dom';
import { clearSession, useSession } from '../../utils/session';
import arrowLeftRight from '../../assets/landing/arrow-left-right.svg';
import avatar from '../../assets/landing/avatar.png';
import badgeCheck from '../../assets/landing/badge-check.svg';
import brainCog from '../../assets/landing/brain-cog.svg';
import check from '../../assets/landing/check.svg';
import checkCircle from '../../assets/landing/check-circle.svg';
import database from '../../assets/landing/database.svg';
import fileText from '../../assets/landing/file-text.svg';
import linkIcon from '../../assets/landing/link.svg';
import messageCircle from '../../assets/landing/message-circle.svg';
import search from '../../assets/landing/search.svg';
import sparkles from '../../assets/landing/sparkles.svg';
import squareStack from '../../assets/landing/square-stack.svg';
import zap from '../../assets/landing/zap.svg';
import styles from './LandingPage.module.css';

const features = [
  {
    icon: arrowLeftRight,
    title: '커넥터 연동',
    description: 'Google Drive, Jira, People DB를 한곳에 연결합니다. 흩어진 프로젝트 근거가 빠르게 모입니다.',
  },
  {
    icon: sparkles,
    title: 'AI 업무 추천',
    description: '업무 문서를 분석해 핵심 태스크를 추출하고, 기술 스택과 가용 리소스를 고려해 후보를 추천합니다.',
  },
  {
    icon: badgeCheck,
    title: 'PM 검토 후 반영',
    description: 'AI가 제안한 배정안과 근거를 PM이 검토·수정·승인한 뒤 Jira 반영 단계로 전달합니다.',
  },
];

const steps = [
  { number: '01', icon: linkIcon, title: '연결', description: 'Google Drive, Jira, People DB 연동' },
  { number: '02', icon: search, title: '분석', description: '문서와 프로젝트 데이터 분석' },
  { number: '03', icon: brainCog, title: '추천', description: 'AI가 담당자 후보와 근거 제안' },
  { number: '04', icon: zap, title: '검토', description: 'PM 검토와 승인 후 Jira 반영' },
];

const plans = [
  {
    name: 'Free',
    price: '₩0',
    description: '개인 기획자 및 소팀을 위한 요금제',
    items: ['기본 Google Drive 및 Jira 연동', '월 최대 20회 AI 업무 추천', '기본 워크로드 대시보드 제공'],
    action: '무료로 시작하기',
  },
  {
    name: 'Pro',
    price: '₩49,000',
    description: '본격적인 업무 관리가 필요한 성장기 팀',
    items: ['Google Drive, Jira, People DB 연동', '무제한 AI 업무 배정 추천', '고급 근거 분석 및 추천 요약', '팀 워크로드 시각화'],
    action: '14일 무료 체험하기',
    recommended: true,
  },
  {
    name: 'Enterprise',
    price: '별도 문의',
    description: '대규모 복합 조직 및 특수 보안 요구 기업',
    items: ['모든 Pro 기능 포함', '전담 기술 지원 매니저', '커스텀 보안 정책 설정(SSO)', '온프레미스·전용 클라우드 구축'],
    action: '세일즈 담당자와 상담',
  },
];

function Logo() {
  return (
    <span className={styles.logo}>
      <span className={styles.logoMark}>h</span>
      <span className={styles.logoText}>halil</span>
    </span>
  );
}

function PrimaryLink({ children, to }: { children: string; to: string }) {
  return (
    <Link className={styles.primaryButton} to={to}>
      {children}
    </Link>
  );
}

export default function LandingPage() {
  const session = useSession();
  // 이미 로그인한 사람에게 가입을 다시 시키지 않는다. 헤더가 세션에 따라
  // 로그인/회원가입과 대시보드를 바꿔 다는 것과 같은 기준이다.
  const startHref = session ? '/dashboard' : '/signup';

  return (
    <div className={styles.page}>
      <header className={styles.navbar}>
        <div className={styles.navbarInner}>
          <Logo />
          <div className={styles.navActions}>
            {session ? (
              <>
                <span className={styles.loginName}>{session.account.display_name} 님</span>
                <Link className={styles.loginLink} to="/dashboard">
                  대시보드
                </Link>
                <button type="button" className={styles.logoutButton} onClick={clearSession}>
                  로그아웃
                </button>
              </>
            ) : (
              <>
                <Link className={styles.loginLink} to="/login">
                  로그인
                </Link>
                <Link className={styles.loginLink} to="/signup">
                  회원가입
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      <section className={styles.hero}>
        <div className={styles.heroBody}>
          <p className={styles.releaseBadge}>✨ AI 기반 업무 배정 코파일럿 halil 출시</p>
          <div className={styles.heroCopy}>
            <h1>흩어진 업무, AI가 정리하고 배정까지</h1>
            <p>
              문서·업무·인력 데이터를 연결하면 halil이 담당자 후보와 근거를 제안합니다.
              <br />
              PM의 검토와 승인으로 더 투명하게 업무를 배정하세요.
            </p>
          </div>
          <div className={styles.heroActions}>
            <PrimaryLink to={startHref}>무료로 시작하기</PrimaryLink>
          </div>

          <div className={styles.preview}>
            <div className={styles.previewTop}>
              <div className={styles.browserMeta}>
                <span className={`${styles.dot} ${styles.red}`} />
                <span className={`${styles.dot} ${styles.yellow}`} />
                <span className={`${styles.dot} ${styles.green}`} />
                <span>workspace.halil.ai</span>
              </div>
              <span className={styles.connectionBadge}>
                <img src={linkIcon} alt="" />
                Workspace 연결됨
              </span>
            </div>
            <div className={styles.previewGrid}>
              <aside className={styles.documentPanel}>
                <strong>분석된 문서 목록</strong>
                {['2026_Q3_서비스_기획서.docx', '시스템_성능_개선_요구사항.pdf', '사용자_피드백_정리.xlsx'].map((file) => (
                  <span className={styles.documentRow} key={file}>
                    <img src={fileText} alt="" />
                    {file}
                  </span>
                ))}
              </aside>
              <article className={styles.recommendationPanel}>
                <div className={styles.recommendationHeader}>
                  <span>
                    <b>AI</b> 추천 배정 제안
                  </span>
                  <em>데모 신뢰도 98%</em>
                </div>
                <div className={styles.extractedTask}>
                  <span>추출된 업무</span>
                  <strong>“성과 대시보드 UI 개발 및 API 연동”</strong>
                </div>
                <div className={styles.assigneeRow}>
                  <span className={styles.person}>
                    <img src={avatar} alt="" />
                    <span>
                      <strong>김민수 (Frontend Lead)</strong>
                      <small>가용 상태: 확인 필요</small>
                    </span>
                  </span>
                  <button type="button" disabled title="실제 Jira 연동 전 데모 버튼입니다.">
                    PM 검토 후 Jira 반영
                  </button>
                </div>
                <p className={styles.rationale}>
                  <strong>🤖 추천 근거</strong>
                  유사 업무 경험과 스킬을 기준으로 제안된 데모입니다. 실제 업무량·부재 데이터가 부족하면 추천을 확정하지
                  않습니다.
                </p>
              </article>
            </div>
          </div>
        </div>
      </section>

      <main>
        <section className={styles.trust}>
          <p>
            🚀 이미 <strong>1,200개 이상의 팀</strong>이 halil로 업무를 완벽하게 배정하고 있습니다
          </p>
          <div className={styles.companyNames}>
            <span>TOSS</span><span>LINE</span><span>SOPHIST</span><span>MUSINSA</span><span>SENDRE</span>
          </div>
        </section>

        <section className={`${styles.section} ${styles.whiteSection}`} id="features">
          <div className={styles.sectionHeading}>
            <h2>스마트한 협업의 새로운 기준</h2>
            <p>따로 수집하고 기획할 필요 없이, 기존 도구들과 유기적으로 연결됩니다.</p>
          </div>
          <div className={styles.featureGrid}>
            {features.map((feature) => (
              <article className={styles.featureCard} key={feature.title}>
                <span className={styles.iconBox}><img src={feature.icon} alt="" /></span>
                <div>
                  <h3>{feature.title}</h3>
                  <p>{feature.description}</p>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className={styles.section}>
          <div className={styles.sectionHeading}>
            <h2>단 4단계로 끝나는 인력 배정 혁신</h2>
            <p>복잡했던 업무 조율과 분석 과정을 하나의 흐름으로 정리합니다.</p>
          </div>
          <div className={styles.stepGrid}>
            {steps.map((step) => (
              <article className={styles.stepCard} key={step.number}>
                <div><strong>{step.number}</strong><img src={step.icon} alt="" /></div>
                <h3>{step.title}</h3>
                <p>{step.description}</p>
              </article>
            ))}
          </div>
        </section>

        <section className={`${styles.detailSection} ${styles.whiteSection}`}>
          <div className={styles.evidenceDemo}>
            <p className={styles.demoLabel}><span /> AI 추천 사유 심층 분석</p>
            <div className={styles.evidenceCard}>
              <div><strong>추천 후보: 이지우 (Backend Engineer)</strong><em>데모 신뢰도 95%</em></div>
              {[
                '과거 유사한 결제 API 업무를 3회 완수함',
                'People DB의 근무 기준과 부재 데이터 확인 필요',
                '연관 문서의 기술 요구사항과 보유 스킬이 일치함',
              ].map((reason) => (
                <p key={reason}><img src={checkCircle} alt="" />{reason}</p>
              ))}
            </div>
          </div>
          <div className={styles.detailCopy}>
            <span>투명한 의사결정 지원</span>
            <h2>단순한 추측이 아닌,<br />명확한 근거 데이터 제공</h2>
            <p>
              AI가 왜 특정 팀원을 추천했는지 스킬, 현재 업무, 근무 기준과 부재 정보를 함께 보여줍니다. 데이터가 부족한
              경우에는 조건부 또는 차단 상태와 이유를 명확하게 안내합니다.
            </p>
          </div>
        </section>

        <section className={`${styles.section} ${styles.whiteSection}`} id="integrations">
          <div className={styles.sectionHeading}>
            <h2>기존에 사용하던 도구 그대로</h2>
            <p>프로젝트 운영에 필요한 데이터 소스를 한곳에서 연결합니다.</p>
          </div>
          <div className={styles.integrationGrid}>
            {[
              { icon: database, name: 'Google Drive', status: '연동 준비' },
              { icon: squareStack, name: 'Jira Software', status: '연동 준비' },
              { icon: messageCircle, name: 'People DB', status: '목업 제공' },
            ].map((integration) => (
              <article key={integration.name}>
                <span><img src={integration.icon} alt="" /></span>
                <div><strong>{integration.name}</strong><small>{integration.status}</small></div>
              </article>
            ))}
          </div>
          <p className={styles.securityNote}>🔒 연결 상태와 데이터 최신성을 검증하고, 필수 데이터가 없으면 분석을 차단합니다.</p>
        </section>

        <section className={styles.detailSection}>
          <div className={styles.detailCopy}>
            <span>과부하 없는 지속 가능한 팀워크</span>
            <h2>팀원별 업무량과<br />가용 리소스 시각화</h2>
            <p>
              People DB의 근무시간·부재와 Jira의 현재 업무량을 함께 확인합니다. 한쪽 데이터만으로 가용성을 추정하지 않고,
              기준 시각과 제한 사항을 함께 표시합니다.
            </p>
          </div>
          <div className={styles.workloadDemo}>
            <strong>이번 주 가용성 및 리소스 현황</strong>
            {[
              { name: '김민수 (FE)', label: '여유 80%', width: '20%', tone: 'green' },
              { name: '이지우 (BE)', label: '여유 30%', width: '70%', tone: 'mint' },
              { name: '박아름 (DE)', label: '여유 15%', width: '85%', tone: 'red' },
            ].map((member) => (
              <div className={styles.workloadRow} key={member.name}>
                <div><span>{member.name}</span><span>{member.label}</span></div>
                <span className={styles.workloadTrack}><i className={styles[member.tone]} style={{ width: member.width }} /></span>
              </div>
            ))}
            <small>※ 수치는 랜딩페이지 UI 설명용 데모이며 실제 판정이 아닙니다.</small>
          </div>
        </section>

        <section className={`${styles.section} ${styles.whiteSection}`} id="pricing">
          <div className={styles.sectionHeading}>
            <h2>팀의 규모에 맞는 합리적인 선택</h2>
            <p>소규모 팀부터 대규모 조직까지 알맞은 요금제를 선택하세요.</p>
          </div>
          <div className={styles.pricingGrid}>
            {plans.map((plan) => (
              <article className={`${styles.planCard} ${plan.recommended ? styles.recommended : ''}`} key={plan.name}>
                {plan.recommended && <span className={styles.recommendedBadge}>추천 요금제</span>}
                <div><h3>{plan.name}</h3><strong>{plan.price}</strong><p>{plan.description}</p></div>
                <ul>
                  {plan.items.map((item) => <li key={item}><img src={check} alt="" />{item}</li>)}
                </ul>
                <Link className={plan.recommended ? styles.primaryButton : styles.outlineButton} to={startHref}>{plan.action}</Link>
              </article>
            ))}
          </div>
        </section>

        <section className={styles.cta} id="contact">
          <div><h2>지금 바로 halil과 함께 업무 배정을 혁신하세요</h2><p>중요한 의사결정에 집중하세요. 근거 정리와 후보 제안은 halil이 돕습니다.</p></div>
          <div><Link to={startHref}>무료로 시작하기</Link><a href="mailto:contact@halil.example">도입 상담 신청</a></div>
        </section>
      </main>

      <footer className={styles.footer}>
        <div className={styles.footerTop}>
          <div className={styles.footerBrand}>
            <Logo />
            <p>AI 기반 업무 배정 코파일럿 halil은 연결된 프로젝트 근거를 바탕으로 PM의 판단을 지원합니다.</p>
          </div>
          <div className={styles.footerLinks}>
            <div><strong>제품</strong><a href="#features">주요 기능</a><span>보안 가이드</span><span>업데이트 소식</span></div>
            <div><strong>회사</strong><span>회사 소개</span><span>채용 정보</span><span>블로그</span></div>
            <div><strong>지원</strong><span>도움말 센터</span><a href="#contact">문의하기</a><span>이용 약관</span></div>
          </div>
        </div>
        <div className={styles.footerBottom}><span>© 2026 halil Inc. All rights reserved.</span><span>Privacy Policy　 Terms of Service</span></div>
      </footer>
    </div>
  );
}
