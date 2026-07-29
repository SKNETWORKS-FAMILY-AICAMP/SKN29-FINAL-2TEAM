import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button, Icon, Input, useToast } from '../../components';
import styles from './InviteCodePage.module.css';

export default function InviteCodePage() {
  const { showToast } = useToast();
  const navigate = useNavigate();
  const [inviteCode, setInviteCode] = useState('');

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    showToast('초대코드를 확인했습니다.', 'success');
    setTimeout(() => {
      navigate(`/signup?invite=${encodeURIComponent(inviteCode.trim())}`);
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
              onChange={(event) => setInviteCode(event.target.value)}
            />
          </form>

          <Button type="submit" form="invite-code-form" variant="primary" fullWidth>
            다음: 회원가입
          </Button>
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
