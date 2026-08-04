import { apiRequest } from './client';

/** `proj_source.source_type`. */
export type ProjectSourceType = 'DRIVE_FOLDER' | 'JIRA_PROJECT';

/** 공수 기준 진행률. Jira를 한 번도 안 읽었으면 프로젝트에 아예 없다. */
export interface ProjectProgress {
  task_count: number;
  done_count: number;
  /** 추정치가 없어 분모에서 빠진 이슈 수. 0이 아니면 화면이 따로 알린다. */
  missing_estimate: number;
  total_hours: number;
  completed_hours: number;
  /** 0~100. `(완료 공수 + 미완료 소진 공수) ÷ 전체 공수`. */
  progress: number;
}

export interface Project {
  proj_id: string;
  name: string;
  status: 'DRAFT' | 'ACTIVE' | 'ARCHIVED';
  tz: string;
  owner_account_id: string | null;
  owner_name: string | null;
  /** 컬럼이 생기기 전에 만들어진 프로젝트는 null이다. 날짜를 지어내지 않는다. */
  created_at: string | null;
  /** 목록 조회에만 실린다. 단건 조회에서는 null. */
  progress: ProjectProgress | null;
  /** 소스가 여럿이면 가장 오래된 쪽. 아직 안 읽었으면 null. */
  last_sync_at: string | null;
  /** false면 읽을 Jira 소스가 없다는 뜻이라 갱신 버튼을 줄 이유가 없다. */
  has_jira_source: boolean;
}

export interface ProjectSource {
  proj_source_id: string;
  proj_id: string;
  conn_id: string;
  source_type: ProjectSourceType;
  /** Drive 폴더 id 또는 Jira 프로젝트 키. */
  external_source_id: string;
  /** 원본이 알려준 이름(`SKN29_Final_2Team`). 예전에 저장한 소스는 null이고 화면이 키로 대체한다. */
  display_name: string | null;
  sync_status: string;
  /** 이 소스를 마지막으로 읽어들인 시각. 한 번도 안 읽었으면 null. */
  last_sync_at: string | null;
  /** 이 폴더의 기본 문서 역할. 안의 파일이 물려받는다. Jira 소스는 null. */
  default_doc_role: string | null;
  /** 폴더 탐색 깊이. 1이면 선택한 폴더만, null이면 제한 없음. Jira 소스는 null. */
  max_depth: number | null;
}

/** 내가 소유한 프로젝트. */
export function listMyProjects(token: string) {
  return apiRequest<Project[]>('/projects/', { token });
}

/** 프로젝트를 직접 만든다. 온보딩은 이 경로를 쓰지 않는다 — Jira 등록이 만든다. */
export function createProject(token: string, name: string) {
  return apiRequest<Project>('/projects/', { method: 'POST', token, body: { name, status: 'DRAFT' } });
}

/** 이 프로젝트가 대응하는 Jira 프로젝트. 1:1이라 0개 아니면 1개다. */
export function listProjectSources(token: string, projId: string) {
  return apiRequest<ProjectSource[]>(`/projects/${projId}/sources/`, { token });
}

/** 팀이 읽어들일 Drive 폴더. **프로젝트가 아니라 팀에 매달린다.** */
export interface TeamFolder {
  team_folder_id: string;
  team_id: string;
  conn_id: string;
  /** 실제 Drive 폴더 id. */
  external_folder_id: string;
  /** 고를 때 Drive가 알려준 이름. 비면 화면이 id로 대체한다. */
  display_name: string | null;
  /** 이 폴더의 기본 문서 역할. 안의 파일이 물려받는다. */
  default_doc_role: DocRole | null;
  /** 탐색 깊이. 1이면 선택한 폴더만, null이면 제한 없음. */
  max_depth: number | null;
}

export function listTeamFolders(token: string) {
  return apiRequest<TeamFolder[]>('/team/folders/', { token });
}

/**
 * 팀이 읽을 폴더를 넘긴 목록으로 교체한다. 화면은 항상 전체 선택 상태를 보낸다.
 * `maxDepth`는 1이면 선택한 폴더만, null이면 제한 없음이다.
 *
 * `displayNames`(`{폴더 id: 이름}`)를 함께 보내면 저장된다. 나중에 화면이 id가
 * 아니라 '01_기획'을 보여줄 수 있다 — 그때 Drive에 다시 물어보면 화면이 커넥터
 * 생존에 묶인다. 안 보내면 이전에 저장한 이름을 지킨다.
 */
export function replaceTeamFolders(
  token: string,
  externalFolderIds: string[],
  maxDepth: number | null = 1,
  displayNames: Record<string, string> = {},
) {
  return apiRequest<TeamFolder[]>('/team/folders/', {
    method: 'PUT',
    token,
    body: {
      external_folder_ids: externalFolderIds,
      max_depth: maxDepth,
      display_names: displayNames,
    },
  });
}

/**
 * 고른 Jira 프로젝트를 우리 프로젝트로 등록한다. **하나가 프로젝트 하나다(1:1).**
 * 고르는 행위가 곧 등록이라, 여러 개를 고르면 프로젝트도 그만큼 생긴다.
 *
 * 선택에서 빠진 것은 Jira 연결만 끊고 프로젝트는 남긴다 — 체크 한 번 푼 것으로
 * 되돌릴 수 없는 삭제를 하지 않는다.
 */
/** 이미 등록된 Jira 프로젝트. 선택 화면이 체크 상태를 되살릴 때 쓴다. */
export interface RegisteredJiraProject {
  proj_id: string;
  project_key: string;
  name: string | null;
}

export function listRegisteredJiraProjects(token: string) {
  return apiRequest<RegisteredJiraProject[]>('/projects/jira/', { token });
}

export function registerJiraProjects(
  token: string,
  projects: { project_key: string; name?: string }[],
) {
  return apiRequest<ProjectSource[]>('/projects/jira/', {
    method: 'PUT',
    token,
    body: { projects },
  });
}

/** `doc.doc_role`. 화면의 기획서·회의록·일일보고서·기타에 대응한다. */
export type DocRole = 'PLAN' | 'MEETING_NOTE' | 'DAILY_REPORT' | 'OTHER';

export interface TeamDocument {
  doc_id: string;
  team_id: string | null;
  /** 어느 프로젝트의 문서인지. 등록 시점에는 모르므로 null이다. */
  proj_id: string | null;
  /** Drive 파일 id. */
  src_file_id: string;
  source_type: string;
  file_name: string | null;
  mime_type: string | null;
  doc_role: DocRole | null;
  src_modified_at: string | null;
}

export function listTeamDocuments(token: string) {
  return apiRequest<TeamDocument[]>('/team/documents/', { token });
}

/**
 * 역할 지정 화면의 저장. 파일 목록은 보내지 않는다 — 서버가 저장된 폴더를
 * Drive에서 다시 읽어 `doc` 행을 만든다. `fileRoles`는 폴더 역할을 덮어쓴다.
 */
export function saveDocumentRoles(
  token: string,
  folderRoles: Record<string, DocRole>,
  fileRoles: Record<string, DocRole>,
) {
  return apiRequest<TeamDocument[]>('/team/documents/', {
    method: 'PUT',
    token,
    body: { folder_roles: folderRoles, file_roles: fileRoles },
  });
}

/** 설정된 폴더에 있는데 아직 `doc`에 없는 파일. */
export interface NewDocumentCandidate {
  file_id: string;
  file_name: string;
  mime_type: string | null;
  modified_at: string | null;
  /** 파싱할 수 있는 형식인가. 아니면 등록에서 제외된다. */
  supported: boolean;
  /** 하위 폴더에서 왔으면 그 경로, 아니면 고른 폴더 이름. */
  folder_name: string;
  folder_id: string;
  /** 폴더에 지정된 역할. 화면에서 행마다 바꿀 수 있다. */
  suggested_role: DocRole | null;
}

export function listNewDocuments(token: string) {
  return apiRequest<NewDocumentCandidate[]>('/team/documents/new/', { token });
}

export interface DocumentRegisterResult {
  registered: TeamDocument[];
  skipped: { file_id: string; reason: 'NOT_FOUND' | 'UNSUPPORTED' | 'NO_ROLE' }[];
}

/**
 * 고른 파일만 `doc`에 더한다. 기존 문서는 건드리지 않는다 — 폴더 전체를 동기화하는
 * `saveDocumentRoles`와 다른 경로인 이유가 그것이다.
 *
 * 파일 이름·형식은 보내지 않는다. 서버가 Drive에서 다시 읽는다.
 */
export function registerDocuments(
  token: string,
  files: { file_id: string; doc_role?: DocRole }[],
) {
  return apiRequest<DocumentRegisterResult>('/team/documents/register/', {
    method: 'POST',
    token,
    body: { files },
  });
}

export interface DocumentHistoryEntry {
  audit_id: string;
  action: 'DOCUMENT_REGISTER' | 'DOCUMENT_DOWNLOAD';
  occurred_at: string | null;
  actor_display_name: string | null;
  /** 실제로 실패한 건이 있을 때만 PARTIAL. 미지원이라 걸러진 것은 실패가 아니다. */
  status: 'OK' | 'PARTIAL';
  payload: Record<string, unknown>;
}

export function listDocumentHistory(token: string) {
  return apiRequest<DocumentHistoryEntry[]>('/team/documents/history/', { token });
}

export interface TaskSyncResult {
  sources: { proj_source_id: string; project_key: string; fetched: number }[];
  failed: { project_key: string; detail: string }[];
  unmapped_assignees: number;
  missing_estimate: number;
  synced_at: string;
}

/** 이 프로젝트의 Jira 이슈를 다시 읽어 `exist_task`를 교체한다. */
export function syncProjectTasks(token: string, projId: string) {
  return apiRequest<TaskSyncResult>(`/projects/${projId}/tasks/sync/`, { method: 'POST', token });
}

/** 팀의 모든 프로젝트를 한 번에 다시 읽는다. 목록 화면의 「갱신」이 쓴다. */
export function syncTeamTasks(token: string) {
  return apiRequest<TaskSyncResult>('/team/tasks/sync/', { method: 'POST', token });
}

/** 어느 Jira 프로젝트에서 온 부하인지. "KAN만 90%" 분해가 이 값으로 나온다. */
export interface WorkloadByProject {
  project_key: string;
  /** 저장된 표시 이름. 없으면 서버가 키를 그대로 채워 준다. */
  project_name: string;
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

/**
 * 기간별 사람 부하. `from`·`to`를 안 주면 오늘부터 4주다.
 *
 * **팀 전체가 범위다.** 사람의 부하는 그가 맡은 모든 프로젝트의 합이라, 프로젝트
 * 하나만 보면 "SKN29만 90%"가 나오지만 실제로는 122.5%다. 어느 프로젝트에서 온
 * 부하인지는 `by_project`가 분해해 준다.
 */
export function getTeamWorkload(token: string, from?: string, to?: string) {
  const query = new URLSearchParams();
  if (from) query.set('from', from);
  if (to) query.set('to', to);
  const suffix = query.toString() ? `?${query}` : '';
  return apiRequest<WorkloadResult>(`/team/workload/${suffix}`, { token });
}
