import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { Button, Input, Logo, useToast } from '../../components';
import { requestPasswordReset } from '../../api/auth';
import { ApiError } from '../../api/client';
import { PATHS } from '../../routes';
import styles from './FindPasswordPage.module.css';

export default function FindPasswordPage() {
  const { showToast } = useToast();
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [sentTo, setSentTo] = useState('');
  const [formError, setFormError] = useState('');

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;

    setFormError('');
    setSubmitting(true);
    try {
      const address = email.trim();
      await requestPasswordReset(address);
      setSentTo(address);
    } catch (error) {
      const message = error instanceof ApiError ? error.message : '요청을 처리하지 못했습니다.';
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
          {/* 로고를 눌러 랜딩으로 돌아간다. 예전에는 그냥 `div` 라, 랜딩에서
              「시작하기」를 눌러 들어온 사람이 뒤로가기 말고는 돌아갈 길이
              없었다. `PrivacyPage` 가 이미 쓰던 방식과 문구를 그대로 쓴다. */}
          <Link to={PATHS.landing} className={styles.logoBadge} aria-label="halil 홈으로">
            <Logo height={34} />
          </Link>
          <p className={styles.tagline}>프로젝트 운영 AI 플랫폼</p>
        </div>

        <div className={styles.card}>
          <div>
            <h1 className={styles.cardTitle}>비밀번호 찾기</h1>
            <p className={styles.cardSubtitle}>
              가입한 이메일 주소를 입력하시면 비밀번호 재설정 링크를 발송합니다.
            </p>
          </div>

          {sentTo ? (
            <p className={styles.sentNotice}>
              <strong>{sentTo}</strong> 로 재설정 링크를 보냈습니다. 가입된 이메일이라면 곧 도착합니다.
              <br />
              링크는 1시간 동안만 유효합니다.
            </p>
          ) : (
            <>
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

              {formError && (
                <p className={styles.formError} role="alert">
                  {formError}
                </p>
              )}

              <Button
                type="submit"
                form="find-password-form"
                variant="primary"
                fullWidth
                disabled={submitting}
              >
                {submitting ? '보내는 중…' : '재설정 링크 보내기'}
              </Button>
            </>
          )}
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
