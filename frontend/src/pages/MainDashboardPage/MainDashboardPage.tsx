import { TopNav, useToast } from '../../components';
import { MAIN_NAV_TABS } from '../../routes';
import { OrgChartPanel } from './OrgChartPanel';
import { WorkloadPanel } from './WorkloadPanel';
import { TaskStatusPanel } from './TaskStatusPanel';
import { CalendarWidget } from './CalendarWidget';
import { RecentUpdatesPanel } from './RecentUpdatesPanel';
import styles from './MainDashboardPage.module.css';

export default function MainDashboardPage() {
  const { showToast } = useToast();

  return (
    <div className={styles.page}>
      <TopNav
        tabs={MAIN_NAV_TABS}
        activeTo="/dashboard"
        unreadCount={3}
        userLabel="김민우"
        onBellClick={() => showToast('박서준 님의 업무 부하가 90%를 초과했습니다', 'info')}
      />

      <div className={styles.content}>
        <div className={styles.leftPanel}>
          <OrgChartPanel />
          <WorkloadPanel />
        </div>

        <div className={styles.rightPanel}>
          <TaskStatusPanel />
          <CalendarWidget />
          <RecentUpdatesPanel />
        </div>
      </div>
    </div>
  );
}
