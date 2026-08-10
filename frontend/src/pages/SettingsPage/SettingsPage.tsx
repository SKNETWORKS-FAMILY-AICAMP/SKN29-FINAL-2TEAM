import { useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { AppShell } from '../../components';
import { PATHS, SETTINGS_TABS } from '../../routes';
import { loadUserRole, saveUserRole } from '../../utils/userRole';
import type { UserRole } from '../../utils/userRole';
import TeamLeaderSettingsPage from '../TeamLeaderSettingsPage/TeamLeaderSettingsPage';
import TeamMemberSettingsPage from '../TeamMemberSettingsPage/TeamMemberSettingsPage';
import { ConnectorTab } from './tabs/ConnectorTab';
import { McpTab } from './tabs/McpTab';
import { ModelTab } from './tabs/ModelTab';
import { PermissionsTab } from './tabs/PermissionsTab';
import styles from './SettingsPage.module.css';

/**
 * Settings 허브 — 팀 / Connector / MCP / Model / 권한 탭 컨테이너.
 * 8_화면개편_명세 §2에서 역할 분기 래퍼였던 이 화면을 허브로 승격시켰다.
 *
 * 「팀」 탭은 기존 팀장·팀원 설정 화면을 그대로 편입한다(embedded). 역할은
 * 아직 실권한이 없어 sessionStorage 기반 DEV 전환기를 유지한다 — 실권한
 * 연동은 Permission 설계 후.
 */
export default function SettingsPage() {
  const location = useLocation();
  const [role, setRole] = useState<UserRole>(loadUserRole);

  function handleRoleChange(next: UserRole) {
    setRole(next);
    saveUserRole(next);
  }

  function renderTab() {
    switch (location.pathname) {
      case PATHS.settingsConnectors:
        return <ConnectorTab />;
      case PATHS.settingsMcp:
        return <McpTab />;
      case PATHS.settingsModel:
        return <ModelTab />;
      case PATHS.settingsPermissions:
        return <PermissionsTab />;
      default:
        return role === 'leader' ? (
          <TeamLeaderSettingsPage embedded />
        ) : (
          <TeamMemberSettingsPage embedded />
        );
    }
  }

  const isTeamTab = location.pathname === PATHS.settingsTeam;

  return (
    <AppShell>
      <div className={styles.wrapper}>
        <header className={styles.header}>
          <h1 className={styles.title}>설정</h1>
          <p className={styles.subtitle}>팀·연결·에이전트가 쓸 도구와 모델을 한곳에서 관리합니다.</p>
        </header>

        <nav className={styles.tabBar}>
          {SETTINGS_TABS.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              end
              className={({ isActive }) => [styles.tab, isActive ? styles.tabActive : ''].filter(Boolean).join(' ')}
            >
              {tab.label}
            </NavLink>
          ))}
        </nav>

        {isTeamTab && import.meta.env.DEV && (
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

        <div className={styles.tabPanel}>{renderTab()}</div>
      </div>
    </AppShell>
  );
}
