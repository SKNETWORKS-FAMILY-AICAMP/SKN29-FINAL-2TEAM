import type { ReactNode } from 'react';
import { Icon } from '../components';
import type { ConnectorStatus } from '../utils/connectorStatus';

export interface ConnectorDef {
  id: string;
  name: string;
  desc: string;
  iconBg: string;
  icon: ReactNode;
  initialStatus: ConnectorStatus;
}

function JiraIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="#0052cc" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M11.53 2.5a.75.75 0 0 1 .94 0l8 6.5A.75.75 0 0 1 20 10.4V21a1 1 0 0 1-1 1h-4a1 1 0 0 1-1-1v-6H10v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V10.4a.75.75 0 0 1 .47-.7l8-6.5" />
    </svg>
  );
}

function DriveIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="#ea4335" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 5.5C4 4.67 4.67 4 5.5 4h13c.83 0 1.5.67 1.5 1.5V7H4V5.5Z" />
      <rect x="4" y="7" width="16" height="12.5" rx="1" />
      <line x1="4" y1="10.5" x2="20" y2="10.5" />
    </svg>
  );
}

/**
 * Shared connector catalog used by both the connector onboarding flow and
 * the team leader settings page, so the two stay in sync (same ids, names,
 * icons). 실제 OAuth 연결 상태는 서버의 `connector_conn`이 원본이다.
 */
export const CONNECTOR_DEFS: ConnectorDef[] = [
  {
    id: 'people-db',
    name: 'People DB',
    desc: '인력 정보 데이터베이스. 팀원별 스킬, 가용성, 역할 정보를 연동합니다.',
    iconBg: 'rgba(16,185,129,0.07)',
    icon: <Icon name="database" size={24} color="#10b981" />,
    initialStatus: 'disconnected',
  },
  {
    id: 'jira',
    name: 'Jira',
    desc: '프로젝트 보드, 이슈 진행 상황, 그리고 개발 태스크 백로그를 할릴 AI가 직접 읽고 동기화합니다.',
    iconBg: 'rgba(0,82,204,0.07)',
    icon: <JiraIcon />,
    initialStatus: 'disconnected',
  },
  {
    id: 'google-drive',
    name: 'Google Drive',
    desc: '문서 관리 및 공유, 협업 문서를 안전하게 연결해 업무 배정에 활용합니다.',
    iconBg: 'rgba(234,67,53,0.07)',
    icon: <DriveIcon />,
    initialStatus: 'disconnected',
  },
];
