import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Badge, Button, Card, TopNav, useToast } from '../../components';
import { CONNECTOR_DEFS as CONNECTORS } from '../../data/connectorDefs';
import { loadConnectorStatuses, saveConnectorStatuses } from '../../utils/connectorStatus';
import type { ConnectorStatus } from '../../utils/connectorStatus';
import styles from './ConnectorOnboardingPage.module.css';

function loadStoredStatuses(): Record<string, ConnectorStatus> {
  const defaults = Object.fromEntries(CONNECTORS.map((c) => [c.id, c.initialStatus]));
  return loadConnectorStatuses(defaults);
}

export default function ConnectorOnboardingPage() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [statuses, setStatuses] = useState<Record<string, ConnectorStatus>>(loadStoredStatuses);
  const allConnected = CONNECTORS.every((c) => statuses[c.id] === 'connected');

  useEffect(() => {
    saveConnectorStatuses(statuses);
  }, [statuses]);

  function handleConnectClick(id: string) {
    if (id === 'google-drive') {
      showToast('데이터 소스 설정을 완료하면 연결됩니다.', 'info');
      setTimeout(() => {
        navigate('/onboarding/folders?mode=demo');
      }, 700);
      return;
    }

    if (id === 'jira') {
      showToast('Jira 프로젝트 선택을 완료하면 연결됩니다.', 'info');
      setTimeout(() => {
        navigate('/onboarding/jira-project?mode=demo');
      }, 700);
      return;
    }

    setStatuses((prev) => ({ ...prev, [id]: 'connected' }));
    showToast('데모 연결 상태입니다. 실제 외부 서비스 인증은 아직 연결되지 않았습니다.', 'info');
  }

  function handleResetStatuses() {
    const defaults = Object.fromEntries(CONNECTORS.map((c) => [c.id, c.initialStatus]));
    saveConnectorStatuses(defaults);
    setStatuses(defaults);
    showToast('커넥터 연결 상태를 초기화했습니다.', 'info');
  }

  return (
    <div className={styles.page}>
      {import.meta.env.DEV && (
        <button type="button" className={styles.devResetButton} onClick={handleResetStatuses}>
          연결 상태 초기화 (dev)
        </button>
      )}

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
            const peopleDbConnected = statuses['people-db'] === 'connected';
            const locked = connector.id !== 'people-db' && !peopleDbConnected;
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
                  ) : locked ? (
                    <Button variant="primary" fullWidth disabled title="People DB를 먼저 연결해주세요.">
                      연결하기
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
            disabled={!allConnected}
            title={allConnected ? undefined : '모든 커넥터를 연결해주세요.'}
            onClick={() => navigate('/dashboard')}
          >
            {allConnected ? '커넥터 설정 완료' : '다음 단계로'}
          </Button>
          <Button variant="link" onClick={() => navigate('/dashboard')}>
            나중에 하기
          </Button>
        </div>
      </div>
    </div>
  );
}
