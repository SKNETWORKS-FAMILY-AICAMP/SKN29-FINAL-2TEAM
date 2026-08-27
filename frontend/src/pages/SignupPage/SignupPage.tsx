import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Button, Icon, Input, Logo, useToast } from '../../components';
import { signup } from '../../api/auth';
import { ApiError } from '../../api/client';
import { previewInvite } from '../../api/invites';
import type { InvitePreview } from '../../api/invites';
import { PATHS } from '../../routes';
import { saveSession } from '../../utils/session';
import styles from './SignupPage.module.css';

export default function SignupPage() {
  const { showToast } = useToast();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const inviteCode = searchParams.get('invite')?.trim() ?? '';

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showPasswordConfirm, setShowPasswordConfirm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [invite, setInvite] = useState<InvitePreview | null>(null);
  const [inviteError, setInviteError] = useState('');

  // 초대코드 화면에서 이미 확인했더라도, 코드를 URL에 직접 붙여 들어오는
  // 경우가 있으므로 여기서 한 번 더 확인한다.
  useEffect(() => {
    if (!inviteCode) return;

    let cancelled = false;
    previewInvite(inviteCode)
      .then((preview) => {
        if (cancelled) return;
        setInvite(preview);
        setName((current) => current || preview.person_name);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setInviteError(error instanceof ApiError ? error.message : '초대코드를 확인하지 못했습니다.');
      });

    return () => {
      cancelled = true;
    };
  }, [inviteCode]);

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
      const result = await signup({
        email: email.trim(),
        password,
        displayName: name.trim(),
        inviteCode,
      });
      saveSession(result);
      showToast('회원가입이 완료되었습니다.', 'success');
      // 팀원 대시보드는 아직 없으므로 팀원은 본인 설정 화면으로 보낸다.
      // 가입이 끝나면 바로 Chat 이다(5차 단계 4). 커넥터 연결·팀 생성는
      // Settings > Connector 에 있고, Chat 이 그리로 안내한다.
      navigate(PATHS.chat);
    } catch (error) {
      if (error instanceof ApiError) {
        setFieldErrors(error.fieldErrors);
        setFormError(Object.keys(error.fieldErrors).length ? '' : error.message);
        showToast(error.message, 'error');
      } else {
        setFormError('회원가입하지 못했습니다.');
        showToast('회원가입하지 못했습니다.', 'error');
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
            <h1 className={styles.cardTitle}>회원가입</h1>
            <p className={styles.cardSubtitle}>팀에 필요한 AI 에이전트를 코딩 없이 만들어 씁니다.</p>
          </div>

          <div className={styles.tabsRow}>{inviteCode ? '초대로 참여하기' : '새 팀 생성'}</div>

          {invite && (
            <p className={styles.inviteBanner}>
              <strong>{invite.person_name}</strong>
              {invite.org_name ? ` · ${invite.org_name}` : ''} 님으로 연결되는 초대입니다.
            </p>
          )}

          {inviteError && (
            <p className={styles.formError} role="alert">
              {inviteError}{' '}
              <Link to="/invite-code" className={styles.link}>
                코드 다시 입력하기
              </Link>
            </p>
          )}

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
              error={fieldErrors.display_name}
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
              error={fieldErrors.email}
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
              error={fieldErrors.password}
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
              placeholder="비밀번호를 다시 입력하세요"
              autoComplete="new-password"
              value={passwordConfirm}
              error={fieldErrors.password_confirm}
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

          {formError && (
            <p className={styles.formError} role="alert">
              {formError}
            </p>
          )}

          <Button type="submit" form="signup-form" variant="primary" fullWidth disabled={submitting}>
            {submitting ? '가입 중…' : '가입하기'}
          </Button>
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
