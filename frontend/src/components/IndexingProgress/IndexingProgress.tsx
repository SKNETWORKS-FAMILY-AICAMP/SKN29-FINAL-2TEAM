import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '../Icon/Icon';
import { fetchIndexingProgress, sumIndexing } from '../../api/documentLibrary';
import type { IndexingCounts as Counts, IndexingProgress as Progress } from '../../api/documentLibrary';
import { PATHS } from '../../routes';
import { onIndexingStarted } from '../../utils/indexingSignal';
import { subscribeSession, loadSession } from '../../utils/session';
import styles from './IndexingProgress.module.css';

/**
 * 색인이 도는 동안 **화면 어디에 있든** 떠 있는 진행 카드.
 *
 * ## 왜 전역인가
 *
 * 색인이 시작되는 시점이 둘인데(`services/document_intake/__init__.py`) 둘 다
 * 사람이 특정 화면에 있어야만 볼 수 있었다.
 *
 *   폴더 저장   → 설정 > 커넥터 배지, 문서 화면
 *   대화 시작   → **아무 데도 안 보임** (Drive 변경분을 따라가며 색인한다)
 *
 * 채팅을 열어 놓고 답을 기다리는 사람은 문서가 들어오는 중이라는 사실 자체를
 * 알 수 없었다. 그래서 자리를 화면 밖으로 뺀다.
 *
 * ## 페이지를 옮겨도 살아 있는 방법
 *
 * `App.tsx` 에서 `<Routes>` **바깥**에 둔다. 라우트 전환은 이 컴포넌트를
 * 언마운트하지 않으므로 상태·타이머가 그대로 이어진다(`ToastProvider` 와 같은
 * 자리). 전역 상태 저장소가 따로 필요 없다.
 *
 * **새로고침해도 이어진다** — 이건 Google Drive 의 업로드 진행보다 나은
 * 점이다. 저쪽은 브라우저가 하는 일이라 새로고침하면 사라지지만, 우리 색인은
 * 서버가 하고 상태가 DB 에 있어서 다시 물어보면 그대로 붙는다.
 *
 * ## 폴링 간격
 *
 * 막 시작됐을 때 2초, 도는 동안 5초, 아니면 60초. **탭이 숨겨져 있으면 아예
 * 안 돈다** — 보지도 않는 화면 때문에 서버를 두드릴 이유가 없다. 다시 보이면
 * 그 자리에서 한 번 물어본다(숨은 사이에 끝났을 수 있다).
 */

const POLL_ACTIVE_MS = 5_000;
const POLL_IDLE_MS = 60_000;

/**
 * 신호를 받은 직후에만 쓰는 짧은 간격.
 *
 * **카드가 늦게 뜨는 것이 여기서 갈린다.** 신호가 오는 순간 서버에는 아직
 * `doc` 행이 없어서(수집 스레드가 Drive 를 훑는 중이다) 첫 폴링은 0건을 본다.
 * 그 다음 폴링까지 10초를 기다리면 사람 눈에는 저장하고 한참 뒤에 뜨는 것으로
 * 보인다 — 실제로 그렇게 느껴진다는 지적을 받았다.
 *
 * 짧게 잡아도 부담이 적다. 이 조회는 집계 한 번이고, 이 간격은 아래 창
 * (`NUDGE_WINDOW_MS`) 동안만 쓴다.
 */
const POLL_NUDGE_MS = 2_000;

/**
 * 다 읽은 뒤 카드를 얼마나 더 붙잡아 둘까.
 *
 * **표보다 먼저 꺼지던 것을 막는다.** 이 카드와 「문서」 화면의 표는 각자 따로
 * 돈다 — 카드가 「다 됐다」를 먼저 보고 사라지는 사이 표는 아직 직전 응답을
 * 들고 있어서, 마지막 파일이 「읽는 중」인 채로 카드만 없어졌다(실서버 실측).
 * 표의 주기(5초)보다 넉넉히 길게 잡아야 그 사이가 덮인다.
 *
 * 겸해서 **끝났다는 말을 한다.** 그냥 사라지면 끝난 것인지 무엇이 잘못된 것인지
 * 구별되지 않는다.
 */
const FINISH_HOLD_MS = 8_000;

/**
 * 「방금 시작됐다」는 신호를 받은 뒤 얼마나 바짝 따라붙을까.
 *
 * 신호가 오는 순간 서버에는 **아직 `doc` 행이 없을 수 있다** — 폴더 저장은
 * 응답을 붙잡지 않고 수집을 뒷작업으로 던지므로, 그 스레드가 Drive 를 훑어
 * 등록하기까지 시차가 있다. 한 번만 물어보고 말면 「아직 0건」을 보고 다시
 * 60초를 자 버린다. 그래서 잠시 10초 간격을 유지하며 나타나기를 기다린다.
 */
const NUDGE_WINDOW_MS = 30_000;

/**
 * **이번 회차의 몫만 남긴다.**
 *
 * 서버가 주는 숫자는 내 문서 **전부**의 집계다. 그래서 파일 하나를 올렸을 뿐인데
 * 지난주에 읽어 둔 팀 문서 8건까지 세어 「8/9」로 떴다(2026-08-26 지적). 사람이
 * 기다리는 것은 방금 시킨 일이지 서재의 총량이 아니다.
 *
 * 회차가 시작될 때 **이미 끝나 있던 수**를 기준선으로 잡고 그만큼을 뺀다.
 * 도중에 새 문서가 등록되면 `total` 이 늘어 분모도 따라 는다 — 폴더 저장처럼
 * 문서가 하나씩 나타나는 경우가 그렇다.
 *
 * 문서가 지워지면 음수가 될 수 있어 0 에서 자른다.
 */
function sinceBase(now: Counts, base: Counts | null): Counts {
  if (base === null) return now;
  const doneBefore = base.ready + base.failed;
  return {
    total: Math.max(0, now.total - doneBefore),
    ready: Math.max(0, now.ready - base.ready),
    failed: Math.max(0, now.failed - base.failed),
    running: now.running,
  };
}

/**
 * 아직 읽을 것이 남았는가. **실패도 「끝난 것」으로 센다** — 실패한 문서는
 * 스스로 끝나지 않으므로 빼지 않으면 10/12 에서 영원히 도는 것처럼 보인다.
 */
function isIndexing(progress: Progress | null): boolean {
  if (progress === null) return false;
  const counts = sumIndexing(progress);
  return counts.total > 0 && counts.ready + counts.failed < counts.total;
}

export function IndexingProgress() {
  const navigate = useNavigate();
  const [session, setSession] = useState(loadSession);
  const [progress, setProgress] = useState<Progress | null>(null);
  /** 사람이 닫았다. 이번 회차가 끝날 때까지 다시 안 뜬다. */
  const [dismissed, setDismissed] = useState(false);
  /** 막 끝난 회차. 잠시 「다 읽었습니다」로 남아 있다가 스스로 사라진다. */
  const [finished, setFinished] = useState<Counts | null>(null);
  /** 이 시각까지는 색인이 도는 것으로 치고 바짝 따라붙는다. 0 이면 아님. */
  const [nudgeUntil, setNudgeUntil] = useState(0);
  /**
   * 이번 회차가 시작될 때의 집계. 여기서부터가 「방금 시킨 일」이다.
   * 회차가 끝나면 비운다 — 다음 회차는 그때의 상태에서 다시 센다.
   */
  const [base, setBase] = useState<Counts | null>(null);
  const wasIndexing = useRef(false);
  const timer = useRef<number | null>(null);

  // 로그인·로그아웃을 따라간다. 로그아웃하면 폴링도 멈춰야 한다.
  useEffect(() => subscribeSession(() => setSession(loadSession())), []);

  // 폴더 저장·파일 업로드·재시도가 알려 온다. 그 자리에서 물어본다.
  useEffect(() => onIndexingStarted(() => setNudgeUntil(Date.now() + NUDGE_WINDOW_MS)), []);

  // 창이 지나면 스스로 푼다. 상태가 바뀌면서 폴링 간격도 원래대로 돌아간다.
  useEffect(() => {
    if (nudgeUntil === 0) return;
    const remaining = nudgeUntil - Date.now();
    if (remaining <= 0) {
      setNudgeUntil(0);
      return;
    }
    const timer = window.setTimeout(() => setNudgeUntil(0), remaining);
    return () => window.clearTimeout(timer);
  }, [nudgeUntil]);

  const token = session?.token;

  const nudging = nudgeUntil !== 0;

  const poll = useCallback(async () => {
    if (!token) return;
    try {
      setProgress(await fetchIndexingProgress(token));
    } catch {
      // **조용히 실패한다.** 이 카드는 곁다리 정보라, 못 읽었다고 사람이 보던
      // 화면 위에 오류를 띄우면 하던 일을 방해한다. 다음 회차가 다시 묻는다.
    }
  }, [token]);

  /**
   * 한 타이머로 간격만 바꿔 가며 돈다. `setInterval` 두 개를 조건부로 걸면
   * 상태가 바뀌는 순간 둘 다 살아 있는 구간이 생긴다.
   */
  useEffect(() => {
    if (!token) {
      setProgress(null);
      return;
    }

    function stop() {
      if (timer.current !== null) {
        window.clearInterval(timer.current);
        timer.current = null;
      }
    }

    function start() {
      stop();
      if (document.hidden) return;
      void poll();
      // 막 시작됐을 때가 제일 바쁘다 — 아직 없는 것이 나타나기를 기다리는
      // 구간이라, 여기서 늦으면 카드가 늦게 뜬 것으로 보인다.
      const interval = nudging ? POLL_NUDGE_MS : isIndexing(progress) ? POLL_ACTIVE_MS : POLL_IDLE_MS;
      timer.current = window.setInterval(() => void poll(), interval);
    }

    start();
    document.addEventListener('visibilitychange', start);
    return () => {
      stop();
      document.removeEventListener('visibilitychange', start);
    };
    // `progress` 를 의존성에 넣으면 폴링 결과마다 타이머를 다시 건다. 간격을
    // 바꾸는 것이 목적이므로 「도는가/아닌가」가 바뀔 때만 다시 걸면 된다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, poll, isIndexing(progress), nudging]);

  // **팀 문서와 내 파일을 합쳐 본다.** 기다리는 사람에게는 「내 문서」 하나이고,
  // 올린 파일도 커넥터 문서와 똑같이 워커를 100초씩 기다린다
  // (`apps/personal_files` 의 `_start_processing`).
  const all = progress === null ? null : sumIndexing(progress);
  const counts = all === null ? null : sinceBase(all, base);
  const done = (counts?.ready ?? 0) + (counts?.failed ?? 0);
  const indexing = isIndexing(progress);

  // 회차가 끝나면 닫아 둔 것을 푼다 — 다음에 색인이 돌면 다시 떠야 한다.
  useEffect(() => {
    if (!indexing) setDismissed(false);
  }, [indexing]);

  /**
   * 도는 중 → 끝남으로 넘어가는 **그 순간의 숫자를 붙잡아** 잠시 더 보여준다.
   * 의존성이 `indexing`(불리언) 하나뿐이라 전환에서 한 번만 돈다 — `counts` 를
   * 넣으면 폴링마다 다시 걸려 타이머가 계속 연장된다.
   */
  useEffect(() => {
    const was = wasIndexing.current;
    wasIndexing.current = indexing;
    // 회차가 시작된다. **지금 끝나 있는 것까지가 지난 일이다.**
    if (!was && indexing && all !== null) setBase(all);
    if (was && !indexing) {
      if (counts !== null && counts.total > 0) setFinished(counts);
      setBase(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [indexing]);

  useEffect(() => {
    if (finished === null) return;
    const timer = window.setTimeout(() => setFinished(null), FINISH_HOLD_MS);
    return () => window.clearTimeout(timer);
  }, [finished]);

  // 도는 중도 아니고 막 끝난 것도 아니면 안 그린다.
  if (dismissed) return null;
  // 기준선을 잡기 전에는 안 그린다. 그리면 그 한 프레임 동안 서재 전체 수가
  // 스쳐 지나간다 — 고치려던 바로 그 숫자다.
  if (indexing && base === null) return null;
  const shown = indexing ? counts : finished;
  if (shown === null || shown.total === 0) return null;

  const shownDone = indexing ? done : shown.total;
  const percent = Math.round((shownDone / shown.total) * 100);

  return (
    <aside
      className={styles.card}
      role="status"
      aria-live="polite"
      aria-label={indexing ? `문서 색인 진행 ${shownDone}/${shown.total}` : '문서 색인 완료'}
    >
      <div className={styles.head}>
        {indexing ? (
          <Icon name="loader" size={15} spin color="var(--color-primary)" />
        ) : (
          <Icon name="check-circle" size={15} color="var(--color-success)" />
        )}
        <span className={styles.title}>{indexing ? '문서를 읽는 중' : '문서를 다 읽었습니다'}</span>
        <span className={styles.count}>
          {shownDone}/{shown.total}
        </span>
        <button type="button" className={styles.close} onClick={() => setDismissed(true)} aria-label="닫기">
          <Icon name="x" size={13} />
        </button>
      </div>

      <div className={styles.bar}>
        <div className={styles.barFill} style={{ width: `${percent}%` }} />
      </div>

      <div className={styles.foot}>
        {/* 실패는 숨기지 않는다. 남은 수에서 빠지므로 이 줄이 없으면 왜 8/10
            에서 끝났는지 알 수 없다. **끝난 뒤에는 더 중요하다** — 그때가
            사람이 「그럼 그 몇 건은?」을 물을 유일한 순간이다.

            반대로 「읽은 문서부터 검색에 쓰입니다」 같은 설명은 걷었다. 없어도
            사람이 할 행동이 안 바뀌고, 「검색」은 우리 쪽 말이다. */}
        {shown.failed > 0 && <span className={styles.failed}>읽기 실패 {shown.failed}</span>}
        <button type="button" className={styles.link} onClick={() => navigate(PATHS.documents)}>
          문서 보기
        </button>
      </div>
    </aside>
  );
}

export default IndexingProgress;
