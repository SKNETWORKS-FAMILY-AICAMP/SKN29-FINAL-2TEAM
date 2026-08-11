import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Badge, Button, Icon, useToast } from '../../../components';
import type { BadgeTone } from '../../../components';
import { ApiError } from '../../../api/client';
import {
  beginGoogleDriveAuthorization,
  beginJiraAuthorization,
  listConnectors,
} from '../../../api/connectors';
import type { ConnectorType } from '../../../api/connectors';
import { listRegisteredJiraProjects, listTeamFolders } from '../../../api/projects';
import { PATHS } from '../../../routes';
import { useSession } from '../../../utils/session';
import { DriveFolderModal } from '../DriveFolderModal/DriveFolderModal';
import { PeopleDbConnectModal } from '../PeopleDbConnectModal';
import styles from './tabs.module.css';

type OAuthConnectorId = 'google-drive' | 'jira';

/** 서버가 아는 연결 상태. 화면이 따로 기억하지 않는다. */
type Status = 'CONNECTED' | 'EXPIRED' | 'ERROR' | null;

const TONE: Record<string, BadgeTone> = {
  CONNECTED: 'success',
  EXPIRED: 'warning',
  ERROR: 'danger',
};

const LABEL: Record<string, string> = {
  CONNECTED: '연결됨',
  EXPIRED: '만료됨',
  ERROR: '오류',
};

/**
 * Connector 탭 — 데이터가 들어오는 길.
 *
 * **온보딩 화면이 없어지면서 연결·설정이 전부 여기로 왔다**(5차 단계 4).
 * 이전에는 상태가 하드코딩된 목록이었고 실제 연결은 온보딩으로 보냈다 —
 * 화면이 「연결됨」이라고 말하는데 서버는 만료돼 있을 수 있었다.
 *
 * OAuth 콜백도 이 탭으로 돌아온다(`?connector=…&status=…`).
 */
export function ConnectorTab() {
  const navigate = useNavigate();
  const location = useLocation();
  const session = useSession();
  const { showToast } = useToast();

  const [status, setStatus] = useState<Record<ConnectorType, Status>>({
    PEOPLE_DB: null,
    GOOGLE_DRIVE: null,
    JIRA: null,
  });
  const [folderCount, setFolderCount] = useState<number | null>(null);
  const [jiraProjectCount, setJiraProjectCount] = useState<number | null>(null);
  const [oauthStarting, setOauthStarting] = useState<OAuthConnectorId | null>(null);
  const [driveModalOpen, setDriveModalOpen] = useState(false);
  const [peopleModalOpen, setPeopleModalOpen] = useState(false);
  const handledCallback = useRef<string | null>(null);

  const token = session?.token;
  const isLeader = session?.account.role === 'leader';

  const refresh = useCallback(async () => {
    if (!token) return;
    try {
      const connections = await listConnectors(token);
      const next: Record<ConnectorType, Status> = { PEOPLE_DB: null, GOOGLE_DRIVE: null, JIRA: null };
      for (const connection of connections) next[connection.connector_type] = connection.auth_status;
      setStatus(next);

      // 무엇을 읽고 있는지는 연결 여부와 다른 질문이다. 연결만 보여주면
      // 「연결됨」인데 읽는 것이 하나도 없는 상태를 알 수 없다.
      if (next.GOOGLE_DRIVE === 'CONNECTED') {
        setFolderCount((await listTeamFolders(token)).length);
      }
      if (next.JIRA === 'CONNECTED') {
        setJiraProjectCount((await listRegisteredJiraProjects(token)).length);
      }
    } catch (error) {
      showToast(error instanceof ApiError ? error.message : '연결 상태를 불러오지 못했습니다.', 'error');
    }
  }, [token, showToast]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // OAuth 콜백이 여기로 돌아온다. StrictMode가 effect를 한 번 더 돌리므로 같은
  // 결과를 두 번 알리지 않는다.
  useEffect(() => {
    const query = new URLSearchParams(location.search);
    const connector = query.get('connector');
    if (connector !== 'google-drive' && connector !== 'jira') {
      handledCallback.current = null;
      return;
    }
    if (handledCallback.current === location.search) return;
    handledCallback.current = location.search;

    const name = connector === 'jira' ? 'Jira' : 'Google Drive';
    if (query.get('status') === 'ok') {
      showToast(`${name}를 연결했습니다.`, 'success');
      void refresh();
    } else if (query.get('status') === 'error') {
      showToast(`${name} 연결에 실패했습니다. 잠시 후 다시 시도해주세요.`, 'error');
    }
    navigate(PATHS.settingsConnectors, { replace: true });
  }, [location.search, navigate, refresh, showToast]);

  async function startOAuth(id: OAuthConnectorId) {
    if (!token) return;
    setOauthStarting(id);
    try {
      const { authorization_url } =
        id === 'jira' ? await beginJiraAuthorization(token) : await beginGoogleDriveAuthorization(token);
      window.location.assign(authorization_url);
    } catch (error) {
      showToast(
        error instanceof ApiError ? error.message : `${id === 'jira' ? 'Jira' : 'Google Drive'} 연결을 시작하지 못했습니다.`,
        'error',
      );
      setOauthStarting(null);
    }
  }

  function statusBadge(type: ConnectorType) {
    const value = status[type];
    return (
      <Badge tone={value ? TONE[value] : 'neutral'} dot>
        {value ? LABEL[value] : '미연결'}
      </Badge>
    );
  }

  const driveConnected = status.GOOGLE_DRIVE === 'CONNECTED';
  const jiraConnected = status.JIRA === 'CONNECTED';
  const peopleConnected = status.PEOPLE_DB === 'CONNECTED';

  return (
    <div className={styles.tab}>
      <p className={`${styles.notice} ${styles.noticeNeutral}`}>
        <Icon name="info" size={16} color="var(--color-muted)" />
        <span>
          데이터가 들어오는 길입니다. 여기서 연결한 것은 에이전트가 “읽는” 대상이 됩니다. 에이전트가 무언가를 만들거나
          보내는 연결은 MCP 탭에 있습니다.
        </span>
      </p>

      {session && !isLeader && (
        <p className={`${styles.notice} ${styles.noticeNeutral}`} role="alert">
          <Icon name="info" size={16} color="var(--color-muted)" />
          <span>팀장만 외부 서비스를 연결할 수 있습니다. 팀원은 팀장이 연결한 데이터를 그대로 사용합니다.</span>
        </p>
      )}

      <section className={styles.card}>
        <div className={styles.cardHead}>
          <h2 className={styles.cardTitle}>연결된 서비스</h2>
          <p className={styles.cardSub}>연결 상태는 서버가 아는 값입니다 — 만료되면 여기서 다시 연결하세요.</p>
        </div>

        <div className={styles.list}>
          <div className={styles.row}>
            <span className={styles.rowIcon}>
              <Icon name="database" size={20} color="var(--color-primary)" />
            </span>
            <div className={styles.rowBody}>
              <span className={styles.rowName}>
                People DB
                {statusBadge('PEOPLE_DB')}
              </span>
              <span className={styles.rowDesc}>
                근무 기준·부재 데이터 — 없으면 부하 판정을 보류합니다. 팀도 여기서 만듭니다.
              </span>
            </div>
            <div className={styles.rowActions}>
              <Button size="sm" variant="outline" disabled={!isLeader} onClick={() => setPeopleModalOpen(true)}>
                {peopleConnected ? '다시 연결' : '연결하기'}
              </Button>
            </div>
          </div>

          <div className={styles.row}>
            <span className={styles.rowIcon}>
              <Icon name="app-window" size={20} color="var(--color-primary)" />
            </span>
            <div className={styles.rowBody}>
              <span className={styles.rowName}>
                Google Drive
                {statusBadge('GOOGLE_DRIVE')}
              </span>
              <span className={styles.rowDesc}>
                {driveConnected
                  ? folderCount === null
                    ? '읽는 폴더를 확인하는 중…'
                    : folderCount === 0
                      ? '읽는 폴더가 아직 없습니다 — 폴더를 지정해야 문서가 들어옵니다'
                      : `문서 폴더 ${folderCount}개를 읽습니다`
                  : '문서가 있는 폴더를 읽습니다'}
              </span>
            </div>
            <div className={styles.rowActions}>
              {driveConnected && (
                <Button size="sm" variant="outline" onClick={() => setDriveModalOpen(true)}>
                  폴더 설정
                </Button>
              )}
              <Button
                size="sm"
                variant={driveConnected ? 'ghost' : 'outline'}
                disabled={!isLeader || oauthStarting !== null}
                onClick={() => void startOAuth('google-drive')}
              >
                {oauthStarting === 'google-drive' ? 'Google로 이동 중…' : driveConnected ? '다시 연결' : '연결하기'}
              </Button>
            </div>
          </div>

          <div className={styles.row}>
            <span className={styles.rowIcon}>
              <Icon name="chart-network" size={20} color="var(--color-primary)" />
            </span>
            <div className={styles.rowBody}>
              <span className={styles.rowName}>
                Jira
                {statusBadge('JIRA')}
              </span>
              <span className={styles.rowDesc}>
                {jiraConnected && jiraProjectCount !== null
                  ? `프로젝트 ${jiraProjectCount}개를 읽습니다 · 팀 부하 계산용`
                  : '접근 가능한 전체 프로젝트 · 팀 부하 읽기용'}
              </span>
            </div>
            <div className={styles.rowActions}>
              <Button
                size="sm"
                variant="outline"
                disabled={!isLeader || oauthStarting !== null}
                onClick={() => void startOAuth('jira')}
              >
                {oauthStarting === 'jira' ? 'Atlassian으로 이동 중…' : jiraConnected ? '다시 연결' : '연결하기'}
              </Button>
            </div>
          </div>
        </div>

        <p className={`${styles.notice} ${styles.noticeInfo}`}>
          <Icon name="info" size={15} color="var(--color-info)" />
          <span>
            Jira는 연결하면 접근 가능한 프로젝트를 전부 가져옵니다 — 고르는 단계를 없앴습니다. 고르지 않은 프로젝트의
            업무는 부하 계산에서 조용히 빠지는데, 빠진 줄 모르는 숫자가 맞는 숫자처럼 보이기 때문입니다.
          </span>
        </p>

        <p className={styles.cardSub}>파일 내용은 에이전트가 사용할 때 읽습니다.</p>
      </section>

      {token && (
        <>
          <DriveFolderModal
            open={driveModalOpen}
            token={token}
            onClose={() => setDriveModalOpen(false)}
            onSaved={() => void refresh()}
          />
          <PeopleDbConnectModal
            open={peopleModalOpen}
            token={token}
            onClose={() => setPeopleModalOpen(false)}
            onConnected={() => {
              showToast('HR 시스템을 연결했습니다.', 'success');
              void refresh();
            }}
          />
        </>
      )}
    </div>
  );
}
