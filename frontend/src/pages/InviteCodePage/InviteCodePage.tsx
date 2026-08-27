import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button, Input, Logo, useToast } from '../../components';
import { ApiError } from '../../api/client';
import { previewInvite } from '../../api/invites';
import type { InvitePreview } from '../../api/invites';
import styles from './InviteCodePage.module.css';

const EXPIRY_FORMAT = new Intl.DateTimeFormat('ko-KR', { dateStyle: 'long', timeStyle: 'short' });

export default function InviteCodePage() {
  const { showToast } = useToast();
  const navigate = useNavigate();
  const [inviteCode, setInviteCode] = useState('');
  const [checking, setChecking] = useState(false);
  const [formError, setFormError] = useState('');
  const [preview, setPreview] = useState<InvitePreview | null>(null);

  /**
   * 가입 화면으로 넘기기 전에 코드가 살아 있는지(존재·미만료·PENDING)
   * 먼저 확인하고 대상자를 보여준다 — 팀원_초대_계정_매핑_정책의
   * "팀원 측 UX 흐름" 1~2단계.
   */
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (checking) return;

    setFormError('');
    setChecking(true);
    try {
      setPreview(await previewInvite(inviteCode.trim()));
    } catch (error) {
      const message = error instanceof ApiError ? error.message : '초대코드를 확인하지 못했습니다.';
      setFormError(message);
      showToast(message, 'error');
    } finally {
      setChecking(false);
    }
  }

  return (
    <div className={styles.page}>
      <div className={`${styles.bgBlob} ${styles.bgBlobTl}`} />
      <div className={`${styles.bgBlob} ${styles.bgBlobBr}`} />

      <div className={styles.authContainer}>
        <div className={styles.header}>
          <div className={styles.logoBadge}>
            <Logo height={34} />
          </div>
          <p className={styles.tagline}>프로젝트 운영 AI 플랫폼</p>
        </div>

        <div className={styles.card}>
          <div>
            <h1 className={styles.cardTitle}>초대코드로 회원가입</h1>
            <p className={styles.cardSubtitle}>팀 관리자에게 받은 초대코드를 입력하면 회원가입을 진행할 수 있습니다.</p>
          </div>

          <form id="invite-code-form" className={styles.fieldGroup} onSubmit={handleSubmit}>
            <Input
              label="초대코드"
              required
              type="text"
              id="invite-code"
              name="inviteCode"
              placeholder="초대코드를 입력하세요"
              autoComplete="off"
              value={inviteCode}
              onChange={(event) => {
                setInviteCode(event.target.value);
                setPreview(null);
              }}
            />
          </form>

          {formError && (
            <p className={styles.formError} role="alert">
              {formError}
            </p>
          )}

          {preview && (
            <div className={styles.previewCard}>
              <p className={styles.previewLead}>다음 직원 계정으로 연결됩니다.</p>
              <p className={styles.previewName}>
                {preview.person_name}
                {preview.org_name && <span className={styles.previewOrg}> · {preview.org_name}</span>}
              </p>
              <p className={styles.previewMeta}>{preview.person_email}</p>
              <p className={styles.previewMeta}>
                유효기간 {EXPIRY_FORMAT.format(new Date(preview.expires_at))}까지
              </p>
            </div>
          )}

          {preview ? (
            <Button
              type="button"
              variant="primary"
              fullWidth
              onClick={() => navigate(`/signup?invite=${encodeURIComponent(inviteCode.trim())}`)}
            >
              본인이 맞습니다 · 회원가입 계속
            </Button>
          ) : (
            <Button type="submit" form="invite-code-form" variant="primary" fullWidth disabled={checking}>
              {checking ? '확인 중…' : '초대코드 확인'}
            </Button>
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
