import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Badge, Button, Icon, TopNav, useToast } from '../../components';
import { ApiError } from '../../api/client';
import {
  createProject,
  fetchDocumentProcessing,
  listPipelineDocuments,
  saveProjectSourceDocuments,
  startDocumentProcessing,
  startTaskExtraction,
  TERMINAL_PROCESSING_STATUS,
} from '../../api/projects';
import type { PipelineDocument } from '../../api/projects';
import { MAIN_NAV_TABS } from '../../routes';
import { useSession } from '../../utils/session';
import styles from './PrimaryDocumentSelectPage.module.css';

const collator = new Intl.Collator('ko', { numeric: true });

/** 파일명에서 확장자를 뗀다. 프로젝트 이름 기본값으로 쓴다. */
function baseName(fileName: string): string {
  return fileName.replace(/\.[^.]+$/, '');
}

/**
 * 신규 프로젝트를 문서에서 시작한다.
 *
 * **기존 프로젝트에 업무를 배분하는 화면이 아니다.** Jira 에서 가져온 프로젝트는
 * 이미 진행 중인 것이고, 그것은 팀원의 현재 부하를 재는 재료지 업무를 새로 뽑을
 * 대상이 아니다. 설계 문서 3.2 그대로 — "신규 프로젝트는 Jira 에 없으므로
 * 기획서에서 시작한다".
 *
 * 그래서 여기서 고르는 **메인 문서가 곧 프로젝트를 만드는 행위**다. 기준 문서
 * 하나(라디오)에서 업무 후보를 찾고, 근거 문서 여럿(체크박스)까지 함께 검색해
 * 요구사항·역할·공수를 채운다. 기준 문서만 정하면 Query Agent 의 2~4단계 검색
 * 범위가 그 한 건이 되어 1단계와 똑같아진다.
 *
 * 프로젝트는 `DRAFT` 로 만든다. 설계 문서가 말하는 "승인 전에는 내부 Draft 로만
 * 관리한다"이고, 추출 결과를 `doc.proj_id` 로 묶어야 검색 범위가 성립한다.
 */
export default function PrimaryDocumentSelectPage() {
  const navigate = useNavigate();
  const session = useSession();
  const token = session?.token;
  const { showToast } = useToast();

  const [projectName, setProjectName] = useState('');
  // 사용자가 이름을 직접 고쳤으면 메인 문서를 바꿔도 덮어쓰지 않는다.
  const [nameTouched, setNameTouched] = useState(false);
  const [documents, setDocuments] = useState<PipelineDocument[]>([]);
  const [primaryId, setPrimaryId] = useState<string | null>(null);
  const [subIds, setSubIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [extracting, setExtracting] = useState(false);
  const [processing, setProcessing] = useState<Record<string, string>>({});
  const [error, setError] = useState('');

  // 화면을 떠난 뒤에도 polling 이 돌면 사라진 컴포넌트에 setState 한다.
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError('');
    try {
      setDocuments(await listPipelineDocuments(token));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '문서를 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  /** 파싱·청킹·임베딩. 끝나야 그 문서를 근거로 쓸 수 있다. */
  async function handleProcess(docId: string) {
    if (!token || processing[docId]) return;
    setProcessing((prev) => ({ ...prev, [docId]: 'IN_QUEUE' }));
    try {
      const run = await startDocumentProcessing(token, docId);
      let status = run.status;
      while (!TERMINAL_PROCESSING_STATUS.includes(status)) {
        await new Promise((resolve) => setTimeout(resolve, 3000));
        if (!alive.current) return;
        const next = await fetchDocumentProcessing(token, docId, run.job_id);
        status = next.status;
        setProcessing((prev) => ({ ...prev, [docId]: status }));
        if (status === 'COMPLETED') {
          // 진행률을 지어내지 않는다. 서버가 준 적재 건수만 말한다.
          const done = next.ingested;
          showToast(
            done ? `문서 처리 완료 — 청크 ${done.chunks}건` : '문서 처리 완료',
            'success',
          );
          await load();
        } else if (TERMINAL_PROCESSING_STATUS.includes(status)) {
          showToast(next.error || '문서 처리에 실패했습니다', 'error');
        }
      }
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : '문서 처리를 시작하지 못했습니다', 'error');
    } finally {
      setProcessing((prev) => {
        const next = { ...prev };
        delete next[docId];
        return next;
      });
    }
  }

  function toggleSub(docId: string) {
    setSubIds((prev) =>
      prev.includes(docId) ? prev.filter((id) => id !== docId) : [...prev, docId],
    );
  }

  function choosePrimary(docId: string) {
    setPrimaryId(docId);
    // 기준 문서를 근거 문서로 겹쳐 두면 서버가 거절한다. 화면에서 먼저 푼다.
    setSubIds((prev) => prev.filter((id) => id !== docId));
    setError('');

    // 프로젝트 이름을 아직 안 건드렸으면 메인 문서명을 따라간다. 대부분 그 이름이
    // 맞고, 아니면 고치면 된다 — 빈 칸을 놓고 뭘 적을지 고민하게 하지 않는다.
    if (!nameTouched) {
      const file = documents.find((d) => d.doc_id === docId)?.file_name;
      if (file) setProjectName(baseName(file));
    }
  }

  async function handleExtract() {
    if (!token || !primaryId || extracting) return;
    const name = projectName.trim();
    if (!name) {
      setError('프로젝트 이름을 적어 주세요.');
      return;
    }
    const primary = documents.find((d) => d.doc_id === primaryId);
    if (!primary?.search_ready) {
      setError('기준 문서가 아직 처리되지 않았습니다. 「문서 처리」를 먼저 눌러 주세요.');
      return;
    }
    setExtracting(true);
    setError('');
    try {
      // 순서가 중요하다. 프로젝트가 있어야 문서를 묶을 수 있고, 문서가 묶여야
      // 2~4단계 검색 범위가 생긴다. DRAFT 인 이유는 아직 PM이 승인하기 전이라서다.
      const project = await createProject(token, name);
      await saveProjectSourceDocuments(token, project.proj_id, primaryId, subIds);
      const result = await startTaskExtraction(token, project.proj_id, primaryId);
      navigate('/tasks/extraction', { state: { result, project } });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '업무 추출에 실패했습니다.');
    } finally {
      setExtracting(false);
    }
  }

  const rows = [...documents].sort((a, b) =>
    collator.compare(a.file_name ?? a.doc_id, b.file_name ?? b.doc_id),
  );
  const readySubs = subIds.filter(
    (id) => documents.find((d) => d.doc_id === id)?.search_ready,
  ).length;

  return (
    <div className={styles.page}>
      <TopNav tabs={MAIN_NAV_TABS} activeTo="/projects" />

      <main className={styles.main}>
        <button type="button" className={styles.back} onClick={() => navigate('/projects')}>
          <Icon name="arrow-left" size={16} />
          <span>프로젝트</span>
        </button>

        <h1>신규 프로젝트 업무 추출</h1>
        <p className={styles.guide}>
          기획서·제안요청서 같은 <strong>기준 문서 한 건</strong>에서 업무 후보를 찾고,
          근거 문서까지 함께 검색해 요구사항·역할·공수를 채웁니다. 여기서 고른
          문서가 곧 이 프로젝트를 정의합니다.
        </p>

        <label className={styles.projectPick}>
          <span>프로젝트 이름</span>
          <input
            type="text"
            value={projectName}
            placeholder="기준 문서를 고르면 파일명이 들어옵니다"
            maxLength={200}
            disabled={extracting}
            onChange={(event) => {
              setProjectName(event.target.value);
              setNameTouched(true);
              setError('');
            }}
          />
        </label>

        {error && (
          <div className={styles.error} role="alert">
            {error}
          </div>
        )}

        {loading && <p className={styles.notice}>문서를 불러오는 중…</p>}

        {!loading && (
          <div className={styles.list}>
            <div className={styles.head}>
              <span>기준</span>
              <span>근거</span>
              <span>문서</span>
              <span>상태</span>
              <span />
            </div>

            {rows.map((document) => {
              const busy = processing[document.doc_id];

              return (
                <div key={document.doc_id} className={styles.row}>
                  <input
                    type="radio"
                    name="primary-document"
                    checked={primaryId === document.doc_id}
                    disabled={extracting || !document.search_ready}
                    onChange={() => choosePrimary(document.doc_id)}
                    aria-label={`${document.file_name ?? document.doc_id} 을 기준 문서로`}
                  />
                  <input
                    type="checkbox"
                    checked={subIds.includes(document.doc_id)}
                    disabled={
                      extracting || primaryId === document.doc_id || !document.search_ready
                    }
                    onChange={() => toggleSub(document.doc_id)}
                    aria-label={`${document.file_name ?? document.doc_id} 을 근거 문서로`}
                  />

                  <span className={styles.name}>
                    {document.file_name || document.doc_id}
                    {/* 다른 프로젝트가 이미 쓰고 있다는 사실은 알려야 한다. 고르면
                        그쪽에서 빠진다. */}
                    {document.proj_id !== null && (
                      <Badge tone="warning">다른 프로젝트 사용 중</Badge>
                    )}
                  </span>

                  <span
                    className={document.search_ready ? styles.ready : styles.notReady}
                  >
                    {document.search_ready
                      ? '검색 준비 완료'
                      : document.downloaded
                        ? '처리 필요'
                        : '원문 미수신'}
                  </span>

                  <span className={styles.action}>
                    {!document.search_ready && document.downloaded && (
                      <button
                        type="button"
                        className={styles.processBtn}
                        disabled={Boolean(busy) || extracting}
                        onClick={() => void handleProcess(document.doc_id)}
                      >
                        {busy ? `처리 중… ${busy}` : '문서 처리'}
                      </button>
                    )}
                  </span>
                </div>
              );
            })}

            {rows.length === 0 && (
              <p className={styles.empty}>
                등록된 팀 문서가 없습니다. 「문서 등록」에서 Drive 문서를 먼저 등록해 주세요.
              </p>
            )}
          </div>
        )}

        <div className={styles.actions}>
          <span className={styles.summary}>
            {primaryId ? `기준 1건 · 근거 ${readySubs}건` : '기준 문서를 골라 주세요'}
          </span>
          <Button variant="secondary" onClick={() => navigate('/projects')}>
            이전
          </Button>
          <Button
            variant="primary"
            disabled={!primaryId || !projectName.trim() || extracting}
            onClick={handleExtract}
          >
            {extracting ? '업무 추출 중…' : '업무 추출 시작'}
          </Button>
        </div>
      </main>
    </div>
  );
}
