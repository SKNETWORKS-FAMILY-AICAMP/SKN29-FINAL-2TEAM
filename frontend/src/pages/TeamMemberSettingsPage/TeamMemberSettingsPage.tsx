import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Badge,
  Button,
  Card,
  Input,
  AvatarPicker,
  PasswordChangeCard,
  SkillList,
  ToggleSwitch,
  useToast,
} from '../../components';
import { fetchCurrentAccount } from '../../api/auth';
import type { Account } from '../../api/auth';
import { PATHS } from '../../routes';
import { loadSessionToken } from '../../utils/session';
import styles from './TeamMemberSettingsPage.module.css';

interface NotificationSetting {
  id: string;
  label: string;
  desc: string;
}

const NOTIFICATION_SETTINGS: NotificationSetting[] = [
  { id: 'task-assignment', label: '업무 배정 알림', desc: '새로운 태스크나 프로젝트 마일스톤에 담당자로 추가될 때 알림을 보냅니다.' },
  { id: 'schedule-change', label: '일정 변경 알림', desc: '배정된 업무의 시작일, 종료일 또는 요구 공수가 업데이트될 경우 알림을 전송합니다.' },
  { id: 'invite', label: '초대 알림', desc: '새로운 워크스페이스나 채널 워크스페이스에 초대를 수신할 때 메일과 인앱으로 알립니다.' },
  { id: 'system-notice', label: '시스템 공지 알림', desc: '서비스 점검 예정 안내 및 중대한 보안기능 업데이트 공지사항을 수신합니다.' },
];

const DEFAULT_NOTIFICATION_STATE: Record<string, boolean> = {
  'task-assignment': true,
  'schedule-change': true,
  invite: true,
  'system-notice': false,
};

export interface TeamMemberSettingsPageProps {
}

export default function TeamMemberSettingsPage() {
  const navigate = useNavigate();
  const { showToast } = useToast();

  const [token] = useState(loadSessionToken);
  const [account, setAccount] = useState<Account | null>(null);
  const [jiraLinked, setJiraLinked] = useState(false);
  const [notifications, setNotifications] = useState<Record<string, boolean>>(DEFAULT_NOTIFICATION_STATE);

  // 이름·부서·직책과 보유 스킬은 전부 HR에서 온다. 우리가 저장하는 값이 아니다.
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

  function handleToggleJira(checked: boolean) {
    setJiraLinked(checked);
    showToast(checked ? 'Jira 개인 계정을 연동했습니다.' : 'Jira 개인 계정 연동을 해제했습니다.', 'info');
  }

  function handleToggleNotification(id: string, checked: boolean) {
    setNotifications((prev) => ({ ...prev, [id]: checked }));
  }

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
            <h2>보유 스킬</h2>
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

      <section id="linked-accounts" className={styles.sectionBlock}>
        <Card padding="lg">
          <div className={styles.sectionHeading}>
            <h2>계정 연동</h2>
          </div>

          <div className={styles.linkedAccountRow}>
            <div className={styles.linkedAccountInfo}>
              <p className={styles.linkedAccountName}>
                Jira 개인 계정
                <Badge tone={jiraLinked ? 'success' : 'neutral'} dot>
                  {jiraLinked ? '활성화됨' : '미연동'}
                </Badge>
              </p>
              <p className={styles.linkedAccountDesc}>
                {jiraLinked ? '개인 Jira 계정과 동기화되고 있습니다.' : '아직 연동된 Jira 개인 계정이 없습니다.'}
              </p>
            </div>
            <ToggleSwitch checked={jiraLinked} onChange={handleToggleJira} label="연동 상태" />
          </div>
        </Card>
      </section>

      <section id="notifications" className={styles.sectionBlock}>
        <Card padding="lg">
          <div className={styles.sectionHeading}>
            <h2>알림 설정</h2>
          </div>

          <div className={styles.notificationList}>
            {NOTIFICATION_SETTINGS.map((setting) => (
              <div key={setting.id} className={styles.notificationRow}>
                <div className={styles.notificationInfo}>
                  <p className={styles.notificationLabel}>{setting.label}</p>
                  <p className={styles.notificationDesc}>{setting.desc}</p>
                </div>
                <ToggleSwitch
                  checked={notifications[setting.id]}
                  onChange={(checked) => handleToggleNotification(setting.id, checked)}
                />
              </div>
            ))}
          </div>
        </Card>
      </section>
    </>
  );
}
