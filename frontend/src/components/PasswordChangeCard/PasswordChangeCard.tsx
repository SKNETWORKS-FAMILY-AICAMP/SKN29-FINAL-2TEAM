import { useState } from 'react';
import { Button } from '../Button/Button';
import { Input } from '../Input/Input';
import { ApiError } from '../../api/client';
import { changePassword } from '../../api/auth';
import styles from './PasswordChangeCard.module.css';

export interface PasswordChangeCardProps {
  token: string | null;
  onDone: (message: string) => void;
  onError: (message: string) => void;
}

/**
 * 비밀번호 변경. 현재 비밀번호를 함께 보낸다 — 토큰만으로 바꾸게 하면 자리를
 * 비운 사이 남이 세션을 잡아 갈아 끼울 수 있다.
 *
 * 새 비밀번호는 두 번 받는다. 화면에 안 보이는 값이라 오타를 알 방법이 없고,
 * 틀린 채로 저장되면 본인도 못 들어온다.
 */
export function PasswordChangeCard({ token, onDone, onError }: PasswordChangeCardProps) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [saving, setSaving] = useState(false);

  const mismatch = confirm.length > 0 && next !== confirm;
  const ready = current.length > 0 && next.length > 0 && next === confirm;

  async function handleSubmit() {
    if (!token || !ready || saving) return;
    setSaving(true);
    try {
      const result = await changePassword(token, current, next);
      setCurrent('');
      setNext('');
      setConfirm('');
      onDone(result.detail);
    } catch (error) {
      onError(error instanceof ApiError ? error.message : '비밀번호를 변경하지 못했습니다.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className={styles.form}>
      <div className={styles.row}>
        <Input
          label="현재 비밀번호"
          type="password"
          autoComplete="current-password"
          value={current}
          onChange={(event) => setCurrent(event.target.value)}
        />
      </div>
      <div className={styles.row}>
        <Input
          label="새 비밀번호"
          type="password"
          autoComplete="new-password"
          value={next}
          onChange={(event) => setNext(event.target.value)}
        />
        <Input
          label="새 비밀번호 확인"
          type="password"
          autoComplete="new-password"
          value={confirm}
          onChange={(event) => setConfirm(event.target.value)}
        />
      </div>

      <p className={mismatch ? styles.mismatch : styles.rule}>
        {mismatch ? '새 비밀번호가 서로 다릅니다.' : '8자 이상이고 영문과 숫자를 함께 포함해야 합니다.'}
      </p>

      <div className={styles.actions}>
        <Button variant="primary" onClick={handleSubmit} disabled={!ready || saving}>
          {saving ? '변경 중…' : '비밀번호 변경'}
        </Button>
      </div>
    </div>
  );
}

export default PasswordChangeCard;
