import { Navigate, useLocation } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useSession } from '../../utils/session';

export interface RequireAuthProps {
  children: ReactNode;
}

/**
 * 로그인이 필요한 화면을 감싼다. 세션이 없으면 로그인으로 보내고, 원래 가려던
 * 곳을 `state.from`에 담아 로그인 후 그대로 이어가게 한다.
 *
 * 토큰이 만료돼 API가 401을 주면 `apiRequest`가 세션을 비우는데, 그 변경을
 * `useSession`이 감지하므로 열려 있던 화면도 자동으로 로그인으로 돌아간다.
 */
export function RequireAuth({ children }: RequireAuthProps) {
  const session = useSession();
  const location = useLocation();

  if (!session) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }

  return <>{children}</>;
}
