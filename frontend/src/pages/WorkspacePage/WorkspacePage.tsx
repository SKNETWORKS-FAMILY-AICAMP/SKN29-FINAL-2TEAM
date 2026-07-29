import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Icon, Modal, TopNav, useToast } from '../../components';
import { MAIN_NAV_TABS } from '../../routes';
import { MemberRow } from './MemberRow';
import type { WorkspaceMember } from './MemberRow';
import rowStyles from './MemberRow.module.css';
import styles from './WorkspacePage.module.css';

const MEMBERS: WorkspaceMember[] = [
  { id: '김민수', name: '김민수', role: '팀장', team: '프론트엔드팀', status: 'available', avatarColor: '#3b82f6', avatarInitial: '김' },
  { id: '박서준', name: '박서준', role: '백엔드팀장', team: '백엔드팀', status: 'busy', avatarColor: '#0ea5e9', avatarInitial: '박' },
  { id: '이동현', name: '이동현', role: '사원', team: '백엔드팀', status: 'overloaded', avatarColor: '#8b5cf6', avatarInitial: '이' },
  { id: '최영호', name: '최영호', role: '사원', team: '백엔드팀', status: 'available', avatarColor: '#f59e0b', avatarInitial: '최' },
  { id: '김지은', name: '김지은', role: '팀장', team: '기획팀', status: 'available', avatarColor: '#ec4899', avatarInitial: '김' },
  { id: '한유진', name: '한유진', role: '사원', team: '프론트엔드팀', status: 'busy', avatarColor: '#14b8a6', avatarInitial: '한' },
  { id: '오세영', name: '오세영', role: '사원', team: 'QA팀', status: 'available', avatarColor: '#6366f1', avatarInitial: '오' },
  { id: '정현우', name: '정현우', role: '인프라팀장', team: '인프라팀', status: 'busy', avatarColor: '#0891b2', avatarInitial: '정' },
  { id: '송민기', name: '송민기', role: '사원', team: '인프라팀', status: 'overloaded', avatarColor: '#84603a', avatarInitial: '송' },
];

const DEFAULT_CHECKED_IDS = ['김민수', '최영호', '오세영'];

const REFERENCE_FILES = ['프로젝트_요구사항_v2.docx', 'API_설계_초안.docx', '스프린트3_회의록.docx'];
const EXTRA_FILE_COUNT = 1;

export default function WorkspacePage() {
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set(DEFAULT_CHECKED_IDS));
  const [requirements, setRequirements] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const { showToast } = useToast();
  const navigate = useNavigate();

  const selectionCount = checkedIds.size;

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
    setModalOpen(false);
    showToast('업무 분배가 시작되었습니다.', 'success');
    setTimeout(() => {
      navigate('/tasks/distribution');
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
                {MEMBERS.map((member) => (
                  <MemberRow
                    key={member.id}
                    member={member}
                    checked={checkedIds.has(member.id)}
                    onToggle={toggleMember}
                  />
                ))}
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
