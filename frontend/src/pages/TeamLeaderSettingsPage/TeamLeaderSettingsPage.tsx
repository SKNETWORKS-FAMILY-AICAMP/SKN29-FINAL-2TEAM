import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Badge,
  Button,
  Card,
  Icon,
  Input,
  Modal,
  Select,
  AvatarPicker,
  PasswordChangeCard,
  SettingsLayout,
  SkillList,
  useToast,
} from '../../components';
import type { BadgeTone, SettingsNavItem } from '../../components';
import { ApiError } from '../../api/client';
import { fetchCurrentAccount } from '../../api/auth';
import type { Account } from '../../api/auth';
import { listConnectors } from '../../api/connectors';
import { CONNECTOR_TYPE_BY_ID } from '../../api/connectors';
import { createInvite, listInviteCandidates, revokeInvite } from '../../api/invites';
import type { InviteCandidate, InviteStatus, IssuedInvite } from '../../api/invites';
import {
  fetchTeamSettings,
  listTeamMembers,
  removeTeamMember,
  saveTeamSettings,
} from '../../api/teams';
import type { TeamMember, TeamSettings } from '../../api/teams';
import { CONNECTOR_DEFS } from '../../data/connectorDefs';
import { PATHS } from '../../routes';
import { loadConnectorStatuses } from '../../utils/connectorStatus';
import type { ConnectorStatus } from '../../utils/connectorStatus';
import { loadSessionToken } from '../../utils/session';
import styles from './TeamLeaderSettingsPage.module.css';

const NAV_ITEMS: SettingsNavItem[] = [
  { id: 'profile', label: '내 프로필', icon: 'user' },
  { id: 'skills', label: '보유 스킬', icon: 'sparkles' },
  { id: 'password', label: '비밀번호 변경', icon: 'lock' },
  { id: 'connectors', label: '연동 관리', icon: 'link' },
  { id: 'team', label: '팀원 관리', icon: 'users' },
  { id: 'workload', label: '팀 업무량 기준', icon: 'sliders' },
];

const INVITE_STATUS_LABEL: Record<InviteStatus, string> = {
  PENDING: '초대됨',
  ACCEPTED: '가입 완료',
  EXPIRED: '만료됨',
  REVOKED: '취소됨',
};

const INVITE_STATUS_TONE: Record<InviteStatus, BadgeTone> = {
  PENDING: 'warning',
  ACCEPTED: 'success',
  EXPIRED: 'neutral',
  REVOKED: 'neutral',
};

const DATE_FORMAT = new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium' });

export interface TeamLeaderSettingsPageProps {
  /** Settings 허브의 「팀」 탭 안에서 렌더될 때는 자체 껍데기를 그리지 않는다. */
  embedded?: boolean;
}

export default function TeamLeaderSettingsPage({ embedded = false }: TeamLeaderSettingsPageProps = {}) {
  const navigate = useNavigate();
  const { showToast } = useToast();

  const [connectorStatuses, setConnectorStatuses] = useState<Record<string, ConnectorStatus>>(() =>
    loadConnectorStatuses(Object.fromEntries(CONNECTOR_DEFS.map((c) => [c.id, c.initialStatus]))),
  );
  // 빈 문자열이 "설정 안 함"이다. 0과 구분해야 하므로 숫자로 들고 있지 않는다.
  const [settings, setSettings] = useState<TeamSettings | null>(null);
  const [baseHours, setBaseHours] = useState('');
  const [overloadThreshold, setOverloadThreshold] = useState('');
  const [workloadWeeks, setWorkloadWeeks] = useState('');
  const [savingSettings, setSavingSettings] = useState(false);
  const [account, setAccount] = useState<Account | null>(null);

  const [token] = useState(loadSessionToken);
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [memberError, setMemberError] = useState('');
  const [inviteModalOpen, setInviteModalOpen] = useState(false);
  const [candidates, setCandidates] = useState<InviteCandidate[]>([]);
  const [selectedPersonId, setSelectedPersonId] = useState('');
  const [issuing, setIssuing] = useState(false);
  const [issued, setIssued] = useState<IssuedInvite | null>(null);

  // 명부가 주인공이다. 초대는 각 팀원의 계정 상태로 붙는다 — 초대 목록을 따로
  // 받지 않는다.
  const refreshMembers = useCallback(async () => {
    if (!token) {
      setMemberError('로그인해야 팀원 목록을 볼 수 있습니다.');
      return;
    }
    try {
      setMembers(await listTeamMembers(token));
      setMemberError('');
    } catch (error) {
      setMemberError(error instanceof ApiError ? error.message : '팀원 목록을 불러오지 못했습니다.');
    }
  }, [token]);

  useEffect(() => {
    void refreshMembers();
  }, [refreshMembers]);

  const hrHoursHint = (() => {
    const min = settings?.hr_wk_hours_min;
    const max = settings?.hr_wk_hours_max;
    if (min === null || min === undefined) return '인사 시스템 값';
    return min === max ? `주 ${min}시간` : `주 ${min}~${max}시간`;
  })();

  const applySettings = useCallback((row: TeamSettings) => {
    setSettings(row);
    setBaseHours(row.capacity_wk_hours === null ? '' : String(row.capacity_wk_hours));
    setOverloadThreshold(row.overload_pct === null ? '' : String(row.overload_pct));
    setWorkloadWeeks(row.workload_weeks === null ? '' : String(row.workload_weeks));
  }, []);

  useEffect(() => {
    if (!token) return;

    let cancelled = false;
    fetchTeamSettings(token)
      .then((row) => {
        if (!cancelled) applySettings(row);
      })
      .catch(() => {
        // 팀이 아직 없으면 404다. 나머지 구획은 보여준다.
      });

    return () => {
      cancelled = true;
    };
  }, [token, applySettings]);

  async function handleSaveWorkload() {
    if (!token || savingSettings) return;
    setSavingSettings(true);
    try {
      applySettings(
        await saveTeamSettings(token, {
          capacity_wk_hours: baseHours.trim(),
          overload_pct: overloadThreshold.trim(),
          workload_weeks: workloadWeeks.trim(),
        }),
      );
      showToast('팀 업무량 기준을 저장했습니다.', 'success');
    } catch (error) {
      showToast(error instanceof ApiError ? error.message : '기준을 저장하지 못했습니다.', 'error');
    } finally {
      setSavingSettings(false);
    }
  }

  async function handleRemoveMember(member: TeamMember) {
    if (!token) return;
    try {
      setMembers(await removeTeamMember(token, member.person_id));
      showToast(`${member.name ?? member.person_id} 님을 명부에서 뺐습니다.`, 'success');
    } catch (error) {
      showToast(error instanceof ApiError ? error.message : '팀원을 빼지 못했습니다.', 'error');
    }
  }

  // 이름·부서·직책과 보유 스킬은 전부 HR에서 온다. 우리가 저장하는 값이 아니다.
  const reloadAccount = useCallback(async () => {
    if (!token) return;
    try {
      setAccount(await fetchCurrentAccount(token));
    } catch {
      // 프로필을 못 읽어도 나머지 구획은 보여준다.
    }
  }, [token]);

  useEffect(() => {
    void reloadAccount();
  }, [reloadAccount]);

  // 서버에 실제로 기록된 연결(현재는 People DB)을 데모 상태 위에 덮어쓴다.
  useEffect(() => {
    if (!token) return;

    let cancelled = false;
    listConnectors(token)
      .then((connections) => {
        if (cancelled) return;
        const fromServer: Record<string, ConnectorStatus> = {};
        for (const def of CONNECTOR_DEFS) {
          const type = CONNECTOR_TYPE_BY_ID[def.id];
          if (!type) continue;
          const match = connections.find((c) => c.connector_type === type);
          if (match) {
            fromServer[def.id] = match.auth_status === 'CONNECTED' ? 'connected' : 'disconnected';
          }
        }
        setConnectorStatuses((prev) => ({ ...prev, ...fromServer }));
      })
      .catch(() => {
        // 연동 상태 조회 실패는 화면을 막지 않는다. 데모 상태를 그대로 보여준다.
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  async function handleOpenInviteModal() {
    if (!token) {
      showToast('BLOCKED · 로그인해야 팀원을 초대할 수 있습니다.', 'error');
      return;
    }

    setIssued(null);
    setSelectedPersonId('');
    setInviteModalOpen(true);
    try {
      const rows = await listInviteCandidates(token);
      setCandidates(rows);
      setSelectedPersonId(rows[0]?.person_id ?? '');
    } catch (error) {
      showToast(
        error instanceof ApiError ? error.message : '초대 가능한 팀원을 불러오지 못했습니다.',
        'error',
      );
      setInviteModalOpen(false);
    }
  }

  async function handleIssueInvite() {
    if (!token || !selectedPersonId || issuing) return;

    setIssuing(true);
    try {
      setIssued(await createInvite(token, selectedPersonId));
      await refreshMembers();
    } catch (error) {
      showToast(error instanceof ApiError ? error.message : '초대를 발급하지 못했습니다.', 'error');
    } finally {
      setIssuing(false);
    }
  }

  async function handleRevokeInvite(inviteId: string) {
    if (!token) return;

    try {
      await revokeInvite(token, inviteId);
      showToast('초대를 취소했습니다.', 'success');
      await refreshMembers();
    } catch (error) {
      showToast(error instanceof ApiError ? error.message : '초대를 취소하지 못했습니다.', 'error');
    }
  }

  return (
    <SettingsLayout
      subtitle="팀 관리자 설정"
      navItems={NAV_ITEMS}
      footerLabel="관리자"
      onFooterClick={() => navigate(PATHS.chat)}
      embedded={embedded}
    >
      {/* Settings 허브 안에서는 허브가 이미 「설정」 h1을 갖고 있어 제목이 두 개 겹친다. */}
      {!embedded && (
        <div className={styles.pageHeader}>
          <h1>팀장 설정</h1>
          <p>워크스페이스 연동, 팀원 관리 및 협업 추천 자동화 기준을 관리합니다.</p>
        </div>
      )}

      <section id="profile" className={styles.sectionBlock}>
        <Card padding="lg">
          <div className={styles.sectionHeading}>
            <h2>내 프로필</h2>
            <p>회사 인사 시스템에서 온 내 정보입니다.</p>
          </div>

          <div className={styles.identityRow}>
            <AvatarPicker
              token={token}
              name={account?.person?.name ?? account?.display_name ?? ''}
              hasAvatar={account?.has_avatar ?? false}
              onChanged={() => void reloadAccount()}
              onError={(message) => showToast(message, 'error')}
            />
            <div className={styles.identityText}>
              <span className={styles.identityName}>
                {account?.person?.name ?? account?.display_name ?? '-'}
              </span>
              <span className={styles.identityMeta}>
                {[account?.person?.org_name, account?.person?.job_role].filter(Boolean).join(' · ') || '-'}
              </span>
            </div>
          </div>

          {account && !account.person && (
            <p className={styles.warnBox}>
              인사 시스템에 연결된 직원 정보가 없습니다. 회사 이메일로 가입했는지 확인해 주세요.
            </p>
          )}

          <p className={styles.subheading}>계정 정보</p>
          <div className={styles.accountRow}>
            <Input label="이메일" type="email" value={account?.email ?? ''} readOnly disabled />
            <Input label="표시 이름" value={account?.display_name ?? ''} readOnly disabled />
          </div>
          {/* 이메일은 로그인 ID이자 HR 직원을 찾는 근거다. 화면에서 고치게 하면
              로그인 계정이 바뀌고, 아직 HR 연결 전이라면 다른 사람에게 붙을 수 있다. */}
          <p className={styles.hint}>
            이메일은 로그인 ID이자 인사 정보를 연결하는 기준이라 여기서 바꿀 수 없습니다.
          </p>
        </Card>
      </section>

      <section id="skills" className={styles.sectionBlock}>
        <Card padding="lg">
          <div className={styles.sectionHeading}>
            <h2>보유 스킬</h2>
            <p>업무 배정 후보를 고를 때 근거가 되는 값입니다. 인사 시스템에서 옵니다.</p>
          </div>
          <SkillList skills={account?.skills ?? []} />
        </Card>
      </section>

      <section id="password" className={styles.sectionBlock}>
        <Card padding="lg">
          <div className={styles.sectionHeading}>
            <h2>비밀번호 변경</h2>
            <p>현재 비밀번호를 확인한 뒤 새 비밀번호로 바꿉니다.</p>
          </div>
          <PasswordChangeCard
            token={token}
            onDone={(message) => showToast(message, 'success')}
            onError={(message) => showToast(message, 'error')}
          />
        </Card>
      </section>

      <section id="connectors" className={styles.sectionBlock}>
        <Card padding="lg">
          <div className={styles.sectionHeading}>
            <h2>연동 관리</h2>
            <p>업무 추적 및 파일 협업 도구를 연결하여 실시간 데이터를 동기화합니다.</p>
          </div>
          <div className={styles.connectorGrid}>
            {CONNECTOR_DEFS.map((connector) => {
              const connected = connectorStatuses[connector.id] === 'connected';
              return (
                <div key={connector.id} className={styles.connectorCard}>
                  <div className={styles.connectorIconBox} style={{ background: connector.iconBg }}>
                    {connector.icon}
                  </div>
                  <div className={styles.connectorInfo}>
                    <p className={styles.connectorName}>{connector.name}</p>
                    <Badge tone={connected ? 'success' : 'neutral'} dot>
                      {connected ? '연결됨' : '미연결'}
                    </Badge>
                  </div>
                  <Button variant="outline" size="sm" onClick={() => navigate('/onboarding/connectors')}>
                    {connected ? '업데이트' : '재연동'}
                  </Button>
                </div>
              );
            })}
          </div>
        </Card>
      </section>

      <section id="team" className={styles.sectionBlock}>
        <Card padding="lg">
          <div className={styles.sectionHeadingRow}>
            <div className={styles.sectionHeading}>
              <h2>팀원 관리</h2>
              <p>업무 배정 대상이 되는 팀 명부입니다. 계정과 초대 상태를 함께 봅니다.</p>
            </div>
            <Button
              variant="primary"
              size="sm"
              iconLeft={<Icon name="users" size={14} />}
              onClick={handleOpenInviteModal}
            >
              팀원 초대하기
            </Button>
          </div>

          <p className={styles.tableCaption}>팀원 ({members.length}명)</p>

          <div className={styles.teamTable}>
            <div className={styles.teamTableHead}>
              <span>이름</span>
              <span>소속 · 직책</span>
              <span>계정</span>
              <span>초대</span>
              <span />
            </div>
            {memberError && <p className={styles.emptyNote}>{memberError}</p>}
            {!memberError && members.length === 0 && (
              <p className={styles.emptyNote}>아직 팀원이 없습니다.</p>
            )}
            {members.map((member) => (
              <div key={member.team_member_id} className={styles.teamTableRow}>
                <span className={styles.memberName}>
                  {member.name ?? member.person_id}
                  {member.is_owner && <span className={styles.ownerTag}>팀 소유자</span>}
                </span>
                <span className={styles.memberEmail}>
                  {[member.org_name, member.job_role].filter(Boolean).join(' · ') || '-'}
                </span>
                <span>
                  {member.account_email ? (
                    <span className={styles.memberEmail}>{member.account_email}</span>
                  ) : (
                    <Badge tone="neutral">미가입</Badge>
                  )}
                </span>
                <span className={styles.inviteCell}>
                  {member.invite_status ? (
                    <>
                      <Badge tone={INVITE_STATUS_TONE[member.invite_status]}>
                        {INVITE_STATUS_LABEL[member.invite_status]}
                      </Badge>
                      {member.invite_status === 'PENDING' && member.invite_id && (
                        <button
                          type="button"
                          className={styles.cancelLink}
                          onClick={() => void handleRevokeInvite(member.invite_id as string)}
                        >
                          취소
                        </button>
                      )}
                    </>
                  ) : (
                    // 직접 가입한 팀장은 초대를 받은 적이 없다. 빈 것이 정상이다.
                    <span className={styles.dim}>-</span>
                  )}
                </span>
                <span className={styles.rowAction}>
                  {/* 팀 계정을 쓰는 사람과 팀 소유자는 서버가 막는다. 누를 수 없는
                      버튼을 보여 주느니 아예 감춘다. */}
                  {!member.is_owner && !member.account_id && (
                    <button
                      type="button"
                      className={styles.removeLink}
                      onClick={() => void handleRemoveMember(member)}
                    >
                      명부에서 빼기
                    </button>
                  )}
                </span>
              </div>
            ))}
          </div>
        </Card>
      </section>

      <Modal
        open={inviteModalOpen}
        onClose={() => setInviteModalOpen(false)}
        title="팀원 초대하기"
        footer={
          issued ? (
            <Button variant="primary" onClick={() => setInviteModalOpen(false)}>
              닫기
            </Button>
          ) : (
            <Button
              variant="primary"
              onClick={() => void handleIssueInvite()}
              disabled={issuing || !selectedPersonId}
            >
              {issuing ? '발급 중…' : '초대 코드 발급'}
            </Button>
          )
        }
      >
        {issued ? (
          <div className={styles.inviteResult}>
            <p>
              <strong>{issued.person_name}</strong> 님의 초대 코드입니다. 이 화면을 닫으면 다시 볼 수
              없으니 지금 복사해서 전달해 주세요.
            </p>
            <code className={styles.inviteCode}>{issued.code}</code>
            <p className={styles.inviteHint}>
              유효기간 {DATE_FORMAT.format(new Date(issued.expires_at))}까지
            </p>
          </div>
        ) : candidates.length === 0 ? (
          <p className={styles.emptyNote}>
            초대할 수 있는 팀원이 없습니다. 이미 연결됐거나 초대가 진행 중인 직원은 제외됩니다.
          </p>
        ) : (
          <div className={styles.inviteResult}>
            <p className={styles.inviteHint}>초대할 직원을 선택하세요. 내 하위 조직 직원만 보입니다.</p>
            <Select
              options={candidates.map((candidate) => ({
                value: candidate.person_id,
                label: `${candidate.name} · ${candidate.org_name ?? '소속 미상'} · ${candidate.email}`,
              }))}
              value={selectedPersonId}
              onChange={(event) => setSelectedPersonId(event.target.value)}
            />
          </div>
        )}
      </Modal>

      <section id="workload" className={styles.sectionBlock}>
        <Card padding="lg">
          <div className={styles.sectionHeading}>
            <h2>팀 업무량 기준</h2>
            <p>부하율 계산과 과부하 판정에 쓰이는 값입니다. 비우면 기본값으로 돌아갑니다.</p>
          </div>

          <div className={styles.workloadRow}>
            <Input
              label="기준 근무시간 (주 단위)"
              type="number"
              value={baseHours}
              placeholder={hrHoursHint}
              onChange={(e) => setBaseHours(e.target.value)}
              rightElement={<span className={styles.unitLabel}>시간/주</span>}
            />
            <Input
              label="과부하 경고 임계값"
              type="number"
              value={overloadThreshold}
              placeholder={String(settings?.default_overload_pct ?? 100)}
              onChange={(e) => setOverloadThreshold(e.target.value)}
              rightElement={<span className={styles.unitLabel}>%</span>}
            />
            <Input
              label="부하 조회 기간"
              type="number"
              value={workloadWeeks}
              placeholder={String(settings?.default_workload_weeks ?? 4)}
              onChange={(e) => setWorkloadWeeks(e.target.value)}
              rightElement={<span className={styles.unitLabel}>주</span>}
            />
          </div>

          <p className={styles.helperNote}>
            <Icon name="circle-help" size={14} color="var(--color-placeholder)" />
            {/* 사람마다 다른 HR 값을 하나로 덮어쓴다는 사실을 밝힌다. 지금은 전원
                같은 값이라 티가 안 나지만, 시간제 근무자가 생기면 그 사람 값까지
                덮인다. */}
            기준 근무시간을 비우면 인사 시스템의 팀원별 값을 그대로 씁니다({hrHoursHint}).
            값을 넣으면 팀원 모두에게 그 값이 적용됩니다.
          </p>

          <div className={styles.saveRow}>
            <Button variant="primary" onClick={() => void handleSaveWorkload()} disabled={savingSettings}>
              {savingSettings ? '저장 중…' : '기준 저장하기'}
            </Button>
          </div>
        </Card>
      </section>

    </SettingsLayout>
  );
}
