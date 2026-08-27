import { Link } from 'react-router-dom';
// 이 파일에도 `Logo` 라는 지역 함수가 있다. 이름이 겹치면 어느 쪽이 도는지
// 읽는 사람이 헷갈리므로 들여올 때 이름을 바꾼다.
import { BrandIcon, Icon, Logo as BrandLogo } from '../../components';
import { PATHS } from '../../routes';
import { clearSession, useSession } from '../../utils/session';
import styles from './LandingPage.module.css';

/**
 * 랜딩 (TO-BE). 서사와 사실관계는 Figma `랜딩 (TO-BE) · /` (74:1131, 수정 지시
 * v2) 를 따르고, **레이아웃과 문장은 2026-08-27 리뉴얼에서 다시 짰다.**
 *
 * 리뉴얼이 고친 것 — 전부 「말이 틀렸다」가 아니라 「화면이 비어 있다」였다.
 *
 * 1. 히어로 좌측이 비었다. 목업이 세로로 길어 카피가 가운데로 밀리고 위아래에
 *    120px 씩 죽은 공간이 생겼다. → 위 정렬로 바꾸고, 히어로 서브에서 뒷문장을
 *    떼어 근거 3줄(`PROOFS`)로 세웠다. 한 문단에 뭉쳐 있던 약속이 훑어진다.
 * 2. 모든 섹션이 중앙 정렬에 같은 패딩이었다. → 좌측 정렬을 기본으로 하고,
 *    중앙 정렬은 마감 CTA 하나에만 남겼다.
 * 3. 기능 카드가 시각물 → 제목 순서였고 시각물이 고정 높이에 잘렸다.
 *    → 제목 → 본문 → 시각물 순으로 뒤집고 높이 제한을 없앴다.
 * 4. 마감 CTA 가 `--color-primary-soft`(네이비 6%)라 사실상 연회색이었다.
 *    → 네이비를 꽉 채운 유일한 밴드로 만들었다. 페이지에서 여기만 어둡다.
 *
 * 화면 속 목업은 실제 07 TO-BE 화면(Chat 확인 대기·에이전트 편집·결과 카드)을
 * 축약한 것이다. 수치는 데모 기준선(20건 → 17/20, E1~E24)을 따른다.
 */

/**
 * 히어로 근거 3줄. 리뉴얼 전에는 히어로 서브 뒷문장에 뭉쳐 있던 내용이다.
 *
 * ⚠ **명사로 끝내지 않는다.** 처음에는 「답변마다 원문 근거」처럼 명사만 쌓아
 * 뒀는데, 짧아 보일 뿐 무슨 일이 일어난다는 말이 없어 읽는 사람이 뜻을 스스로
 * 지어내야 했다. 세 줄 다 무엇이 일어나는지를 말하는 문장으로 둔다.
 */
const PROOFS = [
  { icon: 'file-text', text: '답을 어디서 가져왔는지 같이 보여줍니다' },
  { icon: 'shield-check', text: '사람이 승인해야 실제로 등록됩니다' },
  { icon: 'sparkles', text: '코딩은 한 줄도 필요 없습니다' },
] as const;

/**
 * 2 · 흩어짐. 「문서는 Drive에, 업무는 Jira에, 기준은 사람 머릿속에」를 문장
 * 그대로 두지 않고 셋으로 갈랐다 — 흩어져 있다는 말을 화면이 같이 해야 한다.
 */
const SCATTER = [
  { label: '문서', place: 'Google Drive' },
  { label: '업무', place: 'Jira' },
  { label: '기준', place: '사람 머릿속' },
] as const;

const FEATURES = [
  {
    id: 'evidence',
    title: '답에는 항상 근거가 붙습니다',
    body: '어느 문서 어느 문단에서 가져왔는지 그대로 보여줍니다. 근거를 못 찾은 값은 지어내지 않고 비워 둡니다.',
  },
  {
    id: 'builder',
    title: '에이전트는 직접 만들어 씁니다',
    // 리뉴얼 전 본문은 히어로 서브와 같은 말("세 가지만 적으면")이었다. 같은
    // 화면에서 두 번 읽히므로, 여기서는 그다음에 무슨 일이 생기는지를 쓴다.
    body: '만든 에이전트는 나만 쓸 수도, 팀에 공유할 수도 있습니다. 고칠 때마다 버전이 남아 언제든 되돌립니다.',
  },
  {
    id: 'gate',
    title: '승인 없이는 아무것도 바꾸지 않습니다',
    // 「Jira에 등록하기 전」이라는 옛 문구가 여기 남아 있었다. 8/12 에 **등록은
    // 우리 플랫폼(`task`)이 먼저**가 됐다 — 히어로 목업은 그때 고쳤는데 이
    // 카드는 안 고쳐져 랜딩 안에서 두 말이 어긋나 있었다.
    body: '등록하기 전에 무엇이 올라갈지 먼저 보여 줍니다. 20건 중 3건이 실패하면 3건이 실패했다고 말합니다.',
  },
] as const;

const STEPS = [
  { num: '1', title: '도구를 연결합니다', caption: '예: Google Drive, Jira' },
  { num: '2', title: '에이전트를 고르거나 만듭니다', caption: '이미 있는 것으로 시작해도 됩니다' },
  { num: '3', title: '필요한 일을 말합니다', caption: '어디서 나온 답인지 같이 봅니다' },
  { num: '4', title: '승인하면 그때 등록됩니다', caption: '예: Jira 이슈 등록' },
] as const;

/**
 * 커넥터. Drive·Jira 는 `simple-icons` 의 공식 마크가 있고(`BrandIcon`),
 * People DB 는 없다 — 없는 로고를 지어내지 않고 일반 글리프로 둔다.
 */
const CONNECTORS = [
  { name: 'Google Drive', brand: 'google-drive' as const },
  { name: 'Jira', brand: 'jira' as const },
  { name: 'People DB', glyph: 'database' as const },
] as const;

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
              <p className={styles.badge}>프로젝트 운영 Agent Platform</p>
              <h1 className={styles.heroTitle}>
                팀에 필요한 AI 에이전트를,
                <br />
                코딩 없이 만들어 씁니다
              </h1>
              <p className={styles.heroSub}>
                할 일과 참고할 문서, 쓸 도구를 적으면 됩니다. 그렇게 만든 에이전트는 팀 전체가 같이
                씁니다.
              </p>
              <div className={styles.heroActions}>
                <Link className={styles.btnPrimary} to={startHref}>
                  시작하기
                </Link>
                {/* 「데모 보기」였다. 누르면 기능 카드로 갈 뿐 데모가 없어, 이름이
                    없는 것을 약속하고 있었다. 목적지(#how)와 이름을 맞춘다. */}
                <a className={styles.btnGhost} href="#how">
                  작동 방식 보기
                </a>
              </div>

              <ul className={styles.proofs}>
                {PROOFS.map((proof) => (
                  <li className={styles.proof} key={proof.text}>
                    <Icon name={proof.icon} size={16} />
                    {proof.text}
                  </li>
                ))}
              </ul>
            </div>

            <div className={styles.heroVisual}>
              <ApprovalMock />
              <p className={styles.visualNote}>※ 화면 속 수치는 UI 설명용 예시입니다.</p>
            </div>
          </div>
        </section>

        {/* 2 · 흩어짐 → 전환 */}
        <section className={styles.bandWhite}>
          <div className={styles.bandInner}>
            <h2 className={styles.h2}>일은 한 곳에서 안 끝납니다</h2>
            <div className={styles.scatterRow}>
              {SCATTER.map((item) => (
                <div className={styles.scatterCard} key={item.label}>
                  <span className={styles.scatterLabel}>{item.label}</span>
                  <strong className={styles.scatterPlace}>{item.place}</strong>
                </div>
              ))}
            </div>
            <p className={styles.lead}>
              halil은 이 셋을 한자리에 모읍니다. 그리고 거기서 일할 에이전트를 팀이 직접 만듭니다.
            </p>
          </div>
        </section>

        {/* 3 · 핵심 기능 3 */}
        <section className={styles.band} id="features">
          <div className={styles.bandInner}>
            <h2 className={styles.h2}>이런 점이 다릅니다</h2>
            <div className={styles.featureGrid}>
              {FEATURES.map((feature, index) => (
                <article className={styles.featureCard} key={feature.id}>
                  <h3 className={styles.featureTitle}>
                    <span className={styles.featureNum}>{index + 1}</span>
                    {feature.title}
                  </h3>
                  <p className={styles.featureBody}>{feature.body}</p>
                  {/* 시각물이 제목 위에 있었다. 카드를 읽으려면 시선이 그림에서
                      제목으로 한 번 되돌아가야 했다. 아래로 내린다. */}
                  <div className={styles.featureVisual}>
                    <FeatureVisual id={feature.id} />
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* 4 · 작동 방식 */}
        <section className={styles.bandWhite} id="how">
          <div className={styles.bandInner}>
            <h2 className={styles.h2}>작동 방식</h2>
            {/* 회색 상자 4개로 보이던 것을 하나의 선 위에 꿴다 — 네 칸이 별개가
                아니라 한 줄기라는 것이 카드 테두리로는 안 보였다. */}
            <ol className={styles.stepRail}>
              {STEPS.map((step) => (
                <li className={styles.stepItem} key={step.num}>
                  <span className={styles.stepNum}>{step.num}</span>
                  <strong className={styles.stepTitle}>{step.title}</strong>
                  <small className={styles.stepCaption}>{step.caption}</small>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* 5 · 확장성 */}
        <section className={styles.band}>
          <div className={styles.bandInner}>
            <h2 className={styles.h2}>쓰던 도구 그대로, 필요한 도구는 더</h2>
            <p className={styles.lead}>
              지금은 Google Drive와 Jira를 연결할 수 있습니다. 사용 중인 다른 시스템은 요청 시 연결해
              드립니다. 한 번 연결하면 에이전트가 똑같이 씁니다.
            </p>
            <div className={styles.connectorRow}>
              {CONNECTORS.map((conn) => (
                <span className={styles.connector} key={conn.name}>
                  {'brand' in conn ? (
                    <BrandIcon name={conn.brand} size={20} />
                  ) : (
                    <Icon name={conn.glyph} size={20} />
                  )}
                  {conn.name}
                </span>
              ))}
              <span className={styles.connectorMore}>+ 우리 시스템으로 확장</span>
            </div>
          </div>
        </section>

        {/* 6 · 마감 CTA (요금제 섹션은 제외 — 8/12 결정) */}
        <section className={styles.cta}>
          <div className={styles.ctaInner}>
            <h2 className={styles.ctaTitle}>기본 에이전트부터 바로 써 보세요</h2>
            {/* 「기본 제공 에이전트로 바로 시작할 수 있습니다」는 작동 방식 섹션
                맨 아래에 홀로 떠 있던 줄이다. 전환을 청하는 자리로 옮긴다. */}
            <p className={styles.ctaSub}>업무 추출과 부하 리포트가 이미 들어 있습니다.</p>
            <Link className={styles.btnOnDark} to={startHref}>
              시작하기
            </Link>
          </div>
        </section>
      </main>

      <footer className={styles.footer}>
        <div className={styles.footerInner}>
          <span className={styles.footerName}>halil · 프로젝트 운영 Agent Platform</span>
          <span className={styles.footerSide}>
            {/* 개인정보처리방침은 로그인 없이 열려야 하는데(Google 커넥터 심사가
                이 주소를 직접 연다) 공개 화면 어디에도 링크가 없었다. */}
            <Link className={styles.footerLink} to={PATHS.privacy}>
              개인정보처리방침
            </Link>
            SKN29 Final 2Team
          </span>
        </div>
      </footer>
    </div>
  );
}
