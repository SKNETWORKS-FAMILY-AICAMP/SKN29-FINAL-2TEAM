import { useState } from 'react';
import {
  Button,
  Modal,
  OpsPageHeader,
  OpsSectionCard,
  OpsStatusBadge,
  useToast,
} from '../../components';
import styles from '../OpsShared/OpsPages.module.css';

type NoticeStatus = '게시 중' | '게시 예정' | '종료';
type ScheduleMode = '부터' | '까지';

interface Notice {
  id: number;
  title: string;
  content: string;
  status: NoticeStatus;
  scheduleDate: string;
  scheduleTime: string;
  scheduleMode: ScheduleMode;
}

interface PolicyChange {
  id: number;
  title: string;
  before: string;
  after: string;
  appliedAt: string;
  reason: string;
  author: string;
}

const INITIAL_NOTICES: Notice[] = [
  { id: 1, title: '서비스 점검 안내', content: '점검 시간 동안 일부 연결 서비스 확인이 지연될 수 있습니다.', status: '게시 중', scheduleDate: '2026-07-30', scheduleTime: '18:00', scheduleMode: '까지' },
  { id: 2, title: '새 기능 배포 안내', content: '감사 로그 단계별 조회 기능을 배포합니다.', status: '게시 예정', scheduleDate: '2026-07-31', scheduleTime: '09:00', scheduleMode: '부터' },
  { id: 3, title: '개인정보 처리방침 개정', content: '개정된 처리방침 적용이 완료되었습니다.', status: '종료', scheduleDate: '2026-07-28', scheduleTime: '18:00', scheduleMode: '까지' },
];

const INITIAL_CHANGES: PolicyChange[] = [
  { id: 1, title: '초대 만료 기간 14일 → 7일', before: '14일', after: '7일', appliedAt: '07.28 15:30 이후 신규 발급 초대', reason: '장기 미수락 초대의 오사용 위험 감소', author: '김운영' },
  { id: 2, title: '서비스 점검 공지 게시', before: '게시 전', after: '게시 중', appliedAt: '07.29 09:00', reason: '정기 점검 사전 안내', author: '이관리' },
  { id: 3, title: '시스템 공지 게시 종료', before: '게시 중', after: '종료', appliedAt: '07.29 18:00', reason: '공지 유효기간 종료', author: '김운영' },
];

function noticeTone(status: NoticeStatus) {
  if (status === '게시 중') return 'success';
  if (status === '게시 예정') return 'info';
  return 'neutral';
}

function formatSchedule(notice: Notice) {
  const [, month = '', day = ''] = notice.scheduleDate.split('-');
  return `${month}.${day} ${notice.scheduleTime} ${notice.scheduleMode}`;
}

function noticeSnapshot(notice: Notice) {
  return `${notice.status} · ${formatSchedule(notice)}`;
}

export default function OpsPoliciesPage() {
  const { showToast } = useToast();
  const [inviteDays, setInviteDays] = useState('7');
  const [savedInviteDays, setSavedInviteDays] = useState('7');
  const [notices, setNotices] = useState(INITIAL_NOTICES);
  const [changes, setChanges] = useState(INITIAL_CHANGES);
  const [selectedChangeId, setSelectedChangeId] = useState(1);
  const [editingNotice, setEditingNotice] = useState<Notice | null>(null);
  const [noticeMode, setNoticeMode] = useState<'view' | 'edit' | 'create' | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Notice | null>(null);

  const selectedChange = changes.find((change) => change.id === selectedChangeId) ?? changes[0];

  function addChange(change: Omit<PolicyChange, 'id'>) {
    const next = { ...change, id: Date.now() };
    setChanges((current) => [next, ...current]);
    setSelectedChangeId(next.id);
  }

  function closeNotice() {
    setNoticeMode(null);
    setEditingNotice(null);
  }

  function saveInvitePolicy() {
    const numericDays = Number(inviteDays);
    if (!Number.isInteger(numericDays) || numericDays < 1 || numericDays > 90) {
      showToast('초대 만료 기간은 1일에서 90일 사이로 입력해 주세요.', 'error');
      return;
    }
    if (inviteDays === savedInviteDays) {
      showToast('변경된 초대 정책이 없습니다.', 'info');
      return;
    }
    const before = savedInviteDays;
    setSavedInviteDays(inviteDays);
    addChange({
      title: `초대 만료 기간 ${before}일 → ${inviteDays}일`,
      before: `${before}일`,
      after: `${inviteDays}일`,
      appliedAt: '저장 시점 이후 신규 발급 초대',
      reason: '운영자 정책 변경',
      author: '현재 운영자',
    });
    showToast('초대 정책을 저장했습니다.', 'success');
  }

  function openCreate() {
    setEditingNotice({
      id: 0,
      title: '',
      content: '',
      status: '게시 예정',
      scheduleDate: '2026-07-31',
      scheduleTime: '09:00',
      scheduleMode: '부터',
    });
    setNoticeMode('create');
  }

  function openNotice(notice: Notice) {
    setEditingNotice({ ...notice });
    setNoticeMode('view');
  }

  function startEditing() {
    if (!editingNotice) return;
    setEditingNotice({ ...editingNotice });
    setNoticeMode('edit');
  }

  function cancelEditing() {
    if (!editingNotice) return;
    const original = notices.find((notice) => notice.id === editingNotice.id);
    if (original) {
      setEditingNotice({ ...original });
      setNoticeMode('view');
    } else {
      closeNotice();
    }
  }

  function saveNotice() {
    if (!editingNotice?.title.trim() || !editingNotice.content.trim()) {
      showToast('공지 제목과 내용을 입력해 주세요.', 'error');
      return;
    }
    if (!editingNotice.scheduleDate || !editingNotice.scheduleTime) {
      showToast('공지 날짜와 시간을 선택해 주세요.', 'error');
      return;
    }

    if (noticeMode === 'create') {
      const nextNotice = { ...editingNotice, id: Date.now() };
      setNotices((current) => [nextNotice, ...current]);
      addChange({
        title: `시스템 공지 생성 · ${nextNotice.title}`,
        before: '공지 없음',
        after: noticeSnapshot(nextNotice),
        appliedAt: formatSchedule(nextNotice),
        reason: '시스템 공지 생성',
        author: '현재 운영자',
      });
      setEditingNotice(nextNotice);
      setNoticeMode('view');
      showToast('시스템 공지를 생성했습니다.', 'success');
      return;
    }

    const before = notices.find((notice) => notice.id === editingNotice.id);
    setNotices((current) => current.map((notice) => notice.id === editingNotice.id ? editingNotice : notice));
    addChange({
      title: `시스템 공지 수정 · ${editingNotice.title}`,
      before: before ? noticeSnapshot(before) : '이전 정보 없음',
      after: noticeSnapshot(editingNotice),
      appliedAt: formatSchedule(editingNotice),
      reason: '시스템 공지 내용 또는 게시 일정 변경',
      author: '현재 운영자',
    });
    setNoticeMode('view');
    showToast('시스템 공지를 수정했습니다.', 'success');
  }

  function requestDelete() {
    if (!editingNotice) return;
    setDeleteTarget(editingNotice);
  }

  function deleteNotice() {
    if (!deleteTarget) return;
    setNotices((current) => current.filter((notice) => notice.id !== deleteTarget.id));
    addChange({
      title: `시스템 공지 삭제 · ${deleteTarget.title}`,
      before: noticeSnapshot(deleteTarget),
      after: '삭제',
      appliedAt: '현재 화면에서 처리',
      reason: '운영자 공지 삭제',
      author: '현재 운영자',
    });
    setDeleteTarget(null);
    closeNotice();
    showToast('시스템 공지를 삭제했습니다.', 'success');
  }

  return (
    <div className={styles.page}>
      <OpsPageHeader
        title="전역 정책"
        description="플랫폼 전체에 적용되는 최소한의 운영 상수와 시스템 공지를 관리합니다."
      />

      <OpsSectionCard
        title="초대 정책"
        subtitle={`신규 발급 초대부터 적용 · 현재 ${savedInviteDays}일 · 변경 시 기존 발급 건에는 영향 없음`}
      >
        <div className={styles.inlinePolicy}>
          <div className={styles.fieldGroup}>
            <label htmlFor="invite-days">초대 기록 만료 기간</label>
            <input id="invite-days" type="number" min={1} max={90} value={inviteDays} onChange={(event) => setInviteDays(event.target.value)} />
          </div>
          <span className={styles.detailText}>일</span>
          <Button variant="primary" onClick={saveInvitePolicy}>변경사항 저장</Button>
          <Button variant="secondary" onClick={() => setInviteDays(savedInviteDays)}>변경 취소</Button>
        </div>
      </OpsSectionCard>

      <div className={styles.policyGrid}>
        <OpsSectionCard
          title="시스템 공지"
          subtitle={`전체 ${notices.length} · 게시 중 ${notices.filter((item) => item.status === '게시 중').length} · 게시 예정 ${notices.filter((item) => item.status === '게시 예정').length}`}
          actions={<Button variant="primary" size="sm" onClick={openCreate}>새 공지</Button>}
        >
          <div className={styles.noticeList}>
            {notices.map((notice) => (
              <div className={styles.noticeItem} key={notice.id}>
                <OpsStatusBadge tone={noticeTone(notice.status)}>{notice.status}</OpsStatusBadge>
                <div>
                  <strong>{notice.title}</strong>
                  <p>{formatSchedule(notice)}</p>
                </div>
                <div className={styles.compactActions}>
                  <button type="button" aria-label={`${notice.title} 보기`} onClick={() => openNotice(notice)}>보기</button>
                </div>
              </div>
            ))}
          </div>
        </OpsSectionCard>

        <OpsSectionCard title="최근 정책 변경" subtitle="항목을 선택하면 변경 전후와 적용 근거를 확인할 수 있습니다.">
          <div className={styles.policyHistory}>
            {changes.map((change) => (
              <button
                key={change.id}
                type="button"
                className={[styles.historyButton, selectedChange.id === change.id ? styles.historyButtonActive : ''].filter(Boolean).join(' ')}
                onClick={() => setSelectedChangeId(change.id)}
              >
                {change.title}
                <span className={styles.historyMeta}>변경자 {change.author}</span>
              </button>
            ))}
          </div>
        </OpsSectionCard>
      </div>

      <OpsSectionCard title={`선택 변경 · ${selectedChange.title}`} subtitle="변경 영향과 적용 근거를 한눈에 확인합니다. 저장 내용은 감사 대상으로 관리됩니다.">
        <div className={styles.compareFlow}>
          <div className={styles.compareCard}><span>변경 전</span><strong>{selectedChange.before}</strong></div>
          <span className={styles.compareArrow} aria-label="변경 후로 이동">→</span>
          <div className={styles.compareCard}><span>변경 후</span><strong>{selectedChange.after}</strong></div>
        </div>
        <dl className={styles.policyMetadata}>
          <div><dt>적용 시점</dt><dd>{selectedChange.appliedAt}</dd></div>
          <div><dt>변경 사유</dt><dd>{selectedChange.reason}</dd></div>
          <div><dt>변경자</dt><dd>{selectedChange.author}</dd></div>
        </dl>
      </OpsSectionCard>

      <Modal
        open={noticeMode !== null && editingNotice !== null}
        onClose={closeNotice}
        title={noticeMode === 'create' ? '새 시스템 공지' : noticeMode === 'edit' ? '시스템 공지 수정' : '시스템 공지 상세'}
        width={600}
        footer={noticeMode === 'view' ? (
          <>
            <Button variant="secondary" onClick={closeNotice}>닫기</Button>
            <Button variant="danger" onClick={requestDelete}>삭제</Button>
            <Button variant="primary" onClick={startEditing}>수정</Button>
          </>
        ) : (
          <>
            <Button variant="secondary" onClick={noticeMode === 'edit' ? cancelEditing : closeNotice}>취소</Button>
            <Button variant="primary" onClick={saveNotice}>저장</Button>
          </>
        )}
      >
        {editingNotice && noticeMode === 'view' && (
          <div className={styles.noticeDetail}>
            <div className={styles.noticeDetailTopline}>
              <OpsStatusBadge tone={noticeTone(editingNotice.status)}>{editingNotice.status}</OpsStatusBadge>
              <span>{formatSchedule(editingNotice)}</span>
            </div>
            <h3>{editingNotice.title}</h3>
            <p>{editingNotice.content}</p>
          </div>
        )}

        {editingNotice && noticeMode !== 'view' && (
          <div className={styles.formGrid}>
            <div className={styles.fieldGroup}>
              <label htmlFor="notice-title">공지 제목</label>
              <input id="notice-title" value={editingNotice.title} onChange={(event) => setEditingNotice({ ...editingNotice, title: event.target.value })} />
            </div>
            <div className={styles.fieldGroup}>
              <label htmlFor="notice-content">공지 내용</label>
              <textarea id="notice-content" value={editingNotice.content} onChange={(event) => setEditingNotice({ ...editingNotice, content: event.target.value })} />
            </div>
            <div className={styles.fieldGroup}>
              <label htmlFor="notice-status">게시 상태</label>
              <select id="notice-status" value={editingNotice.status} onChange={(event) => setEditingNotice({ ...editingNotice, status: event.target.value as NoticeStatus })}>
                <option>게시 중</option>
                <option>게시 예정</option>
                <option>종료</option>
              </select>
            </div>
            <fieldset className={styles.scheduleFieldset}>
              <legend>게시 일정</legend>
              <div className={styles.scheduleGrid}>
                <div className={styles.fieldGroup}>
                  <label htmlFor="notice-date">날짜</label>
                  <input id="notice-date" type="date" value={editingNotice.scheduleDate} onChange={(event) => setEditingNotice({ ...editingNotice, scheduleDate: event.target.value })} />
                </div>
                <div className={styles.fieldGroup}>
                  <label htmlFor="notice-time">시간</label>
                  <input id="notice-time" type="time" value={editingNotice.scheduleTime} onChange={(event) => setEditingNotice({ ...editingNotice, scheduleTime: event.target.value })} />
                </div>
                <div className={styles.fieldGroup}>
                  <label htmlFor="notice-schedule-mode">적용 기준</label>
                  <select id="notice-schedule-mode" value={editingNotice.scheduleMode} onChange={(event) => setEditingNotice({ ...editingNotice, scheduleMode: event.target.value as ScheduleMode })}>
                    <option>부터</option>
                    <option>까지</option>
                  </select>
                </div>
              </div>
            </fieldset>
          </div>
        )}
      </Modal>

      <Modal
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        title="시스템 공지 삭제"
        footer={(
          <>
            <Button variant="secondary" onClick={() => setDeleteTarget(null)}>취소</Button>
            <Button variant="danger" onClick={deleteNotice}>삭제</Button>
          </>
        )}
      >
        <p className={styles.modalCopy}>‘{deleteTarget?.title}’ 공지를 삭제합니다. 삭제 작업은 최근 정책 변경에 기록됩니다.</p>
      </Modal>
    </div>
  );
}
