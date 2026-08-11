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
const NewFilesPage = lazy(() => import('./pages/NewFilesPage/NewFilesPage'));
const ProjectListPage = lazy(() => import('./pages/ProjectListPage/ProjectListPage'));
const ProjectDetailPage = lazy(() => import('./pages/ProjectDetailPage/ProjectDetailPage'));
const ChatPage = lazy(() => import('./pages/ChatPage/ChatPage'));
const AgentListPage = lazy(() => import('./pages/AgentListPage/AgentListPage'));
const AgentEditPage = lazy(() => import('./pages/AgentEditPage/AgentEditPage'));
const DocumentsPage = lazy(() => import('./pages/DocumentsPage/DocumentsPage'));
const OpsLoginPage = lazy(() => import('./pages/OpsLoginPage/OpsLoginPage'));
const OpsOverviewPage = lazy(() => import('./pages/OpsOverviewPage/OpsOverviewPage'));
const OpsTeamsPage = lazy(() => import('./pages/OpsTeamsPage/OpsTeamsPage'));
const OpsAccountsPage = lazy(() => import('./pages/OpsAccountsPage/OpsAccountsPage'));
const OpsMappingsPage = lazy(() => import('./pages/OpsMappingsPage/OpsMappingsPage'));
const OpsConnectorsPage = lazy(() => import('./pages/OpsConnectorsPage/OpsConnectorsPage'));
const OpsAuditPage = lazy(() => import('./pages/OpsAuditPage/OpsAuditPage'));
const OpsPoliciesPage = lazy(() => import('./pages/OpsPoliciesPage/OpsPoliciesPage'));

function DevIndexPage() {
  const groups = Array.from(new Set(ROUTES.map((r) => r.group)));
  return (
    <div className={styles.indexPage}>
      <h1 className={styles.indexTitle}>halil — 화면 목록</h1>
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
          <Route path={PATHS.devIndex} element={<DevIndexPage />} />
          <Route path={PATHS.devIndexAlias} element={<DevIndexPage />} />
          <Route path={PATHS.login} element={<LoginPage />} />
          <Route path={PATHS.signup} element={<SignupPage />} />
          <Route path={PATHS.inviteCode} element={<InviteCodePage />} />
          <Route path={PATHS.findPassword} element={<FindPasswordPage />} />
          <Route path={PATHS.resetPassword} element={<ResetPasswordPage />} />
          {/* 아래는 로그인이 필요한 화면. 세션이 없으면 /login으로 보내고 원래 가려던 곳을 기억한다. */}
          <Route path={PATHS.settingsTeam} element={<RequireAuth><SettingsPage /></RequireAuth>} />
          <Route path={PATHS.settingsConnectors} element={<RequireAuth><SettingsPage /></RequireAuth>} />
          <Route path={PATHS.settingsMcp} element={<RequireAuth><SettingsPage /></RequireAuth>} />
          <Route path={PATHS.settingsModel} element={<RequireAuth><SettingsPage /></RequireAuth>} />
          <Route path={PATHS.settingsPermissions} element={<RequireAuth><SettingsPage /></RequireAuth>} />
          {/* TO-BE (Agent Platform) — 개발지시 2차. 로그인 후 랜딩은 4차 단계 1에서 /chat 이 됐다. */}
          <Route path={PATHS.chat} element={<RequireAuth><ChatPage /></RequireAuth>} />
          <Route path={PATHS.agents} element={<RequireAuth><AgentListPage /></RequireAuth>} />
          <Route path={PATHS.agentEdit} element={<RequireAuth><AgentEditPage /></RequireAuth>} />
          <Route path={PATHS.documents} element={<RequireAuth><DocumentsPage /></RequireAuth>} />
          <Route path={PATHS.filesNew} element={<RequireAuth><NewFilesPage /></RequireAuth>} />
          <Route path={PATHS.projects} element={<RequireAuth><ProjectListPage /></RequireAuth>} />
          <Route path={PATHS.projectDetail} element={<RequireAuth><ProjectDetailPage /></RequireAuth>} />
          <Route path={PATHS.opsLogin} element={<OpsLoginPage />} />
          <Route element={<OpsRouteGuard />}>
            <Route path={PATHS.ops} element={<OpsLayout />}>
              <Route index element={<OpsOverviewPage />} />
              <Route path={PATHS.opsTeams} element={<OpsTeamsPage />} />
              <Route path={PATHS.opsAccounts} element={<OpsAccountsPage />} />
              <Route path={PATHS.opsMappings} element={<OpsMappingsPage />} />
              <Route path={PATHS.opsConnectors} element={<OpsConnectorsPage />} />
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
