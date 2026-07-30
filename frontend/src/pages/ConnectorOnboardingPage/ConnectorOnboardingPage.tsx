import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Badge, Button, Card, TopNav, useToast } from '../../components';
import { ApiError } from '../../api/client';
import { listConnectors } from '../../api/connectors';
import { PeopleDbConnectModal } from './PeopleDbConnectModal';
import { CONNECTOR_DEFS as CONNECTORS } from '../../data/connectorDefs';
import { loadConnectorStatuses, saveConnectorStatuses } from '../../utils/connectorStatus';
import type { ConnectorStatus } from '../../utils/connectorStatus';
import { loadSession } from '../../utils/session';
import styles from './ConnectorOnboardingPage.module.css';

/** People DB만 서버에 실제로 기록된다. 나머지는 목업 흐름이라 세션에 남는다. */
const REAL_CONNECTOR_ID = 'people-db';

function loadStoredStatuses(): Record<string, ConnectorStatus> {
  const defaults = Object.fromEntries(CONNECTORS.map((c) => [c.id, c.initialStatus]));
  return loadConnectorStatuses(defaults);
}

export default function ConnectorOnboardingPage() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [session] = useState(loadSession);
  const [statuses, setStatuses] = useState<Record<string, ConnectorStatus>>(loadStoredStatuses);
  const [peopleDbConnected, setPeopleDbConnected] = useState(false);
  const [peopleDbError, setPeopleDbError] = useState('');
  const [modalOpen, setModalOpen] = useState(false);

  const isLeader = session?.account.role === 'leader';

  const refreshPeopleDb = useCallback(async () => {
    if (!session) return;

    try {
      const connections = await listConnectors(session.token);
      setPeopleDbConnected(
        connections.some((c) => c.connector_type === 'PEOPLE_DB' && c.auth_status === 'CONNECTED'),
      );
    } catch (error) {
      setPeopleDbError(
        error instanceof ApiError ? error.message : 'HR 연결 상태를 불러오지 못했습니다.',
      );
    }
  }, [session]);

  useEffect(() => {
    void refreshPeopleDb();
  }, [refreshPeopleDb]);

  // 데모 커넥터 상태만 세션에 남긴다. People DB는 서버가 원본이다.
  useEffect(() => {
    saveConnectorStatuses(statuses);
  }, [statuses]);

  function handleConnected() {
    setPeopleDbConnected(true);
    setPeopleDbError('');
    showToast('HR 시스템을 연결했습니다.', 'success');
  }

  function handleConnectClick(id: string) {
    if (id === REAL_CONNECTOR_ID) {
      setPeopleDbError('');
      setModalOpen(true);
      return;
    }

    if (id === 'google-drive') {
      showToast('데모 흐름입니다. 데이터 소스 설정을 완료하면 연결된 것으로 표시됩니다.', 'info');
      setTimeout(() => {
        navigate('/onboarding/folders?mode=demo');
      }, 700);
      return;
    }

    if (id === 'jira') {
      showToast('데모 흐름입니다. Jira 프로젝트 선택을 완료하면 연결된 것으로 표시됩니다.', 'info');
      setTimeout(() => {
        navigate('/onboarding/jira-project?mode=demo');
      }, 700);
      return;
    }

    setStatuses((prev) => ({ ...prev, [id]: 'connected' }));
  }

  function handleResetStatuses() {
    const defaults = Object.fromEntries(CONNECTORS.map((c) => [c.id, c.initialStatus]));
    saveConnectorStatuses(defaults);
    setStatuses(defaults);
    showToast('데모 커넥터 상태를 초기화했습니다. HR 연결은 서버에 남아 있습니다.', 'info');
  }

  function statusOf(id: string): ConnectorStatus {
    if (id === REAL_CONNECTOR_ID) return peopleDbConnected ? 'connected' : 'disconnected';
    return statuses[id];
  }

  const allConnected = CONNECTORS.every((c) => statusOf(c.id) === 'connected');
  const canConnect = Boolean(session) && isLeader;

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

        {!session && (
          <p className={styles.notice} role="alert">
            BLOCKED · 로그인해야 외부 서비스를 연결할 수 있습니다.{' '}
            <Link to="/login" className={styles.noticeLink}>
              로그인하기
            </Link>
          </p>
        )}

        {session && !isLeader && (
          <p className={styles.notice} role="alert">
            팀장만 외부 서비스를 연결할 수 있습니다. 팀원은 팀장이 연결한 데이터를 그대로 사용합니다.
          </p>
        )}

        {peopleDbError && (
          <p className={styles.notice} role="alert">
            {peopleDbError}
          </p>
        )}

        <div className={styles.cardsRow}>
          {CONNECTORS.map((connector) => {
            const connected = statusOf(connector.id) === 'connected';
            const isReal = connector.id === REAL_CONNECTOR_ID;
            const locked = !isReal && !peopleDbConnected;
            return (
              <Card key={connector.id} padding="md" className={styles.connectorCard}>
                <div className={styles.cardTop}>
                  <div className={styles.iconRow}>
                    <div className={styles.connectorIcon} style={{ background: connector.iconBg }}>
                      {connector.icon}
                    </div>
                    <div className={styles.badgeRow}>
                      {!isReal && <Badge tone="warning">데모</Badge>}
                      <Badge tone={connected ? 'success' : 'neutral'} dot>
                        {connected ? '연결됨' : '미연결'}
                      </Badge>
                    </div>
                  </div>
                  <div>
                    <p className={styles.connectorName}>{connector.name}</p>
                    <p className={styles.connectorDesc}>{connector.desc}</p>
                  </div>
                </div>
                <div className={styles.cardAction}>
                  {isReal && !canConnect ? (
                    <Button variant="primary" fullWidth disabled title="팀장 계정으로 로그인해야 합니다.">
                      연결하기
                    </Button>
                  ) : connected ? (
                    <Button variant="outline" fullWidth onClick={() => handleConnectClick(connector.id)}>
                      {isReal ? '다시 연결' : '설정 관리'}
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

      {session && (
        <PeopleDbConnectModal
          open={modalOpen}
          token={session.token}
          onClose={() => setModalOpen(false)}
          onConnected={handleConnected}
        />
      )}
    </div>
  );
}
