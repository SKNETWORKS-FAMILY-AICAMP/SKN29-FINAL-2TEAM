import { useCallback, useEffect, useState } from 'react';
import { Button, Icon, InfoNote } from '../../components';
import { ApiError } from '../../api/client';
import {
  listProjectSourceDocuments,
  saveProjectPrimaryDocument,
  suggestPrimaryCandidates,
} from '../../api/projects';
import type { PipelineDocument, PrimaryCandidate } from '../../api/projects';
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

  /**
   * **`proj_id` 까지 봐야 한다.** 이 목록은 「이 프로젝트의 문서」가 아니라
   * **팀 문서 전체**다 — 서버가 일부러 그렇게 준다. 그래서 `doc_role`
   * 하나로 고르면 **남의 프로젝트 기준 문서를 자기 것으로 그린다.**
   *
   * 팀에 기준 문서가 하나뿐일 때는 우연히 맞아서 오래 안 드러났다. 기준 문서가
   * 있는 프로젝트와 없는 프로젝트가 함께 생긴 2026-08-19 에야 나왔다 — 없는
   * 쪽이 남의 것을 가져다 그릴 수 있었다.
   */
  const primary =
    documents.find(
      (document) => document.doc_role === 'PRIMARY' && document.proj_id === projectId,
    ) ?? null;

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

  return (
    <section className={styles.card}>
      <div className={styles.head}>
        <span className={styles.title}>
          기준 문서
          <InfoNote title="기준 문서">
            <p>프로젝트 작업 시 참고 기준으로 사용할 문서입니다.</p>
          </InfoNote>
        </span>
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
                    disabled={busy}
                  >
                    <span className={styles.candidateHead}>
                      <strong>{candidate.file_name}</strong>
                      <span className={styles.score}>
                        {candidate.name_score >= 0.6 && <span className={styles.badge}>이름 일치</span>}
                        내용 {Math.round(candidate.content_score * 100)}%
                      </span>
                    </span>
                    {candidate.matched_text && (
                      <span className={styles.summary}>{candidate.matched_text}</span>
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
          <div className={styles.actions}>
            <Button variant="outline" size="sm" onClick={handleFind} disabled={busy}>
              기준 문서 변경
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
            기준 문서가 아직 없습니다. ‘기준 문서 선택’으로 정해 주세요.
          </p>
          <div className={styles.actions}>
            <Button size="sm" onClick={handleFind} disabled={busy}>
              {busy ? '찾는 중…' : '기준 문서 선택'}
            </Button>
          </div>
        </>
      )}
    </section>
  );
}
