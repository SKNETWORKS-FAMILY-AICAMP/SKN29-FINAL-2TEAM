import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Badge, Button, TopNav } from '../../components';
import { listMyProjects, listProjectDocuments, startTaskExtraction } from '../../api/projects';
import type { ProjectDocument } from '../../api/projects';
import { MAIN_NAV_TABS } from '../../routes';
import { loadSessionToken } from '../../utils/session';
import styles from './PrimaryDocumentSelectPage.module.css';

export default function PrimaryDocumentSelectPage() {
  const { projectId = '' } = useParams();
  const navigate = useNavigate();
  const [projectName, setProjectName] = useState('');
  const [documents, setDocuments] = useState<ProjectDocument[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = loadSessionToken();
    if (!token || !projectId) return;
    Promise.all([listMyProjects(token), listProjectDocuments(token, projectId)])
      .then(([projects, docs]) => {
        setProjectName(projects.find((item) => item.proj_id === projectId)?.name ?? projectId);
        setDocuments(docs);
      })
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
  }, [projectId]);

  async function submit() {
    if (!selectedId || submitting) return;
    const selected = documents.find((item) => item.doc_id === selectedId);
    if (!selected?.search_ready) {
      setError('문서가 아직 파싱·청킹·임베딩되지 않았습니다.');
      return;
    }
    const token = loadSessionToken();
    if (!token) {
      setError('로그인이 필요합니다.');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const result = await startTaskExtraction(token, projectId, selectedId);
      navigate(`/tasks/distribution?projectId=${encodeURIComponent(projectId)}`, { state: { result } });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '업무 추출 요청에 실패했습니다.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className={styles.page}>
      <TopNav tabs={MAIN_NAV_TABS} activeTo="/projects" />
      <main className={styles.main}>
        <button type="button" className={styles.back} onClick={() => navigate('/projects')}>← 이전</button>
        <h1>업무 추출 기준 문서 선택</h1>
        <p className={styles.guide}>{projectName}에서 업무 후보를 처음 찾을 문서 한 건을 선택하세요.</p>
        {error && <div className={styles.error} role="alert">{error}</div>}
        {loading ? <p>문서를 불러오는 중입니다.</p> : (
          <div className={styles.list}>
            {documents.map((document) => (
              <label className={styles.row} key={document.doc_id}>
                <input
                  type="radio"
                  name="primary-document"
                  checked={selectedId === document.doc_id}
                  disabled={submitting}
                  onChange={() => { setSelectedId(document.doc_id); setError(null); }}
                />
                <span className={styles.name}>{document.file_name || document.doc_id}</span>
                {document.doc_role && <Badge tone="neutral">{document.doc_role}</Badge>}
                <span className={document.search_ready ? styles.ready : styles.notReady}>
                  {document.search_ready ? '검색 준비 완료' : '처리 필요'}
                </span>
              </label>
            ))}
            {!documents.length && <p className={styles.empty}>업무 추출에 사용할 문서가 없습니다.</p>}
          </div>
        )}
        <div className={styles.actions}>
          <Button variant="secondary" onClick={() => navigate('/projects')}>이전</Button>
          <Button variant="primary" disabled={!selectedId || submitting} onClick={submit}>
            {submitting ? '업무 추출 중…' : '업무 추출 시작'}
          </Button>
        </div>
      </main>
    </div>
  );
}
