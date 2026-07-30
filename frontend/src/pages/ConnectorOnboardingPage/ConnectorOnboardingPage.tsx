import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Badge, Button, Card, TopNav, useToast } from '../../components';
import { ApiError } from '../../api/client';
import { beginGoogleDriveAuthorization, beginJiraAuthorization, listConnectors } from '../../api/connectors';
import { PeopleDbConnectModal } from './PeopleDbConnectModal';
import { CONNECTOR_DEFS as CONNECTORS } from '../../data/connectorDefs';
import type { ConnectorStatus } from '../../utils/connectorStatus';
import { loadSession } from '../../utils/session';
import styles from './ConnectorOnboardingPage.module.css';

/** 모든 커넥터 연결 상태는 서버가 원본이다. */
const REAL_CONNECTOR_IDS = new Set(['people-db', 'google-drive', 'jira']);
type OAuthConnectorId = 'google-drive' | 'jira';

export default function ConnectorOnboardingPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { showToast } = useToast();
  const [session] = useState(loadSession);
  const [peopleDbConnected, setPeopleDbConnected] = useState(false);
  const [googleDriveConnected, setGoogleDriveConnected] = useState(false);
  const [jiraConnected, setJiraConnected] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [oauthStarting, setOauthStarting] = useState<OAuthConnectorId | null>(null);
  const handledOAuthCallback = useRef<string | null>(null);

  const isLeader = session?.account.role === 'leader';

  const refreshPeopleDb = useCallback(async () => {
    if (!session) return;

    try {
      const connections = await listConnectors(session.token);
      setPeopleDbConnected(connections.some((c) => c.connector_type === 'PEOPLE_DB' && c.auth_status === 'CONNECTED'));
      setGoogleDriveConnected(connections.some((c) => c.connector_type === 'GOOGLE_DRIVE' && c.auth_status === 'CONNECTED'));
      setJiraConnected(connections.some((c) => c.connector_type === 'JIRA' && c.auth_status === 'CONNECTED'));
    } catch (error) {
      showToast(error instanceof ApiError ? error.message : '연결 상태를 불러오지 못했습니다.', 'error');
    }
  }, [session, showToast]);

  useEffect(() => {
    void refreshPeopleDb();
  }, [refreshPeopleDb]);

  useEffect(() => {
    const query = new URLSearchParams(location.search);
    const connector = query.get('connector');
    if (connector !== 'google-drive' && connector !== 'jira') {
      handledOAuthCallback.current = null;
      return;
    }
    // React StrictMode는 개발 중 effect를 한 번 더 실행한다. 같은 OAuth 결과는
    // 토스트·상태 갱신을 한 번만 처리하고, URL이 비워진 뒤 다음 연결은 허용한다.
    if (handledOAuthCallback.current === location.search) return;
    handledOAuthCallback.current = location.search;

    if (query.get('status') === 'ok') {
      showToast(connector === 'jira' ? 'Jira를 연결했습니다.' : 'Google Drive를 연결했습니다.', 'success');
      void refreshPeopleDb();
    } else if (query.get('status') === 'error') {
      showToast(connector === 'jira' ? 'Jira 연결에 실패했습니다. 잠시 후 다시 시도해주세요.' : 'Google Drive 연결에 실패했습니다. 잠시 후 다시 시도해주세요.', 'error');
    }
    navigate('/onboarding/connectors', { replace: true });
  }, [location.search, navigate, refreshPeopleDb, showToast]);

  function handleConnected() {
    setPeopleDbConnected(true);
    showToast('HR 시스템을 연결했습니다.', 'success');
  }

  async function handleConnectClick(id: string) {
    if (id === 'people-db') {
      setModalOpen(true);
      return;
    }

    if (id === 'google-drive' || id === 'jira') {
      if (!session) return;
      const oauthConnector = id as OAuthConnectorId;
      setOauthStarting(oauthConnector);
      try {
        const { authorization_url } = oauthConnector === 'jira'
          ? await beginJiraAuthorization(session.token)
          : await beginGoogleDriveAuthorization(session.token);
        window.location.assign(authorization_url);
      } catch (error) {
        showToast(
          error instanceof ApiError
            ? error.message
            : oauthConnector === 'jira' ? 'Jira 연결을 시작하지 못했습니다.' : 'Google Drive 연결을 시작하지 못했습니다.',
          'error',
        );
        setOauthStarting(null);
      }
      return;
    }
  }

  function statusOf(id: string): ConnectorStatus {
    if (id === 'people-db') return peopleDbConnected ? 'connected' : 'disconnected';
    if (id === 'google-drive') return googleDriveConnected ? 'connected' : 'disconnected';
    if (id === 'jira') return jiraConnected ? 'connected' : 'disconnected';
    return 'disconnected';
  }

  const allConnected = CONNECTORS.every((c) => statusOf(c.id) === 'connected');
  const canConnect = Boolean(session) && isLeader;

  return (
    <div className={styles.page}>
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

        <div className={styles.cardsRow}>
          {CONNECTORS.map((connector) => {
            const connected = statusOf(connector.id) === 'connected';
            const isReal = REAL_CONNECTOR_IDS.has(connector.id);
            const isOAuthConnector = connector.id === 'google-drive' || connector.id === 'jira';
            const locked = connector.id !== 'people-db' && !peopleDbConnected;
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
                    <Button variant="outline" fullWidth disabled={isOAuthConnector && oauthStarting !== null} onClick={() => void handleConnectClick(connector.id)}>
                      {isReal ? '다시 연결' : '설정 관리'}
                    </Button>
                  ) : locked ? (
                    <Button variant="primary" fullWidth disabled title="People DB를 먼저 연결해주세요.">
                      연결하기
                    </Button>
                  ) : (
                    <Button variant="primary" fullWidth disabled={isOAuthConnector && oauthStarting !== null} onClick={() => void handleConnectClick(connector.id)}>
                      {oauthStarting === 'google-drive' ? 'Google로 이동 중…' : oauthStarting === 'jira' ? 'Atlassian으로 이동 중…' : '연결하기'}
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
