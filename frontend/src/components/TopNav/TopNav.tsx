import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { Icon } from '../Icon/Icon';
import { clearSession, useSession } from '../../utils/session';
import styles from './TopNav.module.css';

export interface NavTabItem {
  label: string;
  to: string;
}

export interface TopNavProps {
  tabs: NavTabItem[];
  activeTo?: string;
  stepBadge?: string;
  unreadCount?: number;
  onBellClick?: () => void;
  userLabel?: string;
}

export function TopNav({
  tabs,
  activeTo,
  stepBadge,
  unreadCount = 0,
  onBellClick,
  userLabel,
}: TopNavProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const session = useSession();
  const currentPath = activeTo ?? location.pathname;
  // 아바타에는 로그인한 계정 이름을 쓴다. userLabel은 명시적으로 넘긴 경우만 우선한다.
  const label = userLabel ?? session?.account.display_name;

  function handleLogout() {
    clearSession();
    navigate('/login', { replace: true });
  }

  return (
    <header className={styles.nav}>
      <Link to="/dashboard" className={styles.logo} aria-label="대시보드로 이동">
        <span className={styles.mark}>h</span>
        <span className={styles.wordmark}>halil</span>
      </Link>

      {tabs.length > 0 && !stepBadge && (
        <nav className={styles.tabs}>
          {tabs.map((tab) => {
            const isActive = tab.to === currentPath;
            return (
              <NavLink
                key={`${tab.label}:${tab.to}`}
                to={tab.to}
                className={() => [styles.tab, isActive ? styles.tabActive : ''].filter(Boolean).join(' ')}
              >
                {tab.label}
              </NavLink>
            );
          })}
        </nav>
      )}

      <div className={styles.right}>
        {stepBadge ? (
          <span className={styles.stepBadge}>{stepBadge}</span>
        ) : (
          <>
            <button
              type="button"
              className={styles.iconButton}
              aria-label="알림"
              onClick={onBellClick}
            >
              <Icon name="bell" size={20} />
              {unreadCount > 0 && <span className={styles.dot} aria-hidden="true" />}
            </button>
            <div className={styles.avatar} title={label}>
              {label ? label.slice(0, 1) : <Icon name="user" size={16} />}
            </div>
            {session && (
              <button type="button" className={styles.logoutButton} onClick={handleLogout}>
                로그아웃
              </button>
            )}
          </>
        )}
      </div>
    </header>
  );
}
