import type { ReactNode } from 'react';
import { MAIN_NAV_TABS } from '../../routes';
import { Icon } from '../Icon/Icon';
import type { IconName } from '../Icon/Icon';
import { TopNav } from '../TopNav/TopNav';
import styles from './SettingsLayout.module.css';

export interface SettingsNavItem {
  id: string;
  label: string;
  icon: IconName;
}

export interface SettingsLayoutProps {
  subtitle: string;
  navItems: SettingsNavItem[];
  footerLabel: string;
  onFooterClick?: () => void;
  children: ReactNode;
}

function scrollToSection(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/**
 * Shared shell for the settings screens (팀장 설정 / 팀원 설정): a left
 * sidebar with the halil logo, a section nav that scrolls the main content,
 * and a footer identity row, plus a scrollable main content area for the
 * page's own header + section cards.
 */
export function SettingsLayout({ subtitle, navItems, footerLabel, onFooterClick, children }: SettingsLayoutProps) {
  return (
    <div className={styles.page}>
      <TopNav tabs={MAIN_NAV_TABS} activeTo="/settings/team" />

      <div className={styles.body}>
        <aside className={styles.sidebar}>
          <div className={styles.sidebarHeader}>
            <p className={styles.sidebarSubtitle}>{subtitle}</p>
          </div>

          <nav className={styles.sidebarNav}>
            {navItems.map((item) => (
              <button
                key={item.id}
                type="button"
                className={styles.navItem}
                onClick={() => scrollToSection(item.id)}
              >
                <Icon name={item.icon} size={18} />
                <span>{item.label}</span>
              </button>
            ))}
          </nav>

          <button type="button" className={styles.sidebarFooter} onClick={onFooterClick}>
            <span className={styles.footerAvatar}>
              <Icon name="user" size={16} color="var(--color-muted)" />
            </span>
            <span className={styles.footerLabel}>{footerLabel}</span>
          </button>
        </aside>

        <main className={styles.main}>{children}</main>
      </div>
    </div>
  );
}
