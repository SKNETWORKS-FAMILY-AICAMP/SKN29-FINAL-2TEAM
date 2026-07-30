import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { Icon } from '../Icon/Icon';
import type { IconName } from '../Icon/Icon';
import { opsLogout } from '../../api/ops';
import { clearOpsSession, loadOpsSession } from '../../utils/opsSession';
import styles from './OpsLayout.module.css';

interface OpsNavItem {
  label: string;
  to: string;
  icon: IconName;
  end?: boolean;
}

const OPS_NAV_ITEMS: OpsNavItem[] = [
  { label: '운영 현황', to: '/ops', icon: 'app-window', end: true },
  { label: '연결 조직', to: '/ops/organizations', icon: 'chart-network' },
  { label: '계정 관리', to: '/ops/accounts', icon: 'users' },
  { label: '계정 연결·초대', to: '/ops/mappings', icon: 'link' },
  { label: '연결 서비스', to: '/ops/connectors', icon: 'database' },
  { label: '감사 로그', to: '/ops/audit', icon: 'shield-check' },
  { label: '전역 정책', to: '/ops/policies', icon: 'sliders' },
];

export function OpsLayout() {
  const navigate = useNavigate();
  const session = loadOpsSession();

  function handleLogout() {
    const token = session?.token;
    clearOpsSession();
    navigate('/ops/login', { replace: true });
    // 로그아웃 감사 기록은 화면 전환을 막지 않는다 — 실패해도 클라이언트 세션은 이미 지워졌다.
    if (token) opsLogout(token).catch(() => {});
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <NavLink to="/ops" className={styles.brand} aria-label="운영 현황으로 이동">
          <span className={styles.brandMark}>h</span>
          <span>halil 운영자 콘솔</span>
        </NavLink>

        <div className={styles.operator}>
          <span className={styles.operatorEmail}>{session?.admin.email ?? '운영자'}</span>
          <span aria-hidden="true">·</span>
          <button type="button" onClick={handleLogout}>
            로그아웃
          </button>
        </div>
      </header>

      <div className={styles.body}>
        <aside className={styles.sidebar}>
          <p className={styles.sidebarLabel}>운영자 메뉴</p>
          <nav className={styles.navigation} aria-label="운영자 메뉴">
            {OPS_NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  [styles.navItem, isActive ? styles.navItemActive : ''].filter(Boolean).join(' ')
                }
              >
                <Icon name={item.icon} size={17} />
                <span>{item.label}</span>
              </NavLink>
            ))}
          </nav>
        </aside>

        <main className={styles.main}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
