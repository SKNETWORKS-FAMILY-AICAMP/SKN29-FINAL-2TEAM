import { useState } from 'react';
import type { FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { Button, Input, Logo } from '../../components';
import { opsLogin } from '../../api/ops';
import { ApiError } from '../../api/client';
import { loadOpsSession, saveOpsSession } from '../../utils/opsSession';
import styles from './OpsLoginPage.module.css';

interface LoginLocationState {
  from?: string;
}

export default function OpsLoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const target = (location.state as LoginLocationState | null)?.from ?? '/ops';

  if (loadOpsSession()) {
    return <Navigate to={target} replace />;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    if (!email.trim() || !password) {
      setError('운영자 이메일과 비밀번호를 모두 입력해 주세요.');
      return;
    }

    setError('');
    setSubmitting(true);
    try {
      const result = await opsLogin(email.trim(), password);
      saveOpsSession(result.token, result.admin);
      navigate(target, { replace: true });
    } catch (thrown) {
      setError(thrown instanceof ApiError ? thrown.message : '로그인하지 못했습니다.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className={styles.page}>
      <form className={styles.loginCard} onSubmit={handleSubmit}>
        <div className={styles.brand}>
          <Logo height={30} />
        </div>
        <h1>운영자 로그인</h1>

        <div className={styles.fields}>
          <Input
            label="운영자 이메일"
            type="email"
            value={email}
            onChange={(event) => {
              setEmail(event.target.value);
              setError('');
            }}
            placeholder="운영자 이메일을 입력하세요"
            autoComplete="username"
          />
          <Input
            label="비밀번호"
            type="password"
            value={password}
            onChange={(event) => {
              setPassword(event.target.value);
              setError('');
            }}
            placeholder="비밀번호를 입력하세요"
            autoComplete="current-password"
          />
        </div>

        {error && (
          <p className={styles.error} role="alert">
            {error}
          </p>
        )}

        <Button type="submit" variant="primary" size="lg" className={styles.submit} disabled={submitting}>
          {submitting ? '로그인 중…' : '로그인'}
        </Button>
        <p className={styles.note}>로그인 기록은 운영 감사 대상으로 관리됩니다.</p>
      </form>
    </main>
  );
}
