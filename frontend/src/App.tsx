import { Suspense, lazy, useEffect } from 'react';
import { Routes, Route, Link, Navigate, useLocation } from 'react-router-dom';
import {
  IndexingProgress,
  OpsLayout,
  OpsRouteGuard,
  ProgressCardStack,
  RequireAuth,
  SkillJobCenter,
  ToastProvider,
} from './components';
import { AppErrorBoundary } from './components/AppErrorBoundary/AppErrorBoundary';
import { PATHS, ROUTES } from './routes';
import styles from './App.module.css';

const LandingPage = lazy(() => import('./pages/LandingPage/LandingPage'));
const LoginPage = lazy(() => import('./pages/LoginPage/LoginPage'));
const PrivacyPage = lazy(() => import('./pages/PrivacyPage/PrivacyPage'));
const SignupPage = lazy(() => import('./pages/SignupPage/SignupPage'));
const InviteCodePage = lazy(() => import('./pages/InviteCodePage/InviteCodePage'));
const FindPasswordPage = lazy(() => import('./pages/FindPasswordPage/FindPasswordPage'));
const ResetPasswordPage = lazy(() => import('./pages/ResetPasswordPage/ResetPasswordPage'));
const SettingsPage = lazy(() => import('./pages/SettingsPage/SettingsPage'));
const DocumentsPage = lazy(() => import('./pages/DocumentsPage/DocumentsPage'));
const ProjectListPage = lazy(() => import('./pages/ProjectListPage/ProjectListPage'));
const ProjectDetailPage = lazy(() => import('./pages/ProjectDetailPage/ProjectDetailPage'));
const ChatPage = lazy(() => import('./pages/ChatPage/ChatPage'));
const AgentVersionListPage = lazy(() => import('./pages/AgentVersionListPage/AgentVersionListPage'));
const AgentVersionEditPage = lazy(() => import('./pages/AgentVersionEditPage/AgentVersionEditPage'));
const OpsLoginPage = lazy(() => import('./pages/OpsLoginPage/OpsLoginPage'));
const OpsOverviewPage = lazy(() => import('./pages/OpsOverviewPage/OpsOverviewPage'));
const OpsTeamsPage = lazy(() => import('./pages/OpsTeamsPage/OpsTeamsPage'));
const OpsTeamDetailPage = lazy(() => import('./pages/OpsTeamDetailPage/OpsTeamDetailPage'));
const OpsAccountsPage = lazy(() => import('./pages/OpsAccountsPage/OpsAccountsPage'));
const OpsAccountDetailPage = lazy(() => import('./pages/OpsAccountDetailPage/OpsAccountDetailPage'));
const OpsMappingsPage = lazy(() => import('./pages/OpsMappingsPage/OpsMappingsPage'));
const OpsInviteDetailPage = lazy(() => import('./pages/OpsInviteDetailPage/OpsInviteDetailPage'));
const OpsConnectorsPage = lazy(() => import('./pages/OpsConnectorsPage/OpsConnectorsPage'));
const OpsConnectorDetailPage = lazy(() => import('./pages/OpsConnectorDetailPage/OpsConnectorDetailPage'));
const OpsModelsPage = lazy(() => import('./pages/OpsModelsPage/OpsModelsPage'));
const OpsMcpPage = lazy(() => import('./pages/OpsMcpPage/OpsMcpPage'));
const OpsGuardrailsPage = lazy(() => import('./pages/OpsGuardrailsPage/OpsGuardrailsPage'));
const OpsUsagePage = lazy(() => import('./pages/OpsUsagePage/OpsUsagePage'));
const OpsAuditPage = lazy(() => import('./pages/OpsAuditPage/OpsAuditPage'));
const OpsPoliciesPage = lazy(() => import('./pages/OpsPoliciesPage/OpsPoliciesPage'));
const NotFoundPage = lazy(() => import('./pages/NotFoundPage/NotFoundPage'));

const DEFAULT_DESCRIPTION =
  'halil은 팀의 문서·사람·프로젝트 정보를 근거와 함께 찾아 실제 업무 실행으로 연결하는 프로젝트 운영 AI 플랫폼입니다.';

function pageMeta(pathname: string): { title: string; description: string; canonical: boolean } {
  const exact: Record<string, [string, string, boolean]> = {
    [PATHS.landing]: ['halil · 프로젝트 운영 AI 플랫폼', DEFAULT_DESCRIPTION, true],
    [PATHS.login]: ['로그인 · halil', 'halil 프로젝트 운영 AI 플랫폼에 로그인합니다.', true],
    [PATHS.signup]: ['회원가입 · halil', 'halil 팀 계정을 만들고 프로젝트 운영을 시작합니다.', true],
    [PATHS.inviteCode]: ['초대코드 회원가입 · halil', '팀 초대코드로 halil 계정을 만듭니다.', true],
    [PATHS.findPassword]: ['비밀번호 찾기 · halil', 'halil 계정의 비밀번호 재설정 링크를 요청합니다.', true],
    [PATHS.resetPassword]: ['비밀번호 재설정 · halil', 'halil 계정의 비밀번호를 재설정합니다.', false],
    [PATHS.privacy]: ['개인정보처리방침 · halil', 'halil의 개인정보 수집·이용·보관 방침을 확인합니다.', true],
    [PATHS.chat]: ['채팅 · halil', DEFAULT_DESCRIPTION, false],
    [PATHS.agentVersions]: ['에이전트 · halil', DEFAULT_DESCRIPTION, false],
    [PATHS.agentVersionsTeam]: ['팀 에이전트 · halil', DEFAULT_DESCRIPTION, false],
    [PATHS.agentVersionsFavorites]: ['즐겨찾는 에이전트 · halil', DEFAULT_DESCRIPTION, false],
    [PATHS.projects]: ['프로젝트 · halil', DEFAULT_DESCRIPTION, false],
    [PATHS.documents]: ['문서 · halil', DEFAULT_DESCRIPTION, false],
    [PATHS.settingsTeam]: ['팀 설정 · halil', DEFAULT_DESCRIPTION, false],
    [PATHS.settingsConnectors]: ['커넥터 설정 · halil', DEFAULT_DESCRIPTION, false],
    [PATHS.settingsSkills]: ['스킬 설정 · halil', DEFAULT_DESCRIPTION, false],
    [PATHS.opsLogin]: ['운영자 로그인 · halil', 'halil 운영자 콘솔에 로그인합니다.', false],
  };
  const found = exact[pathname];
  if (found) return { title: found[0], description: found[1], canonical: found[2] };
  if (pathname.startsWith('/chat/')) return { title: '대화 · halil', description: DEFAULT_DESCRIPTION, canonical: false };
  if (pathname.startsWith('/projects/')) return { title: '프로젝트 상세 · halil', description: DEFAULT_DESCRIPTION, canonical: false };
  if (pathname.startsWith('/agents/versions/')) return { title: '에이전트 편집 · halil', description: DEFAULT_DESCRIPTION, canonical: false };
  if (pathname.startsWith('/ops')) return { title: '운영자 콘솔 · halil', description: DEFAULT_DESCRIPTION, canonical: false };
  return { title: '페이지를 찾을 수 없음 · halil', description: '요청한 halil 페이지를 찾을 수 없습니다.', canonical: false };
}

function RouteMeta() {
  const { pathname } = useLocation();

  useEffect(() => {
    const meta = pageMeta(pathname);
    document.title = meta.title;

    let description = document.querySelector<HTMLMetaElement>('meta[name="description"]');
    if (!description) {
      description = document.createElement('meta');
      description.name = 'description';
      document.head.append(description);
    }
    description.content = meta.description;

    let canonical = document.querySelector<HTMLLinkElement>('link[rel="canonical"]');
    if (meta.canonical) {
      if (!canonical) {
        canonical = document.createElement('link');
        canonical.rel = 'canonical';
        document.head.append(canonical);
      }
      canonical.href = `${window.location.origin}${pathname}`;
    } else {
      canonical?.remove();
    }
  }, [pathname]);

  return null;
}

function DevIndexPage() {
  const groups = Array.from(new Set(ROUTES.map((r) => r.group)));
  return (
    <div className={styles.indexPage}>
      <h1 className={styles.indexTitle}>halil 화면 목록</h1>
      <p className={styles.indexSubtitle}>Figma에서 변환된 모든 화면입니다. 아래 목록에서 확인할 화면을 선택하세요.</p>
      {groups.map((group) => (
        <div key={group} className={styles.indexGroup}>
          <h2 className={styles.indexGroupTitle}>{group}</h2>
          <ul className={styles.indexList}>
            {ROUTES.filter((r) => r.group === group).map((r) => (
              <li key={r.path}>
                <Link to={r.path} className={styles.indexLink}>
                  {r.label}
                  <span className={styles.indexPath}>{r.path}</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function LoadingFallback() {
  return <div className={styles.loading}>불러오는 중…</div>;
}

function App() {
  const location = useLocation();

  return (
    <ToastProvider>
      <RouteMeta />
      <AppErrorBoundary key={location.pathname}>
        <Suspense fallback={<LoadingFallback />}>
          <Routes>
          <Route path={PATHS.landing} element={<LandingPage />} />
          {/* 개발용 화면 목록은 개발 서버에서만 연다. 배포본에서는 라우트가 없어
              랜딩으로 떨어진다 — `ROUTES` 에 운영자 콘솔 경로와 「문서 관리 (구)」가
              라벨과 함께 들어 있어, 공개 주소에서 열리면 그 목록이 그대로 보인다. */}
          {import.meta.env.DEV && (
            <>
              <Route path={PATHS.devIndex} element={<DevIndexPage />} />
              <Route path={PATHS.devIndexAlias} element={<DevIndexPage />} />
            </>
          )}
          <Route path={PATHS.login} element={<LoginPage />} />
          {/* 로그인 위쪽에 둔다 — 로그인 없이 열려야 하는 공개 문서다. */}
          <Route path={PATHS.privacy} element={<PrivacyPage />} />
          <Route path={PATHS.signup} element={<SignupPage />} />
          <Route path={PATHS.inviteCode} element={<InviteCodePage />} />
          <Route path={PATHS.findPassword} element={<FindPasswordPage />} />
          <Route path={PATHS.resetPassword} element={<ResetPasswordPage />} />
          {/* 아래는 로그인이 필요한 화면. 세션이 없으면 /login으로 보내고 원래 가려던 곳을 기억한다. */}
          {/* 탭 없는 `/settings` 는 라우트가 없어 **랜딩으로 떨어졌다**(2026-08-12 QA §C).
              사이드바는 `/settings/team` 으로 보내지만, 주소를 직접 치거나 북마크한
              사람은 로그아웃된 것처럼 보인다. 첫 탭으로 넘긴다. */}
          <Route path="/settings" element={<Navigate to={PATHS.settingsTeam} replace />} />
          <Route path={PATHS.settingsTeam} element={<RequireAuth><SettingsPage /></RequireAuth>} />
          <Route path={PATHS.settingsConnectors} element={<RequireAuth><SettingsPage /></RequireAuth>} />
          <Route path={PATHS.settingsSkills} element={<RequireAuth><SettingsPage /></RequireAuth>} />
          {/* 「내 파일」이 있던 자리(`/settings/my-files`). 2026-08-25 에 「문서」로
              옮겼고, 북마크한 사람이 랜딩으로 떨어지지 않게 넘겨 준다 — 탭 없는
              `/settings` 가 랜딩으로 떨어졌던 것과 같은 사고를 되풀이하지 않는다. */}
          <Route path="/settings/my-files" element={<Navigate to={PATHS.documents} replace />} />
          <Route path={PATHS.documents} element={<RequireAuth><DocumentsPage /></RequireAuth>} />
          {/* TO-BE (Agent Platform) — 개발지시 2차. 로그인 후 랜딩은 4차 단계 1에서 /chat 이 됐다. */}
          <Route path={PATHS.chat} element={<RequireAuth><ChatPage /></RequireAuth>} />
          <Route path={PATHS.chatSession} element={<RequireAuth><ChatPage /></RequireAuth>} />
          {/* 새 버전 스키마(services/agent_runtime/) 전용 — 옛 위 두 라우트와
              나란히 존재한다. Chat은 아직 이 스키마를 모른다. */}
          <Route path={PATHS.agentVersions} element={<RequireAuth><AgentVersionListPage /></RequireAuth>} />
          <Route path={PATHS.agentVersionsTeam} element={<RequireAuth><AgentVersionListPage /></RequireAuth>} />
          <Route path={PATHS.agentVersionsFavorites} element={<RequireAuth><AgentVersionListPage /></RequireAuth>} />
          <Route path={PATHS.agentVersionEdit} element={<RequireAuth><AgentVersionEditPage /></RequireAuth>} />
          <Route path={PATHS.projects} element={<RequireAuth><ProjectListPage /></RequireAuth>} />
          <Route path={PATHS.projectDetail} element={<RequireAuth><ProjectDetailPage /></RequireAuth>} />
          <Route path={PATHS.opsLogin} element={<OpsLoginPage />} />
          <Route element={<OpsRouteGuard />}>
            <Route path={PATHS.ops} element={<OpsLayout />}>
              <Route index element={<OpsOverviewPage />} />
              <Route path={PATHS.opsTeams} element={<OpsTeamsPage />} />
              <Route path={PATHS.opsTeamDetail} element={<OpsTeamDetailPage />} />
              <Route path={PATHS.opsAccounts} element={<OpsAccountsPage />} />
              <Route path={PATHS.opsAccountDetail} element={<OpsAccountDetailPage />} />
              <Route path={PATHS.opsMappings} element={<OpsMappingsPage />} />
              <Route path={PATHS.opsInviteDetail} element={<OpsInviteDetailPage />} />
              <Route path={PATHS.opsConnectors} element={<OpsConnectorsPage />} />
              <Route path={PATHS.opsConnectorDetail} element={<OpsConnectorDetailPage />} />
              <Route path={PATHS.opsModels} element={<OpsModelsPage />} />
              <Route path={PATHS.opsMcp} element={<OpsMcpPage />} />
              <Route path={PATHS.opsGuardrails} element={<OpsGuardrailsPage />} />
              <Route path={PATHS.opsUsage} element={<OpsUsagePage />} />
              <Route path={PATHS.opsAudit} element={<OpsAuditPage />} />
              <Route path={PATHS.opsPolicies} element={<OpsPoliciesPage />} />
              <Route path="*" element={<Navigate to={PATHS.ops} replace />} />
            </Route>
          </Route>
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </Suspense>
      </AppErrorBoundary>
      {/* **`<Routes>` 바깥이다.** 라우트가 바뀌어도 이 컴포넌트들은 언마운트되지
          않아서 진행 카드와 폴링이 그대로 이어진다 — 페이지를 옮겨도 유지되는
          것이 이 자리의 전부이고, 그래서 전역 상태 저장소가 따로 필요 없다.
          `IndexingProgress`/`SkillJobCenter`는 이제 직접 안 그리고
          `useStackedCard()`로 등록만 한다(2026-08-26) — 실제로 오른쪽 아래에
          쌓아 그리는 건 `ProgressCardStack` 하나뿐이라 두 카드가 동시에
          떠도 겹치지 않는다. */}
      <IndexingProgress />
      <SkillJobCenter />
      <ProgressCardStack />
    </ToastProvider>
  );
}

export default App;
