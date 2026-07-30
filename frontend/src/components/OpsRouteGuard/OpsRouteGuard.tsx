import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { loadOpsSession } from '../../utils/opsSession';

export function OpsRouteGuard() {
  const location = useLocation();

  if (!loadOpsSession()) {
    return <Navigate to="/ops/login" replace state={{ from: location.pathname }} />;
  }

  return <Outlet />;
}
