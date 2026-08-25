import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '../Icon/Icon';
import { fetchIndexingProgress, sumIndexing } from '../../api/documentLibrary';
import type { IndexingCounts as Counts, IndexingProgress as Progress } from '../../api/documentLibrary';
import { PATHS } from '../../routes';
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
 * 도는 동안 10초, 아니면 60초. **탭이 숨겨져 있으면 아예 안 돈다** — 보지도
 * 않는 화면 때문에 서버를 두드릴 이유가 없다. 다시 보이면 그 자리에서 한 번
 * 물어본다(숨은 사이에 끝났을 수 있다).
 */

const POLL_ACTIVE_MS = 10_000;
const POLL_IDLE_MS = 60_000;

/**
 * 다 읽은 뒤 카드를 얼마나 더 붙잡아 둘까.
 *
 * **표보다 먼저 꺼지던 것을 막는다.** 이 카드와 「문서」 화면의 표는 각자 10초로
 * 따로 돈다 — 카드가 「다 됐다」를 먼저 보고 사라지는 사이 표는 아직 직전 응답을
 * 들고 있어서, 마지막 파일이 「읽는 중」인 채로 카드만 없어졌다(실서버 실측).
 * 표의 주기(10초)보다 길게 잡아야 그 사이가 덮인다.
 *
 * 겸해서 **끝났다는 말을 한다.** 그냥 사라지면 끝난 것인지 무엇이 잘못된 것인지
 * 구별되지 않는다.
 */
const FINISH_HOLD_MS = 12_000;

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
  const wasIndexing = useRef(false);
  const timer = useRef<number | null>(null);

  // 로그인·로그아웃을 따라간다. 로그아웃하면 폴링도 멈춰야 한다.
  useEffect(() => subscribeSession(() => setSession(loadSession())), []);

  const token = session?.token;

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
      const interval = isIndexing(progress) ? POLL_ACTIVE_MS : POLL_IDLE_MS;
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
  }, [token, poll, isIndexing(progress)]);

  // **팀 문서와 내 파일을 합쳐 본다.** 기다리는 사람에게는 「내 문서」 하나이고,
  // 올린 파일도 커넥터 문서와 똑같이 워커를 100초씩 기다린다
  // (`apps/personal_files` 의 `_start_processing`).
  const counts = progress === null ? null : sumIndexing(progress);
  const total = counts?.total ?? 0;
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
    if (was && !indexing && counts !== null && counts.total > 0) setFinished(counts);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [indexing]);

  useEffect(() => {
    if (finished === null) return;
    const timer = window.setTimeout(() => setFinished(null), FINISH_HOLD_MS);
    return () => window.clearTimeout(timer);
  }, [finished]);

  // 도는 중도 아니고 막 끝난 것도 아니면 안 그린다.
  if (dismissed) return null;
  const shown = indexing ? counts : finished;
  if (shown === null) return null;

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
            사람이 「그럼 그 몇 건은?」을 물을 유일한 순간이다. */}
        {shown.failed > 0 ? (
          <span className={styles.failed}>실패 {shown.failed}</span>
        ) : (
          <span className={styles.hint}>
            {indexing ? '읽은 문서부터 검색에 쓰입니다' : '이제 검색에 쓰입니다'}
          </span>
        )}
        <button type="button" className={styles.link} onClick={() => navigate(PATHS.documents)}>
          문서 보기
        </button>
      </div>
    </aside>
  );
}

export default IndexingProgress;
