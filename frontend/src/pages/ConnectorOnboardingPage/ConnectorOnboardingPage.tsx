import { useState } from 'react';
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { Badge, Button, Card, Icon, TopNav, useToast } from '../../components';
import styles from './ConnectorOnboardingPage.module.css';

type ConnectorStatus = 'disconnected' | 'connected';

interface ConnectorDef {
  id: string;
  name: string;
  desc: string;
  iconBg: string;
  icon: ReactNode;
  initialStatus: ConnectorStatus;
}

function JiraIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="#0052cc" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M11.53 2.5a.75.75 0 0 1 .94 0l8 6.5A.75.75 0 0 1 20 10.4V21a1 1 0 0 1-1 1h-4a1 1 0 0 1-1-1v-6H10v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V10.4a.75.75 0 0 1 .47-.7l8-6.5" />
    </svg>
  );
}

function DriveIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="#ea4335" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 5.5C4 4.67 4.67 4 5.5 4h13c.83 0 1.5.67 1.5 1.5V7H4V5.5Z" />
      <rect x="4" y="7" width="16" height="12.5" rx="1" />
      <line x1="4" y1="10.5" x2="20" y2="10.5" />
    </svg>
  );
}

const CONNECTORS: ConnectorDef[] = [
  {
    id: 'jira',
    name: 'Jira',
    desc: '프로젝트 보드, 이슈 진행 상황, 그리고 개발 태스크 백로그를 할릴 AI가 직접 읽고 동기화합니다.',
    iconBg: 'rgba(0,82,204,0.07)',
    icon: <JiraIcon />,
    initialStatus: 'disconnected',
  },
  {
    id: 'google-drive',
    name: 'Google Drive',
    desc: '문서 관리 및 공유, 협업 문서를 안전하게 연결해 업무 배정에 활용합니다.',
    iconBg: 'rgba(234,67,53,0.07)',
    icon: <DriveIcon />,
    initialStatus: 'disconnected',
  },
  {
    id: 'people-db',
    name: 'People DB',
    desc: '인력 정보 데이터베이스. 팀원별 스킬, 가용성, 역할 정보를 연동합니다.',
    iconBg: 'rgba(16,185,129,0.07)',
    icon: <Icon name="database" size={24} color="#10b981" />,
    initialStatus: 'connected',
  },
];

export default function ConnectorOnboardingPage() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [statuses, setStatuses] = useState<Record<string, ConnectorStatus>>(() =>
    Object.fromEntries(CONNECTORS.map((c) => [c.id, c.initialStatus])),
  );

  function handleConnectClick(id: string) {
    setStatuses((prev) => ({ ...prev, [id]: 'connected' }));
    showToast('데모 연결 상태입니다. 실제 외부 서비스 인증은 아직 연결되지 않았습니다.', 'info');
  }

  return (
    <div className={styles.page}>
      <TopNav tabs={[]} stepBadge="Step 1 of 2" />

      <div className={styles.wizardArea}>
        <div className={styles.intro}>
          <span className={styles.badge}>PM / 관리자 전용 온보딩</span>
          <h1 className={styles.title}>외부 서비스 연결</h1>
          <p className={styles.subtitle}>업무 배정에 필요한 조직의 외부 서비스를 안전하게 연결해주세요</p>
        </div>

        <div className={styles.cardsRow}>
          {CONNECTORS.map((connector) => {
            const status = statuses[connector.id];
            const connected = status === 'connected';
            return (
              <Card key={connector.id} padding="md" className={styles.connectorCard}>
                <div className={styles.cardTop}>
                  <div className={styles.iconRow}>
                    <div className={styles.connectorIcon} style={{ background: connector.iconBg }}>
                      {connector.icon}
                    </div>
                    <Badge tone={connected ? 'success' : 'neutral'} dot>
                      {connected ? '연결됨' : '미연결'}
                    </Badge>
                  </div>
                  <div>
                    <p className={styles.connectorName}>{connector.name}</p>
                    <p className={styles.connectorDesc}>{connector.desc}</p>
                  </div>
                </div>
                <div className={styles.cardAction}>
                  {connected ? (
                    <Button variant="outline" fullWidth onClick={() => handleConnectClick(connector.id)}>
                      설정 관리
                    </Button>
                  ) : (
                    <Button variant="primary" fullWidth onClick={() => handleConnectClick(connector.id)}>
                      연결하기
                    </Button>
                  )}
                </div>
              </Card>
            );
          })}
        </div>

        <div className={styles.actions}>
          <Button
            variant="primary"
            size="lg"
            className={styles.nextButton}
            onClick={() => navigate('/onboarding/folders?mode=demo')}
          >
            다음 단계로
          </Button>
          <Button variant="link" onClick={() => navigate('/dashboard')}>
            나중에 하기
          </Button>
        </div>
      </div>
    </div>
  );
}
