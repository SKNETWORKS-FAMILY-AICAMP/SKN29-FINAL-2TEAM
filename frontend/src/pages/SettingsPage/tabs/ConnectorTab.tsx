import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Badge, BrandIcon, Button, Icon, InfoNote, useToast } from '../../../components';
import { connectorStatusLabel, connectorStatusTone } from '../../../data/connectorStatus';
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
import { ConnectorPicker } from './ConnectorPicker';
import type { PickerOption } from './ConnectorPicker';
import { josa } from '../../../utils/josa';
import styles from './tabs.module.css';

type OAuthConnectorId = 'google-drive' | 'jira';

/** 서버가 아는 연결 상태. 화면이 따로 기억하지 않는다. */
type Status = 'CONNECTED' | 'EXPIRED' | 'ERROR' | 'REVOKED' | null;

// 라벨·톤은 **운영자 콘솔과 한 표를 쓴다.** 각자 들고 있다가 같은 `EXPIRED` 를
// 여기서는 「만료됨」, 운영자 화면에서는 「확인 필요」로 부르고 있었다(2026-08-13).

/**
 * Connector 탭 — 데이터가 들어오는 길.
 *
 * **온보딩 화면이 없어지면서 연결·설정이 전부 여기로 왔다**(5차 단계 4).
 * 이전에는 상태가 하드코딩된 목록이었고 실제 연결은 온보딩으로 보냈다 —
 * 화면이 「연결됨」이라고 말하는데 서버는 만료돼 있을 수 있었다.
 *
 * OAuth 콜백도 이 탭으로 돌아온다(`?connector=…&status=…`).
 */
/**
 * 자리마다 꽂을 수 있는 것.
 *
 * **안 되는 것도 적어 둔다.** 카드가 하나뿐이면 왜 고르게 하는지 알 수 없고,
 * 「자리」라는 개념도 안 드러난다 — 그걸 문장으로 설명하려다 줄마다 안내문이
 * 길어졌던 것을 걷어낸 자리다(2026-08-12). 다만 **「아직 지원하지 않습니다」를
 * 반드시 붙인다.** 곧 된다고 읽히면 지키지 못할 약속이 된다.
 */
const SLOTS: Record<ConnectorType, { title: string; options: PickerOption[] }> = {
  PEOPLE_DB: {
    title: '인사 시스템: 무엇에서 사람 정보를 가져올까요?',
    options: [
      // 「예시 데이터」·「사내 인사 시스템」은 제품이 아니라 자리를 채우는 방식이라
      // 로고가 없다. Workday 는 제품이지만 `simple-icons` 에 없다(BrandIcon 참고).
      { id: 'mock', label: '예시 데이터', icon: 'database', available: true },
      { id: 'workday', label: 'Workday', icon: 'users', available: false },
      { id: 'inhouse', label: '사내 인사 시스템', icon: 'app-window', available: false },
    ],
  },
  GOOGLE_DRIVE: {
    title: '문서 저장소: 문서가 어디 있나요?',
    options: [
      { id: 'google-drive', label: 'Google Drive', brand: 'google-drive', icon: 'folder', available: true },
      { id: 'notion', label: 'Notion', brand: 'notion', icon: 'file-text', available: false },
      { id: 'confluence', label: 'Confluence', brand: 'confluence', icon: 'file-text', available: false },
      { id: 'sharepoint', label: 'SharePoint', icon: 'folder', available: false },
    ],
  },
  JIRA: {
    title: '업무 기록소: 업무를 어디에 쌓고 있나요?',
    options: [
      { id: 'jira', label: 'Jira', brand: 'jira', icon: 'chart-network', available: true },
      { id: 'asana', label: 'Asana', brand: 'asana', icon: 'circle-help', available: false },
      { id: 'linear', label: 'Linear', brand: 'linear', icon: 'chart-network', available: false },
      { id: 'trello', label: 'Trello', brand: 'trello', icon: 'app-window', available: false },
    ],
  },
};

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
  /** 어느 자리의 피커가 열려 있는가. */
  const [picker, setPicker] = useState<ConnectorType | null>(null);
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
      showToast(`${name}${josa(name, '을/를')} 연결했습니다.`, 'success');
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

  /**
   * 지금 몇 개를 읽고 있는가. **문장이 아니라 뱃지다.**
   *
   * 「문서 폴더 1개를 읽습니다」·「프로젝트 3개를 읽습니다 · 팀 부하 계산용」처럼
   * 적어 두었더니, 실제로 전하는 것은 숫자 하나인데 줄이 문장으로 길어졌다
   * (2026-08-13 PM 지적). 상태 뱃지 옆에 같은 모양으로 붙인다.
   *
   * 확인 중이면 아무것도 안 그린다 — 「확인하는 중…」은 곧 사라질 상태이고,
   * 그 한 줄 때문에 줄 높이가 흔들린다. 0 은 숨기지 않는다. **읽을 것이 없다는
   * 사실이 그 자리에서 제일 중요한 정보**라 오히려 눈에 띄어야 한다.
   */
  function countBadge(count: number | null, label: string) {
    if (count === null) return null;
    return (
      <Badge tone={count === 0 ? 'warning' : 'neutral'}>
        {label} {count}
      </Badge>
    );
  }

  function statusBadge(type: ConnectorType) {
    const value = status[type];
    return (
      <Badge tone={value ? connectorStatusTone(value) : 'neutral'} dot>
        {value ? connectorStatusLabel(value) : '미연결'}
      </Badge>
    );
  }

  const driveConnected = status.GOOGLE_DRIVE === 'CONNECTED';
  const jiraConnected = status.JIRA === 'CONNECTED';
  const peopleConnected = status.PEOPLE_DB === 'CONNECTED';

  return (
    <div className={styles.tab}>
      {session && !isLeader && (
        <p className={`${styles.notice} ${styles.noticeNeutral}`} role="alert">
          <Icon name="info" size={16} color="var(--color-muted)" />
          <span>팀장만 외부 서비스를 연결할 수 있습니다. 팀원은 팀장이 연결한 데이터를 그대로 사용합니다.</span>
        </p>
      )}

      <section className={styles.card}>
        <div className={styles.cardHead}>
          {/* 설명은 ⓘ 안으로 넣는다. 제목은 탭 이름과 같은 말이면 된다. */}
          <h2 className={styles.cardTitle}>
            커넥터
            <InfoNote title="커넥터">
              <p>
                데이터를 가져오는 <strong>자리</strong>입니다. 자리마다 하나씩 연결하고, 여기서 연결한
                것은 에이전트가 <strong>읽는</strong> 대상이 됩니다.
              </p>
              <p>
                <strong>인사 시스템</strong>만 필수입니다. 연결하는 순간 팀이 만들어지고, 근무 기준과
                부재 데이터가 여기서 옵니다. 나머지 둘은 그 자리의 기능이 필요할 때 붙이면 됩니다.
              </p>
              {/* 「만들거나 보내는 연결은 MCP」는 **틀린 문장이었다** — 여기 붙은
                  Jira 가 그 반례다(수집도 하고 이슈도 만든다). 가르는 것은 읽기·쓰기가
                  아니라 인증 주체다(확정 ⑨). 커스텀 도구 탭은 2026-08-18 에 걷었고, 같은
                  말은 이제 이 문단 하나만 한다. */}
              <p>
                <strong>미리 붙여 둔 통로</strong>라 자리만 고르면 됩니다. 직접 만들거나
                운영하는 서버는 <strong>커스텀 도구</strong>로 등록해 드립니다. 가르는 것은 읽기·쓰기가
                아니라 <strong>누구의 서버인가</strong>입니다. 여기 붙은 Jira 도 이슈를 만듭니다.
              </p>
              <p>
                연결 상태는 서버가 아는 값입니다. Jira는 연결하면 접근 가능한 프로젝트를 전부
                가져옵니다. 고르지 않은 프로젝트의 업무가 부하 계산에서 조용히 빠지면, 빠진 줄 모르는
                숫자가 맞는 숫자처럼 보이기 때문입니다.
              </p>
            </InfoNote>
          </h2>
        </div>

        <div className={styles.list}>
          <div className={styles.row}>
            <span className={styles.rowIcon}>
              <Icon name="database" size={20} color="var(--color-primary)" />
            </span>
            <div className={styles.rowBody}>
              {/* 셋의 층위를 맞춘다. 문서 저장소·업무 기록소는 **곳**인데
                  「사람 정보」만 데이터라 혼자 튀었다(2026-08-12 PM 지적).

                  설명 문구는 걷어냈다. 무엇을 꽂을 수 있는지는 「연결하기」가
                  여는 피커가 말한다 — 문장보다 짧고 정확하다. */}
              <span className={styles.rowName}>
                <span>
                  인사 시스템
                  <span className={styles.requiredMark} aria-label="필수">
                    {' *'}
                  </span>
                </span>
                <span className={styles.rowBadges}>{statusBadge('PEOPLE_DB')}</span>
              </span>
              {peopleConnected && <span className={styles.rowVendor}>예시 데이터</span>}
            </div>
            <div className={styles.rowActions}>
              <Button size="sm" variant="outline" disabled={!isLeader} onClick={() => setPicker('PEOPLE_DB')}>
                {peopleConnected ? '바꾸기' : '연결하기'}
              </Button>
            </div>
          </div>

          <div className={styles.row}>
            {/* 꽂혀 있으면 그 제품의 로고를, 비어 있으면 자리를 뜻하는 글리프를
                보여준다. 줄 제목이 자리(문서 저장소)이고 그 아래가 제품이라,
                아이콘도 같은 짝을 따라가야 말이 맞는다. */}
            <span className={styles.rowIcon}>
              {driveConnected ? (
                <BrandIcon name="google-drive" size={20} />
              ) : (
                <Icon name="app-window" size={20} color="var(--color-primary)" />
              )}
            </span>
            <div className={styles.rowBody}>
              <span className={styles.rowName}>
                문서 저장소
                <span className={styles.rowBadges}>
                  {statusBadge('GOOGLE_DRIVE')}
                  {driveConnected && countBadge(folderCount, '폴더')}
                </span>
              </span>
              {driveConnected && <span className={styles.rowVendor}>Google Drive</span>}
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
                onClick={() => setPicker('GOOGLE_DRIVE')}
              >
                {oauthStarting === 'google-drive' ? 'Google로 이동 중…' : driveConnected ? '바꾸기' : '연결하기'}
              </Button>
            </div>
          </div>

          <div className={styles.row}>
            <span className={styles.rowIcon}>
              {jiraConnected ? (
                <BrandIcon name="jira" size={20} />
              ) : (
                <Icon name="chart-network" size={20} color="var(--color-primary)" />
              )}
            </span>
            <div className={styles.rowBody}>
              <span className={styles.rowName}>
                업무 기록소
                <span className={styles.rowBadges}>
                  {statusBadge('JIRA')}
                  {jiraConnected && countBadge(jiraProjectCount, '프로젝트')}
                </span>
              </span>
              {jiraConnected && <span className={styles.rowVendor}>Jira</span>}
            </div>
            <div className={styles.rowActions}>
              <Button
                size="sm"
                variant="outline"
                disabled={!isLeader || oauthStarting !== null}
                onClick={() => setPicker('JIRA')}
              >
                {oauthStarting === 'jira' ? 'Atlassian으로 이동 중…' : jiraConnected ? '바꾸기' : '연결하기'}
              </Button>
            </div>
          </div>
        </div>

      </section>

      {/* 자리를 누르면 무엇을 꽂을지 고른다. 고른 뒤의 흐름(People DB 모달 ·
          OAuth)은 원래 것을 그대로 탄다 — 피커는 앞에 한 겹 얹은 것뿐이다. */}
      <ConnectorPicker
        open={picker !== null}
        onClose={() => setPicker(null)}
        title={picker ? SLOTS[picker].title : ''}
        busy={oauthStarting !== null}
        options={
          picker
            ? SLOTS[picker].options.map((option) => ({
                ...option,
                current: option.available && status[picker] !== null,
              }))
            : []
        }
        onPick={(id) => {
          setPicker(null);
          if (id === 'mock') setPeopleModalOpen(true);
          else if (id === 'google-drive') void startOAuth('google-drive');
          else if (id === 'jira') void startOAuth('jira');
        }}
      />

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
              showToast('인사 시스템을 연결했습니다.', 'success');
              void refresh();
            }}
          />
        </>
      )}
    </div>
  );
}
