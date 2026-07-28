import { useState } from 'react';
import { Badge } from '../../components';
import type { BadgeTone } from '../../components';
import styles from './OrgChartPanel.module.css';

type MemberStatus = 'available' | 'overload' | 'working';

interface OrgMember {
  id: string;
  name: string;
  role: string;
  status: MemberStatus;
}

interface Department {
  name: string;
  lead: OrgMember;
  members: OrgMember[];
}

const STATUS_LABEL: Record<MemberStatus, string> = {
  available: '가용',
  overload: '과부하',
  working: '작업중',
};

const STATUS_TONE: Record<MemberStatus, BadgeTone> = {
  available: 'success',
  overload: 'danger',
  working: 'warning',
};

const PM_MEMBER: OrgMember = { id: '김민수', name: '김민수', role: 'PM/관리자', status: 'available' };

const DEPARTMENTS: Department[] = [
  {
    name: '백엔드팀',
    lead: { id: '박서준', name: '박서준', role: '팀장', status: 'overload' },
    members: [
      { id: '이동현', name: '이동현', role: '사원', status: 'overload' },
      { id: '최영호', name: '최영호', role: '사원', status: 'available' },
    ],
  },
  {
    name: '프론트엔드팀',
    lead: { id: '김지은', name: '김지은', role: '팀장', status: 'working' },
    members: [
      { id: '한유진', name: '한유진', role: '사원', status: 'available' },
      { id: '오세영', name: '오세영', role: '사원', status: 'available' },
    ],
  },
  {
    name: '인프라팀',
    lead: { id: '정현우', name: '정현우', role: '팀장', status: 'working' },
    members: [{ id: '송민기', name: '송민기', role: '사원', status: 'working' }],
  },
];

function MemberCard({
  member,
  pm = false,
  selected,
  onSelect,
}: {
  member: OrgMember;
  pm?: boolean;
  selected: boolean;
  onSelect: (id: string) => void;
}) {
  const classes = [styles.memberCard, pm ? styles.pm : '', selected ? styles.selected : '']
    .filter(Boolean)
    .join(' ');

  return (
    <button type="button" className={classes} onClick={() => onSelect(member.id)}>
      <div>
        <p className={styles.memberName}>{member.name}</p>
        <p className={styles.memberRole}>{member.role}</p>
      </div>
      <Badge tone={STATUS_TONE[member.status]}>{STATUS_LABEL[member.status]}</Badge>
    </button>
  );
}

export function OrgChartPanel() {
  const [selectedMember, setSelectedMember] = useState<string | null>(null);

  function handleSelect(id: string) {
    setSelectedMember((prev) => (prev === id ? null : id));
  }

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <p className={styles.panelTitle}>조직도 현황</p>
        <p className={styles.panelSubtitle}>팀별 업무 분배 및 가용 인원 모니터링</p>
      </div>

      <div className={styles.summaryRow}>
        <div className={styles.summaryCard}>
          <p className={styles.summaryLabel}>전체 팀원</p>
          <p className={styles.summaryValue}>12명</p>
        </div>
        <div className={styles.summaryCard}>
          <p className={styles.summaryLabel}>가용 팀원</p>
          <p className={styles.summaryValue}>5명</p>
        </div>
        <div className={styles.summaryCard}>
          <p className={styles.summaryLabel}>과부하 상태</p>
          <p className={styles.summaryValue}>3명</p>
        </div>
      </div>

      <div className={styles.sectionBlock}>
        <p className={styles.cardTitle}>팀원 리스트</p>
        <div className={styles.orgChartCard}>
          <div className={styles.pmWrap}>
            <MemberCard member={PM_MEMBER} pm selected={selectedMember === PM_MEMBER.id} onSelect={handleSelect} />
            <div className={styles.vConnector} />
          </div>

          <div className={styles.deptHeadsRow}>
            {DEPARTMENTS.map((dept) => (
              <div key={dept.name} className={styles.deptColumn}>
                <p className={styles.deptLabel}>{dept.name}</p>
                <MemberCard member={dept.lead} selected={selectedMember === dept.lead.id} onSelect={handleSelect} />
                <div className={styles.deptLine} />
                <div className={styles.membersRow}>
                  {dept.members.map((member) => (
                    <MemberCard
                      key={member.id}
                      member={member}
                      selected={selectedMember === member.id}
                      onSelect={handleSelect}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default OrgChartPanel;
