import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Button,
  Modal,
  OpsFilterBar,
  OpsPageHeader,
  OpsSearchField,
  OpsSectionCard,
  OpsStatusBadge,
  useToast,
} from '../../components';
import type { OpsTone } from '../../components';
import {
  createNotice,
  deleteNotice,
  fetchGuardrailEvents,
  fetchInviteTtl,
  fetchNotices,
  fetchPolicyChanges,
  saveInviteTtl,
  updateNotice,
} from '../../api/opsPolicies';
import type {
  GuardrailEvent,
  NoticeStatus,
  OpsNotice,
  OpsPolicyChange,
  ScheduleMode,
} from '../../api/opsPolicies';
import { ApiError } from '../../api/client';
import { loadOpsSession } from '../../utils/opsSession';
import { actionLabel } from '../../utils/auditActions';
import styles from '../OpsShared/OpsPages.module.css';

interface NoticeForm {
  notice_id: string | null;
  title: string;
  content: string;
  status: NoticeStatus;
  schedule_date: string;
  schedule_time: string;
  schedule_mode: ScheduleMode;
  reason: string;
}

const NOTICE_STATUS_LABELS: Record<NoticeStatus, string> = {
  PUBLISHED: '게시 중',
  SCHEDULED: '게시 예정',
  ENDED: '종료',
};

const NOTICE_STATUS_TONES: Record<NoticeStatus, OpsTone> = {
  PUBLISHED: 'success',
  SCHEDULED: 'info',
  ENDED: 'neutral',
};

const GUARDRAIL_RULE_LABELS: Record<string, string> = {
  PII: '민감정보',
  MODERATION: '유해 표현',
  BLOCKED_WORD: '차단 단어',
  // 등록된 외부 가드레일이 판단한 건. 무엇에 걸렸는지는 공급자마다 다르므로
  // `detail.guardrail` 로 따로 붙인다.
  PROVIDER: '외부 가드레일',
};

const GUARDRAIL_ACTION_LABELS: Record<string, string> = {
  MASKED: '가림',
  BLOCKED: '막음',
  // **검사를 못 한 건.** 지금까지는 로그 한 줄이 전부라, 검사가 통째로 빠져도
  // 이 목록에는 아무것도 안 뜨고 등록 화면은 「연결됨」을 계속 보여줬다.
  SKIPPED: '건너뜀',
};

const GUARDRAIL_STAGE_LABELS: Record<string, string> = {
  INPUT: '입력',
  OUTPUT: '출력',
  TOOL_RESULT: '도구 결과',
};

function pad2(value: number) {
  return String(value).padStart(2, '0');
}

function splitScheduleAt(iso: string) {
  const parsed = new Date(iso);
  return {
    date: `${parsed.getFullYear()}-${pad2(parsed.getMonth() + 1)}-${pad2(parsed.getDate())}`,
    time: `${pad2(parsed.getHours())}:${pad2(parsed.getMinutes())}`,
  };
}

function scheduleLabel(scheduleAt: string, mode: ScheduleMode) {
  const { date, time } = splitScheduleAt(scheduleAt);
  const [, month, day] = date.split('-');
  return `${month}.${day} ${time} ${mode === 'FROM' ? '부터' : '까지'}`;
}

function occurredAtLabel(iso: string) {
  const parsed = new Date(iso);
  return `${pad2(parsed.getMonth() + 1)}.${pad2(parsed.getDate())} ${pad2(parsed.getHours())}:${pad2(parsed.getMinutes())}`;
}

function noticeSnapshotLabel(snapshot: unknown): string {
  if (!snapshot || typeof snapshot !== 'object') return '공지 없음';
  const snap = snapshot as { title?: string; status?: NoticeStatus };
  const statusLabel = snap.status ? NOTICE_STATUS_LABELS[snap.status] ?? snap.status : '';
  return [statusLabel, snap.title].filter(Boolean).join(' · ') || '공지 없음';
}

function changeTitle(change: OpsPolicyChange): string {
  const payload = (change.payload ?? {}) as Record<string, unknown>;
  if (change.action === 'POLICY_INVITE_TTL_CHANGE') {
    return `초대 만료 기간 ${payload.before ?? '-'}일 → ${payload.after ?? '-'}일`;
  }
  if (change.action === 'NOTICE_CREATE') {
    return `시스템 공지 생성 · ${(payload.after as { title?: string } | undefined)?.title ?? ''}`;
  }
  if (change.action === 'NOTICE_UPDATE') {
    return `시스템 공지 수정 · ${(payload.after as { title?: string } | undefined)?.title ?? ''}`;
  }
  if (change.action === 'NOTICE_DELETE') {
    return `시스템 공지 삭제 · ${(payload.before as { title?: string } | undefined)?.title ?? ''}`;
  }
  return actionLabel(change.action);
}

function changeCompareValue(change: OpsPolicyChange, key: 'before' | 'after'): string {
  const payload = (change.payload ?? {}) as Record<string, unknown>;
  if (change.action === 'POLICY_INVITE_TTL_CHANGE') {
    const value = payload[key];
    return value != null ? `${value}일` : '알 수 없음';
  }
  if (change.action === 'NOTICE_DELETE' && key === 'after') return '삭제됨';
  if (change.action === 'NOTICE_CREATE' && key === 'before') return '공지 없음';
  return noticeSnapshotLabel(payload[key]);
}

function actorLabel(change: OpsPolicyChange) {
  return change.actor_display_name ?? change.actor_email ?? change.actor_account_id ?? '알 수 없음';
}

function reasonLabel(change: OpsPolicyChange) {
  const payload = (change.payload ?? {}) as Record<string, unknown>;
  const reason = payload.reason;
  return typeof reason === 'string' && reason ? reason : '입력된 사유 없음';
}

function defaultScheduleParts() {
  const now = new Date();
  return {
    date: `${now.getFullYear()}-${pad2(now.getMonth() + 1)}-${pad2(now.getDate())}`,
    time: `${pad2(now.getHours())}:${pad2(now.getMinutes())}`,
  };
}

const HISTORY_PREVIEW_COUNT = 5;

const POLICY_CHANGE_ACTIONS = [
  'POLICY_INVITE_TTL_CHANGE',
  'NOTICE_CREATE',
  'NOTICE_UPDATE',
  'NOTICE_DELETE',
] as const;

const POLICY_ACTION_TONES: Record<string, OpsTone> = {
  POLICY_INVITE_TTL_CHANGE: 'info',
  NOTICE_CREATE: 'success',
  NOTICE_UPDATE: 'warning',
  NOTICE_DELETE: 'danger',
};

function policyActionTone(action: string): OpsTone {
  return POLICY_ACTION_TONES[action] ?? 'neutral';
}

/** 막은 것과 가린 것을 색으로 가른다 — 막힌 발화는 사용자가 답을 못 받은 것이다. */
function guardrailEventTone(action: string): OpsTone {
  return action === 'BLOCKED' ? 'danger' : 'warning';
}

/** 못 부른 사유. 공급자가 아니라 **우리가 쓴 문구**라 그대로 보여줘도 된다. */
function guardrailSkipReason(event: GuardrailEvent): string | null {
  if (event.action !== 'SKIPPED') return null;
  const detail = event.detail ?? {};
  const reason = typeof detail.reason === 'string' ? detail.reason : null;
  const blocked = detail.blocked === true;
  // 어느 쪽이었는지 함께 말한다 — 같은 SKIPPED 라도 그 팀 설정에 따라 결과가
  // 정반대다. 팀 상세의 선택지와 **같은 말**을 쓴다(「연결 실패 시」).
  return `${reason ?? '이유를 알 수 없습니다.'} ${blocked ? '· 대화 차단' : '· 대화 계속'}`;
}

/** 발동 한 줄. `detail`에 원문이 없으므로 그대로 붙여 읽는다. */
function guardrailEventTitle(event: GuardrailEvent): string {
  const rule = GUARDRAIL_RULE_LABELS[event.rule] ?? event.rule;
  const stage = GUARDRAIL_STAGE_LABELS[event.stage] ?? event.stage;
  const detail = event.detail ?? {};
  const skip = guardrailSkipReason(event);
  if (skip) return `${stage} · ${rule} — ${skip}`;

  const word = typeof detail.word === 'string' ? detail.word : null;
  const category = typeof detail.category === 'string' ? detail.category : null;
  const score = typeof detail.score === 'number' ? detail.score : null;

  if (word) return `${stage} · ${rule} 「${word}」`;
  if (category) {
    // 카테고리 이름은 공급자가 주는 값을 그대로 쓴다 — 우리 목록으로 번역하면
    // 공급자가 바뀔 때 조용히 안 맞는다.
    return score != null ? `${stage} · ${rule} ${category} ${score}` : `${stage} · ${rule} ${category}`;
  }
  return `${stage} · ${rule}`;
}

export default function OpsPoliciesPage() {
  const { showToast } = useToast();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [savedInviteDays, setSavedInviteDays] = useState<number | null>(null);
  const [inviteDays, setInviteDays] = useState('');
  const [inviteReason, setInviteReason] = useState('');
  const [savingInvite, setSavingInvite] = useState(false);

  const [guardrailEvents, setGuardrailEvents] = useState<GuardrailEvent[] | null>(null);

  const [notices, setNotices] = useState<OpsNotice[] | null>(null);
  const [changes, setChanges] = useState<OpsPolicyChange[] | null>(null);
  const [selectedChangeId, setSelectedChangeId] = useState('');
  const [historyModalOpen, setHistoryModalOpen] = useState(false);
  const [historyActionFilter, setHistoryActionFilter] = useState('전체');
  const [historyQuery, setHistoryQuery] = useState('');

  const [selectedNotice, setSelectedNotice] = useState<OpsNotice | null>(null);
  const [form, setForm] = useState<NoticeForm | null>(null);
  const [modalMode, setModalMode] = useState<'view' | 'edit' | 'create' | null>(null);
  const [savingNotice, setSavingNotice] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<OpsNotice | null>(null);
  const [deleteReason, setDeleteReason] = useState('');
  const [deletingNotice, setDeletingNotice] = useState(false);

  async function load() {
    const currentSession = loadOpsSession();
    if (!currentSession) {
      navigate('/ops/login', { replace: true });
      return;
    }

    setLoading(true);
    setError('');
    try {
      const [ttl, eventRows, noticeRows, changeRows] = await Promise.all([
        fetchInviteTtl(currentSession.token),
        fetchGuardrailEvents(currentSession.token),
        fetchNotices(currentSession.token),
        fetchPolicyChanges(currentSession.token),
      ]);
      setGuardrailEvents(eventRows);
      setSavedInviteDays(ttl.days);
      setInviteDays(String(ttl.days));
      setNotices(noticeRows);
      setChanges(changeRows);
      setSelectedChangeId(changeRows[0]?.audit_id ?? '');
    } catch (thrown) {
      if (thrown instanceof ApiError && thrown.status === 401) {
        navigate('/ops/login', { replace: true });
        return;
      }
      setError(thrown instanceof ApiError ? thrown.message : '전역 정책을 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function reloadNotices() {
    const currentSession = loadOpsSession();
    if (!currentSession) return;
    try {
      setNotices(await fetchNotices(currentSession.token));
    } catch {
      // 새로고침 실패는 방금 완료한 작업 자체를 실패로 만들지 않는다 — 다음 새로고침에서 재시도.
    }
  }

  async function reloadChanges() {
    const currentSession = loadOpsSession();
    if (!currentSession) return;
    try {
      const rows = await fetchPolicyChanges(currentSession.token);
      setChanges(rows);
      setSelectedChangeId(rows[0]?.audit_id ?? '');
    } catch {
      // 위와 동일한 이유로 조용히 무시한다.
    }
  }

  const selectedChange = (changes ?? []).find((change) => change.audit_id === selectedChangeId) ?? (changes ?? [])[0] ?? null;

  function openHistoryModal() {
    setHistoryActionFilter('전체');
    setHistoryQuery('');
    setHistoryModalOpen(true);
  }

  function closeHistoryModal() {
    setHistoryModalOpen(false);
  }

  function pickHistoryChange(auditId: string) {
    setSelectedChangeId(auditId);
    setHistoryModalOpen(false);
  }

  async function saveInvitePolicy() {
    if (savingInvite) return;
    const currentSession = loadOpsSession();
    if (!currentSession) {
      navigate('/ops/login', { replace: true });
      return;
    }

    const numericDays = Number(inviteDays);
    if (!Number.isInteger(numericDays) || numericDays < 1 || numericDays > 90) {
      showToast('초대 만료 기간은 1일에서 90일 사이로 입력하세요.', 'error');
      return;
    }
    if (numericDays === savedInviteDays) {
      showToast('변경된 초대 정책이 없습니다.', 'info');
      return;
    }

    setSavingInvite(true);
    try {
      const result = await saveInviteTtl(currentSession.token, numericDays, inviteReason);
      setSavedInviteDays(result.days);
      setInviteDays(String(result.days));
      setInviteReason('');
      showToast('초대 정책을 저장했습니다.', 'success');
      await reloadChanges();
    } catch (thrown) {
      if (thrown instanceof ApiError && thrown.status === 401) {
        navigate('/ops/login', { replace: true });
        return;
      }
      showToast(thrown instanceof ApiError ? thrown.message : '요청을 처리하지 못했습니다.', 'error');
    } finally {
      setSavingInvite(false);
    }
  }

  function cancelInviteEdit() {
    setInviteDays(savedInviteDays != null ? String(savedInviteDays) : '');
    setInviteReason('');
  }

  function openCreate() {
    const { date, time } = defaultScheduleParts();
    setForm({
      notice_id: null,
      title: '',
      content: '',
      status: 'SCHEDULED',
      schedule_date: date,
      schedule_time: time,
      schedule_mode: 'FROM',
      reason: '',
    });
    setSelectedNotice(null);
    setModalMode('create');
  }

  function openView(notice: OpsNotice) {
    setSelectedNotice(notice);
    setForm(null);
    setModalMode('view');
  }

  function startEdit() {
    if (!selectedNotice) return;
    const { date, time } = splitScheduleAt(selectedNotice.schedule_at);
    setForm({
      notice_id: selectedNotice.notice_id,
      title: selectedNotice.title,
      content: selectedNotice.content,
      status: selectedNotice.status,
      schedule_date: date,
      schedule_time: time,
      schedule_mode: selectedNotice.schedule_mode,
      reason: '',
    });
    setModalMode('edit');
  }

  function cancelFormEdit() {
    if (modalMode === 'create') {
      closeModal();
      return;
    }
    setForm(null);
    setModalMode('view');
  }

  function closeModal() {
    setModalMode(null);
    setForm(null);
    setSelectedNotice(null);
  }

  async function saveNotice() {
    if (!form || savingNotice) return;
    const currentSession = loadOpsSession();
    if (!currentSession) {
      navigate('/ops/login', { replace: true });
      return;
    }

    if (!form.title.trim() || !form.content.trim()) {
      showToast('공지 제목과 내용을 입력하세요.', 'error');
      return;
    }
    if (!form.schedule_date || !form.schedule_time) {
      showToast('공지 날짜와 시간을 선택하세요.', 'error');
      return;
    }

    setSavingNotice(true);
    try {
      const input = {
        title: form.title,
        content: form.content,
        status: form.status,
        schedule_date: form.schedule_date,
        schedule_time: form.schedule_time,
        schedule_mode: form.schedule_mode,
        reason: form.reason,
      };
      const saved = form.notice_id
        ? await updateNotice(currentSession.token, form.notice_id, input)
        : await createNotice(currentSession.token, input);
      showToast(form.notice_id ? '시스템 공지를 수정했습니다.' : '시스템 공지를 생성했습니다.', 'success');
      setSelectedNotice(saved);
      setForm(null);
      setModalMode('view');
      await Promise.all([reloadNotices(), reloadChanges()]);
    } catch (thrown) {
      if (thrown instanceof ApiError && thrown.status === 401) {
        navigate('/ops/login', { replace: true });
        return;
      }
      showToast(thrown instanceof ApiError ? thrown.message : '요청을 처리하지 못했습니다.', 'error');
    } finally {
      setSavingNotice(false);
    }
  }

  function requestDelete() {
    if (!selectedNotice) return;
    setDeleteTarget(selectedNotice);
    setDeleteReason('');
  }

  async function confirmDelete() {
    if (!deleteTarget || deletingNotice) return;
    const currentSession = loadOpsSession();
    if (!currentSession) {
      navigate('/ops/login', { replace: true });
      return;
    }

    setDeletingNotice(true);
    try {
      await deleteNotice(currentSession.token, deleteTarget.notice_id, deleteReason);
      showToast('시스템 공지를 삭제했습니다.', 'success');
      setDeleteTarget(null);
      setDeleteReason('');
      closeModal();
      await Promise.all([reloadNotices(), reloadChanges()]);
    } catch (thrown) {
      if (thrown instanceof ApiError && thrown.status === 401) {
        navigate('/ops/login', { replace: true });
        return;
      }
      showToast(thrown instanceof ApiError ? thrown.message : '요청을 처리하지 못했습니다.', 'error');
    } finally {
      setDeletingNotice(false);
    }
  }

  if (loading && notices === null) {
    return (
      <div className={styles.page}>
        <OpsPageHeader title="전역 정책" />
        <p className={styles.inlineEmpty}>불러오는 중…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.page}>
        <OpsPageHeader title="전역 정책" />
        <p className={styles.inlineEmpty} role="alert">{error}</p>
        <Button variant="outline" onClick={load}>다시 시도</Button>
      </div>
    );
  }

  const noticeRows = notices ?? [];
  const changeRows = changes ?? [];
  const publishedCount = noticeRows.filter((notice) => notice.status === 'PUBLISHED').length;
  const scheduledCount = noticeRows.filter((notice) => notice.status === 'SCHEDULED').length;

  const filteredHistory = changeRows.filter((change) => {
    const matchesAction = historyActionFilter === '전체' || change.action === historyActionFilter;
    const normalized = historyQuery.trim().toLowerCase();
    const matchesQuery = !normalized || [changeTitle(change), actorLabel(change)].some((value) => value.toLowerCase().includes(normalized));
    return matchesAction && matchesQuery;
  });

  return (
    <div className={styles.page}>
      <OpsPageHeader
        title="전역 정책"
      />

      <OpsSectionCard
        title="초대 정책"
        subtitle={`현재 ${savedInviteDays ?? '-'}일 · 바꿔도 이미 발급된 초대에는 영향 없음`}
      >
        <div className={styles.inlinePolicy}>
          <div className={styles.fieldGroup}>
            <label htmlFor="invite-days">초대 코드 만료 기간</label>
            <input
              id="invite-days"
              type="number"
              min={1}
              max={90}
              value={inviteDays}
              onChange={(event) => setInviteDays(event.target.value)}
              disabled={savingInvite}
            />
          </div>
          <span className={styles.detailText}>일</span>
          <Button variant="primary" onClick={saveInvitePolicy} disabled={savingInvite}>
            {savingInvite ? '저장 중…' : '변경사항 저장'}
          </Button>
          <Button variant="secondary" onClick={cancelInviteEdit} disabled={savingInvite}>변경 취소</Button>
        </div>
        <div className={[styles.fieldGroup, styles.inlinePolicyReason].join(' ')}>
          <label htmlFor="invite-reason">변경 사유(선택)</label>
          <input
            id="invite-reason"
            value={inviteReason}
            onChange={(event) => setInviteReason(event.target.value)}
            placeholder="정책을 변경하는 이유를 입력하세요"
            disabled={savingInvite}
          />
        </div>
      </OpsSectionCard>

      <div className={styles.policyGrid}>
        <OpsSectionCard
          title="시스템 공지"
          subtitle={`전체 ${noticeRows.length} · 게시 중 ${publishedCount} · 게시 예정 ${scheduledCount}`}
          actions={<Button variant="primary" size="sm" onClick={openCreate}>새 공지 작성</Button>}
        >
          {noticeRows.length > 0 ? (
            <div className={styles.noticeList}>
              {noticeRows.map((notice) => (
                <div className={styles.noticeItem} key={notice.notice_id}>
                  <OpsStatusBadge tone={NOTICE_STATUS_TONES[notice.status]}>
                    {NOTICE_STATUS_LABELS[notice.status]}
                  </OpsStatusBadge>
                  <div>
                    <strong>{notice.title}</strong>
                    <p>{scheduleLabel(notice.schedule_at, notice.schedule_mode)}</p>
                  </div>
                  <div className={styles.compactActions}>
                    <button type="button" aria-label={`${notice.title} 보기`} onClick={() => openView(notice)}>보기</button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className={styles.inlineEmpty}>등록된 공지가 없습니다.</p>
          )}
        </OpsSectionCard>

        <OpsSectionCard
          title="정책 변경 이력"
          actions={changeRows.length > 0 ? (
            <Button variant="outline" size="sm" onClick={openHistoryModal}>전체 보기</Button>
          ) : undefined}
        >
          {changeRows.length > 0 ? (
            <div className={styles.policyHistory}>
              {changeRows.slice(0, HISTORY_PREVIEW_COUNT).map((change) => (
                <button
                  key={change.audit_id}
                  type="button"
                  className={[styles.historyButton, selectedChange?.audit_id === change.audit_id ? styles.historyButtonActive : ''].filter(Boolean).join(' ')}
                  onClick={() => setSelectedChangeId(change.audit_id)}
                >
                  <span className={styles.historyRow}>
                    <OpsStatusBadge tone={policyActionTone(change.action)}>{actionLabel(change.action)}</OpsStatusBadge>
                    <span className={styles.historyTitle}>{changeTitle(change)}</span>
                  </span>
                  <span className={styles.historyMeta}>변경자 {actorLabel(change)}</span>
                </button>
              ))}
            </div>
          ) : (
            <p className={styles.inlineEmpty}>정책 변경 이력이 없습니다.</p>
          )}
        </OpsSectionCard>

        {/* 정한 것(위)과 걸린 것(아래)을 한 화면에서 본다 — 기준값을 어디로
            옮길지는 실제로 무엇이 걸렸는지를 봐야 정할 수 있다. */}
        <OpsSectionCard
          title="가드레일 발동"
          subtitle={guardrailEvents ? `최근 ${guardrailEvents.length}건` : ''}
        >
          {guardrailEvents && guardrailEvents.length > 0 ? (
            <div className={styles.policyHistory}>
              {guardrailEvents.slice(0, HISTORY_PREVIEW_COUNT).map((event) => (
                <div key={event.event_id} className={styles.historyButton}>
                  <span className={styles.historyRow}>
                    <OpsStatusBadge tone={guardrailEventTone(event.action)}>
                      {GUARDRAIL_ACTION_LABELS[event.action] ?? event.action}
                    </OpsStatusBadge>
                    <span className={styles.historyTitle}>{guardrailEventTitle(event)}</span>
                  </span>
                  <span className={styles.historyMeta}>
                    {occurredAtLabel(event.occurred_at)} · {event.account_display_name ?? '알 수 없음'}
                    {event.team_name ? ` · ${event.team_name}` : ''}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className={styles.inlineEmpty}>가드레일이 발동한 기록이 없습니다.</p>
          )}
        </OpsSectionCard>
      </div>

      {selectedChange && (
        <OpsSectionCard
          title={`선택 변경 · ${changeTitle(selectedChange)}`}
        >
          <div className={styles.compareFlow}>
            <div className={styles.compareCard}><span>변경 전</span><strong>{changeCompareValue(selectedChange, 'before')}</strong></div>
            <span className={styles.compareArrow} aria-label="변경 후로 이동">→</span>
            <div className={styles.compareCard}><span>변경 후</span><strong>{changeCompareValue(selectedChange, 'after')}</strong></div>
          </div>
          <dl className={styles.policyMetadata}>
            <div><dt>변경 시각</dt><dd>{occurredAtLabel(selectedChange.occurred_at)}</dd></div>
            <div><dt>변경 사유</dt><dd>{reasonLabel(selectedChange)}</dd></div>
            <div><dt>변경자</dt><dd>{actorLabel(selectedChange)}</dd></div>
          </dl>
        </OpsSectionCard>
      )}

      <Modal
        open={modalMode !== null && (modalMode === 'create' ? form !== null : selectedNotice !== null)}
        onClose={closeModal}
        title={modalMode === 'create' ? '새 시스템 공지' : modalMode === 'edit' ? '시스템 공지 수정' : '시스템 공지 상세'}
        width={600}
        footer={modalMode === 'view' ? (
          <>
            <Button variant="secondary" onClick={closeModal}>닫기</Button>
            <Button variant="danger" onClick={requestDelete}>삭제</Button>
            <Button variant="primary" onClick={startEdit}>수정</Button>
          </>
        ) : (
          <>
            <Button variant="secondary" onClick={cancelFormEdit} disabled={savingNotice}>취소</Button>
            <Button variant="primary" onClick={saveNotice} disabled={savingNotice}>
              {savingNotice ? '저장 중…' : '저장'}
            </Button>
          </>
        )}
      >
        {selectedNotice && modalMode === 'view' && (
          <div className={styles.noticeDetail}>
            <div className={styles.noticeDetailTopline}>
              <OpsStatusBadge tone={NOTICE_STATUS_TONES[selectedNotice.status]}>
                {NOTICE_STATUS_LABELS[selectedNotice.status]}
              </OpsStatusBadge>
              <span>{scheduleLabel(selectedNotice.schedule_at, selectedNotice.schedule_mode)}</span>
            </div>
            <h3>{selectedNotice.title}</h3>
            <p>{selectedNotice.content}</p>
          </div>
        )}

        {form && modalMode !== 'view' && (
          <div className={styles.formGrid}>
            <div className={styles.fieldGroup}>
              <label htmlFor="notice-title">공지 제목</label>
              <input
                id="notice-title"
                value={form.title}
                onChange={(event) => setForm({ ...form, title: event.target.value })}
                disabled={savingNotice}
              />
            </div>
            <div className={styles.fieldGroup}>
              <label htmlFor="notice-content">공지 내용</label>
              <textarea
                id="notice-content"
                value={form.content}
                onChange={(event) => setForm({ ...form, content: event.target.value })}
                disabled={savingNotice}
              />
            </div>
            <div className={styles.fieldGroup}>
              <label htmlFor="notice-status">게시 상태</label>
              <select
                id="notice-status"
                value={form.status}
                onChange={(event) => setForm({ ...form, status: event.target.value as NoticeStatus })}
                disabled={savingNotice}
              >
                <option value="PUBLISHED">게시 중</option>
                <option value="SCHEDULED">게시 예정</option>
                <option value="ENDED">종료</option>
              </select>
            </div>
            <fieldset className={styles.scheduleFieldset}>
              <legend>게시 일정</legend>
              <div className={styles.scheduleGrid}>
                <div className={styles.fieldGroup}>
                  <label htmlFor="notice-date">날짜</label>
                  <input
                    id="notice-date"
                    type="date"
                    value={form.schedule_date}
                    onChange={(event) => setForm({ ...form, schedule_date: event.target.value })}
                    disabled={savingNotice}
                  />
                </div>
                <div className={styles.fieldGroup}>
                  <label htmlFor="notice-time">시간</label>
                  <input
                    id="notice-time"
                    type="time"
                    value={form.schedule_time}
                    onChange={(event) => setForm({ ...form, schedule_time: event.target.value })}
                    disabled={savingNotice}
                  />
                </div>
                <div className={styles.fieldGroup}>
                  <label htmlFor="notice-schedule-mode">적용 기준</label>
                  <select
                    id="notice-schedule-mode"
                    value={form.schedule_mode}
                    onChange={(event) => setForm({ ...form, schedule_mode: event.target.value as ScheduleMode })}
                    disabled={savingNotice}
                  >
                    <option value="FROM">부터</option>
                    <option value="UNTIL">까지</option>
                  </select>
                </div>
              </div>
            </fieldset>
            <div className={styles.fieldGroup}>
              <label htmlFor="notice-reason">변경 사유(선택)</label>
              <input
                id="notice-reason"
                value={form.reason}
                onChange={(event) => setForm({ ...form, reason: event.target.value })}
                disabled={savingNotice}
              />
            </div>
          </div>
        )}
      </Modal>

      <Modal
        open={historyModalOpen}
        onClose={closeHistoryModal}
        title="정책 변경 이력 전체 보기"
        width={640}
        footer={<Button variant="secondary" onClick={closeHistoryModal}>닫기</Button>}
      >
        <OpsFilterBar>
          <select
            value={historyActionFilter}
            onChange={(event) => setHistoryActionFilter(event.target.value)}
            aria-label="변경 유형"
          >
            <option value="전체">전체</option>
            {POLICY_CHANGE_ACTIONS.map((action) => (
              <option key={action} value={action}>{actionLabel(action)}</option>
            ))}
          </select>
          <OpsSearchField value={historyQuery} onChange={setHistoryQuery} placeholder="제목 또는 변경자 검색" />
        </OpsFilterBar>

        {filteredHistory.length > 0 ? (
          <div className={styles.policyHistory} style={{ maxHeight: 420, overflowY: 'auto', paddingRight: 4 }}>
            {filteredHistory.map((change) => (
              <button
                key={change.audit_id}
                type="button"
                className={[styles.historyButton, selectedChange?.audit_id === change.audit_id ? styles.historyButtonActive : ''].filter(Boolean).join(' ')}
                onClick={() => pickHistoryChange(change.audit_id)}
              >
                <span className={styles.historyRow}>
                  <OpsStatusBadge tone={policyActionTone(change.action)}>{actionLabel(change.action)}</OpsStatusBadge>
                  <span className={styles.historyTitle}>{changeTitle(change)}</span>
                </span>
                <span className={styles.historyMeta}>변경자 {actorLabel(change)} · {occurredAtLabel(change.occurred_at)}</span>
              </button>
            ))}
          </div>
        ) : (
          <p className={styles.inlineEmpty}>조건에 맞는 정책 변경 이력이 없습니다.</p>
        )}
      </Modal>

      <Modal
        open={deleteTarget !== null}
        onClose={() => (deletingNotice ? null : setDeleteTarget(null))}
        title="시스템 공지 삭제"
        footer={(
          <>
            <Button variant="secondary" onClick={() => setDeleteTarget(null)} disabled={deletingNotice}>취소</Button>
            <Button variant="danger" onClick={confirmDelete} disabled={deletingNotice}>
              {deletingNotice ? '삭제 중…' : '삭제'}
            </Button>
          </>
        )}
      >
        <p className={styles.modalCopy}>‘{deleteTarget?.title}’ 공지를 삭제합니다. 삭제 작업은 정책 변경 이력에 기록됩니다.</p>
        <div className={styles.fieldGroup}>
          <label htmlFor="notice-delete-reason">삭제 사유(선택)</label>
          <input
            id="notice-delete-reason"
            value={deleteReason}
            onChange={(event) => setDeleteReason(event.target.value)}
            disabled={deletingNotice}
          />
        </div>
      </Modal>
    </div>
  );
}
