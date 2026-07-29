import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Badge, Button, Card, Icon, Input, SettingsLayout, ToggleSwitch, useToast } from '../../components';
import type { SettingsNavItem } from '../../components';
import styles from './TeamMemberSettingsPage.module.css';

const NAV_ITEMS: SettingsNavItem[] = [
  { id: 'profile', label: '내 프로필', icon: 'user' },
  { id: 'linked-accounts', label: '계정 연동', icon: 'link' },
  { id: 'notifications', label: '알림 설정', icon: 'bell' },
];

interface HrField {
  label: string;
  value: string;
}

const HR_FIELDS: HrField[] = [
  { label: '이름', value: '-' },
  { label: '부서', value: '-' },
  { label: '직급', value: '-' },
  { label: '입사일', value: '-' },
];

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

export default function TeamMemberSettingsPage() {
  const navigate = useNavigate();
  const { showToast } = useToast();

  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [jiraLinked, setJiraLinked] = useState(false);
  const [notifications, setNotifications] = useState<Record<string, boolean>>(DEFAULT_NOTIFICATION_STATE);

  function handleSaveProfile() {
    showToast('계정 정보를 저장했습니다.', 'success');
  }

  function handleToggleJira(checked: boolean) {
    setJiraLinked(checked);
    showToast(checked ? 'Jira 개인 계정을 연동했습니다.' : 'Jira 개인 계정 연동을 해제했습니다.', 'info');
  }

  function handleToggleNotification(id: string, checked: boolean) {
    setNotifications((prev) => ({ ...prev, [id]: checked }));
  }

  return (
    <SettingsLayout
      subtitle="팀원 전용 설정 페이지"
      navItems={NAV_ITEMS}
      footerLabel="팀원"
      onFooterClick={() => navigate('/dashboard')}
    >
      <div className={styles.pageHeader}>
        <h1>팀원 설정</h1>
        <p>내 소속 정보 관리 및 연동 계정 제어와 개별 알림 설정을 지정할 수 있습니다.</p>
      </div>

      <section id="profile" className={styles.sectionBlock}>
        <Card padding="lg">
          <div className={styles.sectionHeading}>
            <h2>내 프로필</h2>
            <p>회사 인사 시스템 연동 정보 및 관리용 계정 정보를 파악합니다.</p>
          </div>

          <div className={styles.hrBox}>
            <div className={styles.hrBoxHeader}>
              <Icon name="lock" size={14} color="var(--color-placeholder)" />
              <span>HR 연동 정보 (읽기 전용)</span>
            </div>
            <div className={styles.hrFieldGrid}>
              {HR_FIELDS.map((field) => (
                <div key={field.label} className={styles.hrField}>
                  <span className={styles.hrFieldLabel}>{field.label}</span>
                  <span className={styles.hrFieldValue}>{field.value}</span>
                </div>
              ))}
            </div>
          </div>

          <p className={styles.subheading}>계정 정보 (수정 가능)</p>
          <div className={styles.accountRow}>
            <Input label="이메일" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            <Input label="전화번호" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />
          </div>

          <div className={styles.saveRow}>
            <Button variant="primary" onClick={handleSaveProfile}>
              개인 정보 수정
            </Button>
          </div>
        </Card>
      </section>

      <section id="linked-accounts" className={styles.sectionBlock}>
        <Card padding="lg">
          <div className={styles.sectionHeading}>
            <h2>계정 연동</h2>
            <p>업무 추적 도구와의 싱크 상태를 확인하고 연결을 설정합니다.</p>
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
            <p>워크스페이스 업무 배정 및 공지 알림 수신 채널을 맞춤설정합니다.</p>
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
    </SettingsLayout>
  );
}
