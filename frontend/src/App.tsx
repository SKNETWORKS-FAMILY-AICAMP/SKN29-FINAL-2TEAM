import { Suspense, lazy } from 'react';
import { Routes, Route, Link } from 'react-router-dom';
import { ToastProvider } from './components';
import { ROUTES } from './routes';
import styles from './App.module.css';

const LandingPage = lazy(() => import('./pages/LandingPage/LandingPage'));
const LoginPage = lazy(() => import('./pages/LoginPage/LoginPage'));
const SignupPage = lazy(() => import('./pages/SignupPage/SignupPage'));
const FindPasswordPage = lazy(() => import('./pages/FindPasswordPage/FindPasswordPage'));
const ConnectorOnboardingPage = lazy(() => import('./pages/ConnectorOnboardingPage/ConnectorOnboardingPage'));
const FolderSelectPage = lazy(() => import('./pages/FolderSelectPage/FolderSelectPage'));
const FolderRoleAssignmentPage = lazy(() => import('./pages/FolderRoleAssignmentPage/FolderRoleAssignmentPage'));
const JiraProjectSelectPage = lazy(() => import('./pages/JiraProjectSelectPage/JiraProjectSelectPage'));
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
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route path="/find-password" element={<FindPasswordPage />} />
          <Route path="/onboarding/connectors" element={<ConnectorOnboardingPage />} />
          <Route path="/onboarding/folders" element={<FolderSelectPage />} />
          <Route path="/onboarding/folder-roles" element={<FolderRoleAssignmentPage />} />
          <Route path="/onboarding/jira-project" element={<JiraProjectSelectPage />} />
          <Route path="/dashboard" element={<MainDashboardPage />} />
          <Route path="/files/new" element={<NewFilesPage />} />
          <Route path="/projects" element={<ProjectListPage />} />
          <Route path="/workspace" element={<WorkspacePage />} />
          <Route path="/tasks/distribution" element={<TaskDistributionPage />} />
          <Route path="/tasks/recommendation" element={<TaskRecommendationPage />} />
          <Route path="/tasks/result" element={<AssignmentResultPage />} />
          <Route path="*" element={<DevIndexPage />} />
        </Routes>
      </Suspense>
    </ToastProvider>
  );
}

export default App;
