import { useNavigate } from 'react-router-dom';
import { Badge, Button, Icon } from '../../../components';
import type { BadgeTone, IconName } from '../../../components';
import { PATHS } from '../../../routes';
import styles from './tabs.module.css';

interface ConnectorRow {
  icon: IconName;
  name: string;
  tone: BadgeTone;
  status: string;
  desc: string;
  actions: { label: string; to: string; primary?: boolean }[];
}

/**
 * Connector 탭 — 데이터가 들어오는 길. 온보딩에서 쓰는 화면과 같은 대상을
 * 다루지만, 여기서는 목록·상태 중심으로 보여주고 실제 연결·폴더 지정은 기존
 * 온보딩 화면으로 보낸다(한 기능 두 진입점).
 *
 * Jira 프로젝트 선택은 8/11 확정으로 온보딩 필수 스텝에서 빠져 이 탭으로 왔다.
 */
const CONNECTORS: ConnectorRow[] = [
  {
    icon: 'app-window',
    name: 'Google Drive',
    tone: 'success',
    status: '연결됨',
    desc: '문서 3개 폴더 · 파일 128건 등록 · 12건 준비됨',
    actions: [
      { label: '폴더 설정', to: PATHS.onboardingFolders, primary: true },
      { label: '다시 연결', to: PATHS.onboardingConnectors },
    ],
  },
  {
    icon: 'chart-network',
    name: 'Jira',
    tone: 'success',
    status: '연결됨',
    desc: '접근 가능한 전체 프로젝트 · 팀 부하 읽기용',
    actions: [{ label: '다시 연결', to: PATHS.onboardingConnectors, primary: true }],
  },
  {
    icon: 'database',
    name: 'People DB',
    tone: 'neutral',
    status: '미연결',
    desc: '근무 기준·부재 데이터 — 없으면 부하 판정을 보류합니다',
    actions: [{ label: '연결하기', to: PATHS.onboardingConnectors, primary: true }],
  },
];

export function ConnectorTab() {
  const navigate = useNavigate();

  return (
    <div className={styles.tab}>
      <p className={`${styles.notice} ${styles.noticeNeutral}`}>
        <Icon name="info" size={16} color="var(--color-muted)" />
        <span>
          데이터가 들어오는 길입니다. 여기서 연결한 것은 에이전트가 “읽는” 대상이 됩니다. 에이전트가 무언가를 만들거나
          보내는 연결은 MCP 탭에 있습니다.
        </span>
      </p>

      <section className={styles.card}>
        <div className={styles.cardHead}>
          <h2 className={styles.cardTitle}>연결된 서비스</h2>
          <p className={styles.cardSub}>
            온보딩에서 연결한 것과 같은 대상입니다 — 여기서도 다시 연결하거나 범위를 바꿀 수 있습니다.
          </p>
        </div>

        <div className={styles.list}>
          {CONNECTORS.map((connector) => (
            <div key={connector.name} className={styles.row}>
              <span className={styles.rowIcon}>
                <Icon name={connector.icon} size={20} color="var(--color-primary)" />
              </span>
              <div className={styles.rowBody}>
                <span className={styles.rowName}>
                  {connector.name}
                  <Badge tone={connector.tone}>{connector.status}</Badge>
                </span>
                <span className={styles.rowDesc}>{connector.desc}</span>
              </div>
              <div className={styles.rowActions}>
                {connector.actions.map((action) => (
                  <Button
                    key={action.label}
                    size="sm"
                    variant={action.primary ? 'outline' : 'ghost'}
                    onClick={() => navigate(action.to)}
                  >
                    {action.label}
                  </Button>
                ))}
              </div>
            </div>
          ))}
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
    </div>
  );
}
