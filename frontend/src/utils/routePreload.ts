import { PATHS } from '../routes';

function preload(load: Promise<unknown>): void {
  // hover 사전 로딩은 최적화일 뿐이다. 순간적인 네트워크·청크 오류가 나도
  // 처리되지 않은 Promise 오류를 남기지 않고, 실제 클릭 시 라우터가 다시 읽는다.
  void load.catch(() => undefined);
}

/** 메뉴를 누르기 직전 화면 청크를 받아 첫 전환의 전체 fallback을 줄인다. */
export function preloadUserRoute(path: string): void {
  if (path === PATHS.chat) preload(import('../pages/ChatPage/ChatPage'));
  else if (path === PATHS.agentVersions) preload(import('../pages/AgentVersionListPage/AgentVersionListPage'));
  else if (path === PATHS.projects) preload(import('../pages/ProjectListPage/ProjectListPage'));
  else if (path === PATHS.documents) preload(import('../pages/DocumentsPage/DocumentsPage'));
  else if (path.startsWith('/settings')) preload(import('../pages/SettingsPage/SettingsPage'));
}
