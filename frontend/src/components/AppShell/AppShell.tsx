import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { APP_NAV_ITEMS, PATHS } from '../../routes';
import { clearSession, useSession } from '../../utils/session';
import { useNarrowViewport } from '../../utils/viewport';
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
 * 로그인 후 화면의 공통 셸 — 왼쪽 사이드바(로고 / Chat·에이전트·프로젝트·설정 /
 * 바닥의 사용자). 7_홈화면_정의 §1.
 *
 * **상단바는 없앴다.** 프로젝트 선택기를 걷어낸 뒤로 남은 것이 사용자 영역뿐이었는데,
 * 그것 하나 때문에 모든 화면이 64px 를 내주고 있었다. 프로젝트는 모든 대화의 전제가
 * 아니라 대화가 속하는 자리다 — 어느 프로젝트의 대화인지는 Chat 사이드바의 계층
 * (프로젝트 > 대화)이 말한다. 위에 두면 회의록 정리처럼 프로젝트가 무의미한
 * 요청에도 계속 고르라고 하게 된다.
 *
 * 기존 `TopNav`(상단 탭바)를 쓰는 화면은 이제 없다 — 마지막 사용처였던 옛
 * 대시보드를 4차 단계 2에서 지웠고, `SettingsLayout`의 비-embedded 분기에만
 * 남아 있던 코드도 2026-08-13에 걷었다.
 */
/** 접힘 상태를 새로고침 뒤에도 유지한다 — 매번 다시 접게 하지 않는다. */
const COLLAPSE_KEY = 'halil.sidebarCollapsed';

export function AppShell({ children, variant = 'page' }: AppShellProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const session = useSession();
  const displayName = session?.account.display_name ?? '';
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(COLLAPSE_KEY) === '1');
  const narrow = useNarrowViewport();
  const [drawerOpen, setDrawerOpen] = useState(false);

  // 메뉴를 눌러 이동했으면 드로어는 할 일을 끝냈다. 안 닫으면 도착한 화면을
  // 자기가 가린 채로 남는다.
  useEffect(() => {
    setDrawerOpen(false);
  }, [location.pathname]);

  /**
   * 좁은 화면에서는 접힘을 무시한다. 드로어는 **열리거나 닫히거나**지 좁아지는
   * 것이 아니고, 데스크탑에서 접어 둔 사람에게 아이콘만 있는 드로어를 주면
   * 무엇을 누르는지 알 수 없다.
   */
  const iconsOnly = collapsed && !narrow;

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
      {/* 좁은 화면에만 나오는 상단 바. 사이드바가 드로어로 들어가면 로고와
          메뉴로 가는 길이 화면에서 사라지므로, 그 둘만 여기로 꺼내 둔다. */}
      <header className={styles.mobileBar}>
        <button
          type="button"
          className={styles.mobileMenu}
          onClick={() => setDrawerOpen(true)}
          aria-label="메뉴 열기"
          aria-expanded={drawerOpen}
        >
          <Icon name="menu" size={20} color="var(--color-body)" />
        </button>
        <Link to={PATHS.chat} className={styles.mobileLogo} aria-label="채팅으로 이동">
          <Logo variant="full" height={26} />
        </Link>
      </header>

      {/* 드로어 뒤를 덮는 면. 바깥을 누르면 닫히는 것이 이 모양의 약속이다. */}
      {drawerOpen && (
        <button
          type="button"
          className={styles.scrim}
          onClick={() => setDrawerOpen(false)}
          aria-label="메뉴 닫기"
        />
      )}

      <aside
        className={[
          styles.sidebar,
          iconsOnly ? styles.sidebarCollapsed : '',
          drawerOpen ? styles.sidebarOpen : '',
        ]
          .filter(Boolean)
          .join(' ')}
      >
        <div className={styles.brandRow}>
          {/* 접히면 글자가 들어갈 자리가 없다 — 그때만 마크로 바꾼다.
              높이가 두 쪽이 다른 것은 여백 때문이다. 워드마크는 글자가 그림 끝까지 차
              있어 44 가 곧 글자 높이지만, 마크는 96px 그림 안에 글리프가 53px 뿐이라
              같은 44 로는 작아 보인다 — 접힘 폭(68px)이 허락하는 만큼 키웠다. */}
          <Link to={PATHS.chat} className={styles.logo} aria-label="채팅으로 이동">
            <Logo variant={iconsOnly ? 'mark' : 'full'} height={iconsOnly ? 40 : 44} />
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
              title={iconsOnly ? item.label : undefined}
            >
              <Icon name={item.icon} size={18} />
              {!iconsOnly && <span>{item.label}</span>}
            </NavLink>
          ))}
        </nav>

        <div className={styles.userArea}>
          <span className={styles.avatar} title={displayName || undefined}>
            {displayName ? displayName.slice(0, 1) : <Icon name="user" size={15} />}
          </span>
          {/* 접히면 아바타만 남는다 — 이름도 글자 버튼도 좁아진 폭을 삐져나온다. */}
          {!iconsOnly && (
            <>
              <span className={styles.userName}>{displayName}</span>
              {session && (
                <button type="button" className={styles.logout} onClick={handleLogout}>
                  로그아웃
                </button>
              )}
            </>
          )}
        </div>
      </aside>

      <main className={variant === 'flush' ? styles.contentFlush : styles.content}>{children}</main>
    </div>
  );
}
