import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { Button, Icon, Input, useToast } from '../../components';
import styles from './LoginPage.module.css';

function GoogleLogo() {
  return (
    <span className={styles.googleLogo}>
      <span className={styles.googleR} />
      <span className={styles.googleY} />
      <span className={styles.googleG} />
      <span className={styles.googleB} />
    </span>
  );
}

function JiraLogo() {
  return (
    <span className={styles.jiraLogo}>
      <span className={styles.jiraSquare} />
    </span>
  );
}

export default function LoginPage() {
  const { showToast } = useToast();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    showToast('로그인 시도 중입니다.', 'info');
  }

  function handleSocialLogin(provider: string) {
    showToast(`${provider} 계정으로 로그인 시도 중입니다.`, 'info');
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

          <div className={styles.divider}>
            <div className={styles.line} />
            <span className={styles.dividerLabel}>또는</span>
            <div className={styles.line} />
          </div>

          <Button
            type="button"
            variant="secondary"
            fullWidth
            iconLeft={<GoogleLogo />}
            onClick={() => handleSocialLogin('Google')}
          >
            Google 계정으로 로그인
          </Button>

          <Button
            type="button"
            variant="secondary"
            fullWidth
            iconLeft={<JiraLogo />}
            onClick={() => handleSocialLogin('Jira')}
          >
            Jira 계정으로 로그인
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
