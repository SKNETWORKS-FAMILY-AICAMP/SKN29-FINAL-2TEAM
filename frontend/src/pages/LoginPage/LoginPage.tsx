import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Button, Icon, Input, useToast } from '../../components';
import { login } from '../../api/auth';
import { ApiError } from '../../api/client';
import { PATHS } from '../../routes';
import { saveSession } from '../../utils/session';
import styles from './LoginPage.module.css';

/*
 * 로그인 직후는 역할·연결 상태와 무관하게 Chat 이다.
 *
 * 4차 단계 1에서 대시보드 대신 Chat 으로 바뀌었고, 5차 단계 4에서 커넥터
 * 온보딩 분기가 사라졌다 — 온보딩 화면 자체가 없어졌기 때문이다. 연결이
 * 덜 됐으면 Chat 이 그 사실을 말하고 설정으로 보낸다. 홈이 사람마다 다르면
 * "그 화면 어디서 봤더라"를 사람이 기억해야 한다.
 */
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
  const location = useLocation();
  // RequireAuth가 막아서 여기로 온 경우, 로그인 후 원래 가려던 곳으로 되돌린다.
  const from = (location.state as { from?: string } | null)?.from;
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;

    setFormError('');
    setSubmitting(true);
    try {
      const result = await login(email.trim(), password);
      saveSession(result);
      showToast('로그인되었습니다.', 'success');
      navigate(from ?? PATHS.chat, { replace: true });
    } catch (error) {
      const message = error instanceof ApiError ? error.message : '로그인하지 못했습니다.';
      setFormError(message);
      showToast(message, 'error');
    } finally {
      setSubmitting(false);
    }
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
              required
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
              required
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

          {formError && (
            <p className={styles.formError} role="alert">
              {formError}
            </p>
          )}

          <Button type="submit" form="login-form" variant="primary" fullWidth disabled={submitting}>
            {submitting ? '로그인 중…' : '로그인'}
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
