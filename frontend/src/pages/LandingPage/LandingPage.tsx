import { useEffect, useRef, useState } from 'react';
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
  { icon: 'file-text', text: '답마다 남는 확인 근거' },
  { icon: 'shield-check', text: '실행 직전, 사람의 확인' },
  { icon: 'sparkles', text: '반복할수록 쌓이는 팀의 방식' },
] as const;

/**
 * 3 · 안 해도 되는 일. **제품 속성이 아니라 그 사람의 하루에서 사라지는 일**을
 * 적는다 — 「그래서 내가 뭘 안 해도 되나」가 페이지에 한 줄도 없었다.
 */
const GAINS = [
  { gone: '회의록 뒤져서 할 일 옮겨 적기', now: '결정과 다음 할 일을 한 번에' },
  { gone: '누가 여유 있는지 물어보고 다니기', now: '다음 주 여유 인력, 바로 확인' },
  { gone: '업무 하나씩 손으로 등록하기', now: '확인한 업무만 골라 일괄 등록' },
  { gone: '주간 업무량 표 만들어 공유하기', now: '업무량 표를 만들고 즉시 다운로드' },
] as const;

/**
 * 실제 요청 예시. **제품명도, 내부 도구명도 쓰지 않는다.**
 * 예전에는 각 카드 아래에 「문서 검색 · 업무 추출」처럼 어떤 도구가 도는지를
 * 적어 뒀는데, 그건 사용자 가치가 아니라 내부 라우팅 설명이었다.
 */
const ASKS = [
  '회의에서 정한 일을 정리해 줘.',
  '다음 주 여유 인력을 알려 줘.',
  '확정한 업무만 등록해 줘.',
] as const;

/** 에이전트를 만들어 쓰는 차례. 상태 이름은 쓰지 않는다. */
const AGENT_FLOW = ['시킬 일을 적는다', '혼자 써 본다', '팀과 함께 쓴다'] as const;

/** 히어로 데모의 한 흐름. 결과 카드가 바뀌어도 이 네 단계는 제품의 주 경로다. */
const DEMO_PROGRESS = ['요청', '근거 찾기', '검토', '등록'] as const;

/** 실행을 맡기는 제품에서 가입 전에 먼저 보여줘야 할 세 가지 통제 장치. */
const TRUST_POINTS = [
  {
    icon: 'users',
    title: '팀별 권한',
    body: '만든 사람과 팀 권한에 맞춘 에이전트·정보 관리',
  },
  {
    icon: 'shield-check',
    title: '변경 전 확인',
    body: '등록·수정·파일 생성 전, 실행 내용 미리보기',
  },
  {
    icon: 'file-text',
    title: '실행 기록',
    body: '누가 무엇을 실행했는지 빠짐없이 남는 기록',
  },
] as const;

function Logo() {
  return (
    <span className={styles.logo}>
      <BrandLogo height={30} />
    </span>
  );
}

/**
 * 히어로 데모 — 요청부터 등록 결과까지 자동으로 반복해 보여 주는 자리.
 *
 * 그림 한 장으로는 「설명은 알겠는데 실제로도 이렇게 되나」가 남는다. 그래서
 * 묻기 → 찾기 → 확인 → 등록 → 결과를 짧은 대본으로 이어 보여 준다.
 *
 * ⚠ **서버를 부르지 않는다.** 화면만 도는 대본이다.
 *
 * 「※ 실제 데이터가 아닙니다」 같은 표기는 붙이지 않는다(PM) — 눌러 보라고 해
 * 놓고 바로 밑에서 변명하면 제품이 없어 보인다. 브라우저 틀 안의 미리보기라는
 * 것은 관습으로 읽히고, 안에 든 값도 한눈에 예시다. 대신 **실제 결과인 척하는
 * 문구를 어디에도 쓰지 않는 것**으로 지킨다.
 *
 * 단계 이름과 버튼 라벨은 전부 실제 Chat 에서 가져왔다 —
 * 「생각하는 중」·「문서 검색 실행 중」(`ChatPage.tsx` 의 `${toolName} 실행 중`) ·
 * 「선택한 N건 등록」·「등록하는 중…」·「N/N 등록 완료」(`ChatCards.tsx`).
 */
type DemoStep =
  | 'thinking'
  | 'searching'
  | 'verifying'
  | 'ready'
  | 'confirm'
  | 'registering'
  | 'done';

const DEMO_ASK = '어제 회의에서 정한 업무를 정리해 줘.';

function ChatMock() {
  // **빈 채로 기다리지 않는다.** 첫 요청을 바로 보여 주고, 사용자의 클릭 없이
  // 확인과 등록까지 진행한 뒤 처음부터 반복한다.
  const [step, setStep] = useState<DemoStep>('thinking');
  const timers = useRef<number[]>([]);

  // 한 주기의 타이머는 다음 주기가 시작되거나 화면을 떠날 때 전부 정리한다.
  // 이전 주기의 타이머가 남으면 단계가 건너뛰므로 매번 먼저 비운다.
  function startCycle() {
    timers.current.forEach(clearTimeout);
    setStep('thinking');
    timers.current = [
      // 진행 카드의 등장 애니메이션이 끝난 뒤에도 문구를 읽을 시간을 남긴다.
      window.setTimeout(() => setStep('searching'), 2400),
      window.setTimeout(() => setStep('verifying'), 4800),
      window.setTimeout(() => setStep('ready'), 7200),
      window.setTimeout(() => setStep('confirm'), 8100),
      window.setTimeout(() => setStep('registering'), 11400),
      window.setTimeout(() => setStep('done'), 12800),
      window.setTimeout(startCycle, 16400),
    ];
  }

  useEffect(() => {
    // 움직임을 줄이도록 설정한 사람에게는 단계를 돌리지 않고 결과부터 보인다 —
    // 볼 것은 확인 카드이지 기다리는 과정이 아니다.
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setStep('confirm');
      return undefined;
    }
    startCycle();
    return () => timers.current.forEach(clearTimeout);
    // 첫 마운트에서 한 번만 시작한다. `startCycle` 은 타이머 안에서 스스로 반복한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const running =
    step === 'thinking' || step === 'searching' || step === 'verifying' || step === 'ready';
  const showCard = step === 'confirm' || step === 'registering';
  const currentProgress =
    step === 'thinking' ? 0 : step === 'searching' ? 1 : step === 'done' ? 3 : 2;
  const workSteps = [
    { label: '요청 내용 파악', state: step === 'thinking' ? 'doing' : 'done' },
    {
      label: '회의록에서 결정사항 찾기',
      state: step === 'thinking' ? 'todo' : step === 'searching' ? 'doing' : 'done',
    },
    {
      label: '담당자와 마감일 확인',
      state:
        step === 'thinking' || step === 'searching'
          ? 'todo'
          : step === 'verifying'
            ? 'doing'
            : 'done',
    },
  ] as const;

  const workingCopy = {
    thinking: {
      title: '요청을 파악하는 중',
      description: '확인할 내용을 정리합니다',
      count: '1 / 3 단계',
    },
    searching: {
      title: '회의록에서 결정사항 찾는 중',
      description: '결정된 일과 다음 할 일을 찾습니다',
      count: '2 / 3 단계',
    },
    verifying: {
      title: '담당자와 마감일 확인 중',
      description: '빠진 정보가 없는지 살펴봅니다',
      count: '3 / 3 단계',
    },
    ready: {
      title: '확인이 끝났습니다',
      description: '근거 있는 업무만 준비했습니다',
      count: '3 / 3 완료',
    },
  }[running ? step : 'thinking'];

  return (
    <div className={styles.mock}>
      <div className={styles.mockBar}>
        <span className={styles.mockDot} />
        <span className={styles.mockDot} />
        <span className={styles.mockDot} />
        <span className={styles.mockBarLabel}>Chat</span>
        <span className={styles.mockAuto}>자동 재생</span>
      </div>

      <ol className={styles.mockProgress} aria-label="업무 처리 과정">
        {DEMO_PROGRESS.map((label, index) => (
          <li
            className={[
              styles.mockProgressStep,
              index < currentProgress ? styles.mockProgressDone : '',
              index === currentProgress ? styles.mockProgressCurrent : '',
            ]
              .filter(Boolean)
              .join(' ')}
            key={label}
            aria-current={index === currentProgress ? 'step' : undefined}
          >
            <span className={styles.mockProgressDot}>
              {index < currentProgress ? <Icon name="check" size={10} /> : index + 1}
            </span>
            <span>{label}</span>
          </li>
        ))}
      </ol>

      <div className={styles.mockBody}>
        <p className={styles.mockAsk}>{DEMO_ASK}</p>

        {running && (
          <div className={styles.mockWorking} role="status">
            <div className={styles.mockWorkingHead}>
              <span className={styles.mockWorkingIcon}>
                <Icon name={step === 'thinking' ? 'sparkles' : step === 'ready' ? 'check-circle' : 'search'} size={18} />
              </span>
              <span className={styles.mockWorkingText}>
                <strong>{workingCopy.title}</strong>
                <small>{workingCopy.description}</small>
              </span>
              <span className={styles.mockWorkingCount}>{workingCopy.count}</span>
              {step !== 'ready' && (
                <span className={styles.mockThinkingDots} aria-hidden="true">
                  <span />
                  <span />
                  <span />
                </span>
              )}
            </div>
            <span className={styles.mockWorkingTrack} aria-hidden="true">
              <span
                style={{
                  width:
                    step === 'thinking'
                      ? '33%'
                      : step === 'searching'
                        ? '66%'
                        : '100%',
                }}
              />
            </span>
            <ul className={styles.mockWorkSteps}>
              {workSteps.map((item) => (
                <li className={item.state === 'todo' ? styles.mockWorkStepTodo : styles.mockWorkStep} key={item.label}>
                  <Icon
                    name={item.state === 'done' ? 'check-circle' : item.state === 'doing' ? 'loader' : 'circle-help'}
                    size={14}
                    color={
                      item.state === 'done'
                        ? 'var(--color-success)'
                        : item.state === 'doing'
                          ? 'var(--color-primary)'
                          : 'var(--color-border)'
                    }
                    spin={item.state === 'doing'}
                  />
                  {item.label}
                </li>
              ))}
            </ul>
            {(step === 'searching' || step === 'verifying' || step === 'ready') && (
              <>
                <span className={styles.mockWorkQuery}>
                  <Icon name="search" size={13} color="var(--color-placeholder)" />
                  “고객 안내문” · “담당자” · “금요일”
                </span>
                <p className={styles.mockWorkFoot}>참고한 문서 1개 · 근거 1건</p>
              </>
            )}
          </div>
        )}

        {showCard && (
          <div className={styles.mockCard}>
            {/* 실제 확인 카드의 머리줄이다. 「확인이 필요합니다」가 아니다. */}
            <div className={styles.mockConfirmHead}>
              <span className={styles.mockConfirmLeft}>
                <span className={styles.mockCheck} aria-hidden="true">
                  <Icon name="check" size={11} color="#fff" />
                </span>
                <strong>전체 선택</strong>
                <span className={styles.mockMuted}>3건 선택됨</span>
              </span>
              <span className={styles.mockMuted}>업무 3건</span>
            </div>

            <div className={styles.mockTaskRow}>
              <span className={styles.mockCheck} aria-hidden="true">
                <Icon name="check" size={11} color="#fff" />
              </span>
              <div className={styles.mockTaskBody}>
                <span className={styles.mockTaskTitle}>고객 안내문 최종본 검토</span>
                <div className={styles.mockFacts}>
                  <span className={styles.mockFact}>
                    <span className={styles.mockFactLabel}>담당자</span>
                    <strong>김민지</strong>
                  </span>
                  <span className={styles.mockFact}>
                    <span className={styles.mockFactLabel}>마감</span>
                    <strong>이번 주 금요일</strong>
                  </span>
                </div>
                {/* 근거를 못 찾아 비운 칸. 회의록에 없는 예상 시간은 임의로 채우지 않는다. */}
                <p className={styles.mockMissing}>예상 시간: 근거 없어 비움</p>
                <span className={styles.mockEvidenceToggle}>
                  <Icon name="chevron-down" size={13} color="var(--color-primary)" />
                  원문 근거 1건
                </span>
                <blockquote className={styles.mockEvidence}>
                  <p>
                    고객 안내문은 이번 주 금요일까지 최종 검토한다. 김민지 님이 문안을 확인하고, 영업팀은
                    발송 대상 목록과 안내 메일을 준비한다.
                  </p>
                  <footer>
                    <span>4문단</span>
                    <span className={styles.mockEvidenceSource}>출시_준비_회의록.docx</span>
                  </footer>
                </blockquote>
              </div>
            </div>

            <div className={styles.mockConfirmActions}>
              <span className={styles.mockFootBtn}>
                {step === 'registering' ? '등록하는 중…' : '선택한 3건 등록'}
              </span>
              <span className={styles.mockFootGhost}>거절</span>
            </div>
          </div>
        )}

        {step === 'done' && (
          <div className={styles.mockCard}>
            <div className={styles.mockResultHead}>
              <Icon name="check-circle" size={17} color="var(--color-success-text)" />
              3/3 등록 완료
            </div>
            <div className={styles.mockIssueHead}>
              <strong>등록된 업무 3건</strong>
            </div>
            <div className={styles.mockIssueRow}>
              <span className={styles.mockIssueKey}>업무 1</span>
              <span className={styles.mockIssueBody}>
                <strong className={styles.mockIssueTitle}>고객 안내문 최종본 검토</strong>
                <span className={styles.mockIssueMeta}>김민지 · 이번 주 금요일</span>
              </span>
              <span className={styles.mockMuted}>근거 1건</span>
            </div>
            <div className={styles.mockIssueRow}>
              <span className={styles.mockIssueKey}>업무 2</span>
              <span className={styles.mockIssueBody}>
                <strong className={styles.mockIssueTitle}>발송 대상 고객 목록 정리</strong>
                <span className={styles.mockIssueMeta}>영업팀 · 이번 주 목요일</span>
              </span>
              <span className={styles.mockMuted}>근거 1건</span>
            </div>
            <div className={styles.mockIssueRow}>
              <span className={styles.mockIssueKey}>업무 3</span>
              <span className={styles.mockIssueBody}>
                <strong className={styles.mockIssueTitle}>안내 메일 발송 준비</strong>
                <span className={styles.mockIssueMeta}>영업팀 · 안내문 검토 후</span>
              </span>
              <span className={styles.mockMuted}>근거 1건</span>
            </div>
            <p className={styles.mockResultNote}>
              업무별 근거는 이 대화에 그대로 저장됩니다. 새로고침해도 사라지지 않습니다.
            </p>
          </div>
        )}
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
              <p className={styles.badge}>프로젝트를 움직이는 팀의 AI</p>
              <h1 className={styles.heroTitle}>
                찾은 정보에서,
                <span className={styles.heroAccent}>실행할 업무까지.</span>
              </h1>
              <p className={styles.heroSub}>
                halil은 문서·사람·프로젝트에 흩어진 정보를 찾아 근거와 함께 답합니다.
                <br />
                확인한 결과는 곧바로
                <br className={styles.mobileBreak} /> 실제 업무로 연결할 수 있습니다.
              </p>
              <div className={styles.heroActions}>
                <Link className={styles.btnPrimary} to={startHref}>
                  우리 팀에서 시작하기
                </Link>
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
            </div>
          </div>
        </section>

        {/* 2 · 요청 예시 — 큰 설명 섹션이 아니라 히어로 다음의 짧은 시작점이다. */}
        <section className={styles.promptBand}>
          <div className={styles.promptInner}>
            <div className={styles.promptIntro}>
              <span className={styles.sectionKicker}>시작은 간단하게</span>
              <h2 className={styles.promptTitle}>해야 할 일을, 평소 말하듯 적어보세요.</h2>
            </div>
            <ul className={styles.promptList}>
              {ASKS.map((ask) => (
                <li className={styles.prompt} key={ask}>
                  <Icon name="message-square" size={15} />
                  <p>“{ask}”</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* 3 · 안 해도 되는 일 */}
        <section className={styles.bandDark} id="can">
          <div className={styles.bandInner}>
            <div className={styles.gainHeader}>
              <div>
                <p className={styles.sectionKickerDark}>사라지는 수작업</p>
                <h2 className={`${styles.h2} ${styles.bandHeadline}`}>반복 업무는 이제 그만.</h2>
              </div>
              <p className={styles.gainLead}>
                회의록 확인부터 업무 등록까지,
                <br />
                팀이 반복하던 손일을 줄입니다.
              </p>
            </div>
            <ul className={styles.gainGrid}>
              {GAINS.map((item, index) => (
                <li className={styles.gain} key={item.gone}>
                  <span className={styles.gainBefore}>
                    <span>
                      <small>직접 하던 일</small>
                      <span className={styles.gainGone}>{item.gone}</span>
                    </span>
                    <span className={styles.gainNumber} aria-hidden="true">
                      {String(index + 1).padStart(2, '0')}
                    </span>
                  </span>
                  <span className={styles.gainAfter}>
                    <span className={styles.gainArrow} aria-hidden="true">
                      <Icon name="arrow-right" size={16} />
                    </span>
                    <span>
                      <small>이제는</small>
                      <strong className={styles.gainNow}>{item.now}</strong>
                    </span>
                  </span>
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
                <p className={styles.sectionKicker}>팀의 방식</p>
                <h2 className={styles.h2}>팀의 방식을 담은 AI.</h2>
                <p className={styles.statementBody}>
                  반복하는 일을 우리말로 적고 먼저 혼자 써 보세요.
                  <br />
                  준비되면 코딩 없이 팀에 공유할 수 있습니다.
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
            <div className={`${styles.split} ${styles.splitReverse}`}>
              <ApproveMock />
              <div className={styles.statement}>
                <p className={styles.sectionKicker}>사람이 정하는 마지막 단계</p>
                <h2 className={styles.h2}>마지막 결정은 사람이.</h2>
                <p className={styles.statementBody}>
                  업무 등록이나 파일 생성 전,
                  <br className={styles.mobileBreak} /> 실행 내용을 먼저 보여 줍니다.
                  <br />
                  실행 여부는 사람이 정합니다.
                </p>
                <ul className={styles.trustList}>
                  {TRUST_POINTS.map((point) => (
                    <li className={styles.trustPoint} key={point.title}>
                      <span className={styles.trustIcon} aria-hidden="true">
                        <Icon name={point.icon} size={16} />
                      </span>
                      <span>
                        <strong>{point.title}</strong>
                        <small>{point.body}</small>
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </section>

        {/* 6 · 마감 CTA */}
        <section className={styles.cta}>
          <div className={styles.ctaInner}>
            <h2 className={styles.ctaTitle}>찾은 정보, 바로 실행.</h2>
            <p className={styles.ctaSub}>
              새 팀을 만들거나,
              <br className={styles.mobileBreak} /> 초대받은 팀에 합류하세요.
            </p>
            <Link className={styles.btnOnDark} to={startHref}>
              우리 팀에서 시작하기
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
