import { useState } from 'react';
import type { ReactNode } from 'react';
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { APP_NAV_ITEMS, PATHS } from '../../routes';
import { clearSession, useSession } from '../../utils/session';
import { Icon } from '../Icon/Icon';
import { Logo } from '../Logo/Logo';
import styles from './AppShell.module.css';

export interface AppShellProps {
  children: ReactNode;
  /**
   * 'page'  — 셸이 여백을 주고 세로 스크롤을 맡는다 (목록·설정처럼 보통 화면)
   * 'flush' — 여백 없이 남은 높이를 그대로 넘긴다 (Chat처럼 자체 레이아웃을 쓰는 화면)
   */
  variant?: 'page' | 'flush';
}

/**
 * 로그인 후 화면의 공통 셸 — 왼쪽 사이드바(Chat/에이전트/프로젝트/설정) +
 * 상단바(사용자). 7_홈화면_정의 §1.
 *
 * **상단바의 프로젝트 선택기는 없앴다.** 프로젝트는 모든 대화의 전제가 아니라
 * 대화가 속하는 자리다 — 어느 프로젝트의 대화인지는 Chat 사이드바의 계층
 * (프로젝트 > 대화)이 말한다. 상단바에 두면 회의록 정리처럼 프로젝트가 무의미한
 * 요청에도 계속 고르라고 하게 된다.
 *
 * 기존 `TopNav`(상단 탭바)를 쓰는 화면은 이제 없다 — 마지막 사용처였던 옛
 * 대시보드를 4차 단계 2에서 지웠다. `SettingsLayout`의 비-embedded 분기에만
 * 코드가 남아 있는데, 그 분기로 들어오는 라우트도 없다.
 */
/** 접힘 상태를 새로고침 뒤에도 유지한다 — 매번 다시 접게 하지 않는다. */
const COLLAPSE_KEY = 'halil.sidebarCollapsed';

export function AppShell({ children, variant = 'page' }: AppShellProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const session = useSession();
  const displayName = session?.account.display_name ?? '';
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(COLLAPSE_KEY) === '1');

  function isActive(match: string[]): boolean {
    return match.some((prefix) => location.pathname === prefix || location.pathname.startsWith(`${prefix}/`));
  }

  function toggleCollapsed() {
    setCollapsed((prev) => {
      localStorage.setItem(COLLAPSE_KEY, prev ? '0' : '1');
      return !prev;
    });
  }

  function handleLogout() {
    clearSession();
    navigate(PATHS.login, { replace: true });
  }

  return (
    <div className={styles.shell}>
      <aside className={[styles.sidebar, collapsed ? styles.sidebarCollapsed : ''].filter(Boolean).join(' ')}>
        <div className={styles.brandRow}>
          {/* 접히면 글자가 들어갈 자리가 없다 — 그때만 마크로 바꾼다. */}
          <Link to={PATHS.chat} className={styles.logo} aria-label="채팅으로 이동">
            <Logo variant={collapsed ? 'mark' : 'full'} height={collapsed ? 30 : 26} />
          </Link>
          <button
            type="button"
            className={styles.collapse}
            onClick={toggleCollapsed}
            aria-label={collapsed ? '사이드바 펼치기' : '사이드바 접기'}
            title={collapsed ? '펼치기' : '접기'}
          >
            <Icon name={collapsed ? 'arrow-right' : 'arrow-left'} size={16} color="var(--color-muted)" />
          </button>
        </div>

        <nav className={styles.nav}>
          {APP_NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={[styles.navItem, isActive(item.match) ? styles.navItemActive : ''].filter(Boolean).join(' ')}
              // 접히면 라벨이 없으므로 아이콘만으로 무엇인지 알아야 한다.
              title={collapsed ? item.label : undefined}
            >
              <Icon name={item.icon} size={18} />
              {!collapsed && <span>{item.label}</span>}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className={styles.right}>
        <header className={styles.topbar}>
          <div className={styles.userArea}>
            <button type="button" className={styles.iconButton} aria-label="알림">
              <Icon name="bell" size={18} color="var(--color-body)" />
            </button>
            <span className={styles.avatar} title={displayName || undefined}>
              {displayName ? displayName.slice(0, 1) : <Icon name="user" size={15} />}
            </span>
            {session && (
              <button type="button" className={styles.logout} onClick={handleLogout}>
                로그아웃
              </button>
            )}
          </div>
        </header>

        <main className={variant === 'flush' ? styles.contentFlush : styles.content}>{children}</main>
      </div>
    </div>
  );
}
