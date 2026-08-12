import { Icon, InfoNote } from '../../../components';
import styles from './tabs.module.css';

/** 역할별 권한. 에이전트 소유·가시성은 멘토링 후 확정이라 아직 행이 없다. */
const PERMISSIONS: { label: string; leader: boolean; member: boolean }[] = [
  { label: '팀원 초대 · 명부 관리', leader: true, member: false },
  { label: 'Connector 연결 · 폴더 지정', leader: true, member: false },
  { label: 'MCP 서버 등록', leader: true, member: false },
  { label: '에이전트 만들기 · 편집', leader: true, member: true },
  { label: 'Chat에서 에이전트 사용', leader: true, member: true },
  { label: '팀 업무량 기준 변경', leader: true, member: false },
];

function Mark({ on }: { on: boolean }) {
  return on ? (
    <Icon name="check" size={16} color="var(--color-success)" />
  ) : (
    <Icon name="x" size={16} color="var(--color-border)" />
  );
}

export function PermissionsTab() {
  return (
    <div className={styles.tab}>
      <section className={styles.card}>
        <div className={styles.cardHead}>
          <h2 className={styles.cardTitle}>
            역할별 권한
            <InfoNote title="역할별 권한">
              <p>역할은 팀장과 팀원 둘뿐입니다. 지금은 화면에서 바꿀 수 없는 고정 값입니다.</p>
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
            <span style={{ width: 120 }}>팀장</span>
            <span style={{ width: 120 }}>팀원</span>
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
