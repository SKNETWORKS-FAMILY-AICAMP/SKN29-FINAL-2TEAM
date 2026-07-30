import { Suspense, lazy } from 'react';
import { Routes, Route, Link } from 'react-router-dom';
import { RequireAuth, ToastProvider } from './components';
import { ROUTES } from './routes';
import styles from './App.module.css';

const LandingPage = lazy(() => import('./pages/LandingPage/LandingPage'));
const LoginPage = lazy(() => import('./pages/LoginPage/LoginPage'));
const SignupPage = lazy(() => import('./pages/SignupPage/SignupPage'));
const InviteCodePage = lazy(() => import('./pages/InviteCodePage/InviteCodePage'));
const FindPasswordPage = lazy(() => import('./pages/FindPasswordPage/FindPasswordPage'));
const ResetPasswordPage = lazy(() => import('./pages/ResetPasswordPage/ResetPasswordPage'));
const ConnectorOnboardingPage = lazy(() => import('./pages/ConnectorOnboardingPage/ConnectorOnboardingPage'));
const FolderSelectPage = lazy(() => import('./pages/FolderSelectPage/FolderSelectPage'));
const FolderRoleAssignmentPage = lazy(() => import('./pages/FolderRoleAssignmentPage/FolderRoleAssignmentPage'));
const JiraProjectSelectPage = lazy(() => import('./pages/JiraProjectSelectPage/JiraProjectSelectPage'));
const SettingsPage = lazy(() => import('./pages/SettingsPage/SettingsPage'));
const MainDashboardPage = lazy(() => import('./pages/MainDashboardPage/MainDashboardPage'));
const NewFilesPage = lazy(() => import('./pages/NewFilesPage/NewFilesPage'));
const ProjectListPage = lazy(() => import('./pages/ProjectListPage/ProjectListPage'));
const WorkspacePage = lazy(() => import('./pages/WorkspacePage/WorkspacePage'));
const TaskDistributionPage = lazy(() => import('./pages/TaskDistributionPage/TaskDistributionPage'));
const TaskRecommendationPage = lazy(() => import('./pages/TaskRecommendationPage/TaskRecommendationPage'));
const AssignmentResultPage = lazy(() => import('./pages/AssignmentResultPage/AssignmentResultPage'));

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
          <Route path="/" element={<LandingPage />} />
          <Route path="/screens" element={<DevIndexPage />} />
          <Route path="/dev/screens" element={<DevIndexPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route path="/invite-code" element={<InviteCodePage />} />
          <Route path="/find-password" element={<FindPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          {/* 아래는 로그인이 필요한 화면. 세션이 없으면 /login으로 보내고 원래 가려던 곳을 기억한다. */}
          <Route path="/onboarding/connectors" element={<RequireAuth><ConnectorOnboardingPage /></RequireAuth>} />
          <Route path="/onboarding/folders" element={<RequireAuth><FolderSelectPage /></RequireAuth>} />
          <Route path="/onboarding/folder-roles" element={<RequireAuth><FolderRoleAssignmentPage /></RequireAuth>} />
          <Route path="/onboarding/jira-project" element={<RequireAuth><JiraProjectSelectPage /></RequireAuth>} />
          <Route path="/settings/team" element={<RequireAuth><SettingsPage /></RequireAuth>} />
          <Route path="/dashboard" element={<RequireAuth><MainDashboardPage /></RequireAuth>} />
          <Route path="/files/new" element={<RequireAuth><NewFilesPage /></RequireAuth>} />
          <Route path="/projects" element={<RequireAuth><ProjectListPage /></RequireAuth>} />
          <Route path="/workspace" element={<RequireAuth><WorkspacePage /></RequireAuth>} />
          <Route path="/tasks/distribution" element={<RequireAuth><TaskDistributionPage /></RequireAuth>} />
          <Route path="/tasks/recommendation" element={<RequireAuth><TaskRecommendationPage /></RequireAuth>} />
          <Route path="/tasks/result" element={<RequireAuth><AssignmentResultPage /></RequireAuth>} />
          <Route path="*" element={<LandingPage />} />
        </Routes>
      </Suspense>
    </ToastProvider>
  );
}

export default App;
