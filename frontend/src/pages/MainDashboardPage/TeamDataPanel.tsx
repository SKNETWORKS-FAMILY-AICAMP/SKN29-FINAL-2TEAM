import { Link } from 'react-router-dom';
import type { ConnectorConnection } from '../../api/connectors';
import type { DocRole, ProjectDocument, ProjectSource } from '../../api/projects';
import styles from './TeamDashboard.module.css';

const ROLE_LABEL: Record<DocRole, string> = {
  PLAN: '기획서',
  MEETING_NOTE: '회의록',
  DAILY_REPORT: '일일보고서',
  OTHER: '기타',
};

interface Props {
  connectors: ConnectorConnection[];
  sources: ProjectSource[];
  documents: ProjectDocument[];
}

/**
 * 무엇이 연결돼 있고 무엇을 읽고 있는가.
 *
 * 매일 들여다보는 값이 아니라 "이 숫자들이 어디서 왔는지"를 확인하는 자리라
 * 카드가 아니라 가로 한 줄로 둔다. 커넥터 상태·소스·문서를 각각 줄 세워 쌓으면
 * 부하 분석보다 시선을 더 끌어간다.
 */
export function TeamDataPanel({ connectors, sources, documents }: Props) {
  const connected = connectors.filter((c) => c.auth_status === 'CONNECTED').length;
  const allConnected = connectors.length > 0 && connected === connectors.length;

  const driveFolders = sources.filter((s) => s.source_type === 'DRIVE_FOLDER').length;
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

      <div className={styles.strip}>
        <div className={styles.stripItem}>
          <span className={styles.stripLabel}>커넥터</span>
          <span className={styles.stripValue}>
            <span className={`${styles.dot} ${allConnected ? styles.dotOk : styles.dotBad}`} />
            {connectors.length > 0 ? `${connected} / ${connectors.length}` : '없음'}
          </span>
          <span className={styles.stripSub}>
            {connectors.length === 0
              ? '연결된 커넥터가 없습니다'
              : allConnected
                ? '모두 연결됨'
                : '재연결 필요'}
          </span>
        </div>

        <div className={styles.stripItem}>
          <span className={styles.stripLabel}>Drive 폴더</span>
          <span className={styles.stripValue}>{driveFolders}개</span>
          <span className={styles.stripSub}>문서를 읽어오는 폴더</span>
        </div>

        <div className={styles.stripItem}>
          <span className={styles.stripLabel}>Jira 프로젝트</span>
          <span className={styles.stripValue}>{jiraProjects.length}개</span>
          <span className={styles.stripSub}>
            {jiraProjects.length > 0
              ? jiraProjects.map((s) => s.display_name || s.external_source_id).join(' · ')
              : '선택된 프로젝트 없음'}
          </span>
        </div>

        <div className={styles.stripItem}>
          <span className={styles.stripLabel}>등록 문서</span>
          <span className={styles.stripValue}>{documents.length}건</span>
          <span className={styles.stripSub}>
            {documents.length > 0
              ? Object.entries(byRole)
                  .sort()
                  .map(([role, count]) => `${ROLE_LABEL[role as DocRole] ?? role} ${count}`)
                  .join(' · ')
              : '등록된 문서 없음'}
          </span>
        </div>
      </div>
    </div>
  );
}

export default TeamDataPanel;
