import { useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { Button, Input } from '../../components';
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
  const [error, setError] = useState('');
  const target = (location.state as LoginLocationState | null)?.from ?? '/ops';

  if (loadOpsSession()) {
    return <Navigate to={target} replace />;
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!email.trim() || !password) {
      setError('관리자 이메일과 비밀번호를 모두 입력해 주세요.');
      return;
    }

    saveOpsSession(email.trim());
    navigate(target, { replace: true });
  }

  return (
    <main className={styles.page}>
      <form className={styles.loginCard} onSubmit={handleSubmit}>
        <div className={styles.brand}>
          <span>h</span>
          <strong>halil</strong>
        </div>
        <h1>관리자 로그인</h1>

        <div className={styles.fields}>
          <Input
            label="관리자 이메일"
            type="email"
            value={email}
            onChange={(event) => {
              setEmail(event.target.value);
              setError('');
            }}
            placeholder="관리자 이메일을 입력하세요"
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

        <Button type="submit" variant="primary" size="lg" className={styles.submit}>
          로그인
        </Button>
        <p className={styles.note}>로그인 기록은 운영 감사 대상으로 관리됩니다.</p>
      </form>
    </main>
  );
}
