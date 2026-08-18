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
  SkillList,
  useToast,
} from '../../components';
import type { BadgeTone } from '../../components';
import { ApiError } from '../../api/client';
import { fetchCurrentAccount } from '../../api/auth';
import type { Account } from '../../api/auth';
import { listConnectors } from '../../api/connectors';
import { createInvite, listInviteCandidates, revokeInvite } from '../../api/invites';
import type { InviteCandidate, InviteStatus, IssuedInvite } from '../../api/invites';
import {
  listTeamMembers,
  removeTeamMember,
} from '../../api/teams';
import type { TeamMember } from '../../api/teams';
import { PATHS } from '../../routes';
import { loadSessionToken } from '../../utils/session';
import styles from './TeamLeaderSettingsPage.module.css';

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
}

export default function TeamLeaderSettingsPage() {
  const navigate = useNavigate();
  const { showToast } = useToast();

  /** 인사 시스템이 붙어 있는가. 「내 정보를 못 찾은 이유」가 이것으로 갈린다. */
  /**
   * **서버가 원본이다.** 예전에는 세 커넥터의 상태를 sessionStorage 에 얹어 두고
   * 서버 값으로 덮어썼는데, 이 화면이 실제로 읽는 것은 People DB 하나뿐이고
   * 나머지 둘은 계산만 되고 아무 데도 안 나왔다. 「연동 관리」 섹션을 걷어낸
   * 2026-08-12 의 잔재라 함께 정리했다(2026-08-13).
   */
  const [peopleConnected, setPeopleConnected] = useState(false);
  // 빈 문자열이 "설정 안 함"이다. 0과 구분해야 하므로 숫자로 들고 있지 않는다.
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

  // 이 화면에 필요한 것은 People DB 하나다 — 팀원 조회·초대가 그 연결에 달려 있다.
  useEffect(() => {
    if (!token) return;

    let cancelled = false;
    listConnectors(token)
      .then((connections) => {
        if (cancelled) return;
        setPeopleConnected(
          connections.some((c) => c.connector_type === 'PEOPLE_DB' && c.auth_status === 'CONNECTED'),
        );
      })
      .catch(() => {
        // 연동 상태 조회 실패는 화면을 막지 않는다. 미연결로 두고 안내를 띄운다.
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
    <>

      <section id="profile" className={styles.sectionBlock}>
        <Card padding="lg">
          <div className={styles.sectionHeading}>
            <h2>내 프로필</h2>
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
              {/* **빈 값은 빈 값 자리에서 말한다.** 노란 경고 바를 카드 한가운데
                  끼워 넣었더니 프로필 안에 오류가 난 것처럼 보였다(2026-08-12).
                  부서·직책이 들어올 자리가 비어 있는 것이므로 그 줄에서 이유를
                  말하면 된다. 이건 사고가 아니라 아직 안 한 일이다.

                  **원인을 짐작해서 말하지 않는다.** 예전에는 「회사 이메일로
                  가입했는지 확인해 주세요」라고 이메일을 탓했는데, 연결을 아직
                  안 했을 때도 똑같이 떴다 — 그때는 이메일 문제가 아니다. */}
              <span className={styles.identityMeta}>
                {account?.person
                  ? [account.person.org_name, account.person.job_role].filter(Boolean).join(' · ') || '-'
                  : peopleConnected
                    ? '인사 시스템에서 찾지 못했습니다 — 가입한 이메일이 회사 이메일과 같은지 확인해 주세요'
                    : '인사 시스템을 연결하면 부서와 직책이 채워집니다'}
              </span>
            </div>
          </div>

          <p className={styles.subheading}>계정 정보</p>
          <div className={styles.accountRow}>
            <Input label="이메일" type="email" value={account?.email ?? ''} readOnly disabled />
            <Input label="표시 이름" value={account?.display_name ?? ''} readOnly disabled />
          </div>
        </Card>
      </section>

      <section id="skills" className={styles.sectionBlock}>
        <Card padding="lg">
          <div className={styles.sectionHeading}>
            <h2>보유 스킬</h2>
          </div>
          <SkillList skills={account?.skills ?? []} />
        </Card>
      </section>

      <section id="password" className={styles.sectionBlock}>
        <Card padding="lg">
          <div className={styles.sectionHeading}>
            <h2>비밀번호 변경</h2>
          </div>
          <PasswordChangeCard
            token={token}
            onDone={(message) => showToast(message, 'success')}
            onError={(message) => showToast(message, 'error')}
          />
        </Card>
      </section>

      {/* 「연동 관리」 섹션을 걷어냈다 (2026-08-12). 상태만 보여주고 버튼은 전부
          Connector 탭으로 보내던 자리라, 같은 것을 두 곳에서 관리하는 것처럼
          보였다. 연결은 Connector 탭 하나에서 한다. */}

      <section id="team" className={styles.sectionBlock}>
        <Card padding="lg">
          <div className={styles.sectionHeadingRow}>
            <div className={styles.sectionHeading}>
              <h2>팀원 관리</h2>
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
                <span className={styles.memberEmail} data-label="소속 · 직책">
                  {[member.org_name, member.job_role].filter(Boolean).join(' · ') || '-'}
                </span>
                <span data-label="계정">
                  {member.account_email ? (
                    <span className={styles.memberEmail}>{member.account_email}</span>
                  ) : (
                    <Badge tone="neutral">미가입</Badge>
                  )}
                </span>
                <span className={styles.inviteCell} data-label="초대">
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

    </>
  );
}
