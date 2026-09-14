import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import styles from './AppErrorBoundary.module.css';

interface Props {
  children: ReactNode;
  /**
   * 이 값이 바뀌면 떠 있던 오류 화면을 걷는다. `key` 로 넘기면 **오류가 없을 때도**
   * 아래 화면 전체가 새로 만들어진다 — 새 대화의 첫 발화가 주소를 `/chat` →
   * `/chat/:id` 로 바꾸는 순간 ChatPage 가 다시 마운트돼 스트림이 끊기고 빈 화면으로
   * 돌아갔다(2026-09-14 운영).
   */
  resetKey?: string;
}

interface State {
  error: Error | null;
}

function isLazyChunkError(error: Error): boolean {
  return /chunkloaderror|dynamically imported module|failed to fetch.*module|importing a module script/i.test(
    error.message,
  );
}

/**
 * 배포로 해시 자산이 교체된 동안 열려 있던 탭을 위한 마지막 복구선이다.
 * React.lazy()가 이전 청크를 읽지 못하면 Error Boundary가 없을 때 앱 전체가
 * 빈 화면이 된다. 자동 새로고침은 네트워크 장애에서 반복될 수 있으므로,
 * 원인을 설명하고 사람이 한 번만 다시 읽도록 한다.
 */
export class AppErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('화면 렌더링 오류', error, info.componentStack);
  }

  componentDidUpdate(prevProps: Props) {
    if (this.state.error && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ error: null });
    }
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    const chunkError = isLazyChunkError(error);
    return (
      <main className={styles.page}>
        <section className={styles.card} role="alert">
          <p className={styles.eyebrow}>{chunkError ? '새 버전 감지' : '화면 오류'}</p>
          <h1>{chunkError ? '새 화면을 불러올 준비가 됐습니다.' : '화면을 불러오지 못했습니다.'}</h1>
          <p>
            {chunkError
              ? '배포된 버전이 바뀌어 이전 화면 파일을 더 이상 사용할 수 없습니다. 새로고침하면 최신 버전으로 이어집니다.'
              : '일시적인 오류일 수 있습니다. 새로고침한 뒤에도 반복되면 관리자에게 알려 주세요.'}
          </p>
          <div className={styles.actions}>
            <button type="button" onClick={() => window.location.reload()}>
              새로고침
            </button>
            <a href="/">홈으로 이동</a>
          </div>
        </section>
      </main>
    );
  }
}
