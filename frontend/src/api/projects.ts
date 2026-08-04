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
  downloaded: boolean;
  search_ready: boolean;
}

export function listProjectDocuments(token: string, projId: string) {
  return apiRequest<ProjectDocument[]>(`/projects/${projId}/documents/`, { token });
}

export interface DocumentProcessingRun {
  job_id: string;
  status: 'IN_QUEUE' | 'IN_PROGRESS' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED' | 'TIMED_OUT';
  ingested?: { blocks: number; chunks: number; vectors: number };
  error?: string;
}

export function startDocumentProcessing(token: string, projId: string, docId: string) {
  return apiRequest<DocumentProcessingRun>(`/projects/${projId}/documents/${docId}/processing-runs/`, {
    method: 'POST', token,
  });
}

export function fetchDocumentProcessing(token: string, projId: string, docId: string, jobId: string) {
  return apiRequest<DocumentProcessingRun>(
    `/projects/${projId}/documents/${docId}/processing-runs/${encodeURIComponent(jobId)}/`,
    { token },
  );
}

export interface TaskExtractionResult {
  tasks: Array<Record<string, unknown>>;
  warnings: string[];
  evidence: Array<Record<string, unknown>>;
  trace: string[];
  model: string;
  reasoning_effort: string;
}

export function startTaskExtraction(token: string, projId: string, primaryDocumentId: string) {
  return apiRequest<TaskExtractionResult>(`/projects/${projId}/task-extraction-runs/`, {
    method: 'POST', token, body: { primary_document_id: primaryDocumentId },
  });
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
