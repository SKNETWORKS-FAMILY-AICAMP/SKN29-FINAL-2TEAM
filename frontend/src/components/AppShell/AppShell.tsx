import type { ReactNode } from 'react';
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { APP_NAV_ITEMS, PATHS } from '../../routes';
import { clearSession, useSession } from '../../utils/session';
import { Icon } from '../Icon/Icon';
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
 * 상단바(프로젝트 컨텍스트 선택기 · 사용자). 7_홈화면_정의 §1.
 *
 * 기존 `TopNav`(상단 탭바)는 인증·Ops 화면과 아직 남아 있는 구 화면에만 쓴다.
 * 대시보드 탭이 G3에서 사라지고 문서 관리가 독립 메뉴에서 빠지므로 탭 구성
 * 자체가 유지되지 않는다 — 그래서 교체가 아니라 새 셸이다.
 */
export function AppShell({ children, variant = 'page' }: AppShellProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const session = useSession();
  const displayName = session?.account.display_name ?? '';

  function isActive(match: string[]): boolean {
    return match.some((prefix) => location.pathname === prefix || location.pathname.startsWith(`${prefix}/`));
  }

  function handleLogout() {
    clearSession();
    navigate(PATHS.login, { replace: true });
  }

  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar}>
        <Link to={PATHS.chat} className={styles.logo} aria-label="Chat으로 이동">
          <span className={styles.logoMark}>h</span>
          <span className={styles.logoText}>halil</span>
        </Link>

        <button type="button" className={styles.newChat} onClick={() => navigate(PATHS.chat)}>
          <Icon name="plus" size={16} />
          <span>새 대화</span>
        </button>

        <nav className={styles.nav}>
          {APP_NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={[styles.navItem, isActive(item.match) ? styles.navItemActive : ''].filter(Boolean).join(' ')}
            >
              <Icon name={item.icon} size={18} />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className={styles.right}>
        <header className={styles.topbar}>
          {/*
            프로젝트 컨텍스트 선택기 — 단계 A에서는 UI만이다. 실제 선택은
            chat_session.proj_id 연동(P1) 때 붙인다.
          */}
          <button type="button" className={styles.contextPicker} aria-haspopup="listbox">
            <Icon name="folder" size={15} color="var(--color-body)" />
            <span className={styles.contextLabel}>전체(팀)</span>
            <Icon name="chevron-down" size={14} color="var(--color-placeholder)" />
          </button>

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
