import { Icon } from '../../../components';
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
          <h2 className={styles.cardTitle}>역할별 권한</h2>
          <p className={styles.cardSub}>
            지금은 팀장/팀원 두 역할만 있습니다. 에이전트 소유·가시성은 멘토링에서 범위를 확정한 뒤 채웁니다.
          </p>
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

        <p className={`${styles.notice} ${styles.noticeWarning}`}>
          <Icon name="triangle-alert" size={15} color="var(--color-warning-text)" />
          <span>
            에이전트를 만든 사람만 수정할 수 있게 할지, 팀 전체가 편집할 수 있게 할지는 아직 정하지 않았습니다
            (1_서비스구조_IA §4-3). 확정 후 이 표에 행이 늘어납니다.
          </span>
        </p>
      </section>
    </div>
  );
}
