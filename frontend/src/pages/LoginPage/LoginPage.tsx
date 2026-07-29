import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button, Icon, Input, useToast } from '../../components';
import styles from './LoginPage.module.css';

function InviteIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" width={18} height={18}>
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <line x1="19" y1="8" x2="19" y2="14" />
      <line x1="22" y1="11" x2="16" y2="11" />
    </svg>
  );
}

export default function LoginPage() {
  const { showToast } = useToast();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    showToast('로그인되었습니다.', 'success');
    setTimeout(() => {
      navigate('/onboarding/connectors');
    }, 700);
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
            <h1 className={styles.cardTitle}>로그인</h1>
            <p className={styles.cardSubtitle}>서비스를 이용하려면 로그인을 진행해주세요.</p>
          </div>

          <form id="login-form" className={styles.fieldGroup} onSubmit={handleSubmit}>
            <Input
              label="이메일"
              type="email"
              id="email"
              name="email"
              placeholder="name@company.com"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
            <Input
              label="비밀번호"
              type={showPassword ? 'text' : 'password'}
              id="password"
              name="password"
              placeholder="비밀번호를 입력하세요"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              rightElement={
                <button
                  type="button"
                  className={styles.eyeToggle}
                  onClick={() => setShowPassword((prev) => !prev)}
                  aria-label={showPassword ? '비밀번호 숨기기' : '비밀번호 보기'}
                >
                  <Icon name={showPassword ? 'eye-off' : 'eye'} size={20} color="var(--color-placeholder)" />
                </button>
              }
            />
          </form>

          <Button type="submit" form="login-form" variant="primary" fullWidth>
            로그인
          </Button>

          <Button
            type="button"
            variant="outline"
            fullWidth
            iconLeft={<InviteIcon />}
            onClick={() => navigate('/invite-code')}
          >
            초대코드로 회원가입
          </Button>
        </div>

        <div className={styles.footerLinks}>
          <Link to="/find-password" className={styles.link}>
            비밀번호 찾기
          </Link>
          <p className={styles.footerText}>
            계정이 없으신가요?{' '}
            <Link to="/signup" className={styles.link}>
              회원가입
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
