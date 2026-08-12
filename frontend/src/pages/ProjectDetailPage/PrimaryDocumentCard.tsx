import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Icon } from '../../components';
import { ApiError } from '../../api/client';
import {
  listProjectSourceDocuments,
  saveProjectPrimaryDocument,
  suggestPrimaryCandidates,
} from '../../api/projects';
import type { PipelineDocument, PrimaryCandidate } from '../../api/projects';
import { PATHS } from '../../routes';
import styles from './PrimaryDocumentCard.module.css';

/**
 * 이 프로젝트의 **기준 문서**.
 *
 * 프로젝트를 만들 때 정하지만, 그때 못 정한 경우와 잘못 고른 경우가 있다 —
 * 문서가 아직 색인 전이었거나, 후보가 안 나왔거나, 나중에 더 맞는 문서가
 * 들어온다. 그 셋 다 여기서 고친다.
 *
 * **화면에 없으면 고칠 방법이 없다.** 지금까지 기준 문서를 정하는 경로는
 * 생성 마법사 하나뿐이었고, 거기서 「나중에」를 누른 사람은 프로젝트를 다시
 * 만드는 것 말고는 방법이 없었다.
 */

export interface PrimaryDocumentCardProps {
  projectId: string;
  token: string;
  /** 후보를 찾을 질의가 된다. 프로젝트 자신의 이름·설명이다. */
  name: string;
  description: string | null;
}

export function PrimaryDocumentCard({ projectId, token, name, description }: PrimaryDocumentCardProps) {
  const navigate = useNavigate();

  const [documents, setDocuments] = useState<PipelineDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const [picking, setPicking] = useState(false);
  const [candidates, setCandidates] = useState<PrimaryCandidate[]>([]);
  const [searchError, setSearchError] = useState('');


  const load = useCallback(async () => {
    setLoading(true);
    try {
      setDocuments(await listProjectSourceDocuments(token, projectId));
    } catch {
      // 문서를 못 읽어도 상세 화면 전체를 막지 않는다. 이 카드만 조용히 빈다.
      setDocuments([]);
    } finally {
      setLoading(false);
    }
  }, [token, projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const primary = documents.find((document) => document.doc_role === 'PRIMARY') ?? null;

  async function handleFind() {
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      const result = await suggestPrimaryCandidates(token, name, description ?? '');
      setCandidates(result.candidates);
      setSearchError(result.error ?? '');
      setPicking(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '문서를 찾지 못했습니다.');
    } finally {
      setBusy(false);
    }
  }

  async function handleChoose(docId: string | null) {
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      setDocuments(await saveProjectPrimaryDocument(token, projectId, docId));
      setPicking(false);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : docId === null
            ? '기준 문서를 해제하지 못했습니다.'
            : '기준 문서를 지정하지 못했습니다.',
      );
    } finally {
      setBusy(false);
    }
  }

  /**
   * 업무 추출은 **Chat 에서 돌린다.** 여기서 직접 부르지 않는다.
   *
   * 도구 자체는 여기서도 부를 수 있다(`streamTaskExtraction`). 그런데 뽑은
   * 업무를 Jira 에 올리려면 승인 게이트를 타야 하고, 그 확인 카드는 대화 안에서
   * 뜬다(`awaiting_confirmation` → `confirm` → resume). 추출만 여기서 하면
   * **그 결과가 버려지고 Chat 에서 처음부터 다시 뽑게 된다** — 몇 분짜리 작업을
   * 두 번 하는 것이다.
   *
   * 그래서 이 버튼은 대화를 열고 **거기서 바로 실행시킨다.** 사람이 다시 칠
   * 것은 없다(`ChatPage` 가 `ask` 를 받으면 자동으로 보낸다).
   */
  function handleExtract() {
    navigate(
      `${PATHS.chat}?proj=${projectId}&ask=${encodeURIComponent('이 프로젝트의 기준 문서에서 업무를 뽑아줘')}`,
    );
  }

  return (
    <section className={styles.card}>
      <div className={styles.head}>
        <span className={styles.title}>기준 문서</span>
      </div>

      {error && <p className={styles.error}>{error}</p>}

      {loading ? (
        <p className={styles.muted}>문서를 불러오는 중…</p>
      ) : picking ? (
        <>
          {searchError ? (
            <p className={styles.muted}>{searchError}</p>
          ) : candidates.length === 0 ? (
            <p className={styles.muted}>
              이 프로젝트와 맞는 문서를 팀 저장소에서 찾지 못했습니다. Drive를 연결했는지, 문서가 처리를
              마쳤는지 확인해 주세요.
            </p>
          ) : (
            <ul className={styles.candidates}>
              {candidates.map((candidate) => (
                <li key={candidate.doc_id}>
                  <button
                    type="button"
                    className={styles.candidate}
                    onClick={() => void handleChoose(candidate.doc_id)}
                    disabled={busy || !candidate.search_ready}
                  >
                    <span className={styles.candidateHead}>
                      <strong>{candidate.file_name}</strong>
                      <span className={styles.score}>
                        {candidate.name_score >= 0.6 && <span className={styles.badge}>이름 일치</span>}
                        내용 {Math.round(candidate.summary_score * 100)}%
                      </span>
                    </span>
                    {candidate.summary && <span className={styles.summary}>{candidate.summary}</span>}
                    {!candidate.search_ready && (
                      <span className={styles.notReady}>본문이 아직 색인되지 않아 고를 수 없습니다</span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
          <Button variant="outline" size="sm" onClick={() => setPicking(false)} disabled={busy}>
            취소
          </Button>
        </>
      ) : primary ? (
        <>
          <div className={styles.primary}>
            <Icon name="file-text" size={16} color="var(--color-primary)" />
            <span className={styles.primaryName}>{primary.file_name ?? primary.doc_id}</span>
          </div>
          {/* 색인 전 문서가 기준으로 잡혀 있을 수 있다(고른 뒤 파이프라인이 다시
              돌거나, 예전에 지정해 둔 문서다). 그 상태로는 업무 추출이 거절한다. */}
          {!primary.search_ready && (
            <p className={styles.warn}>
              본문이 아직 색인되지 않았습니다. 이 상태로는 업무를 뽑을 수 없습니다.
            </p>
          )}
          <p className={styles.footnote}>
            업무 추출은 이 문서를 근거로 돕니다. 근거 문서는 따로 묶지 않고 에이전트가 팀 문서에서
            찾습니다. 「업무 뽑기」를 누르면 이 프로젝트의 대화가 열리고 곧바로 실행됩니다.
          </p>

          {/* 이 문서로 할 수 있는 일과 이 문서를 바꾸는 일. 같은 대상에 대한
              행동이라 한 줄에 둔다. */}
          <div className={styles.actions}>
            <Button size="sm" disabled={busy || !primary.search_ready} onClick={handleExtract}>
              업무 뽑기
            </Button>
            <Button variant="outline" size="sm" onClick={handleFind} disabled={busy}>
              문서 바꾸기
            </Button>
            {/* 바꿀 문서가 없을 수도 있다. 「없음」으로 못 가면 잘못 고른 문서를
                달고 있는 수밖에 없고, 그대로 뽑으면 엉뚱한 업무가 등록된다. */}
            <Button variant="ghost" size="sm" onClick={() => void handleChoose(null)} disabled={busy}>
              기준 문서 해제
            </Button>
          </div>
        </>
      ) : (
        <>
          <p className={styles.muted}>
            기준 문서가 아직 없습니다. 업무 추출은 기준 문서가 있어야 돌아갑니다 — 「문서 찾기」로
            정해 주세요.
          </p>
          <div className={styles.actions}>
            <Button size="sm" onClick={handleFind} disabled={busy}>
              {busy ? '찾는 중…' : '문서 찾기'}
            </Button>
          </div>
        </>
      )}
    </section>
  );
}
