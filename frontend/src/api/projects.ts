import { apiRequest } from './client';

/** `proj_source.source_type`. */
export type ProjectSourceType = 'DRIVE_FOLDER' | 'JIRA_PROJECT';

export interface Project {
  proj_id: string;
  name: string;
  status: 'DRAFT' | 'ACTIVE' | 'ARCHIVED';
  tz: string;
  owner_account_id: string | null;
  owner_name: string | null;
}

export interface ProjectSource {
  proj_source_id: string;
  proj_id: string;
  conn_id: string;
  source_type: ProjectSourceType;
  /** Drive 폴더 id 또는 Jira 프로젝트 키. */
  external_source_id: string;
  sync_status: string;
  /** 이 폴더의 기본 문서 역할. 안의 파일이 물려받는다. Jira 소스는 null. */
  default_doc_role: string | null;
  /** 폴더 탐색 깊이. 1이면 선택한 폴더만, null이면 제한 없음. Jira 소스는 null. */
  max_depth: number | null;
}

/** 내가 소유한 프로젝트. */
export function listMyProjects(token: string) {
  return apiRequest<Project[]>('/projects/', { token });
}

/** 온보딩 중인 프로젝트는 아직 내용이 없으므로 DRAFT로 만든다. */
export function createProject(token: string, name: string) {
  return apiRequest<Project>('/projects/', { method: 'POST', token, body: { name, status: 'DRAFT' } });
}

export function listProjectSources(token: string, projId: string) {
  return apiRequest<ProjectSource[]>(`/projects/${projId}/sources/`, { token });
}

/**
 * 이 종류의 소스를 넘긴 목록으로 교체한다. 화면은 항상 전체 선택 상태를 보낸다.
 * `maxDepth`는 1이면 선택한 폴더만, null이면 제한 없음이다(Drive 폴더에만 쓰인다).
 */
export function replaceProjectSources(
  token: string,
  projId: string,
  sourceType: ProjectSourceType,
  externalSourceIds: string[],
  maxDepth: number | null = 1,
) {
  return apiRequest<ProjectSource[]>(`/projects/${projId}/sources/`, {
    method: 'PUT',
    token,
    body: {
      source_type: sourceType,
      external_source_ids: externalSourceIds,
      max_depth: maxDepth,
    },
  });
}

/** `doc.doc_role`. 화면의 기획서·회의록·일일보고서·기타에 대응한다. */
export type DocRole = 'PLAN' | 'MEETING_NOTE' | 'DAILY_REPORT' | 'OTHER';

export interface ProjectDocument {
  doc_id: string;
  proj_id: string;
  /** Drive 파일 id. */
  src_file_id: string;
  source_type: string;
  file_name: string | null;
  mime_type: string | null;
  doc_role: DocRole | null;
  src_modified_at: string | null;
}

export function listProjectDocuments(token: string, projId: string) {
  return apiRequest<ProjectDocument[]>(`/projects/${projId}/documents/`, { token });
}

/**
 * 역할 지정 화면의 저장. 파일 목록은 보내지 않는다 — 서버가 저장된 폴더를
 * Drive에서 다시 읽어 `doc` 행을 만든다. `fileRoles`는 폴더 역할을 덮어쓴다.
 */
export function saveDocumentRoles(
  token: string,
  projId: string,
  folderRoles: Record<string, DocRole>,
  fileRoles: Record<string, DocRole>,
) {
  return apiRequest<ProjectDocument[]>(`/projects/${projId}/documents/`, {
    method: 'PUT',
    token,
    body: { folder_roles: folderRoles, file_roles: fileRoles },
  });
}

/**
 * 온보딩이 소스를 매달 프로젝트. Drive 폴더든 Jira 프로젝트든 어느 화면을 먼저
 * 끝내도 같은 프로젝트에 붙어야 하므로 진행 중인 DRAFT를 공유한다.
 */
export async function findOnboardingProject(token: string): Promise<Project | null> {
  const mine = await listMyProjects(token);
  return mine.find((project) => project.status === 'DRAFT') ?? mine[0] ?? null;
}

/** 저장할 것이 생긴 시점에 프로젝트를 만든다. 화면을 열기만 해서는 만들지 않는다. */
export async function ensureOnboardingProject(token: string, fallbackName: string): Promise<Project> {
  return (await findOnboardingProject(token)) ?? (await createProject(token, fallbackName));
}

export interface TaskSyncResult {
  sources: { proj_source_id: string; project_key: string; fetched: number }[];
  failed: { project_key: string; detail: string }[];
  unmapped_assignees: number;
  missing_estimate: number;
  synced_at: string;
}

/** 연결된 Jira 프로젝트의 미완료 이슈를 가져와 `exist_task`를 교체한다. */
export function syncProjectTasks(token: string, projId: string) {
  return apiRequest<TaskSyncResult>(`/projects/${projId}/tasks/sync/`, { method: 'POST', token });
}

/** 어느 Jira 프로젝트에서 온 부하인지. "KAN만 90%" 분해가 이 값으로 나온다. */
export interface WorkloadByProject {
  project_key: string;
  hours: number;
  load_rate: number | null;
}

export interface PersonWorkload {
  person_id: string;
  name: string | null;
  job_role: string | null;
  gross_capacity: number | null;
  absence_hours: number | null;
  absent_days: number;
  effective_capacity: number | null;
  current_allocation: number;
  remaining_capacity: number | null;
  /** %. 용량이 0 이하거나 근무조건이 없으면 null이고 `blocked_reason`이 채워진다. */
  load_rate: number | null;
  blocked_reason: 'NO_SCHEDULE' | 'ON_LEAVE' | 'NO_EFFECTIVE_CAPACITY' | null;
  by_project: WorkloadByProject[];
  unscheduled_backlog_hours: number;
  unscheduled_backlog_count: number;
  missing_estimate_count: number;
}

export interface WorkloadResult {
  period_start: string;
  period_end: string;
  workdays: number;
  people: PersonWorkload[];
  unmapped_assignee_count: number;
  missing_estimate_count: number;
  unscheduled_backlog_hours: number;
  limitations: string[];
  as_of: string;
}

/** 기간별 사람 부하. `from`·`to`를 안 주면 오늘부터 4주다. */
export function getProjectWorkload(token: string, projId: string, from?: string, to?: string) {
  const query = new URLSearchParams();
  if (from) query.set('from', from);
  if (to) query.set('to', to);
  const suffix = query.toString() ? `?${query}` : '';
  return apiRequest<WorkloadResult>(`/projects/${projId}/workload/${suffix}`, { token });
}
