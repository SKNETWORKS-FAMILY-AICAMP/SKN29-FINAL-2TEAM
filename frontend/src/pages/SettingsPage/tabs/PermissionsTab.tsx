import { Badge, Icon, InfoNote } from '../../../components';
import { useSession } from '../../../utils/session';
import styles from './tabs.module.css';

/**
 * 역할별 권한.
 *
 * **이 표는 서버가 실제로 막는 것과 같아야 한다.** 2026-08-13 이전에는 아니었다 —
 * 「팀장만」이라고 선언한 넷 중 서버가 막던 것은 커넥터 연결 하나뿐이었고 나머지
 * 셋은 API 를 직접 부르면 통과했다. 지금은 `apps/accounts/permissions.py` 의
 * `require_leader` 가 여덟 경로에서 막고, `LeaderOnlyGuardTests` 가 그것을 고정한다.
 *
 * 그래서 여기 줄을 늘릴 때는 **서버 문지기를 먼저 세운다.** 표가 먼저 나가면 지켜지지
 * 않는 약속이 되고, 틀린 권한 표는 없는 표보다 나쁘다.
 */
const PERMISSIONS: { label: string; leader: boolean; member: boolean }[] = [
  { label: '팀원 초대 · 명부 관리', leader: true, member: false },
  { label: 'Connector 연결 · 폴더 지정', leader: true, member: false },
  { label: 'MCP 서버 등록', leader: true, member: false },
  { label: '팀 업무량 기준 변경', leader: true, member: false },
  { label: '에이전트 만들기 · 편집', leader: true, member: true },
  { label: 'Chat에서 에이전트 사용', leader: true, member: true },
];

function Mark({ on }: { on: boolean }) {
  return on ? (
    <Icon name="check" size={16} color="var(--color-success)" />
  ) : (
    <Icon name="x" size={16} color="var(--color-border)" />
  );
}

export function PermissionsTab() {
  const session = useSession();
  const role = session?.account.role;

  return (
    <div className={styles.tab}>
      <section className={styles.card}>
        <div className={styles.cardHead}>
          <h2 className={styles.cardTitle}>
            역할별 권한
            <InfoNote title="역할별 권한">
              <p>역할은 팀장과 팀원 둘뿐이고, 가입 경로로 정해집니다 — 초대 코드로 들어오면 팀원입니다.</p>
              <p>
                <strong>서버가 막습니다.</strong> 화면에서 버튼이 안 보이는 것뿐 아니라, 주소를 직접
                불러도 팀원은 거절됩니다.
              </p>
              <p>
                에이전트를 만든 사람만 고칠 수 있게 할지, 팀 전체가 고칠 수 있게 할지는{' '}
                <strong>아직 정하지 않았습니다.</strong> 정해지면 이 표에 줄이 늘어납니다.
              </p>
            </InfoNote>
          </h2>
        </div>

        <div className={styles.table}>
          <div className={styles.tableHead}>
            <span style={{ flex: 1 }}>권한</span>
            {/* 표가 둘 다 보여 주면 자기 것이 어느 쪽인지 매번 헤아려야 한다. */}
            <span style={{ width: 120 }}>
              팀장 {role === 'leader' && <Badge tone="primary">내 역할</Badge>}
            </span>
            <span style={{ width: 120 }}>
              팀원 {role === 'member' && <Badge tone="primary">내 역할</Badge>}
            </span>
          </div>
          {PERMISSIONS.map((permission) => (
            <div key={permission.label} className={styles.tableRow}>
              <span style={{ flex: 1 }}>{permission.label}</span>
              <span style={{ width: 120 }}>
                <Mark on={permission.leader} />
              </span>
              <span style={{ width: 120 }}>
                <Mark on={permission.member} />
              </span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
