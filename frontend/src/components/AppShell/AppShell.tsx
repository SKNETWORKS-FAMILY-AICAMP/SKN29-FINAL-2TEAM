import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { listMyProjects } from '../../api/projects';
import type { Project } from '../../api/projects';
import { APP_NAV_ITEMS, PATHS } from '../../routes';
import { saveProjectContext, useProjectContext } from '../../utils/projectContext';
import { clearSession, useSession } from '../../utils/session';
import { Icon } from '../Icon/Icon';
import { Select } from '../Select/Select';
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
 * 기존 `TopNav`(상단 탭바)를 쓰는 화면은 이제 없다 — 마지막 사용처였던 옛
 * 대시보드를 4차 단계 2에서 지웠다. `SettingsLayout`의 비-embedded 분기에만
 * 코드가 남아 있는데, 그 분기로 들어오는 라우트도 없다.
 */
export function AppShell({ children, variant = 'page' }: AppShellProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const session = useSession();
  const displayName = session?.account.display_name ?? '';
  const context = useProjectContext();
  const [projects, setProjects] = useState<Project[]>([]);

  useEffect(() => {
    const token = session?.token;
    if (!token) return;
    // 목록을 못 읽어도 화면을 막지 않는다 — 프로젝트 문맥은 「전체(팀)」로
    // 남고, 그 상태가 무엇을 뜻하는지는 Chat 이 말해 준다.
    listMyProjects(token).then(setProjects).catch(() => undefined);
  }, [session?.token]);

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
            프로젝트 컨텍스트 선택기. 여기서 고른 값이 새 대화의
            `chat_session.proj_id` 가 된다 — 「전체(팀)」은 그 값이 없다는 뜻이다.
          */}
          <div className={styles.contextPicker}>
            <Icon name="folder" size={15} color="var(--color-body)" />
            <Select
              size="sm"
              className={styles.contextSelect}
              value={context?.proj_id ?? ''}
              onChange={(event) => {
                const picked = projects.find((project) => project.proj_id === event.target.value);
                saveProjectContext(picked ? { proj_id: picked.proj_id, name: picked.name } : null);
              }}
              aria-label="프로젝트 컨텍스트 선택"
              options={[
                { label: '전체(팀)', value: '' },
                ...projects.map((project) => ({ label: project.name, value: project.proj_id })),
              ]}
            />
          </div>

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
