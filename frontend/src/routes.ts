import type { IconName } from './components/Icon/Icon';

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
  settingsTeam: '/settings/team',
  filesNew: '/files/new',
  projects: '/projects',
  projectDetail: '/projects/:projectId',
  opsLogin: '/ops/login',
  ops: '/ops',
  opsTeams: '/ops/teams',
  opsAccounts: '/ops/accounts',
  opsAccountDetail: '/ops/accounts/:accountId',
  opsMappings: '/ops/mappings',
  opsInviteDetail: '/ops/mappings/:inviteId',
  opsConnectors: '/ops/connectors',
  opsModels: '/ops/models',
  opsAudit: '/ops/audit',
  opsPolicies: '/ops/policies',

  // --- TO-BE (Agent Platform) — 개발지시 2차 단계 A ---
  chat: '/chat',
  agents: '/agents',
  agentEdit: '/agents/:agentId/edit',
  agentNew: '/agents/new/edit',
  /** 문서는 팀 소속이라 프로젝트로 좁히지 않는다. 경로는 PM 확정 대기(상수라 바꾸기 쉽다). */
  documents: '/documents',
  settingsConnectors: '/settings/connectors',
  settingsMcp: '/settings/mcp',
  settingsModel: '/settings/model',
  settingsPermissions: '/settings/permissions',
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
  { path: PATHS.chat, label: 'Chat (홈)', group: 'Agent Platform' },
  { path: PATHS.agents, label: '에이전트 목록', group: 'Agent Platform' },
  { path: PATHS.agentNew, label: '에이전트 만들기', group: 'Agent Platform' },
  { path: PATHS.documents, label: '문서', group: 'Agent Platform' },
  { path: PATHS.settingsTeam, label: '설정 · 팀', group: '설정' },
  { path: PATHS.settingsConnectors, label: '설정 · Connector', group: '설정' },
  { path: PATHS.settingsMcp, label: '설정 · MCP', group: '설정' },
  { path: PATHS.settingsModel, label: '설정 · Model', group: '설정' },
  { path: PATHS.settingsPermissions, label: '설정 · 권한', group: '설정' },
  { path: PATHS.filesNew, label: '문서 관리 (구)', group: '메인' },
  { path: PATHS.projects, label: '프로젝트 목록', group: '메인' },
  { path: PATHS.opsLogin, label: '운영자 로그인', group: '운영자 콘솔' },
  { path: PATHS.ops, label: '운영 현황', group: '운영자 콘솔' },
  { path: PATHS.opsTeams, label: '팀 현황', group: '운영자 콘솔' },
  { path: PATHS.opsAccounts, label: '계정 관리', group: '운영자 콘솔' },
  { path: PATHS.opsAccountDetail, label: '계정 상세', group: '운영자 콘솔' },
  { path: PATHS.opsMappings, label: '계정 연결·초대 현황', group: '운영자 콘솔' },
  { path: PATHS.opsInviteDetail, label: '초대 상세', group: '운영자 콘솔' },
  { path: PATHS.opsConnectors, label: '연결 서비스 현황', group: '운영자 콘솔' },
  { path: PATHS.opsModels, label: '모델 등록', group: '운영자 콘솔' },
  { path: PATHS.opsAudit, label: '감사 로그', group: '운영자 콘솔' },
  { path: PATHS.opsPolicies, label: '전역 정책', group: '운영자 콘솔' },
];

/**
 * Convenience lookup for the top-nav tab bar shared across the main app
 * screens (projects/files/settings). Maps the Figma nav labels to the
 * closest real route we have.
 *
 * 새 화면은 AppShell(사이드바)을 쓴다. 이 탭바는 아직 남아 있는 기존 화면
 * (문서 관리·프로젝트 상세 등)에서만 쓴다 — G3에서 정리된다.
 *
 * 4차 단계 1 — 「대시보드」 탭을 메뉴에서 뺀다. 라우트는 살아 있어 직접 URL로
 * 여전히 열린다(데모 백업). 처분은 단계 2(멘토링 Q13) 소관.
 */
export const MAIN_NAV_TABS = [
  { label: '문서 관리', to: PATHS.filesNew },
  { label: '프로젝트', to: PATHS.projects },
  { label: '설정', to: PATHS.settingsTeam },
];

export interface AppNavItem {
  label: string;
  to: string;
  icon: IconName;
  /** 이 접두사 중 하나로 시작하는 경로면 활성으로 본다. */
  match: string[];
}

/** AppShell 사이드바 4항목. Admin(Ops)은 별도 로그인이라 여기 없다. */
export const APP_NAV_ITEMS: AppNavItem[] = [
  { label: '채팅', to: PATHS.chat, icon: 'message-square', match: [PATHS.chat] },
  { label: '에이전트', to: PATHS.agents, icon: 'sparkles', match: [PATHS.agents] },
  { label: '프로젝트', to: PATHS.projects, icon: 'folder', match: [PATHS.projects, PATHS.documents] },
  { label: '설정', to: PATHS.settingsTeam, icon: 'sliders', match: ['/settings'] },
];

/** Settings 허브 탭. 8_화면개편_명세 §2 — SettingsPage를 탭 컨테이너로 개편. */
export const SETTINGS_TABS = [
  { label: '팀', to: PATHS.settingsTeam },
  { label: 'Connector', to: PATHS.settingsConnectors },
  { label: 'MCP', to: PATHS.settingsMcp },
  { label: 'Model', to: PATHS.settingsModel },
  { label: '권한', to: PATHS.settingsPermissions },
];
