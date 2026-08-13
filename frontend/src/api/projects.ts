import { API_BASE_URL, ApiError, apiRequest, parseErrorBody } from './client';

/** `proj_source.source_type`. */

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
  /**
   * 무엇을 하는 프로젝트인가. 기준 문서 후보를 찾는 질의가 이름과 이 문장으로
   * 만들어진다. 컬럼이 생기기 전(2026-08-11)에 만들어진 프로젝트는 null이다.
   */
  description: string | null;
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

/** 내가 소유한 프로젝트. */
export function listMyProjects(token: string) {
  return apiRequest<Project[]>('/projects/', { token });
}

/** Jira 이슈 한 건. 상세 화면의 업무 목록 한 줄이다. */
export interface ExistTask {
  exist_task_id: string;
  jira_issue_id: string;
  /** summary 컬럼이 생기기 전에 적재된 행은 null. 화면이 이슈 키로 대신한다. */
  summary: string | null;
  assignee_person_id: string | null;
  /** HR 매핑이 안 되면 null. 그래도 목록에서 빼지 않는다. */
  assignee_name: string | null;
  /** Jira가 보여주는 말. 프로젝트마다 다르므로 분기에 쓰지 말 것. */
  status: string | null;
  status_category: 'TO_DO' | 'IN_PROGRESS' | 'DONE' | null;
  due_at: string | null;
  estimate: number | null;
  remaining: number | null;
}

/**
 * 기준 문서에서 뽑아 **우리 플랫폼에 등록한** 업무 한 건(`task`).
 *
 * Jira 이슈(`ExistTask`)와 다르다 — 담당자가 없고, 아직 아무도 합의하지 않은
 * `PROPOSED` 다. 그래서 진행률에도 담당자별 배분에도 들어가지 않는다.
 */
export interface ExtractedTask {
  task_id: string;
  title: string;
  required_role: string | null;
  effort_hours: number | null;
  due_at: string | null;
  priority: string | null;
  status: string;
  model_ver: string | null;
  generated_at: string | null;
}

export interface ProjectDetail extends Project {
  tasks: ExistTask[];
  extracted_tasks: ExtractedTask[];
}

export function getProject(token: string, projId: string) {
  return apiRequest<ProjectDetail>(`/projects/${projId}/`, { token });
}

/**
 * 프로젝트 상태를 바꾼다. 지금은 「완료 처리」와 그 되돌리기뿐이다.
 *
 * 진행률 100%를 완료로 자동 판정하지 않는다 — 우리가 아는 것은 Jira에 등록된
 * 업무가 다 끝났다는 사실뿐이고, 프로젝트가 끝났는지는 사람이 정한다.
 */
export function setProjectStatus(token: string, projId: string, status: 'ACTIVE' | 'ARCHIVED') {
  return apiRequest<Project>(`/projects/${projId}/`, { method: 'PATCH', token, body: { status } });
}

/** 프로젝트를 직접 만든다. 온보딩은 이 경로를 쓰지 않는다 — Jira 등록이 만든다. */
export function createProject(token: string, name: string, description?: string) {
  return apiRequest<Project>('/projects/', {
    method: 'POST',
    token,
    body: { name, description: description ?? null, status: 'DRAFT' },
  });
}

/**
 * 기준 문서 후보 한 건.
 *
 * 근거가 둘로 나뉜다. 요약 임베딩은 **파일명을 보지 않으므로**, 이름이 맞아
 * 올라온 것과 내용이 비슷해 올라온 것을 하나의 숫자로 뭉치면 사람이 그 수를
 * 읽을 방법이 없다.
 */
export interface PrimaryCandidate {
  doc_id: string;
  file_name: string;
  summary: string | null;
  doc_type: string | null;
  /** 요약 내용이 얼마나 비슷한가 (0~1). */
  summary_score: number;
  /** 프로젝트 이름 낱말이 파일명에 얼마나 들어 있는가 (0~1). */
  name_score: number;
  /** 본문이 색인됐는가. false면 기준으로 골라도 업무 추출이 거절한다. */
  search_ready: boolean;
}

export interface PrimaryCandidateResult {
  query: string;
  candidates: PrimaryCandidate[];
  /** 검색 자체가 실패한 경우. 「후보가 없다」와 구분해야 한다. */
  error?: string;
}

/**
 * 프로젝트 이름·설명으로 팀 문서 풀에서 기준 문서 후보를 찾는다.
 *
 * **프로젝트를 만들기 전에도 부를 수 있다.** 만들고 나서 "아무것도 없습니다"라고
 * 말하는 것보다, 만들기 전에 무엇이 나오는지 보여 주는 편이 낫다.
 */
export function suggestPrimaryCandidates(token: string, name: string, description: string) {
  return apiRequest<PrimaryCandidateResult>('/projects/primary-candidates/', {
    method: 'POST',
    token,
    body: { name, description },
  });
}

export interface ProjectDeleteResult {
  /** 함께 지운 Jira 업무 수. */
  tasks: number;
  /** 끊은 Jira 프로젝트 연결 수. */
  sources: number;
  /** 팀 문서 풀로 돌려보낸 문서 수. 지우지 않는다. */
  documents_released: number;
}

/**
 * 프로젝트를 지운다. **되돌릴 수 없다.**
 *
 * 문서는 지우지 않고 팀 문서 풀로 돌려보낸다 — 기준 문서는 잠깐 묶여 있었을 뿐이다.
 * Jira 업무는 이 프로젝트 소스의 사본이라 함께 지운다.
 */
export function deleteProject(token: string, projId: string) {
  return apiRequest<ProjectDeleteResult>(`/projects/${projId}/`, { method: 'DELETE', token });
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
  /**
   * 이 문서가 `proj_id` 프로젝트에서 맡는 역할(2026-08-04 의미 변경).
   * null(팀 문서 풀) · PRIMARY(기준 문서) · SUB(근거 문서).
   *
   * 예전에는 문서의 **종류**였다. 폴더에 준 역할을 안의 파일이 물려받아서
   * 「01_기획」에 든 것은 무엇이든 기획서가 됐고, 정작 그 값으로 분기하는 코드는
   * 한 줄도 없었다. 어느 문서가 근거인지는 기준 문서 선택 화면에서 사람이 고른다.
   */
  doc_role: 'PRIMARY' | 'SUB' | null;
  src_modified_at: string | null;
  /** 원문을 문서 저장소에 받아 뒀는가. 등록 직후에는 false다. */
  downloaded: boolean;
}

export function listTeamDocuments(token: string) {
  return apiRequest<TeamDocument[]>('/team/documents/', { token });
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
}

/** Drive 스캔에 더 이상 안 잡히는 등록 문서. */
export interface MissingDocument {
  doc_id: string;
  file_name: string | null;
  mime_type: string | null;
  /** 프로젝트에 묶여 있으면 그 프로젝트. 사라지면 추출 근거가 없어진다. */
  proj_id: string | null;
  project_name: string | null;
  doc_role: 'PRIMARY' | 'SUB' | null;
}

export interface DocumentScanResult {
  candidates: NewDocumentCandidate[];
  missing: MissingDocument[];
}

/**
 * 폴더를 훑어 신규 파일과 사라진 문서를 함께 돌려준다.
 *
 * **조회만 한다.** Drive 휴지통·완전삭제·폴더 밖 이동이 전부 똑같이 「안 잡힘」으로
 * 보여서, 자동으로 내리면 잠깐 옮겨 둔 문서가 조용히 사라진다. 내리는 것은
 * `removeDocuments()`가 한다.
 *
 * 다만 내려 뒀다가 Drive 에 다시 나타난 문서는 서버가 알아서 되살린다 — 있는
 * 것을 있다고 표시하는 복원이라 잃는 것이 없다.
 */
export function listNewDocuments(token: string) {
  return apiRequest<DocumentScanResult>('/team/documents/new/', { token });
}

export interface DocumentRemoveResult {
  removed: number;
  blocks: number;
  chunks: number;
  vectors: number;
}

/**
 * 고른 문서를 정리한다.
 *
 * `doc` 행은 남고 `deleted`만 켜지지만 **파싱 산출물은 지워진다** — 청크에 원문이
 * 통째로 들어 있어서, Drive 에서 지운 문서의 본문을 계속 들고 있을 수 없다.
 * 되돌리면 문서는 살아나지만 「처리 필요」 상태라 다시 파싱해야 한다.
 */
export function removeDocuments(token: string, docIds: string[]) {
  return apiRequest<DocumentRemoveResult>('/team/documents/remove/', {
    method: 'POST',
    token,
    body: { doc_ids: docIds },
  });
}

export interface DocumentRegisterResult {
  registered: TeamDocument[];
  skipped: { file_id: string; reason: 'NOT_FOUND' | 'UNSUPPORTED' }[];
}

/**
 * 고른 파일만 `doc`에 더한다. 기존 문서는 건드리지 않는다.
 *
 * 파일 이름·형식은 보내지 않는다. 서버가 Drive에서 다시 읽는다.
 */
export function registerDocuments(token: string, files: { file_id: string }[]) {
  return apiRequest<DocumentRegisterResult>('/team/documents/register/', {
    method: 'POST',
    token,
    body: { files },
  });
}

export interface DocumentHistoryEntry {
  audit_id: string;
  action: 'DOCUMENT_REGISTER' | 'DOCUMENT_DOWNLOAD' | 'DOCUMENT_REMOVE';
  occurred_at: string | null;
  actor_display_name: string | null;
  /** 실제로 실패한 건이 있을 때만 PARTIAL. 미지원이라 걸러진 것은 실패가 아니다. */
  status: 'OK' | 'PARTIAL';
  payload: Record<string, unknown>;
}

export interface DocumentHistoryPage {
  entries: DocumentHistoryEntry[];
  /** 더 읽을 것이 남았는가. 남은 개수는 화면이 쓰지 않아 주지 않는다. */
  has_more: boolean;
}

/** 이력 한 페이지(20건). `offset`으로 「더 보기」를 이어 받는다. */
export function listDocumentHistory(token: string, offset = 0) {
  const suffix = offset > 0 ? `?offset=${offset}` : '';
  return apiRequest<DocumentHistoryPage>(`/team/documents/history/${suffix}`, { token });
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

/** 한 주의 필요 공수와 그 주의 용량. */
export interface WeekLoad {
  week_start: string;
  hours: number;
  /** 근무조건을 모르면 null. */
  capacity: number | null;
}

/** 마감을 이른 순으로 쌓았을 때 가장 빠듯해지는 시점. */
export interface TightestDeadline {
  due_at: string;
  required_hours: number;
  available_hours: number;
  /** 음수면 그 날짜까지 그만큼 모자란다. */
  slack_hours: number;
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
  /** 주차별 필요 공수. 부하율 하나로는 어느 주에 몰렸는지가 안 보인다. */
  by_week: WeekLoad[];
  /** 조회 기간 뒤에 마감이 있는 몫. */
  later_hours: number;
  /** 남은 일 ÷ 하루 용량. 창과 무관한 절대량이다. */
  runway_days: number | null;
  /** 마감을 이른 순으로 쌓았을 때 가장 모자라는 시점. 근무조건을 모르면 null. */
  tightest: TightestDeadline | null;
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
  /** 이 비율을 넘으면 과부하. 팀 설정이 없으면 100. */
  overload_pct: number;
  /** 조회 기간(주). 팀 설정이 없으면 4. */
  workload_weeks: number;
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

/** 마감이 걸린 업무 한 건. */
export interface DeadlineTask {
  exist_task_id: string;
  jira_issue_id: string;
  summary: string | null;
  assignee_name: string | null;
  due_at: string;
  /** 오늘로부터 며칠. 음수가 지연이다. 시간대 때문에 화면에서 계산하지 않는다. */
  days: number;
  proj_id: string;
  project_name: string;
}

export interface DeadlineResult {
  as_of: string;
  /** 「곧」의 길이(일). */
  soon_days: number;
  overdue: DeadlineTask[];
  soon: DeadlineTask[];
}

/**
 * 지연된 업무와 곧 마감인 업무.
 *
 * 부하와 따로 부른다. 부하는 사람이 단위지만 이쪽은 업무가 단위이고, 보고 할
 * 행동도 다르다 — 부하는 배정을 옮기는 판단, 지연은 그 이슈를 지금 찌르는 판단이다.
 */
export function listTeamDeadlines(token: string) {
  return apiRequest<DeadlineResult>('/team/deadlines/', { token });
}

/* ── 문서 파싱·임베딩 파이프라인 ──────────────────────────────────── */

export interface PipelineDocument {
  doc_id: string;
  file_name: string | null;
  mime_type: string | null;
  /** 어느 프로젝트에 묶여 있는가. null이면 아직 팀 문서 풀에만 있다. */
  proj_id: string | null;
  /** null(팀 문서 풀) · PRIMARY(기준 문서) · SUB(근거 문서) */
  doc_role: 'PRIMARY' | 'SUB' | null;
  /** 원문을 로컬 저장소에 받아 뒀는가. */
  downloaded: boolean;
  /** 파싱·청킹·임베딩까지 끝나 검색할 수 있는가. */
  search_ready: boolean;
  src_modified_at: string | null;
}

export interface DocumentProcessingRun {
  job_id: string;
  status:
    | 'IN_QUEUE'
    | 'IN_PROGRESS'
    | 'RUNNING'
    | 'COMPLETED'
    | 'FAILED'
    | 'CANCELLED'
    | 'TIMED_OUT';
  ingested?: { blocks: number; chunks: number; vectors: number };
  error?: string;
}

/** 종료 상태. 여기 닿으면 polling 을 멈춰야 한다. */
export const TERMINAL_PROCESSING_STATUS = ['COMPLETED', 'FAILED', 'CANCELLED', 'TIMED_OUT'];

export interface DocumentDownloadResult {
  downloaded: { file_name: string; bytes: number }[];
  /** 이미 받아 둔 문서. */
  skipped: string[];
  failed: { file_name: string; detail: string }[];
}

/**
 * Drive 원문을 문서 저장소로 가져온다. 파싱은 Drive 가 아니라 이 저장소를 읽는다.
 *
 * `docIds` 를 주면 그것만 받는다. 등록 직후 문서를 한 건씩 처리하며 진행을
 * 보여주기 위해 하나씩 지정해 부른다.
 */
export function downloadDocuments(token: string, docIds?: string[]) {
  return apiRequest<DocumentDownloadResult>('/team/documents/download/', {
    method: 'POST',
    token,
    body: docIds ? { doc_ids: docIds } : {},
  });
}

/** 기준 문서로 고를 수 있는 후보 — 팀 문서 전부. */
export function listPipelineDocuments(token: string) {
  return apiRequest<PipelineDocument[]>('/team/pipeline-documents/', { token });
}

/**
 * 문서 하나를 RunPod 에 보내 파싱·청킹·임베딩한다.
 *
 * 팀 문서 단위다 — 프로젝트에 묶이는 것은 기준 문서로 선택될 때이고, 그 선택은
 * 이미 처리된 문서 중에서 한다.
 */
export function startDocumentProcessing(token: string, docId: string) {
  return apiRequest<DocumentProcessingRun>(`/team/documents/${docId}/processing-runs/`, {
    method: 'POST',
    token,
  });
}

/** 진행 상태. `COMPLETED`를 처음 본 요청이 결과를 DB에 적재한다. */
export function fetchDocumentProcessing(token: string, docId: string, jobId: string) {
  return apiRequest<DocumentProcessingRun>(
    `/team/documents/${docId}/processing-runs/${jobId}/`,
    { token },
  );
}

/** 이 프로젝트에 묶인 문서(메인+서브). */
export function listProjectSourceDocuments(token: string, projectId: string) {
  return apiRequest<PipelineDocument[]>(`/projects/${projectId}/source-documents/`, { token });
}

/**
 * 기준 문서를 정한다. **이 호출이 프로젝트에 문서를 묶는 행위다.**
 *
 * 묶이는 것은 이 한 건뿐이다. 근거 문서는 에이전트가 팀 문서에서 검색으로 찾으며
 * 프로젝트에 묶이지 않는다 — 같은 회의록이 여러 프로젝트의 근거일 수 있다.
 */
/** `primaryDocumentId` 가 null 이면 기준 문서를 **해제**한다. */
export function saveProjectPrimaryDocument(
  token: string,
  projectId: string,
  primaryDocumentId: string | null,
) {
  return apiRequest<PipelineDocument[]>(`/projects/${projectId}/source-documents/`, {
    method: 'PUT',
    token,
    body: { primary_document_id: primaryDocumentId },
  });
}

export interface ExtractedTask {
  title: string;
  description: string | null;
  required_role: string | null;
  required_skills: string[];
  /** 서버 모델(`ExtractedTask`)의 이름을 그대로 쓴다. 여기서 갈리면 값이 조용히
      비어 보인다 — 실제로 공수·일정이 늘 빈 칸이었다(2026-08-05). */
  effort_hours: number | null;
  start_date: string | null;
  due_date: string | null;
  priority: string | null;
  dependencies: string[];
  constraints: string[];
  risks: string[];
  acceptance_criteria: string[];
  deliverables: string[];
  /** 근거가 없어 비워 둔 항목. 지어내지 않았다는 표시다. */
  missing_fields: string[];
  evidence_chunk_ids: string[];
}

export interface TaskExtractionResult {
  tasks: ExtractedTask[];
  warnings: string[];
  evidence: {
    chunk_id: string;
    doc_id: string;
    text: string;
    retrieval_score: number;
    intent: string;
    query: string;
  }[];
  /**
   * 단계별 검색 결과. `"TASK_DISCOVERY:12"` 처럼 `의도:건수` 한 줄이다.
   *
   * 어떤 질의로 찾았는지는 여기가 아니라 `evidence[].query` 에 있다 — 근거마다
   * 무엇으로 찾혔는지가 붙어 있어야 그 문장을 믿을지 판단할 수 있다.
   */
  trace: string[];
  model: string;
  reasoning_effort: string;
}

/** 추출 진행. 서버가 단계마다 한 줄씩 보낸다(NDJSON). */
export type ExtractionEvent =
  | { type: 'stage'; step: number; total: number; intent: string; label: string }
  | { type: 'queries'; step: number; queries: string[] }
  | { type: 'stage_done'; step: number; found: number; evidence: number }
  | { type: 'result'; result: TaskExtractionResult }
  | { type: 'error'; detail: string };

/**
 * 기준 문서에서 업무를 뽑는다. 몇 분이 걸리므로 진행을 받아 가며 기다린다.
 *
 * `apiRequest` 를 못 쓴다 — 그쪽은 응답을 통째로 받아 JSON 으로 바꾸는데, 여기서는
 * 서버가 보내는 대로 읽어야 진행이 보인다. 응답이 시작된 뒤의 실패는 상태 코드가
 * 아니라 마지막 줄의 `error` 로 온다.
 */
export async function streamTaskExtraction(
  token: string,
  projectId: string,
  primaryDocumentId: string,
  onEvent: (event: ExtractionEvent) => void,
): Promise<TaskExtractionResult> {
  const response = await fetch(
    `${API_BASE_URL}/projects/${projectId}/task-extraction-runs/`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ primary_document_id: primaryDocumentId }),
    },
  );

  if (!response.ok || !response.body) {
    const body = await response.json().catch(() => null);
    throw parseErrorBody(body, response.status);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let result: TaskExtractionResult | null = null;

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // 마지막 조각은 줄이 안 끝났을 수 있어 버퍼에 남긴다.
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      if (!line.trim()) continue;
      const event = JSON.parse(line) as ExtractionEvent;
      if (event.type === 'error') throw new ApiError(event.detail, 500);
      if (event.type === 'result') result = event.result;
      onEvent(event);
    }
  }

  if (result === null) throw new ApiError('업무 추출이 결과 없이 끝났습니다.', 500);
  return result;
}
