import { useState } from 'react';
import styles from './RecentUpdatesPanel.module.css';

type Tone = 'info' | 'danger' | 'success' | 'warning';

interface UpdateItem {
  id: number;
  title: string;
  author: string;
  time: string;
  tag: string;
  tone: Tone;
}

const UPDATES: UpdateItem[] = [
  { id: 1, title: '메인 대시보드 화면 설계 수정', author: '이지원', time: '10분 전', tag: '디자인', tone: 'info' },
  { id: 2, title: 'API 연동 규격서 작성 완료', author: '이정재', time: '1시간 전', tag: '개발', tone: 'danger' },
  { id: 3, title: '런칭 프로모션 기획 검토', author: '한예슬', time: '3시간 전', tag: '기획', tone: 'success' },
  { id: 4, title: '서버 환경 이중화 테스트 실패', author: '강동원', time: '5시간 전', tag: '인프라', tone: 'warning' },
];

const DOT_CLASS: Record<Tone, string> = {
  info: styles.dotInfo,
  danger: styles.dotDanger,
  success: styles.dotSuccess,
  warning: styles.dotWarning,
};

export function RecentUpdatesPanel() {
  const [readIds, setReadIds] = useState<Set<number>>(new Set());

  function toggleRead(id: number) {
    setReadIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  return (
    <div className={styles.card}>
      <p className={styles.cardTitle}>최근 업데이트</p>
      <div className={styles.list}>
        {UPDATES.map((update, idx) => (
          <div key={update.id}>
            <button
              type="button"
              className={[styles.row, readIds.has(update.id) ? styles.read : ''].filter(Boolean).join(' ')}
              onClick={() => toggleRead(update.id)}
            >
              <span className={[styles.dot, DOT_CLASS[update.tone]].join(' ')} />
              <div className={styles.content}>
                <p className={styles.title}>{update.title}</p>
                <div className={styles.meta}>
                  <span className={styles.author}>{update.author}</span>
                  <span className={styles.sep}>&bull;</span>
                  <span className={styles.time}>{update.time}</span>
                </div>
              </div>
              <span className={styles.tag}>{update.tag}</span>
            </button>
            {idx < UPDATES.length - 1 && <div className={styles.divider} />}
          </div>
        ))}
      </div>
    </div>
  );
}

export default RecentUpdatesPanel;
