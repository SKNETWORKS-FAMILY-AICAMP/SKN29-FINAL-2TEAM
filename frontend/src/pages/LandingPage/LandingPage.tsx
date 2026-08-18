import { Link } from 'react-router-dom';
// 이 파일에도 `Logo` 라는 지역 함수가 있다. 이름이 겹치면 어느 쪽이 도는지
// 읽는 사람이 헷갈리므로 들여올 때 이름을 바꾼다.
import { Logo as BrandLogo } from '../../components';
import { PATHS } from '../../routes';
import { clearSession, useSession } from '../../utils/session';
import styles from './LandingPage.module.css';

/**
 * 랜딩 (TO-BE). Figma `랜딩 (TO-BE) · /` (74:1131, 수정 지시 v2) 확정안.
 *
 * 구 랜딩과의 차이 — 서사가 통째로 바뀌었다. 「업무 배정 코파일럿」이 아니라
 * 「프로젝트 운영 Agent Platform」이고, 정체성 자리에 오는 것은 커넥터가 아니라
 * 에이전트다(v2 서열 교정). Drive·Jira는 사례 자리로 내려간다.
 *
 * 지운 것: 요금제 3종, 사회적 증명(「1,200개 이상의 팀」·로고 행), 워크로드
 * 시각화 섹션, 배정 데모 목업. 전부 구 제품 단위이거나 허구 수치였다.
 *
 * 화면 속 목업은 실제 07 TO-BE 화면(Chat 확인 대기·에이전트 편집·결과 카드)을
 * 축약한 것이다. 수치는 데모 기준선(20건 → 17/20, E1~E24)을 따른다.
 */

const FEATURES = [
  {
    id: 'evidence',
    title: '근거와 함께 일하는 에이전트',
    body: '모든 결과에 원문 문단이 붙습니다. 근거가 없는 값은 지어내지 않고 ‘근거 없어 비움’으로 표시합니다.',
  },
  {
    id: 'builder',
    title: '코딩 없이 만드는 나만의 에이전트',
    body: '무슨 일을 하는지, 무엇을 참고할지, 어떤 도구를 쓸지. 세 가지만 적으면 팀 전체가 바로 씁니다.',
  },
  {
    id: 'gate',
    title: '승인 없이는 아무것도 바꾸지 않습니다',
    body: 'Jira에 등록하기 전, 무엇이 만들어지는지 확인하고 선택합니다. 부분 실패도 숨기지 않고 그대로 보여줍니다.',
  },
] as const;

const STEPS = [
  { num: '1', title: '쓰는 도구를 연결한다', caption: '예: Drive·Jira. 몇 분이면 끝납니다' },
  { num: '2', title: '에이전트를 고르거나 만든다', caption: '기본 제공으로 시작하거나, 세 가지만 적어 새로 만듭니다' },
  { num: '3', title: '요청하고 근거를 확인한다', caption: '모든 결과에 원문 문단이 붙습니다' },
  { num: '4', title: '승인하면 실제로 반영된다', caption: '예: Jira 이슈 등록' },
] as const;

const CONNECTORS = ['Google Drive', 'Jira', 'People DB'] as const;

function Logo() {
  return (
    <span className={styles.logo}>
      <BrandLogo height={30} />
    </span>
  );
}

/** 히어로 목업 — Chat 확인 대기(07 · 39:118)의 확인 카드 축약. */
function ApprovalMock() {
  return (
    <div className={styles.mock}>
      <div className={styles.mockBar}>
        <span className={styles.mockDot} />
        <span className={styles.mockDot} />
        <span className={styles.mockDot} />
        <span className={styles.mockBarLabel}>Chat · 확인 대기</span>
      </div>

      <div className={styles.mockBody}>
        <div className={styles.mockRowBetween}>
          <strong className={styles.mockHeading}>확인이 필요합니다</strong>
          <span className={styles.mockMeta}>업무 20건 · 근거 24개 문단</span>
        </div>

        <p className={styles.mockWarn}>
          기준 문서에서 마감일 근거를 찾지 못한 업무가 있습니다. 근거 없는 항목은 채우지 않고 ‘근거 없어
          비움’으로 표시합니다.
        </p>

        <div className={styles.mockTask}>
          <div className={styles.mockRowBetween}>
            <strong>통합포털 SSO 로그인 연동 설계</strong>
            <span className={styles.mockChip}>HIGH</span>
          </div>
          <p className={styles.mockTaskMeta}>담당 역할 백엔드 개발자 · 공수 32h · 마감 2026.08.28</p>

          <p className={styles.mockEvidence}>
            포털 로그인은 사내 계정과 고객 계정을 동일한 화면에서 처리하며, 인증 실패 시 3회까지 재시도를
            허용한다.
            <span className={styles.mockEvidenceMeta}>E1 · DOC-2026-0142 · 역할/기술 · 유사도 87%</span>
          </p>
          <p className={styles.mockEvidence}>
            인증 설계는 8월 4주차까지 확정하여 개발 착수 전 검토를 받는다.
            <span className={styles.mockEvidenceMeta}>E2 · DOC-2026-0139 · 공수/일정·제약 · 유사도 74%</span>
          </p>
        </div>

        {/* 실제 확인 카드와 문구를 맞춘다. 랜딩만 「Jira에 등록」인 옛 문구로 남아
            있었다 — 8/12 에 **등록은 우리 플랫폼(`task`)이 먼저**가 됐고 버튼도
            「선택한 N건 등록」으로 바뀌었다. 랜딩은 공개 주소의 첫 화면이라
            여기서 어긋나면 제품이 아직 Jira 부속으로 읽힌다(2026-08-12 QA §C). */}
        <div className={styles.mockFoot}>
          <span className={styles.mockFootNote}>승인하기 전까지 아무 데도 등록하지 않습니다.</span>
          <span className={styles.mockFootBtn}>선택한 20건 등록</span>
        </div>
      </div>
    </div>
  );
}

/** 카드 ① — 근거 카드 발췌. */
function EvidenceMini() {
  return (
    <div className={styles.mini}>
      <p className={styles.miniTitle}>결제 API 연동 테스트 시나리오 작성</p>
      <p className={styles.miniEvidence}>
        결제 실패 케이스는 타임아웃·한도 초과·카드사 거절 세 가지를 모두 재현한다.
        <span className={styles.miniMeta}>E7 · DOC-2026-0151 · 유사도 91%</span>
      </p>
      <p className={styles.miniEmpty}>마감일: 근거 없어 비움</p>
    </div>
  );
}

/** 카드 ② — 에이전트 편집의 도구 선택 발췌. */
function ToolsMini() {
  return (
    <div className={styles.mini}>
      <p className={styles.miniLabel}>사용할 도구</p>
      {[
        { name: '문서 검색', desc: '팀에 등록된 문서에서 근거를 찾습니다', tag: '기본 제공', on: true },
        { name: '부하 리포트 생성', desc: '팀원별 주간 업무 시간을 계산합니다', tag: '기본 제공', on: false },
        // Jira 는 **Connector 로 붙고 도구는 기본 제공**이다(`jira_create_issues`).
        // 「MCP · Jira」는 두 번 틀린 표기였다 — MCP 탭은 사용자가 직접 운영하는
        // 서버를 붙이는 곳이고, Jira 는 우리가 미리 붙여 둔 통로다(확정 ⑨).
        { name: 'Jira 이슈 생성', desc: '확인받은 업무를 Jira에 등록합니다', tag: '기본 제공', on: true },
      ].map((tool) => (
        <div className={styles.miniTool} key={tool.name}>
          <span className={tool.on ? styles.miniCheckOn : styles.miniCheck} aria-hidden="true" />
          <span className={styles.miniToolText}>
            <strong>{tool.name}</strong>
            <small>{tool.desc}</small>
          </span>
          <span className={styles.miniTag}>{tool.tag}</span>
        </div>
      ))}
    </div>
  );
}

/** 카드 ③ — 부분 실패 결과 카드 발췌. */
function ResultMini() {
  return (
    <div className={styles.mini}>
      <p className={styles.miniWarnBar}>
        <span>17/20 등록 완료 · 3건 실패</span>
        <span className={styles.miniWarnSide}>성공분은 되돌리지 않습니다</span>
      </p>
      {[
        ['PORTAL-141', '통합포털 SSO 로그인 연동 설계'],
        ['PORTAL-142', '권한 등급별 메뉴 노출 규칙 정의'],
      ].map(([key, title]) => (
        <div className={styles.miniIssue} key={key}>
          <strong>{key}</strong>
          <span>{title}</span>
        </div>
      ))}
      <p className={styles.miniFail}>실패 3건 · 사유 표시</p>
    </div>
  );
}

function FeatureVisual({ id }: { id: string }) {
  if (id === 'evidence') return <EvidenceMini />;
  if (id === 'builder') return <ToolsMini />;
  return <ResultMini />;
}

export default function LandingPage() {
  const session = useSession();
  // 로그인한 사람은 가입이 아니라 자기 작업으로 보낸다. 4차 단계 1에서 목적지가
  // 대시보드에서 Chat으로 바뀌었다 — 로그인 직후 랜딩과 같은 기준이다.
  const startHref = session ? PATHS.chat : PATHS.signup;

  return (
    <div className={styles.page}>
      <header className={styles.nav}>
        <div className={styles.navInner}>
          <Logo />
          <div className={styles.navActions}>
            {session ? (
              <>
                <span className={styles.navName}>{session.account.display_name} 님</span>
                <Link className={styles.navLink} to={PATHS.chat}>
                  Chat 열기
                </Link>
                <button type="button" className={styles.navGhost} onClick={clearSession}>
                  로그아웃
                </button>
              </>
            ) : (
              <>
                <Link className={styles.navLink} to={PATHS.login}>
                  로그인
                </Link>
                <Link className={styles.navCta} to={PATHS.signup}>
                  시작하기
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      <main>
        {/* 1 · 히어로 */}
        <section className={styles.hero}>
          <div className={styles.heroInner}>
            <div className={styles.heroCopy}>
              <p className={styles.badge}>✨ 프로젝트 운영 Agent Platform, halil</p>
              <h1 className={styles.heroTitle}>
                팀에 필요한 AI 에이전트를,
                <br />
                코딩 없이 만들어 씁니다
              </h1>
              <p className={styles.heroSub}>
                무슨 일을 하는지, 무엇을 참고할지, 어떤 도구를 쓸지 적으면 팀 전체가 쓰는 에이전트가 됩니다.
                모든 답변에는 원문 근거가 붙고, 실제 등록은 사람의 승인을 거칩니다.
              </p>
              <div className={styles.heroActions}>
                <Link className={styles.btnPrimary} to={startHref}>
                  팀 만들고 시작하기
                </Link>
                <a className={styles.btnGhost} href="#features">
                  데모 보기
                </a>
              </div>
            </div>

            <div className={styles.heroVisual}>
              <ApprovalMock />
              <p className={styles.visualNote}>※ 화면 속 수치는 UI 설명용 예시입니다.</p>
            </div>
          </div>
        </section>

        {/* 2 · 문제 → 전환 */}
        <section className={styles.bandWhite}>
          <div className={styles.centered}>
            <h2 className={styles.h2}>업무 분배만의 문제가 아니었습니다</h2>
            <p className={styles.lead}>
              문서는 Drive에, 업무는 Jira에, 기준은 사람 머릿속에 흩어져 있습니다. halil은 흩어진 데이터를
              연결하는 데서 멈추지 않고, 그 위에서 팀이 필요한 AI 에이전트를 직접 만들어 쓰는 환경을 제공합니다.
            </p>
          </div>
        </section>

        {/* 3 · 핵심 기능 3 */}
        <section className={styles.band} id="features">
          <div className={styles.featureGrid}>
            {FEATURES.map((feature, index) => (
              <article className={styles.featureCard} key={feature.id}>
                <div className={styles.featureVisual}>
                  <FeatureVisual id={feature.id} />
                </div>
                <h3 className={styles.featureTitle}>
                  <span className={styles.featureNum}>{index + 1}</span>
                  {feature.title}
                </h3>
                <p className={styles.featureBody}>{feature.body}</p>
              </article>
            ))}
          </div>
        </section>

        {/* 4 · 작동 방식 */}
        <section className={styles.bandWhite} id="how">
          <h2 className={`${styles.h2} ${styles.h2Center}`}>작동 방식</h2>
          <div className={styles.stepGrid}>
            {STEPS.map((step) => (
              <article className={styles.stepCard} key={step.num}>
                <span className={styles.stepNum}>{step.num}</span>
                <strong className={styles.stepTitle}>{step.title}</strong>
                <small className={styles.stepCaption}>{step.caption}</small>
              </article>
            ))}
          </div>
          <p className={styles.stepNote}>
            기본 제공 에이전트(업무 추출·부하 리포트)로 바로 시작할 수 있습니다.
          </p>
        </section>

        {/* 5 · 확장성 */}
        <section className={styles.band}>
          <div className={styles.centered}>
            <h2 className={styles.h2}>쓰던 도구 그대로, 필요한 도구는 더</h2>
            <p className={styles.lead}>
              에이전트가 쓰는 도구는 전부 커넥터입니다. 지금은 Google Drive·Jira가 준비돼 있고, 회사에 이미
              있는 시스템은 말씀해 주시면 연결해 드립니다. 연결하고 나면 똑같은 도구가 됩니다.
            </p>
            <div className={styles.pillRow}>
              {CONNECTORS.map((name) => (
                <span className={styles.pill} key={name}>
                  {name}
                </span>
              ))}
              <span className={styles.pillStrong}>+ 우리 시스템으로 확장</span>
            </div>
          </div>
        </section>

        {/* 7 · 마감 CTA (6 요금제는 제외 — 8/12 결정) */}
        <section className={styles.cta}>
          <h2 className={styles.ctaTitle}>첫 에이전트를 5분 안에</h2>
          <Link className={styles.btnPrimary} to={startHref}>
            팀 만들고 시작하기
          </Link>
        </section>
      </main>

      <footer className={styles.footer}>
        <span>halil · 프로젝트 운영 Agent Platform</span>
        <span>SKN29 Final 2Team</span>
      </footer>
    </div>
  );
}
