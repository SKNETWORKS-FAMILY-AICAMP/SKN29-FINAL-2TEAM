import { Suspense, lazy } from 'react';
import { Routes, Route, Link, Navigate } from 'react-router-dom';
import { OpsLayout, OpsRouteGuard, RequireAuth, ToastProvider } from './components';
import { PATHS, ROUTES } from './routes';
import styles from './App.module.css';

const LandingPage = lazy(() => import('./pages/LandingPage/LandingPage'));
const LoginPage = lazy(() => import('./pages/LoginPage/LoginPage'));
const SignupPage = lazy(() => import('./pages/SignupPage/SignupPage'));
const InviteCodePage = lazy(() => import('./pages/InviteCodePage/InviteCodePage'));
const FindPasswordPage = lazy(() => import('./pages/FindPasswordPage/FindPasswordPage'));
const ResetPasswordPage = lazy(() => import('./pages/ResetPasswordPage/ResetPasswordPage'));
const SettingsPage = lazy(() => import('./pages/SettingsPage/SettingsPage'));
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
  return (
    <ToastProvider>
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
          <Route path={PATHS.settingsMyFiles} element={<RequireAuth><SettingsPage /></RequireAuth>} />
          <Route path={PATHS.settingsSkills} element={<RequireAuth><SettingsPage /></RequireAuth>} />
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
          <Route path="*" element={<LandingPage />} />
        </Routes>
      </Suspense>
    </ToastProvider>
  );
}

export default App;
