import { Link, NavLink, useLocation } from 'react-router-dom';
import { Icon } from '../Icon/Icon';
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
  const currentPath = activeTo ?? location.pathname;

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
                key={tab.to}
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
            <div className={styles.avatar}>
              {userLabel ? userLabel : <Icon name="user" size={16} />}
            </div>
          </>
        )}
      </div>
    </header>
  );
}
