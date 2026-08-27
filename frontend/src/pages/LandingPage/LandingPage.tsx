import { Link } from 'react-router-dom';
// 이 파일에도 `Logo` 라는 지역 함수가 있다. 이름이 겹치면 어느 쪽이 도는지
// 읽는 사람이 헷갈리므로 들여올 때 이름을 바꾼다.
import { Icon, Logo as BrandLogo } from '../../components';
import { PATHS } from '../../routes';
import { clearSession, useSession } from '../../utils/session';
import styles from './LandingPage.module.css';

/**
 * 랜딩 (TO-BE).
 *
 * ⚠ **이 화면의 정본은 기획 문서가 아니라 코드다**(PM 지시). 다만 코드를 정본으로
 * 삼는다는 것이 **구현을 다 늘어놓는다**는 뜻은 아니다 — 한 번 그렇게 만들었다가
 * 「랜딩이라기보다 기능 명세서를 예쁘게 펼쳐 놓은 상태」라는 지적을 받았다.
 *
 * 그때 걷어낸 것 —
 *
 * - **같은 말의 반복.** 「조회 도구는 처음부터 붙어 있습니다」가 히어로·예시·CTA
 *   세 곳에 있었고, 실행 전 확인과 팀 공유도 각각 두세 번 설명했다.
 * - **내부 구현 노출.** 「19가지 도구」·「7개 승인 도구」·「응답 강도」·「서브
 *   에이전트」·「초안 → 활성화」는 처음 온 사람이 알아야 할 것이 아니다. 숫자는
 *   기능이 늘 때마다 낡기도 한다.
 * - **섹션 과다.** 실제로 할 말은 「할 수 있는 일 · 에이전트 · 승인」 셋인데
 *   일곱 섹션으로 늘어나 흐름이 끊겼다.
 *
 * 지금은 히어로 + 본문 넷 + CTA 다. 빌더 사용법은 에이전트 화면이 안내한다.
 *
 * 그대로 지키는 것 — 실제 요청 예시 3개, 오른쪽 Chat 목업, 「찾고 정리하고
 * 만들고」의 네 갈래, 개인 검증 후 팀 공유라는 실제 흐름, 그리고 **제품명을
 * 전면에서 뺀 것**(커넥터는 제품이 아니라 자리다 — `ConnectorTab.tsx` 의
 * `SLOTS` 가 이미 그렇게 부른다).
 *
 * 화면에 쓰지 않기로 한 문장 — 「모든 답변에 원문 근거가 붙습니다」(날짜·팀원·
 * 부하·프로젝트 조회는 원문 문단이 없다) · 「승인 없이는 아무것도 바꾸지
 * 않습니다」(승인은 `side_effect=True` 도구에만 걸린다) · 「요청 시 연결해
 * 드립니다」(코드에도 정책에도 근거가 없다).
 */

/** 히어로 아래 3줄. 제품이 지키는 약속만 적는다 — 온보딩 정보는 여기 안 온다. */
const PROOFS = [
  { icon: 'file-text', text: '답이 어느 문서에서 나왔는지 같이 보여줍니다' },
  { icon: 'shield-check', text: '올리기 전에 무엇이 올라갈지 먼저 보여줍니다' },
  { icon: 'sparkles', text: '자주 하는 일은 이름 붙여 팀과 함께 씁니다' },
] as const;

/**
 * 3 · 안 해도 되는 일. **제품 속성이 아니라 그 사람의 하루에서 사라지는 일**을
 * 적는다 — 「그래서 내가 뭘 안 해도 되나」가 페이지에 한 줄도 없었다.
 */
const GAINS = [
  { gone: '회의록 뒤져서 할 일 옮겨 적기', now: '지난 회의 정리해 달라고 하면 됩니다.' },
  { gone: '누가 여유 있는지 물어보고 다니기', now: '다음 주에 여유 있는 팀원을 바로 알려 줍니다.' },
  { gone: '업무 하나씩 손으로 등록하기', now: '확인한 것만 골라 한 번에 올립니다.' },
  { gone: '주간 업무량 표 만들어 공유하기', now: '표 파일로 만들어 그 자리에서 받습니다.', file: true },
] as const;

/**
 * 실제 요청 예시. **제품명도, 내부 도구명도 쓰지 않는다.**
 * 예전에는 각 카드 아래에 「문서 검색 · 업무 추출」처럼 어떤 도구가 도는지를
 * 적어 뒀는데, 그건 사용자 가치가 아니라 내부 라우팅 설명이었다.
 */
const ASKS = [
  '지난 회의에서 결정된 일과 해야 할 일을 정리해 줘.',
  '다음 주 업무 여유가 있는 팀원을 알려 줘.',
  '확정한 내용만 프로젝트 업무로 등록해 줘.',
] as const;

/** 에이전트를 만들어 쓰는 차례. 상태 이름은 쓰지 않는다. */
const AGENT_FLOW = ['시킬 일을 적는다', '혼자 써 본다', '팀과 함께 쓴다'] as const;

function Logo() {
  return (
    <span className={styles.logo}>
      <BrandLogo height={30} />
    </span>
  );
}

/**
 * 히어로 목업 — 실제 Chat 의 확인 카드(`ChatCards.tsx` 의 `ConfirmCard`).
 *
 * 머리줄·접기 문구·버튼 라벨을 코드에서 그대로 가져왔다. 지어낸 헤더를 쓰면
 * 공개 주소의 첫 화면이 제품에 없는 화면을 보여주게 된다.
 */
function ChatMock() {
  return (
    <div className={styles.mock}>
      <div className={styles.mockBar}>
        <span className={styles.mockDot} />
        <span className={styles.mockDot} />
        <span className={styles.mockDot} />
        <span className={styles.mockBarLabel}>Chat</span>
      </div>

      <div className={styles.mockBody}>
        <p className={styles.mockAsk}>지난 회의에서 결정된 일과 해야 할 일을 정리해 줘.</p>

        {/* 실제 제품은 답이 한 번에 안 나온다 — 진행 카드가 먼저 뜬다. 「생각하는
            중」은 문구 정리표가 **일부러 남긴** 문구다(무엇을 하는 중인지 말해
            주므로). 등장이 끝나면 카드에 자리를 내주고 사라진다. */}
        <p className={styles.mockThinking} aria-hidden="true">
          <span className={styles.mockThinkingDots}>
            <span />
            <span />
            <span />
          </span>
          생각하는 중
        </p>

        <div className={styles.mockCard}>
          {/* 실제 확인 카드의 머리줄이다. 「확인이 필요합니다」가 아니다. */}
          <div className={styles.mockConfirmHead}>
            <span className={styles.mockConfirmLeft}>
              <span className={styles.mockCheck} aria-hidden="true">
                <Icon name="check" size={11} color="#fff" />
              </span>
              <strong>전체 선택</strong>
              <span className={styles.mockMuted}>8건 선택됨</span>
            </span>
            <span className={styles.mockMuted}>업무 8건</span>
          </div>

          <div className={styles.mockTaskRow}>
            <span className={styles.mockCheck} aria-hidden="true">
              <Icon name="check" size={11} color="#fff" />
            </span>
            <div className={styles.mockTaskBody}>
              <span className={styles.mockTaskTitle}>통합포털 SSO 로그인 연동 설계</span>
              <div className={styles.mockFacts}>
                <span className={styles.mockFact}>
                  <span className={styles.mockFactLabel}>담당 역할</span>
                  <strong>백엔드 개발자</strong>
                </span>
                <span className={styles.mockFact}>
                  <span className={styles.mockFactLabel}>공수</span>
                  <strong>32h</strong>
                </span>
              </div>
              {/* 근거를 못 찾아 비운 칸. 날짜를 박으면 시간이 지나 낡는다. */}
              <p className={styles.mockMissing}>마감일: 근거 없어 비움</p>
              <span className={styles.mockEvidenceToggle}>
                <Icon name="chevron-down" size={13} color="var(--color-primary)" />
                원문 근거 2건
              </span>
              <blockquote className={styles.mockEvidence}>
                <p>
                  포털 로그인은 사내 계정과 고객 계정을 동일한 화면에서 처리하며, 인증 실패 시 3회까지
                  재시도를 허용한다.
                </p>
                <footer>
                  <span>E1 · 유사도 87%</span>
                  <span className={styles.mockEvidenceSource}>통합포털_기획_회의록.docx</span>
                </footer>
              </blockquote>
            </div>
          </div>

          <div className={styles.mockConfirmActions}>
            <span className={styles.mockFootBtn}>선택한 8건 등록</span>
            <span className={styles.mockFootGhost}>거절</span>
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * 「에이전트 만들기」 발췌 — `AgentVersionEditPage.tsx`. 카드 제목·라벨·
 * placeholder 가 전부 그 화면의 실제 값이다. 지시문을 우리가 지어내면 「이렇게
 * 적으면 된다」가 제품과 다른 말이 된다.
 */
function BuilderMock() {
  return (
    <div className={styles.panel}>
      <div className={styles.panelBar}>
        <span className={styles.mockDot} />
        <span className={styles.mockDot} />
        <span className={styles.mockDot} />
        <span className={styles.mockBarLabel}>에이전트 만들기</span>
      </div>
      <div className={styles.panelBody}>
        <div className={styles.field}>
          <span className={styles.fieldLabel}>이름</span>
          <span className={styles.fieldBox}>회의록 정리 에이전트</span>
        </div>
        <div className={styles.field}>
          <span className={styles.fieldLabel}>행동 지시</span>
          <span className={styles.fieldArea}>
            회의록을 읽고 결정된 것과 해야 할 일을 나눠서 정리해줘. 담당자가 없으면 지어내지 말고
            미지정으로 남겨.
          </span>
        </div>
        <div className={styles.field}>
          <span className={styles.fieldLabel}>사용할 도구</span>
          <span className={styles.chipRow}>
            <span className={styles.chip}>문서 검색</span>
            <span className={styles.chip}>업무 등록</span>
            <span className={styles.chipAdd}>+ 도구 추가</span>
          </span>
        </div>
      </div>
    </div>
  );
}

/**
 * 확인 카드의 다른 모양 — 업무 목록이 없는 승인이면 머리줄에 무엇을 할지가
 * 오고 버튼이 「승인 / 거절」이 된다(`ChatCards.tsx` 의 `ConfirmCard`).
 * 히어로의 업무 등록 카드와 겹치지 않게 파일을 만드는 쪽을 보인다.
 */
function ApproveMock() {
  return (
    <div className={styles.panel}>
      <div className={styles.panelBar}>
        <span className={styles.mockDot} />
        <span className={styles.mockDot} />
        <span className={styles.mockDot} />
        <span className={styles.mockBarLabel}>Chat · 실행 전 확인</span>
      </div>
      <div className={styles.approveBody}>
        <div className={styles.approveHead}>
          <strong>주간 업무량 표 만들기</strong>
        </div>
        <p className={styles.approveNote}>
          팀원 8명의 이번 주 업무 시간을 표 파일로 만듭니다.
        </p>
        <div className={styles.approveActions}>
          <span className={styles.mockFootBtn}>승인</span>
          <span className={styles.mockFootGhost}>거절</span>
        </div>
        {/* 빌더 목업의 지시문은 실제 placeholder 라 표시가 필요 없지만, 이쪽
            내용은 우리가 지어낸 예시라 그렇다고 적는다. */}
        <span className={styles.approveNoteSmall}>※ 내용은 예시입니다.</span>
      </div>
    </div>
  );
}

/**
 * 도구가 만든 파일 카드 — `ChatCards.tsx` 의 `ProducedFilesCard`.
 * 안내 문구(「문서 > 내 파일」에도 저장되어 있습니다)는 그 카드의 실제 문장이다.
 */
function FilesMock() {
  return (
    <div className={styles.filesCard}>
      <div className={styles.fileRow}>
        <Icon name="file-text" size={16} color="var(--color-primary)" />
        <span className={styles.fileName}>주간_업무량.xlsx</span>
        <span className={styles.fileBtn}>다운로드</span>
      </div>
      <p className={styles.fileHint}>「문서 &gt; 내 파일」에도 저장되어 있습니다.</p>
    </div>
  );
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
                <a className={styles.navLink} href="#can">
                  달라지는 것
                </a>
                <a className={styles.navLink} href="#agent">
                  에이전트
                </a>
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
              <p className={styles.badge}>대화로 쓰는 팀 업무 플랫폼</p>
              <h1 className={styles.heroTitle}>
                팀의 정보를 한 번에 찾고,
                <br />
                필요한 업무까지 처리합니다
              </h1>
              <p className={styles.heroSub}>
                문서와 팀원, 프로젝트 정보를 한 대화에서 확인하세요. 찾은 내용을 정리해 파일로 만들거나,
                검토한 뒤 실제 업무로 등록할 수 있습니다.
              </p>
              <div className={styles.heroActions}>
                <Link className={styles.btnPrimary} to={startHref}>
                  시작하기
                </Link>
                <a className={styles.btnGhost} href="#can">
                  무엇이 달라지는지 보기
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
              <ChatMock />
              <p className={styles.visualNote}>※ 화면 속 문서와 수치는 UI 설명용 예시입니다.</p>
            </div>
          </div>
        </section>

        {/* 2 · 요청 예시 */}
        <section className={styles.bandWhite}>
          <div className={styles.bandInner}>
            <h2 className={styles.h2}>이렇게 묻습니다</h2>
            <ul className={styles.askList}>
              {ASKS.map((ask) => (
                <li className={styles.ask} key={ask}>
                  <span className={styles.askIcon} aria-hidden="true">
                    <Icon name="message-square" size={16} />
                  </span>
                  <p className={styles.askQuote}>“{ask}”</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* 3 · 안 해도 되는 일 */}
        <section className={styles.bandDark} id="can">
          <div className={styles.bandInner}>
            <h2 className={styles.h2}>이런 일이 없어집니다</h2>
            <ul className={styles.gainGrid}>
              {GAINS.map((item) => (
                <li className={styles.gain} key={item.gone}>
                  <span className={styles.gainGone}>{item.gone}</span>
                  <strong className={styles.gainNow}>{item.now}</strong>
                  {'file' in item && <FilesMock />}
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* 4 · 에이전트 — 만들기와 팀 공유를 한 덩이로 합쳤다. */}
        <section className={styles.bandWhite} id="agent">
          <div className={styles.bandInner}>
            <div className={styles.split}>
              <div className={styles.statement}>
              <h2 className={styles.h2}>적으면 됩니다</h2>
              <p className={styles.statementBody}>
                무엇을 시킬지 우리말로 적으면 됩니다. 자주 하는 일은 이름을 붙여 두고 팀과 함께 씁니다.
                코딩은 한 줄도 하지 않습니다.
              </p>
              {/* 문구를 더 늘리는 대신 흐름만 보인다. 상태 이름(DRAFT·ACTIVE)은
                  쓰지 않는다 — 처음 온 사람이 알아야 할 것이 아니다. */}
              <ol className={styles.miniFlow}>
                {AGENT_FLOW.map((step, index) => (
                  <li className={styles.miniFlowStep} key={step}>
                    {index > 0 && (
                      <span className={styles.miniFlowArrow} aria-hidden="true">
                        <Icon name="arrow-right" size={15} />
                      </span>
                    )}
                    {step}
                  </li>
                ))}
              </ol>
              </div>
              <BuilderMock />
            </div>
          </div>
        </section>

        {/* 5 · 실행 전 확인 */}
        <section className={styles.band}>
          <div className={styles.bandInner}>
            <div className={styles.split}>
              <div className={styles.statement}>
              <h2 className={styles.h2}>잘못 올라갈 일은 없습니다</h2>
              <p className={styles.statementBody}>
                업무를 등록하거나 파일을 만들기 전에 무엇이 올라갈지 먼저 보여 줍니다. 승인하거나,
                고치거나, 그만둘 수 있습니다. 문서에 없는 마감일을 지어내서 채우지 않습니다.
              </p>
              </div>
              <ApproveMock />
            </div>
          </div>
        </section>

        {/* 6 · 마감 CTA */}
        <section className={styles.cta}>
          <div className={styles.ctaInner}>
            <h2 className={styles.ctaTitle}>팀의 정보로 바로 시작해 보세요</h2>
            <p className={styles.ctaSub}>새 팀을 만들거나, 받은 초대로 참여합니다.</p>
            <Link className={styles.btnOnDark} to={startHref}>
              시작하기
            </Link>
          </div>
        </section>
      </main>

      <footer className={styles.footer}>
        <div className={styles.footerInner}>
          <span className={styles.footerName}>halil · 프로젝트 운영 AI 플랫폼</span>
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
