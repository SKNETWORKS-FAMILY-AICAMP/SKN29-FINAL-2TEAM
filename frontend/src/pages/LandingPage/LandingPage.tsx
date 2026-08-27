import { Link } from 'react-router-dom';
// 이 파일에도 `Logo` 라는 지역 함수가 있다. 이름이 겹치면 어느 쪽이 도는지
// 읽는 사람이 헷갈리므로 들여올 때 이름을 바꾼다.
import { Icon, Logo as BrandLogo } from '../../components';
import { PATHS } from '../../routes';
import { clearSession, useSession } from '../../utils/session';
import styles from './LandingPage.module.css';

/**
 * 랜딩 (TO-BE). 2026-08-27 개편.
 *
 * ⚠ **이 화면의 정본은 기획 문서가 아니라 코드다**(PM 지시). 8/12 Figma v2 와
 * 8/18 문구표를 출발점으로 삼던 것을 그만두고 실제 구현에서 문장을 뽑았다.
 * 문서를 먼저 읽으면 「팀 내부 논쟁의 결론」이 그대로 화면에 올라가는데, 그것은
 * 제품을 이미 아는 사람에게만 읽히는 말이었다.
 *
 * 이번에 폐기한 문장과 이유 —
 *
 * - 「모든 답변에 원문 근거가 붙습니다」 → **거짓이다.** 근거 문단이 붙는 것은
 *   `document_search`·`task_extraction` 쪽이고, 날짜·팀원·부하·프로젝트 조회는
 *   원문 문단을 갖지 않는다.
 * - 「승인 없이는 아무것도 바꾸지 않습니다」 → **범위가 과하다.** 승인이 걸리는
 *   것은 `side_effect=True` 도구뿐이다(`agent_runtime/factory.py` 의
 *   `interrupt_on` 이 `tool.side_effect` 로만 만들어진다). 19개 중 7개이고
 *   조회는 그냥 실행된다.
 * - 「세 가지만 적으면 에이전트가 됩니다」 → 실제 빌더 항목은 일곱이다
 *   (`AgentVersionEditPage.tsx`).
 * - 「People DB」 → 지금 연결 가능한 인사 정보는 `mock`(예시 데이터)뿐이다.
 * - 「요청 시 연결해 드립니다」 → 코드에도 운영 정책에도 근거가 없다.
 * - 날짜가 박힌 데모 문구(「마감 2026.08.28」) → 시간이 지나면 낡는다.
 * - 「확인이 필요합니다」 → **제품에 없는 헤더다.** 실제 확인 카드의 머리줄은
 *   「전체 선택 · N건 선택됨 · 업무 N건」이다(`ChatCards.tsx`).
 *
 * **제품명을 메인 메시지에서 반복하지 않는다.** 커넥터는 제품이 아니라 자리이고,
 * 그 어휘는 우리가 지어낸 것이 아니라 `ConnectorTab.tsx` 의 `SLOTS` 가 이미
 * 쓰고 있다 — 「문서 저장소」·「업무 기록소」·「인사 시스템」. 자리마다 지금
 * 켜진 선택지가 하나씩뿐이라, 로고를 늘어놓으면 지원 범위를 과장하게 된다.
 */

/** 히어로 아래 3줄. 각각 아래 섹션 하나와 짝이 맞는다. */
const PROOFS = [
  { icon: 'message-square', text: '조회 도구는 팀을 만들면 바로 붙어 있습니다' },
  { icon: 'shield-check', text: '밖을 바꾸는 작업은 실행 전에 확인합니다' },
  { icon: 'sparkles', text: '반복하는 일은 에이전트로 만들어 팀에 공유합니다' },
] as const;

/**
 * 1 · 실제로 할 수 있는 일. **제품명 없이 사용자의 말로 적는다.**
 * 오른쪽은 그 요청이 실제로 부르는 내장 도구 이름이다(`registry.py` 의 `name`).
 */
const ASKS = [
  { ask: '지난 회의에서 결정된 일과 해야 할 일을 정리해 줘.', tools: '문서 검색 · 업무 추출' },
  { ask: '다음 주 업무 여유가 있는 팀원을 알려 줘.', tools: '부하 리포트 · 부재 조회 · 팀원 조회' },
  { ask: '확정한 내용만 프로젝트 업무로 등록해 줘.', tools: '업무 등록 · 실행 전 확인' },
] as const;

/** 2 · 연결하는 자리. `ConnectorTab.tsx` 의 `SLOTS` 세 개와 1:1 이다. */
const SLOTS = [
  { icon: 'file-text', title: '문서 저장소', body: '회의록·기획서처럼 팀이 쌓아 둔 문서' },
  { icon: 'users', title: '팀·인사 정보', body: '팀원, 맡은 역할, 근무 기준과 부재' },
  { icon: 'folder', title: '프로젝트와 업무 기록', body: '진행 중인 프로젝트와 등록된 업무' },
] as const;

/** 3 · 도구가 하는 일을 네 갈래로. */
const STAGES = [
  { num: '1', title: '조회', caption: '흩어져 있는 문서·팀·프로젝트·업무를 한 번에 찾습니다' },
  { num: '2', title: '정리', caption: '찾은 내용을 할 일 목록이나 팀별 업무량으로 정리합니다' },
  { num: '3', title: '생성', caption: '정리한 결과를 문서나 표 파일로 만듭니다' },
  { num: '4', title: '등록', caption: '확인한 내용만 실제 업무로 등록합니다' },
] as const;

/** 4 · 빌더 항목. `AgentVersionEditPage.tsx` 의 실제 입력 항목 그대로다. */
const BUILDER_FIELDS = [
  '이름',
  '설명',
  '행동 지시',
  '모델',
  '응답 강도',
  '사용할 도구',
  '서브 에이전트',
] as const;

/** 5 · 개인 → 활성화 → 팀 공유. `AgentVersionListPage.tsx` 의 DRAFT/ACTIVE 흐름. */
const LIFECYCLE = [
  { label: '개인', sub: '초안 — 나만 부릅니다' },
  { label: '활성화', sub: '직접 써 보고 켭니다' },
  { label: '팀 공유', sub: '팀 전체가 씁니다' },
] as const;

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
            <span className={styles.mockFootGhost}>취소</span>
          </div>
        </div>
      </div>
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
                  할 수 있는 일
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
        {/* 0 · 히어로 */}
        <section className={styles.hero}>
          <div className={styles.heroInner}>
            <div className={styles.heroCopy}>
              <p className={styles.badge}>대화로 쓰는 팀 업무 플랫폼</p>
              <h1 className={styles.heroTitle}>
                팀의 업무 정보를 연결해,
                <br />
                대화로 찾아보고 실행합니다
              </h1>
              <p className={styles.heroSub}>
                문서에서 필요한 내용을 찾고, 팀과 프로젝트의 상황을 확인하고, 정리한 결과를 실제 업무로
                이어갑니다. 반복하는 방식은 에이전트로 만들어 직접 검증한 뒤 팀에 공유할 수 있습니다.
              </p>
              <div className={styles.heroActions}>
                <Link className={styles.btnPrimary} to={startHref}>
                  시작하기
                </Link>
                <a className={styles.btnGhost} href="#can">
                  할 수 있는 일 보기
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

        {/* 1 · 실제로 할 수 있는 일 */}
        <section className={styles.bandWhite} id="can">
          <div className={styles.bandInner}>
            <h2 className={styles.h2}>이런 걸 물어보면 됩니다</h2>
            <ul className={styles.askList}>
              {ASKS.map((item) => (
                <li className={styles.ask} key={item.ask}>
                  <p className={styles.askQuote}>“{item.ask}”</p>
                  <span className={styles.askTools}>{item.tools}</span>
                </li>
              ))}
            </ul>
            <p className={styles.lead}>
              팀을 만들면 조회 도구는 처음부터 붙어 있습니다. 따로 설정하지 않아도 바로 물어볼 수 있습니다.
            </p>
          </div>
        </section>

        {/* 2 · 한 대화에서 */}
        <section className={styles.band}>
          <div className={styles.bandInner}>
            <h2 className={styles.h2}>한 대화에서 다 봅니다</h2>
            <p className={styles.lead}>
              팀 정보가 있는 자리를 한 번 연결해 두면, 그다음부터는 대화 한 곳에서 씁니다. 어디에 있는지
              기억하지 않아도 됩니다.
            </p>
            <div className={styles.slotGrid}>
              {SLOTS.map((slot) => (
                <article className={styles.slotCard} key={slot.title}>
                  <span className={styles.slotIcon}>
                    <Icon name={slot.icon} size={20} />
                  </span>
                  <strong className={styles.slotTitle}>{slot.title}</strong>
                  <p className={styles.slotBody}>{slot.body}</p>
                </article>
              ))}
            </div>
            <p className={styles.note}>
              자리마다 하나씩 연결합니다. 연결은 팀장이 하고, 팀원은 그대로 씁니다.
            </p>
          </div>
        </section>

        {/* 3 · 조회 · 정리 · 생성 · 등록 */}
        <section className={styles.bandWhite}>
          <div className={styles.bandInner}>
            <h2 className={styles.h2}>찾고, 정리하고, 만들고, 등록합니다</h2>
            <ol className={styles.stepRail}>
              {STAGES.map((stage) => (
                <li className={styles.stepItem} key={stage.num}>
                  <span className={styles.stepNum}>{stage.num}</span>
                  <strong className={styles.stepTitle}>{stage.title}</strong>
                  <small className={styles.stepCaption}>{stage.caption}</small>
                </li>
              ))}
            </ol>
            {/* 19는 `BUILTIN_TOOLS` 의 실제 개수다. 실측이 아닌 수는 쓰지 않는다. */}
            <p className={styles.note}>지금 쓸 수 있는 도구는 19가지입니다.</p>
          </div>
        </section>

        {/* 4 · 반복 업무를 에이전트로 */}
        <section className={styles.band} id="agent">
          <div className={styles.bandInner}>
            <h2 className={styles.h2}>자주 하는 일은 에이전트로 만듭니다</h2>
            <p className={styles.lead}>
              매번 같은 요청을 다시 쓰는 대신, 하는 일과 쓸 도구를 정해 두고 이름을 붙입니다.
            </p>
            <div className={styles.fieldRow}>
              {BUILDER_FIELDS.map((field) => (
                <span className={styles.fieldChip} key={field}>
                  {field}
                </span>
              ))}
            </div>
            <p className={styles.note}>큰 일은 서브 에이전트에게 한 단계 나눠 맡길 수 있습니다.</p>
          </div>
        </section>

        {/* 5 · 개인 검증 후 팀 공유 */}
        <section className={styles.bandWhite}>
          <div className={styles.bandInner}>
            <h2 className={styles.h2}>먼저 혼자 써 보고, 그다음 팀에 넘깁니다</h2>
            <p className={styles.lead}>
              만든 에이전트는 처음에 나만 부를 수 있습니다. 대화에서 직접 시켜 보고 원하는 대로 동작하면
              활성화해서 팀 전체가 쓰게 합니다. 쓰지 않게 되면 사용 중지할 수 있고, 고칠 때마다 버전이
              남습니다.
            </p>
            <ol className={styles.flowRow}>
              {LIFECYCLE.map((stage, index) => (
                <li className={styles.flowStage} key={stage.label}>
                  {index > 0 && (
                    <span className={styles.flowArrow} aria-hidden="true">
                      <Icon name="arrow-right" size={18} />
                    </span>
                  )}
                  <span className={styles.flowBox}>
                    <strong className={styles.flowLabel}>{stage.label}</strong>
                    <small className={styles.flowSub}>{stage.sub}</small>
                  </span>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* 6 · 변경 작업의 사전 확인 */}
        <section className={styles.band}>
          <div className={styles.bandInner}>
            <h2 className={styles.h2}>밖을 바꾸는 작업은 실행 전에 확인합니다</h2>
            <div className={styles.gate}>
              <p className={styles.gateBody}>
                조회는 그대로 답합니다. 업무를 등록하거나 수정하는 것처럼{' '}
                <strong>실제로 무언가를 바꾸는 작업</strong>은 실행 직전에 멈추고, 무엇을 할 것인지
                보여줍니다. 그때 승인하거나, 고치거나, 거절할 수 있습니다.
              </p>
              {/* 19 / 7 은 `BUILTIN_TOOLS` 와 `side_effect` 플래그의 실제 값이다. */}
              <p className={styles.gateStat}>
                <strong>7</strong>
                <span>19가지 도구 중 이 확인을 거치는 수</span>
              </p>
            </div>
          </div>
        </section>

        {/* 7 · 마감 CTA */}
        <section className={styles.cta}>
          <div className={styles.ctaInner}>
            <h2 className={styles.ctaTitle}>팀을 만들고 바로 물어보세요</h2>
            <p className={styles.ctaSub}>조회 도구는 처음부터 붙어 있습니다.</p>
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
