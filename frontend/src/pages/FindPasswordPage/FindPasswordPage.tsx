import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { Button, Icon, Input, useToast } from '../../components';
import styles from './FindPasswordPage.module.css';

export default function FindPasswordPage() {
  const { showToast } = useToast();
  const [email, setEmail] = useState('');

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    showToast('BLOCKED · 비밀번호 재설정 API와 메일 발송이 아직 연결되지 않았습니다.', 'error');
  }

  return (
    <div className={styles.page}>
      <div className={`${styles.bgBlob} ${styles.bgBlobTl}`} />
      <div className={`${styles.bgBlob} ${styles.bgBlobBr}`} />

      <div className={styles.authContainer}>
        <div className={styles.header}>
          <div className={styles.logoBadge}>
            <Icon name="send" size={20} />
            <span>halil</span>
          </div>
          <p className={styles.tagline}>AI 기반 업무 배정 코파일럿</p>
        </div>

        <div className={styles.card}>
          <div>
            <h1 className={styles.cardTitle}>비밀번호 찾기</h1>
            <p className={styles.cardSubtitle}>
              가입한 이메일 주소를 입력하시면 비밀번호 재설정 링크를 보내드립니다.
            </p>
          </div>

          <form id="find-password-form" className={styles.fieldGroup} onSubmit={handleSubmit}>
            <Input
              label="이메일 주소"
              required
              type="email"
              id="recovery-email"
              name="email"
              placeholder="name@company.com"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </form>

          <Button type="submit" form="find-password-form" variant="primary" fullWidth>
            재설정 링크 보내기
          </Button>
        </div>

        <div className={styles.footerLinks}>
          <Link to="/login" className={styles.link}>
            로그인으로 돌아가기
          </Link>
        </div>
      </div>
    </div>
  );
}
