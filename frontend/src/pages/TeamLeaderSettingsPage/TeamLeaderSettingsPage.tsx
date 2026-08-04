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
import {
  createInvite,
  listInviteCandidates,
  listInvites,
  revokeInvite,
} from '../../api/invites';
import type { Invite, InviteCandidate, InviteStatus, IssuedInvite } from '../../api/invites';
import { CONNECTOR_DEFS } from '../../data/connectorDefs';
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

export default function TeamLeaderSettingsPage() {
  const navigate = useNavigate();
  const { showToast } = useToast();

  const [connectorStatuses, setConnectorStatuses] = useState<Record<string, ConnectorStatus>>(() =>
    loadConnectorStatuses(Object.fromEntries(CONNECTOR_DEFS.map((c) => [c.id, c.initialStatus]))),
  );
  const [baseHours, setBaseHours] = useState('40');
  const [overloadThreshold, setOverloadThreshold] = useState('110');
  const [defaultHours, setDefaultHours] = useState('8');
  const [account, setAccount] = useState<Account | null>(null);

  const [token] = useState(loadSessionToken);
  const [invites, setInvites] = useState<Invite[]>([]);
  const [inviteError, setInviteError] = useState('');
  const [inviteModalOpen, setInviteModalOpen] = useState(false);
  const [candidates, setCandidates] = useState<InviteCandidate[]>([]);
  const [selectedPersonId, setSelectedPersonId] = useState('');
  const [issuing, setIssuing] = useState(false);
  const [issued, setIssued] = useState<IssuedInvite | null>(null);

  const refreshInvites = useCallback(async () => {
    if (!token) {
      setInviteError('BLOCKED · 로그인해야 팀원 초대 현황을 볼 수 있습니다.');
      return;
    }
    try {
      setInvites(await listInvites(token));
      setInviteError('');
    } catch (error) {
      setInviteError(error instanceof ApiError ? error.message : '초대 현황을 불러오지 못했습니다.');
    }
  }, [token]);

  useEffect(() => {
    void refreshInvites();
  }, [refreshInvites]);

  // 이름·부서·직급과 보유 스킬은 전부 HR에서 온다. 우리가 저장하는 값이 아니다.
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
      await refreshInvites();
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
      await refreshInvites();
    } catch (error) {
      showToast(error instanceof ApiError ? error.message : '초대를 취소하지 못했습니다.', 'error');
    }
  }


  function handleSaveWorkload() {
    showToast('팀 업무량 기준을 저장했습니다.', 'success');
  }

  return (
    <SettingsLayout
      subtitle="팀 관리자 설정"
      navItems={NAV_ITEMS}
      footerLabel="관리자"
      onFooterClick={() => navigate('/dashboard')}
    >
      <div className={styles.pageHeader}>
        <h1>팀장 설정</h1>
        <p>워크스페이스 연동, 팀원 관리 및 협업 추천 자동화 기준을 관리합니다.</p>
      </div>

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

          <div className={styles.hrBox}>
            <div className={styles.hrBoxHeader}>
              <Icon name="lock" size={14} color="var(--color-placeholder)" />
              <span>HR 연동 정보 (읽기 전용)</span>
            </div>
            <div className={styles.hrFieldGrid}>
              <div className={styles.hrField}>
                <span className={styles.hrFieldLabel}>이름</span>
                <span className={styles.hrFieldValue}>{account?.person?.name ?? '-'}</span>
              </div>
              <div className={styles.hrField}>
                <span className={styles.hrFieldLabel}>부서</span>
                <span className={styles.hrFieldValue}>{account?.person?.org_name ?? '-'}</span>
              </div>
              <div className={styles.hrField}>
                <span className={styles.hrFieldLabel}>직급</span>
                <span className={styles.hrFieldValue}>{account?.person?.job_role ?? '-'}</span>
              </div>
            </div>
            {account && !account.person && (
              <p className={styles.hint}>
                HR 시스템에 연결된 직원 정보가 없습니다. 회사 이메일로 가입했는지 확인해 주세요.
              </p>
            )}
          </div>

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
              <p>팀 내부 멤버를 초대하고 활성화 상태를 모니터링합니다.</p>
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

          <p className={styles.tableCaption}>보낸 초대 ({invites.length}건)</p>

          <div className={styles.teamTable}>
            <div className={styles.teamTableHead}>
              <span>이름</span>
              <span>이메일</span>
              <span>상태</span>
              <span>초대일</span>
              <span>작업</span>
            </div>
            {inviteError && <p className={styles.emptyNote}>{inviteError}</p>}
            {!inviteError && invites.length === 0 && (
              <p className={styles.emptyNote}>아직 초대된 팀원이 없습니다.</p>
            )}
            {invites.map((invite) => (
              <div key={invite.invite_id} className={styles.teamTableRow}>
                <span className={styles.memberName}>{invite.person_name}</span>
                <span className={styles.memberEmail}>{invite.person_email}</span>
                <span>
                  <Badge tone={INVITE_STATUS_TONE[invite.status]}>
                    {INVITE_STATUS_LABEL[invite.status]}
                  </Badge>
                </span>
                <span>{DATE_FORMAT.format(new Date(invite.created_at))}</span>
                <span>
                  {invite.status === 'PENDING' && (
                    <button
                      type="button"
                      className={styles.cancelLink}
                      onClick={() => void handleRevokeInvite(invite.invite_id)}
                    >
                      초대 취소
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
            <p>적정 업무량 배정을 유도하는 임계값을 설정합니다.</p>
          </div>

          <div className={styles.workloadRow}>
            <Input
              label="기준 근무시간 (주 단위)"
              type="number"
              value={baseHours}
              onChange={(e) => setBaseHours(e.target.value)}
              rightElement={<span className={styles.unitLabel}>시간/주</span>}
            />
            <Input
              label="과부하 경고 임계값"
              type="number"
              value={overloadThreshold}
              onChange={(e) => setOverloadThreshold(e.target.value)}
              rightElement={<span className={styles.unitLabel}>%</span>}
            />
            <Input
              label="기본 근무시간 (개인 설정 없는 팀원 적용)"
              type="number"
              value={defaultHours}
              onChange={(e) => setDefaultHours(e.target.value)}
              rightElement={<span className={styles.unitLabel}>시간/일</span>}
            />
          </div>

          <p className={styles.helperNote}>
            <Icon name="circle-help" size={14} color="var(--color-placeholder)" />
            팀원별 기준은 개인 설정 탭에서 별도로 지정하면 검증 단계에서 우선 반영됩니다.
          </p>

          <div className={styles.saveRow}>
            <Button variant="primary" onClick={handleSaveWorkload}>
              기준 저장하기
            </Button>
          </div>
        </Card>
      </section>
    </SettingsLayout>
  );
}
