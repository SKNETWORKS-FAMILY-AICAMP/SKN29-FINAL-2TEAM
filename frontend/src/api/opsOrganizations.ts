import { opsRequest } from './opsClient';

export interface OpsOrganization {
  org_id: string;
  up_org_id: string | null;
  mgr_id: string | null;
  name: string;
  org_type: string;
  status: string;
  member_count: number;
  total_member_count: number;
  mapped_count: number;
  issue_count: number;
}

export function fetchOrganizations(token: string) {
  return opsRequest<OpsOrganization[]>('/ops/organizations/', { token });
}
