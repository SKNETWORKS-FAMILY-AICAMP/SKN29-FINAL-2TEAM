import { useEffect, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Icon } from '../../components';
import { ApiError } from '../../api/client';
import {
  createProject,
  saveProjectPrimaryDocument,
  suggestPrimaryCandidates,
} from '../../api/projects';
import type { PrimaryCandidate } from '../../api/projects';
import { PATHS } from '../../routes';
import { loadSessionToken } from '../../utils/session';
import { josa } from '../../utils/josa';
import styles from './NewProjectDialog.module.css';

/**
 * 프로젝트를 만드는 세 걸음 — **프로젝트 → 문서 → 업무**.
 *
 * 그냥 빈 프로젝트를 만들고 끝내지 않는 이유는, 그러면 사람이 다음에 무엇을 해야
 * 하는지가 화면 어디에도 없기 때문이다. 이름을 받자마자 「이 문서가 기준 문서
 * 같습니다, 맞습니까」를 묻고, 맞으면 「이 문서로 업무를 뽑을까요」로 잇는다.
 *
 * **DB 에 쓰는 것은 맨 마지막 한 번이다.** 걸음마다 저장하면 2걸음에서 닫은
 * 사람 몫으로 빈 프로젝트가 남는다 — `proj.status` 의 `DRAFT` 가 원래 그
 * 「온보딩이 만들다 만 프로젝트」를 뜻하던 값이고, 그 상태를 다시 만들 이유가
 * 없다. 후보 검색은 프로젝트 없이도 도는 API 라 미룰 수 있다.
 *
 * **세 걸음 모두 사람이 확정한다.** 문서 후보는 요약 임베딩과 파일명이 고른
 * 것이라 틀릴 수 있고, 어느 문서로 업무를 뽑았는지는 결과 전체의 전제다
 * (그 규칙은 `services/harness/registry.py` 의 `task_extraction` 에 있다).
 */

type Step = 'form' | 'document' | 'extract';

export interface NewProjectDialogProps {
  onClose: () => void;
  /** 실제로 만들어졌을 때. 목록을 다시 읽으라는 뜻이다. */
  onCreated: () => void;
}

export function NewProjectDialog({ onClose, onCreated }: NewProjectDialogProps) {
  const navigate = useNavigate();
  const token = loadSessionToken();

  const [step, setStep] = useState<Step>('form');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const dialogRef = useRef<HTMLDivElement>(null);

  const [candidates, setCandidates] = useState<PrimaryCandidate[]>([]);
  /** 검색 자체가 실패한 경우. 「후보가 없다」와 다르게 말해야 한다. */
  const [searchError, setSearchError] = useState('');
  /** 사람이 고른 기준 문서. 아직 저장하지 않았다. */
  const [chosen, setChosen] = useState<PrimaryCandidate | null>(null);

  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const frame = window.requestAnimationFrame(() => {
      const dialog = dialogRef.current;
      const first =
        dialog?.querySelector<HTMLElement>('[autofocus]') ??
        dialog?.querySelector<HTMLElement>(
          'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        );
      (first ?? dialog)?.focus();
    });

    return () => {
      window.cancelAnimationFrame(frame);
      document.body.style.overflow = previousOverflow;
      if (previousFocus?.isConnected) window.requestAnimationFrame(() => previousFocus.focus());
    };
  }, []);

  function handleDialogKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape') {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key !== 'Tab') return;

    const dialog = dialogRef.current;
    if (!dialog) return;
    const focusable = Array.from(
      dialog.querySelectorAll<HTMLElement>(
        'button:not([disabled]), a[href], input:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ),
    ).filter((element) => element.getClientRects().length > 0);
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const active = document.activeElement;
    if (!first || !last) {
      event.preventDefault();
      dialog.focus();
    } else if (event.shiftKey && (active === first || !dialog.contains(active))) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (active === last || !dialog.contains(active))) {
      event.preventDefault();
      first.focus();
    }
  }

  /** 1걸음 — 아직 아무것도 만들지 않고 문서만 찾아 본다. */
  async function handleFind() {
    if (!token || !name.trim() || busy) return;
    setBusy(true);
    setError('');
    try {
      const result = await suggestPrimaryCandidates(token, name.trim(), description.trim());
      setCandidates(result.candidates);
      setSearchError(result.error ?? '');
      setStep('document');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '문서를 찾지 못했습니다.');
    } finally {
      setBusy(false);
    }
  }

  /**
   * 마지막 걸음 — **여기서 처음으로 DB 에 쓴다.**
   *
   * 기준 문서 지정이 실패해도 프로젝트는 남긴다. 사람이 이름까지 정해 놓고
   * 누른 것을 문서 하나 때문에 통째로 버리면, 다시 처음부터 적게 된다.
   * 문서는 프로젝트 상세에서 다시 고를 수 있다.
   */
  async function finish(options: { extract: boolean }) {
    if (!token || busy) return;
    setBusy(true);
    setError('');
    try {
      const created = await createProject(token, name.trim(), description.trim() || undefined);

      if (chosen) {
        try {
          await saveProjectPrimaryDocument(token, created.proj_id, chosen.doc_id);
        } catch {
          // 프로젝트는 이미 만들어졌다. 업무 추출로 넘기지는 않는다 —
          // 기준 문서 없이 가면 거기서 다시 거절당한다.
          onCreated();
          setError('프로젝트는 만들었지만 기준 문서를 지정하지 못했습니다. 프로젝트 상세에서 다시 선택하세요.');
          setBusy(false);
          return;
        }
      }

      onCreated();

      if (options.extract) {
        navigate(
          `${PATHS.chat}?proj=${created.proj_id}&ask=${encodeURIComponent('이 프로젝트의 기준 문서에서 업무를 뽑아줘')}`,
        );
        return;
      }
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '프로젝트를 만들지 못했습니다.');
      setBusy(false);
    }
  }

  return (
    <div className={styles.backdrop}>
      <div
        ref={dialogRef}
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-label="새 프로젝트"
        tabIndex={-1}
        onKeyDown={handleDialogKeyDown}
      >
        <header className={styles.head}>
          <h2>
            {step === 'form' && '새 프로젝트'}
            {step === 'document' && '기준 문서를 찾았습니다'}
            {step === 'extract' && '업무를 뽑을까요?'}
          </h2>
          <button type="button" className={styles.close} onClick={onClose} aria-label="닫기">
            <Icon name="x" size={16} color="var(--color-muted)" />
          </button>
        </header>

        {error && <p className={styles.error}>{error}</p>}

        {step === 'form' && (
          <div className={styles.body}>
            <label className={styles.field}>
              <span>프로젝트 이름</span>
              <input
                type="text"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="예: 차세대 정보시스템 구축"
                autoFocus
              />
            </label>
            <label className={styles.field}>
              <span>
                무엇을 하는 프로젝트인가요? <em>기준 문서를 찾는 데 씁니다</em>
              </span>
              <textarea
                rows={3}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="한두 문장이면 충분합니다. 이름만으로는 문서를 좁히기 어렵습니다."
              />
            </label>
            <p className={styles.hint}>
              <Icon name="info" size={14} color="var(--color-muted)" />팀 문서 저장소에서 이 내용과 가장
              관련 문서를 검색해 표시합니다. 프로젝트는 마지막에 만들어집니다.
            </p>
          </div>
        )}

        {step === 'document' && (
          <div className={styles.body}>
            {searchError ? (
              // 못 찾은 것과 없는 것은 다르다. 못 찾았으면 그렇게 말한다.
              <p className={styles.warn}>{searchError} 문서는 나중에 프로젝트 상세에서 고를 수 있습니다.</p>
            ) : candidates.length === 0 ? (
              <p className={styles.warn}>
                이 프로젝트와 맞는 문서를 팀 저장소에서 찾지 못했습니다. Drive를 연결했는지, 문서가 처리를
                마쳤는지 확인해 주세요.
              </p>
            ) : (
              <>
                <p className={styles.lead}>
                  가장 가까운 문서입니다. <strong>맞는지 확인해 주세요.</strong> 어느 문서에서 업무를 추출하는지가
                  결과 전체의 전제가 됩니다.
                </p>
                <ul className={styles.candidates}>
                  {candidates.map((candidate) => (
                    <li key={candidate.doc_id}>
                      <button
                        type="button"
                        className={styles.candidate}
                        onClick={() => {
                          setChosen(candidate);
                          setStep('extract');
                        }}

                      >
                        <span className={styles.candidateHead}>
                          <strong>{candidate.file_name}</strong>
                          {/* 왜 올라왔는지를 말한다. 두 근거를 한 숫자로 뭉치면
                              그 수가 무엇인지 아무도 못 읽는다. */}
                          <span className={styles.score}>
                            {candidate.name_score >= 0.6 && (
                              <span className={styles.badge}>이름 일치</span>
                            )}
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
              </>
            )}
          </div>
        )}

        {step === 'extract' && (
          <div className={styles.body}>
            <p className={styles.lead}>
              <strong>{chosen?.file_name}</strong>{josa(chosen?.file_name ?? '', '을/를')} 기준 문서로 씁니다.
            </p>
            <p className={styles.hint}>
              <Icon name="info" size={14} color="var(--color-muted)" />이 문서에서 업무를 추출해 정리합니다. 몇
              분 걸리고, 결과는 승인 전까지 Jira에 올라가지 않습니다.
            </p>
          </div>
        )}

        <footer className={styles.foot}>
          {step === 'form' && (
            <>
              <Button variant="outline" size="sm" onClick={onClose}>
                취소
              </Button>
              <Button size="sm" onClick={handleFind} disabled={!name.trim() || busy}>
                {busy ? '문서를 찾는 중…' : '기준 문서 선택'}
              </Button>
            </>
          )}
          {step === 'document' && (
            <>
              <Button variant="outline" size="sm" onClick={onClose} disabled={busy}>
                취소
              </Button>
              {/* 문서를 못 찾았거나 나중에 고를 사람도 프로젝트는 원한다. */}
              <Button size="sm" onClick={() => void finish({ extract: false })} disabled={busy}>
                {busy ? '만드는 중…' : '기준 문서 없이 생성'}
              </Button>
            </>
          )}
          {step === 'extract' && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => void finish({ extract: false })}
                disabled={busy}
              >
                생성만 하기
              </Button>
              <Button size="sm" onClick={() => void finish({ extract: true })} disabled={busy}>
                {busy ? '만드는 중…' : '만들고 업무 추출'}
              </Button>
            </>
          )}
        </footer>
      </div>
    </div>
  );
}
