import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ApiError } from '../../api/http';
import { getPeople } from '../../api/people';
import type { Person } from '../../api/types';
import { Button, Icon, Modal, TopNav, useToast } from '../../components';
import { MAIN_NAV_TABS } from '../../routes';
import { MemberRow } from './MemberRow';
import type { WorkspaceMember } from './MemberRow';
import rowStyles from './MemberRow.module.css';
import styles from './WorkspacePage.module.css';

const MEMBERS: WorkspaceMember[] = [
  { id: 'PX002', name: '윤수아', role: '본부장', team: '개발팀', status: 'unknown', avatarColor: '#3b82f6', avatarInitial: '윤' },
  { id: 'PB001', name: '박승우', role: '팀장', team: '백엔드파트', status: 'unknown', avatarColor: '#0ea5e9', avatarInitial: '박' },
  { id: 'PB002', name: '윤유진', role: '사원', team: '백엔드파트', status: 'unknown', avatarColor: '#8b5cf6', avatarInitial: '윤' },
  { id: 'PB003', name: '윤수빈', role: '대리 · FTE 0.5', team: '백엔드파트', status: 'unknown', avatarColor: '#f59e0b', avatarInitial: '윤' },
  { id: 'PF001', name: '조재원', role: '팀장', team: '프론트엔드파트', status: 'unknown', avatarColor: '#ec4899', avatarInitial: '조' },
  { id: 'PF002', name: '송지원', role: '주임', team: '프론트엔드파트', status: 'unknown', avatarColor: '#14b8a6', avatarInitial: '송' },
  { id: 'PN001', name: '신채원', role: '팀장 · FTE 0.5', team: '기획팀', status: 'unknown', avatarColor: '#6366f1', avatarInitial: '신' },
  { id: 'PD001', name: '오수빈', role: '팀장', team: '디자인팀', status: 'unknown', avatarColor: '#0891b2', avatarInitial: '오' },
  { id: 'PQ001', name: '신서준', role: '팀장', team: 'QA팀', status: 'unknown', avatarColor: '#84603a', avatarInitial: '신' },
];

const DEFAULT_CHECKED_IDS = ['PB001', 'PF001', 'PN001'];

const REFERENCE_FILES = ['프로젝트_요구사항_v2.docx', 'API_설계_초안.docx', '스프린트3_회의록.docx'];
const EXTRA_FILE_COUNT = 1;
const AVATAR_COLORS = ['#3b82f6', '#0ea5e9', '#8b5cf6', '#f59e0b', '#ec4899', '#14b8a6'];

type PeopleLoadState = 'loading' | 'ready' | 'empty' | 'blocked' | 'error' | 'demo';

function toWorkspaceMember(person: Person, index: number): WorkspaceMember {
  return {
    id: person.person_id,
    name: person.name,
    role: person.job_role || '역할 정보 없음',
    team: person.organization_name,
    status: 'unknown',
    avatarColor: AVATAR_COLORS[index % AVATAR_COLORS.length],
    avatarInitial: person.name.trim().slice(0, 1) || '?',
  };
}

export default function WorkspacePage() {
  const location = useLocation();
  const navigate = useNavigate();
  const isDemo = new URLSearchParams(location.search).get('mode') === 'demo';
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set(isDemo ? DEFAULT_CHECKED_IDS : []));
  const [apiMembers, setApiMembers] = useState<WorkspaceMember[]>([]);
  const [peopleLoadState, setPeopleLoadState] = useState<PeopleLoadState>(isDemo ? 'demo' : 'loading');
  const [peopleLoadReason, setPeopleLoadReason] = useState('');
  const [requirements, setRequirements] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const { showToast } = useToast();
  const navigate = useNavigate();

  const members = isDemo ? MEMBERS : apiMembers;
  const selectionCount = checkedIds.size;

  useEffect(() => {
    setCheckedIds(new Set(isDemo ? DEFAULT_CHECKED_IDS : []));

    if (isDemo) {
      setPeopleLoadState('demo');
      setPeopleLoadReason('');
      return;
    }

    let cancelled = false;
    setPeopleLoadState('loading');
    setPeopleLoadReason('');

    getPeople()
      .then((people) => {
        if (cancelled) return;
        setApiMembers(people.map(toWorkspaceMember));
        setPeopleLoadState(people.length > 0 ? 'ready' : 'empty');
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
          setPeopleLoadState('blocked');
          setPeopleLoadReason('인증된 세션이 필요하지만 React 로그인 연동이 아직 확정되지 않았습니다.');
          return;
        }
        setPeopleLoadState('error');
        setPeopleLoadReason(error instanceof Error ? error.message : 'People API 응답을 확인할 수 없습니다.');
      });

    return () => {
      cancelled = true;
    };
  }, [isDemo]);

  function toggleMember(id: string) {
    setCheckedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  function handleConfirm() {
    if (!isDemo) {
      setModalOpen(false);
      showToast('BLOCKED · 가용시간·휴가·현재 업무량 데이터가 없어 분석을 시작할 수 없습니다.', 'error');
      return;
    }

    setModalOpen(false);
    showToast('업무 분배가 시작되었습니다.', 'success');
    setTimeout(() => {
      navigate(`/tasks/distribution${location.search}`);
    }, 700);
  }

  const modalFooter = (
    <div className={styles.modalFooter}>
      <div className={styles.buttonGroup}>
        <Button variant="secondary" fullWidth onClick={() => setModalOpen(false)}>
          아니오
        </Button>
        <Button variant="primary" fullWidth onClick={handleConfirm}>
          예
        </Button>
      </div>
      <p className={styles.modalHint}>몇 분 정도 걸릴 수 있어요</p>
    </div>
  );

  return (
    <div className={styles.page}>
      <TopNav tabs={MAIN_NAV_TABS} activeTo="/projects" userLabel="관리자" />

      <main className={styles.workspaceContainer}>
        <div className={styles.pageHeader}>
          <p className={styles.pageTitle}>업무 분배 팀원 선택</p>
          <p className={styles.pageSubtitle}>프로젝트에 참여할 팀원을 지정하고 역할 및 가용 상태를 검토하세요.</p>
        </div>

        <div
          className={[
            styles.statusPanel,
            peopleLoadState === 'blocked' || peopleLoadState === 'error' ? styles.statusBlocked : '',
            peopleLoadState === 'demo' ? styles.statusDemo : '',
          ]
            .filter(Boolean)
            .join(' ')}
          role="status"
        >
          <strong>
            {peopleLoadState === 'loading' && 'People API 연결 중'}
            {peopleLoadState === 'ready' && 'CONDITIONAL · 실제 직원 목록'}
            {peopleLoadState === 'empty' && 'CONDITIONAL · 등록된 직원 없음'}
            {peopleLoadState === 'blocked' && 'BLOCKED · 직원 조회 불가'}
            {peopleLoadState === 'error' && 'BLOCKED · People API 오류'}
            {peopleLoadState === 'demo' && 'DEMO · People DB 합성 목업'}
          </strong>
          <p>
            {peopleLoadState === 'loading' && '백엔드에서 직원 정보를 불러오고 있습니다.'}
            {peopleLoadState === 'ready' && '이름·역할·조직은 실제 데이터입니다. 가용시간·휴가·현재 업무량이 없어 업무 분배 시작은 차단됩니다.'}
            {peopleLoadState === 'empty' && 'API 연결은 성공했지만 표시할 직원이 없습니다.'}
            {(peopleLoadState === 'blocked' || peopleLoadState === 'error') && peopleLoadReason}
            {peopleLoadState === 'demo' &&
              'main의 People DB 목업에서 이름·역할·조직·FTE를 반영했습니다. Jira 업무량이 없어 가용 상태는 확인 필요로 표시합니다.'}
          </p>
        </div>

        <section className={styles.creationCard}>
          <div className={styles.teamSelectionSection}>
            <p className={styles.sectionTitle}>팀원 선택</p>

            <div className={styles.tableBox}>
              <div className={styles.tableHeader}>
                <div className={rowStyles.checkboxCell}>
                  <div className={styles.staticCheckbox}>
                    <Icon name="check" size={10} color="#fff" />
                  </div>
                </div>
                <div className={rowStyles.avatarCell} />
                <div className={rowStyles.name}>
                  <span className={styles.thLabel}>이름</span>
                </div>
                <div className={rowStyles.role}>
                  <span className={styles.thLabel}>역할</span>
                </div>
                <div className={rowStyles.team}>
                  <span className={styles.thLabel}>소속팀</span>
                </div>
                <div className={rowStyles.status}>
                  <span className={styles.thLabel}>상태</span>
                </div>
              </div>

              <div className={styles.tableBody}>
                {members.map((member) => (
                  <MemberRow
                    key={member.id}
                    member={member}
                    checked={checkedIds.has(member.id)}
                    onToggle={toggleMember}
                  />
                ))}
                {members.length === 0 && (
                  <p className={styles.emptyRow}>
                    {peopleLoadState === 'loading' ? '직원 정보를 불러오는 중입니다.' : '표시할 직원 정보가 없습니다.'}
                  </p>
                )}
              </div>
            </div>
          </div>

          <div className={styles.additionalRequirementsSection}>
            <p className={styles.sectionTitle}>추가 요구사항</p>
            <div className={styles.textareaBox}>
              <textarea
                className={styles.reqTextarea}
                placeholder="프로젝트 생성 및 업무 배정 시 참고해야 할 제약 조건이나 추가 요구사항을 적어주세요. (선택)"
                value={requirements}
                onChange={(event) => setRequirements(event.target.value)}
              />
            </div>
          </div>

          <div className={styles.actionsRow}>
            <div className={styles.selectionCountGroup}>
              <span className={styles.selectionCountLabel}>선택된 팀원:</span>
              <span className={styles.selectionCountValue}>{selectionCount}명</span>
            </div>
            <Button
              variant="primary"
              iconRight={<Icon name="arrow-right" size={16} color="currentColor" />}
              onClick={() => setModalOpen(true)}
              disabled={!isDemo || selectionCount === 0}
              title={!isDemo ? '가용시간·휴가·현재 업무량 데이터가 필요합니다.' : undefined}
            >
              업무 분배 시작
            </Button>
          </div>
        </section>
      </main>

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} width={480} footer={modalFooter}>
        <div className={styles.modalHeader}>
          <div className={styles.circleSuccessIcon}>
            <Icon name="check" size={24} color="var(--color-success)" />
          </div>
          <p className={styles.modalTitle}>업무 분배를 시작하겠습니다.</p>
        </div>

        <p className={styles.modalBodyText}>
          {REFERENCE_FILES.length + EXTRA_FILE_COUNT}개 파일이 등록됐어요. 이 파일들을 근거로 업무 분배를 진행할까요?
        </p>

        <div className={styles.fileListBox}>
          {REFERENCE_FILES.map((file) => (
            <div key={file} className={styles.fileRow}>
              <Icon name="file-text" size={16} color="var(--color-body)" />
              <span className={styles.fileName}>{file}</span>
            </div>
          ))}
          <div className={[styles.fileRow, styles.more].join(' ')}>
            <Icon name="circle-help" size={16} color="var(--color-placeholder)" />
            <span className={[styles.fileName, styles.more].join(' ')}>외 {EXTRA_FILE_COUNT}건</span>
          </div>
        </div>
      </Modal>
    </div>
  );
}
