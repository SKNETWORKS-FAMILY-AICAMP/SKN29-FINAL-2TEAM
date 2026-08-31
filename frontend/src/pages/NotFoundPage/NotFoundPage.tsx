import { Link } from 'react-router-dom';
import { PATHS } from '../../routes';
import styles from './NotFoundPage.module.css';

export default function NotFoundPage() {
  return (
    <main className={styles.page}>
      <section className={styles.card}>
        <p className={styles.code}>404</p>
        <h1>페이지를 찾을 수 없습니다.</h1>
        <p>주소가 바뀌었거나 입력한 경로가 올바르지 않습니다.</p>
        <Link to={PATHS.landing}>halil 홈으로</Link>
      </section>
    </main>
  );
}
