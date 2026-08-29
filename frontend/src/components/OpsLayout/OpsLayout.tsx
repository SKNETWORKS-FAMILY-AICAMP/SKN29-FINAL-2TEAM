import { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Icon } from '../Icon/Icon';
import type { IconName } from '../Icon/Icon';
import { Logo } from '../Logo/Logo';
import { opsLogout } from '../../api/ops';
import { clearOpsSession, loadOpsSession } from '../../utils/opsSession';
import { useNarrowViewport } from '../../utils/viewport';
import styles from './OpsLayout.module.css';

interface OpsNavItem {
  label: string;
  to: string;
  icon: IconName;
  end?: boolean;
}

const OPS_NAV_ITEMS: OpsNavItem[] = [
  { label: '운영 현황', to: '/ops', icon: 'app-window', end: true },
  { label: '팀 현황', to: '/ops/teams', icon: 'chart-network' },
  { label: '계정 관리', to: '/ops/accounts', icon: 'users' },
  { label: '계정 연결·초대', to: '/ops/mappings', icon: 'link' },
  { label: '연결 서비스', to: '/ops/connectors', icon: 'database' },
  { label: '모델', to: '/ops/models', icon: 'sparkles' },
  { label: '커스텀 도구', to: '/ops/mcp', icon: 'wrench' },
  { label: '가드레일', to: '/ops/guardrails', icon: 'lock' },
  // 사용 현황과 감사 로그는 「기록을 보는 자리」로 나란히 둔다 — 앞은 실행의
  // 집계, 뒤는 사람의 조치다.
  { label: '사용 현황', to: '/ops/usage', icon: 'chart-network' },
  { label: '감사 로그', to: '/ops/audit', icon: 'shield-check' },
  { label: '전역 정책', to: '/ops/policies', icon: 'sliders' },
];

/**
 * 접힘 상태. 앱 셸과 같은 키 규칙을 쓰되 **자리를 따로 둔다** — 운영자 콘솔은
 * 별도 로그인이고, 한쪽에서 접었다고 다른 쪽이 접힐 이유가 없다.
 */
const OPS_COLLAPSE_KEY = 'halil.opsSidebarCollapsed';

/** 사이드바가 드로어로 들어가는 폭. CSS 의 720px 과 같아야 한다. */
const OPS_NARROW_WIDTH = 720;

export function OpsLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const session = loadOpsSession();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const narrow = useNarrowViewport(OPS_NARROW_WIDTH);
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(OPS_COLLAPSE_KEY) === '1');

  // 드로어는 열리거나 닫히는 것이지 좁아지는 것이 아니다. 데스크탑에서 접어 둔
  // 사람에게 아이콘만 있는 드로어를 주면 무엇을 누르는지 알 수 없다.
  const iconsOnly = collapsed && !narrow;

  // 메뉴를 눌러 이동했으면 드로어는 할 일을 끝냈다.
  useEffect(() => {
    setDrawerOpen(false);
  }, [location.pathname]);

  function toggleCollapsed() {
    setCollapsed((prev) => {
      localStorage.setItem(OPS_COLLAPSE_KEY, prev ? '0' : '1');
      return !prev;
    });
  }

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
        {/* 좁은 화면에서 메뉴는 드로어로 들어간다 — 여는 길을 여기 둔다.
            앱 셸과 같은 자리·같은 모양이라 두 콘솔을 오가도 헷갈리지 않는다. */}
        <button
          type="button"
          className={styles.menuButton}
          onClick={() => setDrawerOpen(true)}
          aria-label="메뉴 열기"
          aria-expanded={drawerOpen}
        >
          <Icon name="menu" size={20} color="var(--color-body)" />
        </button>
        <NavLink to="/ops" className={styles.brand} aria-label="운영 현황으로 이동">
          <Logo height={22} />
          <span>운영자 콘솔</span>
        </NavLink>

        <div className={styles.operator}>
          <span className={styles.operatorEmail}>{session?.admin.email ?? '운영자'}</span>
          <span aria-hidden="true">·</span>
          <button type="button" onClick={handleLogout}>
            로그아웃
          </button>
        </div>
      </header>

      {drawerOpen && (
        <button
          type="button"
          className={styles.scrim}
          onClick={() => setDrawerOpen(false)}
          aria-label="메뉴 닫기"
        />
      )}

      <div className={styles.body}>
        <aside
          className={[
            styles.sidebar,
            iconsOnly ? styles.sidebarCollapsed : '',
            drawerOpen ? styles.sidebarOpen : '',
          ]
            .filter(Boolean)
            .join(' ')}
        >
          <div className={styles.sidebarHead}>
            <span className={styles.sidebarLabel}>메뉴</span>
            <button
              type="button"
              className={styles.collapse}
              onClick={toggleCollapsed}
              aria-label={collapsed ? '메뉴 펼치기' : '메뉴 접기'}
              title={collapsed ? '펼치기' : '접기'}
            >
              <Icon name="sidebar" size={18} />
            </button>
          </div>
          <nav className={styles.navigation} aria-label="운영자 메뉴">
            {OPS_NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  [styles.navItem, isActive ? styles.navItemActive : ''].filter(Boolean).join(' ')
                }
                // 접히면 라벨이 없으므로 아이콘만으로 무엇인지 알아야 한다.
                title={iconsOnly ? item.label : undefined}
              >
                <Icon name={item.icon} size={17} />
                <span className={styles.navLabel}>{item.label}</span>
              </NavLink>
            ))}
          </nav>
        </aside>

        <main className={styles.main}>
          <div key={location.pathname} className={styles.routeContent}>
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
