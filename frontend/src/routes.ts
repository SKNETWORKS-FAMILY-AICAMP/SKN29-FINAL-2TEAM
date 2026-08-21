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
  projects: '/projects',
  projectDetail: '/projects/:projectId',
  opsLogin: '/ops/login',
  ops: '/ops',
  opsTeams: '/ops/teams',
  opsTeamDetail: '/ops/teams/:teamId',
  opsAccounts: '/ops/accounts',
  opsAccountDetail: '/ops/accounts/:accountId',
  opsMappings: '/ops/mappings',
  opsInviteDetail: '/ops/mappings/:inviteId',
  opsConnectors: '/ops/connectors',
  opsConnectorDetail: '/ops/connectors/:connId',
  opsModels: '/ops/models',
  opsMcp: '/ops/mcp',
  opsGuardrails: '/ops/guardrails',
  opsAudit: '/ops/audit',
  opsPolicies: '/ops/policies',

  // --- TO-BE (Agent Platform) — 개발지시 2차 단계 A ---
  chat: '/chat',
  /**
   * 열려 있는 대화. **새로고침하면 보던 대화를 잃던 것**을 URL 로 고쳤다
   * (2026-08-12 QA). 대화 내용 복원은 원래 됐고, 잃던 것은 「어디를 보고
   * 있었는가」였다. 같은 계정 안에서는 링크로 건네줄 수도 있다.
   */
  chatSession: '/chat/:sessionId',
  agents: '/agents',
  agentEdit: '/agents/:agentId/edit',
  agentNew: '/agents/new/edit',
  /** 새 버전 스키마(services/agent_runtime/) 전용 — 위 옛 라우트와 나란히
   * 존재한다. 사이드바 "에이전트"는 이제 이쪽을 가리킨다(2026-08-15) —
   * Chat 상단 드롭다운이 이 스키마 에이전트를 직접 부를 수 있다. 옛 라우트는
   * 직접 URL로만 남아 있다(APP_NAV_ITEMS 주석 참고). */
  /** "개인" 탭 — DRAFT(아직 팀에 공유 안 한) 에이전트. 서버도 같은 기준으로
   * 본인 것만 돌려준다(2026-08-18, `list_for_team()`). */
  agentVersions: '/agents/versions',
  /** "팀 공유" 탭 — ACTIVE·DISABLED. 한 번이라도 활성화된 적이 있으면 여기. */
  agentVersionsTeam: '/agents/versions/team',
  /** "즐겨찾기" 탭(2026-08-18) — 개인/팀 공유와 무관하게, 이 계정이 별을
   * 누른 에이전트만. 계정별 개인 값이라 나만 본다. */
  agentVersionsFavorites: '/agents/versions/favorites',
  agentVersionEdit: '/agents/versions/:agentId/edit',
  agentVersionNew: '/agents/versions/new/edit',
  settingsConnectors: '/settings/connectors',
  settingsMyFiles: '/settings/my-files',
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
  {
    path: PATHS.agentVersions,
    label: '에이전트 목록 · 개인 (버전, Deep Agent)',
    group: 'Agent Platform',
  },
  {
    path: PATHS.agentVersionsTeam,
    label: '에이전트 목록 · 팀 공유 (버전, Deep Agent)',
    group: 'Agent Platform',
  },
  {
    path: PATHS.agentVersionsFavorites,
    label: '에이전트 목록 · 즐겨찾기 (버전, Deep Agent)',
    group: 'Agent Platform',
  },
  {
    path: PATHS.agentVersionNew,
    label: '에이전트 만들기 (버전, Deep Agent)',
    group: 'Agent Platform',
  },
  { path: PATHS.settingsTeam, label: '설정 · 팀', group: '설정' },
  { path: PATHS.settingsConnectors, label: '설정 · 커넥터', group: '설정' },
  { path: PATHS.settingsMyFiles, label: '설정 · 내 파일', group: '설정' },
  { path: PATHS.projects, label: '프로젝트 목록', group: '메인' },
  { path: PATHS.opsLogin, label: '운영자 로그인', group: '운영자 콘솔' },
  { path: PATHS.ops, label: '운영 현황', group: '운영자 콘솔' },
  { path: PATHS.opsTeams, label: '팀 현황', group: '운영자 콘솔' },
  { path: PATHS.opsTeamDetail, label: '팀 상세', group: '운영자 콘솔' },
  { path: PATHS.opsAccounts, label: '계정 관리', group: '운영자 콘솔' },
  { path: PATHS.opsAccountDetail, label: '계정 상세', group: '운영자 콘솔' },
  { path: PATHS.opsMappings, label: '계정 연결·초대 현황', group: '운영자 콘솔' },
  { path: PATHS.opsInviteDetail, label: '초대 상세', group: '운영자 콘솔' },
  { path: PATHS.opsConnectors, label: '연결 서비스 현황', group: '운영자 콘솔' },
  { path: PATHS.opsModels, label: '모델', group: '운영자 콘솔' },
  { path: PATHS.opsMcp, label: '커스텀 도구', group: '운영자 콘솔' },
  { path: PATHS.opsGuardrails, label: '가드레일', group: '운영자 콘솔' },
  { path: PATHS.opsAudit, label: '감사 로그', group: '운영자 콘솔' },
  { path: PATHS.opsPolicies, label: '전역 정책', group: '운영자 콘솔' },
];

export interface AppNavItem {
  label: string;
  to: string;
  icon: IconName;
  /** 이 접두사 중 하나로 시작하는 경로면 활성으로 본다. */
  match: string[];
}

/**
 * AppShell 사이드바 4항목. Admin(Ops)은 별도 로그인이라 여기 없다.
 *
 * "에이전트"는 2026-08-15부터 새 버전 스키마 화면(`agentVersions`)을 가리킨다
 * — Chat이 이제 이 스키마 에이전트를 드롭다운으로 직접 부를 수 있게 되면서
 * (§ChatPage.tsx 헤더 주석) 옛 화면(`agents`, "테스트 실행" 포함)을 사용자
 * 동선에서 뺐다. 옛 화면 자체는 지우지 않았다 — `/agents`로 직접 들어가거나
 * `/screens` 개발 인덱스에서는 여전히 열린다.
 */
export const APP_NAV_ITEMS: AppNavItem[] = [
  { label: '채팅', to: PATHS.chat, icon: 'message-square', match: [PATHS.chat] },
  {
    label: '에이전트',
    to: PATHS.agentVersions,
    icon: 'sparkles',
    match: [PATHS.agentVersions, PATHS.agentVersionsTeam, PATHS.agentVersionsFavorites],
  },
  { label: '프로젝트', to: PATHS.projects, icon: 'folder', match: [PATHS.projects] },
  { label: '설정', to: PATHS.settingsTeam, icon: 'sliders', match: ['/settings'] },
];

/** Settings 허브 탭. 8_화면개편_명세 §2 — SettingsPage를 탭 컨테이너로 개편. */
export const SETTINGS_TABS = [
  { label: '팀', to: PATHS.settingsTeam },
  { label: '커넥터', to: PATHS.settingsConnectors },
  { label: '내 파일', to: PATHS.settingsMyFiles },
];
