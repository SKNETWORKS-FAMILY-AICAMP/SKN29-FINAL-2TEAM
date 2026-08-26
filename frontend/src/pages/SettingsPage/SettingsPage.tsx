import { useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { AppShell } from '../../components';
import { PATHS, SETTINGS_TABS } from '../../routes';
import { ConnectorTab } from './tabs/ConnectorTab';
import { TeamTab } from './tabs/TeamTab';
import { SkillsTab } from './tabs/SkillsTab';
import styles from './SettingsPage.module.css';

/**
 * Settings 허브 — 팀 / 커넥터 / 스킬 탭 컨테이너.
 *
 * **「내 파일」 탭은 「문서」 화면으로 옮겼다**(2026-08-25 · `PATHS.documents`).
 * 설정은 바꾸는 곳인데 파일은 쌓이는 곳이고, 같은 성격의 팀 문서(커넥터가
 * 가져오는 쪽)는 볼 자리가 아예 없어서 둘이 갈라져 있었다. 스킬은 남긴다 —
 * 그건 문서가 아니라 에이전트가 따를 절차다.
 *
 * **Model 탭은 걷었다**(2026-08-18 멘토링). 기본 채팅 모델은 운영자가 팀별로
 * 정하고(`/ops/models`), 에이전트별 모델은 빌더에 그대로 있다.
 *
 * **커스텀 도구 탭은 걷었다**(2026-08-18 PM). 팀이 붙일 수 없게 된 뒤로는
 * 「볼 수만 있는 탭」이었고, 정작 그 서버의 도구를 고르는 자리는 에이전트
 * 편집의 도구 선택이다 — 쓰는 자리에서 보이면 설정에 또 둘 이유가 없다.
 * 8_화면개편_명세 §2에서 역할 분기 래퍼였던 이 화면을 허브로 승격시켰다.
 *
 * 「팀」 탭은 팀장·팀원 설정 화면 **둘을 합친 것**이다(2026-08-26). 예전에는
 * 역할마다 화면 파일이 따로 있었는데 팀원용이 팀장용의 부분집합이라, 한쪽만
 * 고치면 다른 쪽이 조용히 뒤처졌다 — 역할 분기는 이제 `TeamTab` 안에서
 * 「팀원 관리」 구획 하나에만 걸린다.
 */
export default function SettingsPage() {
  const location = useLocation();

  function renderTab() {
    switch (location.pathname) {
      case PATHS.settingsConnectors:
        return <ConnectorTab />;
      case PATHS.settingsSkills:
        return <SkillsTab />;
      default:
        return <TeamTab />;
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
