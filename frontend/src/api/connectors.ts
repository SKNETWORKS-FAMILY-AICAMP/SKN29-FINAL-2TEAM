import { apiRequest } from './client';

/** `connector_conn.connector_type`. Google Drive는 OAuth로 실제 연결한다. */
export type ConnectorType = 'PEOPLE_DB' | 'GOOGLE_DRIVE' | 'JIRA';

/** 화면의 커넥터 카드 id ↔ 서버의 connector_type 대응. */
export const CONNECTOR_TYPE_BY_ID: Record<string, ConnectorType> = {
  'people-db': 'PEOPLE_DB',
  'google-drive': 'GOOGLE_DRIVE',
  jira: 'JIRA',
};

export interface ConnectorConnection {
  conn_id: string;
  connector_type: ConnectorType;
  granted_scopes: string[];
  auth_status: 'CONNECTED' | 'EXPIRED' | 'ERROR' | 'REVOKED';
  connected_at: string;
}

export interface HrPerson {
  person_id: string;
  name: string;
  email: string;
  org_id: string | null;
  org_name: string | null;
  job_role: string | null;
}

export interface PeopleDbSummary {
  org_count: number;
  person_count: number;
  my_org_name: string | null;
  my_org_person_count: number;
  /** 본인 조직 + 하위 조직 인원. 팀원을 초대할 수 있는 범위와 같은 기준이다. */
  scope_person_count: number;
  person: HrPerson | null;
}

export function listConnectors(token: string) {
  return apiRequest<ConnectorConnection[]>('/connectors/', { token });
}

/** HR에서 찾은 본인 후보. 확인 전이라 아직 매핑되지 않는다. 못 찾으면 404. */
export function fetchPeopleDbIdentity(token: string) {
  return apiRequest<HrPerson>('/connectors/people-db/identity/', { token });
}

/** HR 시스템 연결. 본인 PERSON을 찾지 못하면 실패한다. */
export function connectPeopleDb(token: string) {
  return apiRequest<PeopleDbSummary>('/connectors/people-db/', { method: 'POST', token });
}

/** Google OAuth 동의 화면으로 이동하기 위한 서버 생성 URL. */
export function beginGoogleDriveAuthorization(token: string) {
  return apiRequest<{ authorization_url: string }>('/connectors/google-drive/authorize/', { token });
}

/** Atlassian OAuth 동의 화면으로 이동하기 위한 서버 생성 URL. */
export function beginJiraAuthorization(token: string) {
  return apiRequest<{ authorization_url: string }>('/connectors/jira/authorize/', { token });
}

/** 내 드라이브 최상단을 가리키는 Drive의 별칭. */
export const DRIVE_ROOT_ID = 'root';

export interface DriveFolder {
  folder_id: string;
  name: string;
  modified_at: string | null;
}

/**
 * `parentId` 바로 아래의 폴더. 한 단계씩 내려가며 탐색한다. Drive 전체를 한 번에
 * 받으면 무관한 폴더에 묻히기 때문이다. 미연결이면 404, 재연결이 필요하면 502.
 */
export function listDriveFolders(token: string, parentId: string = DRIVE_ROOT_ID) {
  return apiRequest<DriveFolder[]>(
    `/connectors/google-drive/folders/?parent=${encodeURIComponent(parentId)}`,
    { token },
  );
}

export interface DriveFile {
  file_id: string;
  name: string;
  mime_type: string | null;
  modified_at: string | null;
  /** 본문에서 업무를 뽑아낼 수 있는 형식인지. 미지원 파일은 등록되지 않는다. */
  supported: boolean;
  /** 선택한 폴더 기준 상대 경로. 직속 파일은 빈 문자열이다. */
  folder_path: string;
}

/**
 * `parentId` 폴더 아래의 파일. `maxDepth`는 선택한 폴더를 1단계로 세고,
 * null이면 제한 없이 하위 폴더를 따라 내려간다.
 */
export function listDriveFiles(token: string, parentId: string, maxDepth: number | null = 1) {
  const depth = maxDepth === null ? 'unlimited' : String(maxDepth);
  return apiRequest<DriveFile[]>(
    `/connectors/google-drive/files/?parent=${encodeURIComponent(parentId)}&depth=${depth}`,
    { token },
  );
}

/**
 * 저장된 폴더 id로 이름을 되짚는다. `proj_source`에는 id만 남기 때문에
 * 저장된 선택을 다시 보여주려면 Drive에 물어봐야 한다.
 */
export function getDriveFolders(token: string, folderIds: string[]) {
  if (folderIds.length === 0) return Promise.resolve<DriveFolder[]>([]);
  return apiRequest<DriveFolder[]>(
    `/connectors/google-drive/folders/?ids=${encodeURIComponent(folderIds.join(','))}`,
    { token },
  );
}

