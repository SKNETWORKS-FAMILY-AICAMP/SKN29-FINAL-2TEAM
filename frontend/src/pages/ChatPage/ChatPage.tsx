import { AppShell } from '../../components';
import styles from './ChatPage.module.css';

/**
 * Chat 홈. 단계 A에서는 셸 배선만 하고, 카드 6종·상태 5종은 단계 D에서
 * mock 이벤트 스트림으로 채운다(개발지시 2차 단계 D).
 */
export default function ChatPage() {
  return (
    <AppShell variant="flush">
      <div className={styles.placeholder}>
        <p className={styles.title}>Chat</p>
        <p className={styles.desc}>대화 화면은 단계 D에서 붙습니다.</p>
      </div>
    </AppShell>
  );
}
