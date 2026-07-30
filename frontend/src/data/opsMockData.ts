export interface OpsOrganization {
  id: string;
  parentId: string | null;
  managerId: string | null;
  name: string;
  type: '회사' | '본부' | '팀';
  memberCount: number;
  issueCount: number;
  updatedAt: string;
}

export interface OpsAccount {
  id: string;
  email: string;
  employeeId: string | null;
  organization: string;
  mappingStatus: '연결됨' | '중복 연결' | '미연결';
  status: '정상' | '잠김';
  services: string[];
  employeeName?: string;
}

export interface OpsInvitation {
  id: string;
  employeeId: string;
  organization: string;
  inviterEmail: string;
  status: '수락 완료' | '수락 대기' | '만료' | '운영자 폐기' | '연결 실패';
  issuedAt: string;
  accountResult: string;
}

export interface OpsConnector {
  id: string;
  type: '인사 정보' | '구글 드라이브' | 'Jira';
  owner: string;
  organization: string;
  status: '연결됨' | '확인 필요' | '오류';
  checkedAt: string;
  diagnosis: string;
  nextAction: string;
}

export const OPS_ORGANIZATIONS: OpsOrganization[] = [
  { id: 'ORG-001', parentId: null, managerId: null, name: 'halil', type: '회사', memberCount: 26, issueCount: 1, updatedAt: '오늘 09:40' },
  { id: 'ORG-010', parentId: 'ORG-001', managerId: '직원 12', name: '제품본부', type: '본부', memberCount: 12, issueCount: 1, updatedAt: '오늘 09:40' },
  { id: 'ORG-011', parentId: 'ORG-010', managerId: '직원 18', name: '제품전략팀', type: '팀', memberCount: 5, issueCount: 0, updatedAt: '오늘 09:39' },
  { id: 'ORG-012', parentId: 'ORG-010', managerId: '직원 27', name: '플랫폼팀', type: '팀', memberCount: 3, issueCount: 1, updatedAt: '오늘 09:38' },
  { id: 'ORG-013', parentId: 'ORG-010', managerId: '직원 31', name: '디자인팀', type: '팀', memberCount: 4, issueCount: 0, updatedAt: '오늘 09:37' },
  { id: 'ORG-020', parentId: 'ORG-001', managerId: '직원 47', name: '사업본부', type: '본부', memberCount: 8, issueCount: 0, updatedAt: '오늘 09:34' },
];

export const OPS_ACCOUNTS: OpsAccount[] = [
  { id: '계정 12', email: 'minwoo@halil.ai', employeeId: '직원 12', organization: '제품본부', mappingStatus: '연결됨', status: '정상', services: ['인사 정보', '구글 드라이브', 'Jira'] },
  { id: '계정 18', email: 'seojun@halil.ai', employeeId: '직원 18', organization: '플랫폼팀', mappingStatus: '중복 연결', status: '잠김', services: ['구글 드라이브', 'Jira'], employeeName: '박서준' },
  { id: '계정 31', email: 'soyoung@halil.ai', employeeId: '직원 31', organization: '디자인팀', mappingStatus: '연결됨', status: '정상', services: ['인사 정보', 'Jira'] },
  { id: '계정 42', email: 'yujin@halil.ai', employeeId: null, organization: '영업기획팀', mappingStatus: '미연결', status: '잠김', services: [] },
  { id: '계정 47', email: 'jihun@halil.ai', employeeId: '직원 47', organization: '사업본부', mappingStatus: '연결됨', status: '정상', services: ['인사 정보', '구글 드라이브'] },
];

export const OPS_INVITATIONS: OpsInvitation[] = [
  { id: '초대 01', employeeId: '직원 18', organization: '플랫폼팀', inviterEmail: 'minwoo@halil.ai', status: '수락 완료', issuedAt: '07.29', accountResult: '계정 18 · 연결됨' },
  { id: '초대 07', employeeId: '직원 27', organization: '플랫폼팀', inviterEmail: 'minwoo@halil.ai', status: '수락 대기', issuedAt: '07.29', accountResult: '아직 연결 전' },
  { id: '초대 11', employeeId: '직원 42', organization: '영업기획팀', inviterEmail: 'jihun@halil.ai', status: '만료', issuedAt: '07.28', accountResult: '연결되지 않음' },
  { id: '초대 18', employeeId: '직원 55', organization: '디자인팀', inviterEmail: 'soyoung@halil.ai', status: '운영자 폐기', issuedAt: '07.27', accountResult: '연결되지 않음' },
  { id: '초대 21', employeeId: '직원 62', organization: '플랫폼팀', inviterEmail: 'minwoo@halil.ai', status: '연결 실패', issuedAt: '07.29', accountResult: '직원 중복 연결' },
];

export const OPS_CONNECTORS: OpsConnector[] = [
  { id: '연결 01', type: '인사 정보', owner: 'minwoo@halil.ai', organization: '제품본부', status: '연결됨', checkedAt: '07.30 09:40', diagnosis: '정상', nextAction: '조치 없음' },
  { id: '연결 07', type: '구글 드라이브', owner: 'minwoo@halil.ai', organization: '제품전략팀', status: '확인 필요', checkedAt: '07.29 11:42', diagnosis: '인증 토큰 만료', nextAction: '계정 소유자가 설정에서 재연결' },
  { id: '연결 11', type: 'Jira', owner: 'seojun@halil.ai', organization: '플랫폼팀', status: '오류', checkedAt: '07.29 10:18', diagnosis: '프로젝트 읽기 권한 부족', nextAction: '계정 소유자가 Jira 권한 확인' },
  { id: '연결 18', type: '구글 드라이브', owner: 'soyoung@halil.ai', organization: '디자인팀', status: '연결됨', checkedAt: '07.30 08:55', diagnosis: '정상', nextAction: '조치 없음' },
  { id: '연결 24', type: 'Jira', owner: 'jihun@halil.ai', organization: '사업본부', status: '오류', checkedAt: '07.28 17:10', diagnosis: '연결 실패', nextAction: '계정 소유자가 설정에서 연결 재시도' },
];
