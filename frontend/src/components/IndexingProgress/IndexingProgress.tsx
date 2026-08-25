import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '../Icon/Icon';
import { fetchIndexingProgress } from '../../api/documentLibrary';
import type { IndexingProgress as Progress } from '../../api/documentLibrary';
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

export function IndexingProgress() {
  const navigate = useNavigate();
  const [session, setSession] = useState(loadSession);
  const [progress, setProgress] = useState<Progress | null>(null);
  /** 사람이 닫았다. 이번 회차가 끝날 때까지 다시 안 뜬다. */
  const [dismissed, setDismissed] = useState(false);
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
      const running = progress !== null && progress.ready + progress.failed < progress.total;
      timer.current = window.setInterval(() => void poll(), running ? POLL_ACTIVE_MS : POLL_IDLE_MS);
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
  }, [token, poll, progress !== null && progress.ready + progress.failed < progress.total]);

  const total = progress?.total ?? 0;
  const done = (progress?.ready ?? 0) + (progress?.failed ?? 0);
  const indexing = progress !== null && total > 0 && done < total;

  // 회차가 끝나면 닫아 둔 것을 푼다 — 다음에 색인이 돌면 다시 떠야 한다.
  useEffect(() => {
    if (!indexing) setDismissed(false);
  }, [indexing]);

  // 도는 것이 없으면 아무것도 안 그린다. 「전부 읽음」은 정상 상태라 화면 위에
  // 남아 있을 이유가 없다.
  if (!indexing || dismissed) return null;

  const percent = Math.round((done / total) * 100);

  return (
    <aside
      className={styles.card}
      role="status"
      aria-live="polite"
      aria-label={`문서 색인 진행 ${done}/${total}`}
    >
      <div className={styles.head}>
        <Icon name="loader" size={15} spin color="var(--color-primary)" />
        <span className={styles.title}>문서를 읽는 중</span>
        <span className={styles.count}>
          {done}/{total}
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
            에서 끝났는지 알 수 없다. */}
        {progress.failed > 0 ? (
          <span className={styles.failed}>실패 {progress.failed}</span>
        ) : (
          <span className={styles.hint}>읽은 문서부터 검색에 쓰입니다</span>
        )}
        <button type="button" className={styles.link} onClick={() => navigate(PATHS.documents)}>
          문서 보기
        </button>
      </div>
    </aside>
  );
}

export default IndexingProgress;
