import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Button, Icon, Input, useToast } from '../../components';
import { confirmPasswordReset } from '../../api/auth';
import { ApiError } from '../../api/client';
import styles from './ResetPasswordPage.module.css';

export default function ResetPasswordPage() {
  const { showToast } = useToast();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') ?? '';

  const [password, setPassword] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;

    if (password !== passwordConfirm) {
      setFieldErrors({ password_confirm: '비밀번호가 일치하지 않습니다.' });
      return;
    }

    setFormError('');
    setFieldErrors({});
    setSubmitting(true);
    try {
      await confirmPasswordReset(token, password);
      showToast('비밀번호를 변경했습니다. 새 비밀번호로 로그인해 주세요.', 'success');
      navigate('/login');
    } catch (error) {
      if (error instanceof ApiError) {
        setFieldErrors(error.fieldErrors);
        setFormError(Object.keys(error.fieldErrors).length ? '' : error.message);
        showToast(error.message, 'error');
      } else {
        setFormError('비밀번호를 변경하지 못했습니다.');
        showToast('비밀번호를 변경하지 못했습니다.', 'error');
      }
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
            <h1 className={styles.cardTitle}>비밀번호 재설정</h1>
            <p className={styles.cardSubtitle}>새로 사용할 비밀번호를 입력해 주세요.</p>
          </div>

          {token ? (
            <>
              <form id="reset-password-form" className={styles.fieldGroup} onSubmit={handleSubmit}>
                <Input
                  label="새 비밀번호"
                  required
                  type={showPassword ? 'text' : 'password'}
                  id="new-password"
                  name="password"
                  placeholder="8자 이상의 영문, 숫자 조합"
                  autoComplete="new-password"
                  value={password}
                  error={fieldErrors.password}
                  onChange={(event) => setPassword(event.target.value)}
                  rightElement={
                    <button
                      type="button"
                      className={styles.eyeToggle}
                      onClick={() => setShowPassword((prev) => !prev)}
                      aria-label={showPassword ? '비밀번호 숨기기' : '비밀번호 보기'}
                    >
                      <Icon
                        name={showPassword ? 'eye-off' : 'eye'}
                        size={20}
                        color="var(--color-placeholder)"
                      />
                    </button>
                  }
                />
                <Input
                  label="새 비밀번호 확인"
                  required
                  type={showPassword ? 'text' : 'password'}
                  id="new-password-confirm"
                  name="password_confirm"
                  placeholder="비밀번호를 한번 더 입력해 주세요"
                  autoComplete="new-password"
                  value={passwordConfirm}
                  error={fieldErrors.password_confirm}
                  onChange={(event) => setPasswordConfirm(event.target.value)}
                />
              </form>

              {formError && (
                <p className={styles.formError} role="alert">
                  {formError}
                </p>
              )}

              <Button
                type="submit"
                form="reset-password-form"
                variant="primary"
                fullWidth
                disabled={submitting}
              >
                {submitting ? '변경 중…' : '비밀번호 변경'}
              </Button>
            </>
          ) : (
            <p className={styles.formError} role="alert">
              재설정 링크가 올바르지 않습니다.{' '}
              <Link to="/find-password" className={styles.link}>
                다시 요청하기
              </Link>
            </p>
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
