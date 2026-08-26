import { useCallback, useEffect, useState } from 'react';
import {
  Button,
  Card,
  Input,
  AvatarPicker,
  PasswordChangeCard,
  SkillList,
  useToast,
} from '../../components';
import { fetchCurrentAccount } from '../../api/auth';
import type { Account } from '../../api/auth';
import { loadSessionToken } from '../../utils/session';
import styles from './TeamMemberSettingsPage.module.css';

export default function TeamMemberSettingsPage() {
  const { showToast } = useToast();

  const [token] = useState(loadSessionToken);
  const [account, setAccount] = useState<Account | null>(null);

  // 이름·부서·직책과 기술 스택은 전부 HR에서 온다. 우리가 저장하는 값이 아니다.
  const reloadAccount = useCallback(async () => {
    if (!token) return;
    try {
      setAccount(await fetchCurrentAccount(token));
    } catch {
      // 프로필을 못 읽어도 나머지 구획은 보여준다.
    }
  }, [token]);

  useEffect(() => {
    void reloadAccount();
  }, [reloadAccount]);

  return (
    <>

      <section id="profile" className={styles.sectionBlock}>
        <Card padding="lg">
          <div className={styles.sectionHeading}>
            <h2>내 프로필</h2>
          </div>

          <div className={styles.identityRow}>
            <AvatarPicker
              token={token}
              name={account?.person?.name ?? account?.display_name ?? ''}
              hasAvatar={account?.has_avatar ?? false}
              onChanged={() => void reloadAccount()}
              onError={(message) => showToast(message, 'error')}
            />
            <div className={styles.identityText}>
              <span className={styles.identityName}>
                {account?.person?.name ?? account?.display_name ?? '-'}
              </span>
              <span className={styles.identityMeta}>
                {[account?.person?.org_name, account?.person?.job_role].filter(Boolean).join(' · ') || '-'}
              </span>
            </div>
          </div>

          <p className={styles.subheading}>계정 정보</p>
          <div className={styles.accountRow}>
            <Input label="이메일" type="email" value={account?.email ?? ''} readOnly disabled />
            <Input label="표시 이름" value={account?.display_name ?? ''} readOnly disabled />
          </div>
        </Card>
      </section>

      <section id="skills" className={styles.sectionBlock}>
        <Card padding="lg">
          <div className={styles.sectionHeading}>
            <h2>기술 스택</h2>
          </div>
          <SkillList skills={account?.skills ?? []} />
        </Card>
      </section>

      <section id="password" className={styles.sectionBlock}>
        <Card padding="lg">
          <div className={styles.sectionHeading}>
            <h2>비밀번호 변경</h2>
          </div>
          <PasswordChangeCard
            token={token}
            onDone={(message) => showToast(message, 'success')}
            onError={(message) => showToast(message, 'error')}
          />
        </Card>
      </section>

      {/* "Jira 개인 계정" 연동 섹션은 걷어냈다(2026-08-19) — API 호출이
          전혀 없는 로컬 상태뿐이라 탭을 나갔다 오면 항상 미연동으로
          리셋됐다(버그 리포트). 실제 Jira 연동은 팀장 전용으로 이미
          설정 > 커넥터(`ConnectorTab.tsx`)에 있고, 화면도 "팀원은 팀장이
          연결한 데이터를 그대로 사용합니다"라고 안내한다 — 팀원이 개인
          계정을 따로 연동할 이유가 없어 되살리지 않고 지운다. */}

      {/* "알림 설정" 섹션도 같은 이유로 걷어냈다(2026-08-25) — 토글 넷이
          `useState` 뿐이라 탭을 나갔다 오면 항상 기본값으로 돌아갔다. 알림
          기능 자체를 만들지 않기로 해서(PM), 저장할 곳이 생길 일도 없다.
          켜지지 않는 스위치는 없느니만 못하다. */}

    </>
  );
}
