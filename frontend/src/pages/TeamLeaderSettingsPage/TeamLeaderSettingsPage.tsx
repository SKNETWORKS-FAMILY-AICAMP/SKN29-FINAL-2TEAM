import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Badge, Button, Card, Icon, Input, SettingsLayout, useToast } from '../../components';
import type { BadgeTone, SettingsNavItem } from '../../components';
import { CONNECTOR_DEFS } from '../../data/connectorDefs';
import { loadConnectorStatuses } from '../../utils/connectorStatus';
import type { ConnectorStatus } from '../../utils/connectorStatus';
import styles from './TeamLeaderSettingsPage.module.css';

const NAV_ITEMS: SettingsNavItem[] = [
  { id: 'profile', label: '내 프로필', icon: 'user' },
  { id: 'connectors', label: '연동 관리', icon: 'link' },
  { id: 'team', label: '팀원 관리', icon: 'users' },
  { id: 'workload', label: '팀 업무량 기준', icon: 'sliders' },
];

interface TeamMember {
  id: string;
  name: string;
  email: string;
  statusLabel: string;
  statusTone: BadgeTone;
  invitedAt: string;
}

const TEAM_MEMBERS: TeamMember[] = [];

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

export default function TeamLeaderSettingsPage() {
  const navigate = useNavigate();
  const { showToast } = useToast();

  const [connectorStatuses] = useState<Record<string, ConnectorStatus>>(() =>
    loadConnectorStatuses(Object.fromEntries(CONNECTOR_DEFS.map((c) => [c.id, c.initialStatus]))),
  );
  const [baseHours, setBaseHours] = useState('40');
  const [overloadThreshold, setOverloadThreshold] = useState('110');
  const [defaultHours, setDefaultHours] = useState('8');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');

  function handleSaveProfile() {
    showToast('계정 정보를 저장했습니다.', 'success');
  }

  function handleInviteMember() {
    showToast('팀원 초대 기능은 아직 연결되지 않았습니다.', 'info');
  }

  function handleSaveWorkload() {
    showToast('팀 업무량 기준을 저장했습니다.', 'success');
  }

  return (
    <SettingsLayout
      subtitle="팀 관리자 설정"
      navItems={NAV_ITEMS}
      footerLabel="관리자"
      onFooterClick={() => navigate('/dashboard')}
    >
      <div className={styles.pageHeader}>
        <h1>팀장 설정</h1>
        <p>워크스페이스 연동, 팀원 관리 및 협업 추천 자동화 기준을 관리합니다.</p>
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

      <section id="connectors" className={styles.sectionBlock}>
        <Card padding="lg">
          <div className={styles.sectionHeading}>
            <h2>연동 관리</h2>
            <p>업무 추적 및 파일 협업 도구를 연결하여 실시간 데이터를 동기화합니다.</p>
          </div>
          <div className={styles.connectorGrid}>
            {CONNECTOR_DEFS.map((connector) => {
              const connected = connectorStatuses[connector.id] === 'connected';
              return (
                <div key={connector.id} className={styles.connectorCard}>
                  <div className={styles.connectorIconBox} style={{ background: connector.iconBg }}>
                    {connector.icon}
                  </div>
                  <div className={styles.connectorInfo}>
                    <p className={styles.connectorName}>{connector.name}</p>
                    <Badge tone={connected ? 'success' : 'neutral'} dot>
                      {connected ? '연결됨' : '미연결'}
                    </Badge>
                  </div>
                  <Button variant="outline" size="sm" onClick={() => navigate('/onboarding/connectors')}>
                    {connected ? '업데이트' : '재연동'}
                  </Button>
                </div>
              );
            })}
          </div>
        </Card>
      </section>

      <section id="team" className={styles.sectionBlock}>
        <Card padding="lg">
          <div className={styles.sectionHeadingRow}>
            <div className={styles.sectionHeading}>
              <h2>팀원 관리</h2>
              <p>팀 내부 멤버를 초대하고 활성화 상태를 모니터링합니다.</p>
            </div>
            <Button variant="primary" size="sm" iconLeft={<Icon name="users" size={14} />} onClick={handleInviteMember}>
              팀원 초대하기
            </Button>
          </div>

          <p className={styles.tableCaption}>전체 팀원 ({TEAM_MEMBERS.length}명)</p>

          <div className={styles.teamTable}>
            <div className={styles.teamTableHead}>
              <span>이름</span>
              <span>이메일</span>
              <span>상태</span>
              <span>초대일</span>
              <span>작업</span>
            </div>
            {TEAM_MEMBERS.length === 0 && <p className={styles.emptyNote}>아직 초대된 팀원이 없습니다.</p>}
            {TEAM_MEMBERS.map((member) => (
              <div key={member.id} className={styles.teamTableRow}>
                <span className={styles.memberName}>{member.name}</span>
                <span className={styles.memberEmail}>{member.email}</span>
                <span>
                  <Badge tone={member.statusTone}>{member.statusLabel}</Badge>
                </span>
                <span>{member.invitedAt}</span>
                <span>
                  <button type="button" className={styles.cancelLink}>
                    초대 취소
                  </button>
                </span>
              </div>
            ))}
          </div>
        </Card>
      </section>

      <section id="workload" className={styles.sectionBlock}>
        <Card padding="lg">
          <div className={styles.sectionHeading}>
            <h2>팀 업무량 기준</h2>
            <p>적정 업무량 배정을 유도하는 임계값을 설정합니다.</p>
          </div>

          <div className={styles.workloadRow}>
            <Input
              label="기준 근무시간 (주 단위)"
              type="number"
              value={baseHours}
              onChange={(e) => setBaseHours(e.target.value)}
              rightElement={<span className={styles.unitLabel}>시간/주</span>}
            />
            <Input
              label="과부하 경고 임계값"
              type="number"
              value={overloadThreshold}
              onChange={(e) => setOverloadThreshold(e.target.value)}
              rightElement={<span className={styles.unitLabel}>%</span>}
            />
            <Input
              label="기본 근무시간 (개인 설정 없는 팀원 적용)"
              type="number"
              value={defaultHours}
              onChange={(e) => setDefaultHours(e.target.value)}
              rightElement={<span className={styles.unitLabel}>시간/일</span>}
            />
          </div>

          <p className={styles.helperNote}>
            <Icon name="circle-help" size={14} color="var(--color-placeholder)" />
            팀원별 기준은 개인 설정 탭에서 별도로 지정하면 검증 단계에서 우선 반영됩니다.
          </p>

          <div className={styles.saveRow}>
            <Button variant="primary" onClick={handleSaveWorkload}>
              기준 저장하기
            </Button>
          </div>
        </Card>
      </section>
    </SettingsLayout>
  );
}
