import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button, Checkbox, Modal } from '../../components';
import { ApiError } from '../../api/client';
import { connectPeopleDb, fetchPeopleDbIdentity } from '../../api/connectors';
import type { HrPerson } from '../../api/connectors';
import { createInvite, listInviteCandidates } from '../../api/invites';
import type { InviteCandidate } from '../../api/invites';
import styles from './PeopleDbConnectModal.module.css';

/**
 * HR 연결 3단계.
 *
 *   identity  가입 이메일로 찾은 본인이 맞는지 확인 (확인 전에는 매핑하지 않음)
 *   team      내 조직 인원 중 초대할 팀원 선택. 하위 조직은 접어 둔다
 *   codes     발급된 초대 코드. 원문은 서버에 없으므로 이 화면에서만 볼 수 있다
 */
type Step = 'identity' | 'team' | 'codes';

/** 전체 복사 버튼의 피드백 키. 개별 코드 키(코드 원문)와 겹치지 않게 둔다. */
const ALL_CODES_KEY = '__all__';

interface IssuedCode {
  name: string;
  code: string;
}

interface FailedInvite {
  name: string;
  reason: string;
}

export interface PeopleDbConnectModalProps {
  open: boolean;
  token: string;
  onClose: () => void;
  onConnected: () => void;
}

function personLabel(person: { name: string; job_role: string | null; email: string }) {
  return (
    <span className={styles.personLabel}>
      <strong>{person.name}</strong>
      {person.job_role && <span className={styles.personRole}> {person.job_role}</span>}
      <span className={styles.personEmail}>{person.email}</span>
    </span>
  );
}

export function PeopleDbConnectModal({
  open,
  token,
  onClose,
  onConnected,
}: PeopleDbConnectModalProps) {
  const [step, setStep] = useState<Step>('identity');
  const [identity, setIdentity] = useState<HrPerson | null>(null);
  const [myOrgId, setMyOrgId] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<InviteCandidate[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [showOtherOrgs, setShowOtherOrgs] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [rejected, setRejected] = useState(false);
  const [issued, setIssued] = useState<IssuedCode[]>([]);
  const [failed, setFailed] = useState<FailedInvite[]>([]);
  const [copyState, setCopyState] = useState<{ key: string; ok: boolean } | null>(null);
  const copyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (copyTimer.current) clearTimeout(copyTimer.current);
    },
    [],
  );

  async function handleCopy(text: string, key: string) {
    let ok = true;
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // 클립보드는 보안 컨텍스트에서만 쓸 수 있다(localhost는 허용). 실패하면
      // 코드가 화면에 그대로 있으니 직접 복사하면 된다.
      ok = false;
    }
    setCopyState({ key, ok });
    if (copyTimer.current) clearTimeout(copyTimer.current);
    copyTimer.current = setTimeout(() => setCopyState(null), 1800);
  }

  function copyLabel(key: string, idle: string) {
    if (copyState?.key !== key) return idle;
    return copyState.ok ? '복사됨' : '복사 실패';
  }

  const reset = useCallback(() => {
    setStep('identity');
    setIdentity(null);
    setMyOrgId(null);
    setCandidates([]);
    setSelected(new Set());
    setShowOtherOrgs(false);
    setBusy(false);
    setError('');
    setRejected(false);
    setIssued([]);
    setFailed([]);
  }, []);

  useEffect(() => {
    if (!open) return;

    reset();
    let cancelled = false;
    setBusy(true);
    fetchPeopleDbIdentity(token)
      .then((person) => {
        if (!cancelled) setIdentity(person);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : 'HR 정보를 불러오지 못했습니다.');
        }
      })
      .finally(() => {
        if (!cancelled) setBusy(false);
      });

    return () => {
      cancelled = true;
    };
  }, [open, token, reset]);

  const { myOrg, otherOrgs } = useMemo(() => {
    const mine: InviteCandidate[] = [];
    const others = new Map<string, InviteCandidate[]>();
    for (const candidate of candidates) {
      if (candidate.org_id === myOrgId) {
        mine.push(candidate);
      } else {
        const key = candidate.org_name ?? '소속 미상';
        others.set(key, [...(others.get(key) ?? []), candidate]);
      }
    }
    return { myOrg: mine, otherOrgs: [...others.entries()] };
  }, [candidates, myOrgId]);

  async function handleConfirmIdentity() {
    if (busy) return;

    setError('');
    setBusy(true);
    try {
      const summary = await connectPeopleDb(token);
      onConnected();
      setMyOrgId(summary.person?.org_id ?? null);

      const rows = await listInviteCandidates(token);
      setCandidates(rows);
      // 내 조직 인원은 기본으로 선택해 둔다. 하위 조직은 접혀 있고 선택도 안 된다.
      setSelected(
        new Set(rows.filter((r) => r.org_id === summary.person?.org_id).map((r) => r.person_id)),
      );
      setStep('team');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'HR 시스템을 연결하지 못했습니다.');
    } finally {
      setBusy(false);
    }
  }

  async function handleIssueInvites() {
    if (busy || selected.size === 0) return;

    setBusy(true);
    const codes: IssuedCode[] = [];
    const failures: FailedInvite[] = [];
    // 한 명이 실패해도 나머지는 발급한다 — "이미 초대됨"은 자연스러운 상황이다.
    for (const personId of selected) {
      const name = candidates.find((c) => c.person_id === personId)?.name ?? personId;
      try {
        const invite = await createInvite(token, personId);
        codes.push({ name, code: invite.code });
      } catch (err) {
        failures.push({
          name,
          reason: err instanceof ApiError ? err.message : '초대를 발급하지 못했습니다.',
        });
      }
    }
    setIssued(codes);
    setFailed(failures);
    setBusy(false);
    setStep('codes');
  }

  function toggle(personId: string, checked: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (checked) next.add(personId);
      else next.delete(personId);
      return next;
    });
  }

  function renderIdentity() {
    if (rejected) {
      return (
        <div className={styles.body}>
          <p>
            가입한 이메일이 본인 것인지 확인해 주세요. 다른 이메일로 가입하셨다면 회사 이메일로 다시
            가입하셔야 HR 정보와 연결됩니다.
          </p>
          <p className={styles.hint}>
            HR 정보는 이메일을 근거로 찾습니다. 목록에서 임의로 고를 수 없는 이유입니다.
          </p>
        </div>
      );
    }

    if (!identity) {
      return <p className={styles.body}>{busy ? 'HR 정보를 확인하는 중…' : (error || '—')}</p>;
    }

    return (
      <div className={styles.body}>
        <p>HR 시스템에서 아래 직원을 찾았습니다. 본인이 맞습니까?</p>
        <div className={styles.identityCard}>
          <p className={styles.identityName}>
            {identity.name}
            {identity.job_role && <span className={styles.personRole}> {identity.job_role}</span>}
          </p>
          <p className={styles.identityMeta}>{identity.org_name ?? '소속 미상'}</p>
          <p className={styles.identityMeta}>{identity.email}</p>
        </div>
      </div>
    );
  }

  function renderTeam() {
    return (
      <div className={styles.body}>
        <p>초대할 팀원을 선택하세요. 지금 넘어가고 나중에 설정에서 초대해도 됩니다.</p>

        {myOrg.length === 0 ? (
          <p className={styles.hint}>내 조직에 초대할 수 있는 인원이 없습니다.</p>
        ) : (
          <div className={styles.group}>
            <p className={styles.groupTitle}>내 팀 · {myOrg[0].org_name ?? '소속 미상'}</p>
            {myOrg.map((candidate) => (
              <Checkbox
                key={candidate.person_id}
                checked={selected.has(candidate.person_id)}
                onChange={(checked) => toggle(candidate.person_id, checked)}
                label={personLabel(candidate)}
              />
            ))}
          </div>
        )}

        {otherOrgs.length > 0 && (
          <div className={styles.group}>
            <button
              type="button"
              className={styles.disclosure}
              onClick={() => setShowOtherOrgs((prev) => !prev)}
            >
              {showOtherOrgs ? '▾' : '▸'} 하위 조직도 보기 (
              {otherOrgs.map(([name, rows]) => `${name} ${rows.length}`).join(' · ')})
            </button>
            {showOtherOrgs &&
              otherOrgs.map(([orgName, rows]) => (
                <div key={orgName} className={styles.subGroup}>
                  <p className={styles.groupTitle}>{orgName}</p>
                  {rows.map((candidate) => (
                    <Checkbox
                      key={candidate.person_id}
                      checked={selected.has(candidate.person_id)}
                      onChange={(checked) => toggle(candidate.person_id, checked)}
                      label={personLabel(candidate)}
                    />
                  ))}
                </div>
              ))}
          </div>
        )}
      </div>
    );
  }

  function renderCodes() {
    return (
      <div className={styles.body}>
        {issued.length > 0 && (
          <>
            <p>
              초대 코드를 발급했습니다. <strong>이 화면을 닫으면 다시 볼 수 없습니다</strong> — 지금
              복사해서 각자에게 전달해 주세요.
            </p>
            <div className={styles.codeList}>
              {issued.map((row) => (
                <div key={row.code} className={styles.codeRow}>
                  <span>{row.name}</span>
                  <code className={styles.code}>{row.code}</code>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => void handleCopy(row.code, row.code)}
                  >
                    {copyLabel(row.code, '복사')}
                  </Button>
                </div>
              ))}
            </div>
          </>
        )}

        {failed.length > 0 && (
          <div className={styles.failures}>
            <p className={styles.groupTitle}>발급하지 못한 인원</p>
            {failed.map((row) => (
              <p key={row.name} className={styles.hint}>
                {row.name} — {row.reason}
              </p>
            ))}
          </div>
        )}

        {issued.length === 0 && failed.length === 0 && (
          <p className={styles.hint}>발급된 초대가 없습니다.</p>
        )}
      </div>
    );
  }

  function renderFooter() {
    if (step === 'identity') {
      if (rejected) {
        return (
          <Button variant="primary" onClick={onClose}>
            닫기
          </Button>
        );
      }
      return (
        <>
          <Button variant="ghost" onClick={() => setRejected(true)} disabled={!identity || busy}>
            아닙니다
          </Button>
          <Button variant="primary" onClick={handleConfirmIdentity} disabled={!identity || busy}>
            {busy ? '연결 중…' : '본인입니다'}
          </Button>
        </>
      );
    }

    if (step === 'team') {
      return (
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            나중에 초대
          </Button>
          <Button
            variant="primary"
            onClick={handleIssueInvites}
            disabled={busy || selected.size === 0}
          >
            {busy ? '발급 중…' : `선택한 ${selected.size}명 초대하기`}
          </Button>
        </>
      );
    }

    return (
      <>
        {issued.length > 0 && (
          <Button
            variant="outline"
            onClick={() =>
              void handleCopy(
                issued.map((row) => `${row.name}: ${row.code}`).join('\n'),
                ALL_CODES_KEY,
              )
            }
          >
            {copyLabel(ALL_CODES_KEY, '전체 복사')}
          </Button>
        )}
        <Button variant="primary" onClick={onClose}>
          닫기
        </Button>
      </>
    );
  }

  const title =
    step === 'identity' ? 'HR 시스템 연결' : step === 'team' ? '팀원 초대' : '초대 코드';

  return (
    <Modal open={open} onClose={onClose} title={title} width={560} footer={renderFooter()}>
      {step === 'identity' && renderIdentity()}
      {step === 'team' && renderTeam()}
      {step === 'codes' && renderCodes()}
      {error && step !== 'identity' && (
        <p className={styles.errorText} role="alert">
          {error}
        </p>
      )}
    </Modal>
  );
}
