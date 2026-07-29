export interface RouteEntry {
  path: string;
  label: string;
  group: string;
}

export const ROUTES: RouteEntry[] = [
  { path: '/', label: '랜딩 페이지', group: '마케팅' },
  { path: '/login', label: '로그인', group: '인증' },
  { path: '/signup', label: '회원가입', group: '인증' },
  { path: '/find-password', label: '비밀번호 찾기', group: '인증' },
  { path: '/onboarding/connectors', label: '외부 서비스 연결', group: '온보딩' },
  { path: '/onboarding/folders', label: '데이터 소스 설정', group: '온보딩' },
  { path: '/onboarding/folder-roles', label: '폴더 역할 지정', group: '온보딩' },
  { path: '/onboarding/jira-project', label: 'Jira 프로젝트 선택', group: '온보딩' },
  { path: '/settings/team', label: '팀장 설정', group: '설정' },
  { path: '/dashboard', label: '대시보드', group: '메인' },
  { path: '/files/new', label: '신규 파일', group: '메인' },
  { path: '/projects', label: '프로젝트 목록', group: '메인' },
  { path: '/workspace', label: '업무 분배 워크스페이스', group: '메인' },
  { path: '/tasks/distribution', label: '업무 분배 진행', group: '업무 분배' },
  { path: '/tasks/recommendation', label: '업무 추천 결과', group: '업무 분배' },
  { path: '/tasks/result', label: '배정 결과', group: '업무 분배' },
];

/**
 * Convenience lookup for the top-nav tab bar shared across the main app
 * screens (dashboard/projects/connectors/settings). Maps the Figma nav
 * labels to the closest real route we have.
 */
export const MAIN_NAV_TABS = [
  { label: '대시보드', to: '/dashboard' },
  { label: '문서 등록', to: '/files/new' },
  { label: '프로젝트', to: '/projects' },
  { label: '설정', to: '/settings/team' },
];
