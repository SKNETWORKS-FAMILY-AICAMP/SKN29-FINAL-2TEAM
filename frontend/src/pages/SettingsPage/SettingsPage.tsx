import { useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { AppShell } from '../../components';
import { PATHS, SETTINGS_TABS } from '../../routes';
import { loadUserRole } from '../../utils/userRole';
import TeamLeaderSettingsPage from '../TeamLeaderSettingsPage/TeamLeaderSettingsPage';
import TeamMemberSettingsPage from '../TeamMemberSettingsPage/TeamMemberSettingsPage';
import { ConnectorTab } from './tabs/ConnectorTab';
import { MyFilesTab } from './tabs/MyFilesTab';
import styles from './SettingsPage.module.css';

/**
 * Settings 허브 — 팀 / 커넥터 / 내 파일 탭 컨테이너.
 *
 * **Model 탭은 걷었다**(2026-08-18 멘토링). 기본 채팅 모델은 운영자가 팀별로
 * 정하고(`/ops/models`), 에이전트별 모델은 빌더에 그대로 있다.
 *
 * **커스텀 도구 탭은 걷었다**(2026-08-18 PM). 팀이 붙일 수 없게 된 뒤로는
 * 「볼 수만 있는 탭」이었고, 정작 그 서버의 도구를 고르는 자리는 에이전트
 * 편집의 도구 선택이다 — 쓰는 자리에서 보이면 설정에 또 둘 이유가 없다.
 * 8_화면개편_명세 §2에서 역할 분기 래퍼였던 이 화면을 허브로 승격시켰다.
 *
 * 「팀」 탭은 기존 팀장·팀원 설정 화면을 그대로 편입한다. 역할은
 * 로그인 계정(`account.role`)에서 온다 — Permission 설계 전까지는 그 값이 전부다.
 */
export default function SettingsPage() {
  const location = useLocation();
  // 역할은 로그인 계정에서 온다(`account.role`). DEV 전환기는 걷어냈다(`2cc45c1`) —
  // 실제 흐름으로 확인한다.
  const role = loadUserRole();

  function renderTab() {
    switch (location.pathname) {
      case PATHS.settingsConnectors:
        return <ConnectorTab />;
      case PATHS.settingsMyFiles:
        return <MyFilesTab />;
      default:
        return role === 'leader' ? (
          <TeamLeaderSettingsPage />
        ) : (
          <TeamMemberSettingsPage />
        );
    }
  }

  return (
    <AppShell>
      <div className={styles.wrapper}>
        <header className={styles.header}>
          <h1 className={styles.title}>설정</h1>
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

        <div className={styles.tabPanel}>{renderTab()}</div>
      </div>
    </AppShell>
  );
}
