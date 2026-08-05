import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Badge, Button, Icon, Modal, TopNav, useToast } from '../../components';
import { ApiError } from '../../api/client';
import {
  createProject,
  listPipelineDocuments,
  saveProjectPrimaryDocument,
  streamTaskExtraction,
} from '../../api/projects';
import type { PipelineDocument } from '../../api/projects';
import { MAIN_NAV_TABS } from '../../routes';
import { useSession } from '../../utils/session';
import { formatElapsed, useElapsed } from '../../utils/useElapsed';
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
 * 그래서 여기서 고르는 **기준 문서가 곧 프로젝트를 만드는 행위**다. 고르는 것은
 * 그 한 건뿐이다 — 요구사항·역할·공수의 근거가 어느 문서에 있는지는 에이전트가
 * 팀 문서를 검색해서 찾는다(2026-08-04). 근거 문서까지 사람이 체크하게 두면
 * 무엇이 어디 적혀 있는지 미리 알아야 하는데, 그걸 대신 찾아 주는 것이 이 기능의
 * 목적이라 순서가 거꾸로였다.
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
  const [loading, setLoading] = useState(true);
  const [extracting, setExtracting] = useState(false);
  const [error, setError] = useState('');
  /**
   * 추출 진행. 검색 4단계 + 정리 1단계라 퍼센트가 진짜다. `queries` 는 에이전트가
   * 그 단계에서 실제로 만든 검색어다 — 도는 원 대신 이걸 보여준다.
   */
  const [progress, setProgress] = useState<{
    step: number;
    total: number;
    label: string;
    queries: string[];
    found: number | null;
  } | null>(null);

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

  function choosePrimary(docId: string) {
    setPrimaryId(docId);
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
    setProgress({ step: 0, total: 5, label: '프로젝트를 만드는 중', queries: [], found: null });
    try {
      // 순서가 중요하다. 프로젝트가 있어야 기준 문서를 묶을 수 있다. DRAFT 인
      // 이유는 아직 PM이 승인하기 전이라서다.
      const project = await createProject(token, name);
      await saveProjectPrimaryDocument(token, project.proj_id, primaryId);
      const result = await streamTaskExtraction(token, project.proj_id, primaryId, (event) => {
        if (event.type === 'stage') {
          setProgress({
            step: event.step,
            total: event.total,
            label: event.label,
            queries: [],
            found: null,
          });
        } else if (event.type === 'queries') {
          setProgress((prev) => (prev ? { ...prev, queries: event.queries } : prev));
        } else if (event.type === 'stage_done') {
          setProgress((prev) => (prev ? { ...prev, found: event.evidence } : prev));
        }
      });
      navigate('/tasks/extraction', { state: { result, project } });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '업무 추출에 실패했습니다.');
    } finally {
      setProgress(null);
      setExtracting(false);
    }
  }

  // 단계가 바뀔 때마다 다시 센다. 진행률이 안 움직이는 동안에도 이 숫자는 올라가서,
  // 멈춘 것과 오래 걸리는 것을 구분해 준다.
  const elapsed = useElapsed(progress ? progress.step : null);

  const rows = [...documents].sort((a, b) =>
    collator.compare(a.file_name ?? a.doc_id, b.file_name ?? b.doc_id),
  );

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
          기획서·제안요청서 같은 <strong>기준 문서 한 건</strong>만 고르면 됩니다. 여기서
          업무 후보를 찾고, 요구사항·역할·공수의 근거는 에이전트가 팀 문서 전체를
          검색해 찾습니다.
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
              <span>문서</span>
              <span>상태</span>
            </div>

            {rows.map((document) => {
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
                  <span className={styles.name}>
                    {document.file_name || document.doc_id}
                    {/* 다른 프로젝트가 이미 쓰고 있다는 사실은 알려야 한다. 고르면
                        그쪽에서 빠진다. */}
                    {document.proj_id !== null && (
                      <Badge tone="warning">다른 프로젝트 사용 중</Badge>
                    )}
                  </span>

                  {/* 등록이 임베딩까지 끝내므로 여기 걸리는 문서는 등록 중
                      실패한 것뿐이다. 이 화면에서 되살리지 않는다 — 문서를
                      준비시키는 일은 문서 관리의 몫이다. */}
                  <span className={document.search_ready ? styles.ready : styles.notReady}>
                    {document.search_ready ? '검색 준비 완료' : '준비 안 됨'}
                  </span>
                </div>
              );
            })}

            {rows.length === 0 && (
              <p className={styles.empty}>
                등록된 팀 문서가 없습니다. 「문서 관리」에서 Drive 문서를 먼저 등록해 주세요.
              </p>
            )}
          </div>
        )}

        <div className={styles.actions}>
          <span className={styles.summary}>
            {primaryId ? '기준 문서 1건' : '기준 문서를 골라 주세요'}
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

      {/*
        몇 분이 걸리는 일이다. 도는 원만 띄우면 되고 있는 건지 멈춘 건지 알 수 없어,
        서버가 단계마다 보내 주는 것을 그대로 보여준다. 특히 검색어는 에이전트가
        그 단계에서 실제로 내린 판단이라, 「불러오는 중」보다 이쪽이 정직하다.
      */}
      <Modal
        open={progress !== null}
        onClose={() => {}}
        dismissible={false}
        title="업무 추출"
        width={440}
      >
        {progress && (
          <>
            <div className={styles.progressHead}>
              <span className={styles.progressCount}>
                {progress.step} / {progress.total}
              </span>
              <span className={styles.progressStage}>{formatElapsed(elapsed)}</span>
            </div>
            <div
              className={styles.progressTrack}
              role="progressbar"
              aria-valuenow={progress.step}
              aria-valuemin={0}
              aria-valuemax={progress.total}
            >
              <span
                className={styles.progressFill}
                style={{ width: `${(progress.step / progress.total) * 100}%` }}
              />
            </div>

            <p className={styles.progressNeed}>{progress.label}</p>

            {progress.queries.length > 0 && (
              <ul className={styles.progressQueries}>
                {progress.queries.map((query) => (
                  <li key={query}>{query}</li>
                ))}
              </ul>
            )}

            <p className={styles.progressMeta}>
              {progress.found !== null && `근거 ${progress.found}건 · `}
              몇 분 걸립니다 · 창을 닫지 마세요
            </p>
          </>
        )}
      </Modal>
    </div>
  );
}
