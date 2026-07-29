import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button, Icon, Input, useToast } from '../../components';
import styles from './SignupPage.module.css';

export default function SignupPage() {
  const { showToast } = useToast();
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showPasswordConfirm, setShowPasswordConfirm] = useState(false);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    showToast('회원가입이 완료되었습니다.', 'success');
    setTimeout(() => {
      navigate('/login');
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
            <h1 className={styles.cardTitle}>회원가입</h1>
            <p className={styles.cardSubtitle}>halil과 함께 지능형 업무 배정을 경험해 보세요.</p>
          </div>

          <div className={styles.tabsRow}>새 팀 만들기</div>

          <form id="signup-form" className={styles.fieldGroup} onSubmit={handleSubmit}>
            <Input
              label="이름"
              required
              type="text"
              id="name"
              name="name"
              placeholder="홍길동"
              autoComplete="name"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
            <Input
              label="이메일 주소"
              required
              type="email"
              id="signup-email"
              name="email"
              placeholder="name@company.com"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
            <Input
              label="비밀번호"
              required
              type={showPassword ? 'text' : 'password'}
              id="signup-password"
              name="password"
              placeholder="8자 이상의 영문, 숫자 조합"
              autoComplete="new-password"
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
            <Input
              label="비밀번호 확인"
              required
              type={showPasswordConfirm ? 'text' : 'password'}
              id="signup-password-confirm"
              name="password_confirm"
              placeholder="비밀번호를 한번 더 입력해 주세요"
              autoComplete="new-password"
              value={passwordConfirm}
              onChange={(event) => setPasswordConfirm(event.target.value)}
              rightElement={
                <button
                  type="button"
                  className={styles.eyeToggle}
                  onClick={() => setShowPasswordConfirm((prev) => !prev)}
                  aria-label={showPasswordConfirm ? '비밀번호 숨기기' : '비밀번호 보기'}
                >
                  <Icon
                    name={showPasswordConfirm ? 'eye-off' : 'eye'}
                    size={20}
                    color="var(--color-placeholder)"
                  />
                </button>
              }
            />
          </form>

          <Button type="submit" form="signup-form" variant="primary" fullWidth>
            가입하기
          </Button>

          <div className={styles.divider}>
            <div className={styles.line} />
            <span className={styles.dividerLabel}>또는</span>
            <div className={styles.line} />
          </div>
        </div>

        <div className={styles.footerLinks}>
          <p className={styles.footerText}>
            이미 계정이 있으신가요?{' '}
            <Link to="/login" className={styles.link}>
              로그인
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
