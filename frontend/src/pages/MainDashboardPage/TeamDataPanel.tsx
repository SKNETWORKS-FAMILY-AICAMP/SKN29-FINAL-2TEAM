import { Link } from 'react-router-dom';
import type { ConnectorConnection } from '../../api/connectors';
import type { DocRole, ProjectDocument, ProjectSource } from '../../api/projects';
import styles from './TeamDashboard.module.css';

const CONNECTOR_LABEL: Record<string, string> = {
  PEOPLE_DB: '인사 정보',
  GOOGLE_DRIVE: 'Google Drive',
  JIRA: 'Jira',
};

const ROLE_LABEL: Record<DocRole, string> = {
  PLAN: '기획서',
  MEETING_NOTE: '회의록',
  DAILY_REPORT: '일일보고서',
  OTHER: '기타',
};

const STATUS_LABEL: Record<string, string> = {
  CONNECTED: '연결됨',
  EXPIRED: '재연결 필요',
  ERROR: '오류',
};

function statusDot(status: string): string {
  if (status === 'CONNECTED') return styles.dotOk;
  if (status === 'EXPIRED' || status === 'ERROR') return styles.dotBad;
  return styles.dotIdle;
}

interface Props {
  connectors: ConnectorConnection[];
  sources: ProjectSource[];
  documents: ProjectDocument[];
}

export function TeamDataPanel({ connectors, sources, documents }: Props) {
  const driveFolders = sources.filter((s) => s.source_type === 'DRIVE_FOLDER');
  const jiraProjects = sources.filter((s) => s.source_type === 'JIRA_PROJECT');

  const byRole = documents.reduce<Record<string, number>>((acc, doc) => {
    const key = doc.doc_role ?? 'OTHER';
    acc[key] = (acc[key] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className={styles.card}>
      <div className={styles.cardHeader}>
        <p className={styles.cardTitle}>연결된 데이터</p>
        <Link to="/onboarding/connectors" className={styles.cardLink}>
          설정 →
        </Link>
      </div>

      <div className={styles.rows}>
        <p className={styles.sectionLabel}>커넥터</p>
        {connectors.map((connector) => (
          <div key={connector.conn_id} className={styles.row}>
            <span className={`${styles.dot} ${statusDot(connector.auth_status)}`} />
            <span className={styles.rowLabel}>
              {CONNECTOR_LABEL[connector.connector_type] ?? connector.connector_type}
            </span>
            <span className={styles.rowValue}>
              {STATUS_LABEL[connector.auth_status] ?? connector.auth_status}
            </span>
          </div>
        ))}
        {connectors.length === 0 && <p className={styles.empty}>연결된 커넥터가 없습니다.</p>}
      </div>

      <div className={styles.divider} />

      <div className={styles.rows}>
        <p className={styles.sectionLabel}>읽고 있는 소스</p>
        <div className={styles.row}>
          <span className={styles.rowLabel}>Drive 폴더</span>
          <span className={styles.rowValue}>{driveFolders.length}개</span>
        </div>
        <div className={styles.row}>
          <span className={styles.rowLabel}>Jira 프로젝트</span>
          <span className={styles.rowValue}>
            {jiraProjects.length > 0
              ? jiraProjects.map((s) => s.external_source_id).join(' · ')
              : '없음'}
          </span>
        </div>
      </div>

      <div className={styles.divider} />

      <div className={styles.rows}>
        <p className={styles.sectionLabel}>등록된 문서 {documents.length}건</p>
        {Object.entries(byRole)
          .sort()
          .map(([role, count]) => (
            <div key={role} className={styles.row}>
              <span className={styles.rowLabel}>{ROLE_LABEL[role as DocRole] ?? role}</span>
              <span className={styles.rowValue}>{count}건</span>
            </div>
          ))}
        {documents.length === 0 && <p className={styles.empty}>등록된 문서가 없습니다.</p>}
      </div>
    </div>
  );
}

export default TeamDataPanel;
