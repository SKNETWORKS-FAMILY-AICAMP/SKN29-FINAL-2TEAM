import { useState } from 'react';
import { loadUserRole, saveUserRole } from '../../utils/userRole';
import type { UserRole } from '../../utils/userRole';
import TeamLeaderSettingsPage from '../TeamLeaderSettingsPage/TeamLeaderSettingsPage';
import TeamMemberSettingsPage from '../TeamMemberSettingsPage/TeamMemberSettingsPage';
import styles from './SettingsPage.module.css';

/**
 * Role-based entry point for the settings screens. This app has no real
 * auth/roles, so the demo role is kept in sessionStorage and can be flipped
 * with the dev-only switcher below — 팀장(leader) sees the org-wide
 * settings, 팀원(member) sees their personal settings.
 */
export default function SettingsPage() {
  const [role, setRole] = useState<UserRole>(loadUserRole);

  function handleRoleChange(next: UserRole) {
    setRole(next);
    saveUserRole(next);
  }

  return (
    <div className={styles.wrapper}>
      {import.meta.env.DEV && (
        <div className={styles.devRoleSwitch}>
          <button
            type="button"
            className={[styles.devRoleBtn, role === 'leader' ? styles.devRoleBtnActive : ''].join(' ')}
            onClick={() => handleRoleChange('leader')}
          >
            팀장 보기
          </button>
          <button
            type="button"
            className={[styles.devRoleBtn, role === 'member' ? styles.devRoleBtnActive : ''].join(' ')}
            onClick={() => handleRoleChange('member')}
          >
            팀원 보기
          </button>
        </div>
      )}

      {role === 'leader' ? <TeamLeaderSettingsPage /> : <TeamMemberSettingsPage />}
    </div>
  );
}
