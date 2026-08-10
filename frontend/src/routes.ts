/**
 * 라우트 경로의 유일한 선언처. App.tsx는 문자열을 직접 쓰지 않고 여기의
 * PATHS를 참조한다 — 경로를 두 곳에 적어서 어긋나는 일을 막기 위함이다.
 */
export const PATHS = {
  landing: '/',
  devIndex: '/screens',
  devIndexAlias: '/dev/screens',
  login: '/login',
  signup: '/signup',
  inviteCode: '/invite-code',
  findPassword: '/find-password',
  resetPassword: '/reset-password',
  onboardingConnectors: '/onboarding/connectors',
  onboardingFolders: '/onboarding/folders',
  onboardingJiraProject: '/onboarding/jira-project',
  settingsTeam: '/settings/team',
  dashboard: '/dashboard',
  filesNew: '/files/new',
  projects: '/projects',
  projectDetail: '/projects/:projectId',
  taskDistributionDocuments: '/tasks/distribution/documents',
  taskExtraction: '/tasks/extraction',
  opsLogin: '/ops/login',
  ops: '/ops',
  opsTeams: '/ops/teams',
  opsAccounts: '/ops/accounts',
  opsMappings: '/ops/mappings',
  opsConnectors: '/ops/connectors',
  opsAudit: '/ops/audit',
  opsPolicies: '/ops/policies',
} as const;

export interface RouteEntry {
  path: string;
  label: string;
  group: string;
}

/**
 * 개발용 화면 목록(`/screens`)에 노출할 화면. 파라미터가 필요한 화면
 * (`projectDetail`)과 목록 화면 자신은 링크로 갈 수 없어 제외한다.
 */
export const ROUTES: RouteEntry[] = [
  { path: PATHS.landing, label: '랜딩 페이지', group: '마케팅' },
  { path: PATHS.login, label: '로그인', group: '인증' },
  { path: PATHS.signup, label: '회원가입', group: '인증' },
  { path: PATHS.inviteCode, label: '초대코드로 회원가입', group: '인증' },
  { path: PATHS.findPassword, label: '비밀번호 찾기', group: '인증' },
  { path: PATHS.resetPassword, label: '비밀번호 재설정', group: '인증' },
  { path: PATHS.onboardingConnectors, label: '외부 서비스 연결', group: '온보딩' },
  { path: PATHS.onboardingFolders, label: '데이터 소스 설정', group: '온보딩' },
  { path: PATHS.onboardingJiraProject, label: 'Jira 프로젝트 선택', group: '온보딩' },
  { path: PATHS.settingsTeam, label: '팀장 설정', group: '설정' },
  { path: PATHS.dashboard, label: '대시보드', group: '메인' },
  { path: PATHS.filesNew, label: '문서 관리', group: '메인' },
  { path: PATHS.projects, label: '프로젝트 목록', group: '메인' },
  { path: PATHS.taskDistributionDocuments, label: '신규 프로젝트 업무 추출', group: '업무 분배' },
  { path: PATHS.taskExtraction, label: '추출된 업무 확인', group: '업무 분배' },
  { path: PATHS.opsLogin, label: '운영자 로그인', group: '운영자 콘솔' },
  { path: PATHS.ops, label: '운영 현황', group: '운영자 콘솔' },
  { path: PATHS.opsTeams, label: '팀 현황', group: '운영자 콘솔' },
  { path: PATHS.opsAccounts, label: '계정 관리', group: '운영자 콘솔' },
  { path: PATHS.opsMappings, label: '계정 연결·초대 현황', group: '운영자 콘솔' },
  { path: PATHS.opsConnectors, label: '연결 서비스 현황', group: '운영자 콘솔' },
  { path: PATHS.opsAudit, label: '감사 로그', group: '운영자 콘솔' },
  { path: PATHS.opsPolicies, label: '전역 정책', group: '운영자 콘솔' },
];

/**
 * Convenience lookup for the top-nav tab bar shared across the main app
 * screens (dashboard/projects/connectors/settings). Maps the Figma nav
 * labels to the closest real route we have.
 */
export const MAIN_NAV_TABS = [
  { label: '대시보드', to: PATHS.dashboard },
  { label: '문서 관리', to: PATHS.filesNew },
  { label: '프로젝트', to: PATHS.projects },
  { label: '설정', to: PATHS.settingsTeam },
];
