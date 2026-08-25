import { apiRequest } from './client';

/**
 * 「문서」 화면이 쓰는 것 — 팀 문서가 **어느 폴더에서 왔고 검색에 쓰일 수 있는가.**
 *
 * `api/projects.ts` 의 `TeamDocument` 와 나눠 둔다. 저쪽은 문서의 신원(어느
 * 파일인지)이고 여기는 **처리 상태**다 — 한 타입으로 합치면 상태가 필요 없는
 * 자리까지 색인 칸을 들고 다니게 된다.
 */

/** 트리의 뿌리 하나 — 사람이 커넥터에서 고른 폴더. */
export interface LibraryFolder {
  team_folder_id: string;
  /** 어느 저장소 연결에서 오는가. 화면은 이것으로 먼저 묶는다. */
  conn_id: string;
  /** 연결이 강제 해제되면 빈다. 그때도 폴더는 보여준다. */
  connector_type: 'GOOGLE_DRIVE' | 'JIRA' | 'PEOPLE_DB' | null;
  auth_status: 'CONNECTED' | 'EXPIRED' | 'ERROR' | 'REVOKED' | null;
  /** 고를 때 저장해 둔 이름. 없으면 화면이 id로 대체한다. */
  display_name: string | null;
  external_folder_id: string;
  /** 1이면 고른 폴더만, null이면 제한 없음. */
  max_depth: number | null;
}

export interface LibraryDocument {
  doc_id: string;
  file_name: string | null;
  mime_type: string | null;
  /** 어느 프로젝트의 기준 문서인지. 지우기 전에 사람이 알아야 한다. */
  proj_id: string | null;
  doc_role: 'PRIMARY' | 'SUB' | null;
  src_modified_at: string | null;
  /** 원문을 받았는가. 안 받았으면 색인이 시작조차 못 한다. */
  downloaded: boolean;
  access_revoked: boolean;
  /** RUNNING · FAILED · null. null은 「아직 안 돌렸거나 끝났거나」 둘 다다. */
  index_status: string | null;
  index_detail: string | null;
  /**
   * 청크가 있는가. **`index_status` 와 뜻이 다르다** — 이쪽은 계산값이고
   * 저쪽은 지금 돌고 있는지·실패했는지다. 둘을 뭉치면 「실패했는데 옛 청크는
   * 남아 있는」 상태를 표현할 수 없다.
   */
  search_ready: boolean;
  /** 트리에서 어디에 매달릴지. null이면 「미분류」다. */
  team_folder_id: string | null;
  /**
   * 뿌리 폴더 안에서의 상대 경로. **빈 문자열과 null이 다르다** — ''는 뿌리
   * 바로 아래이고 null은 「모른다」(이 칸이 생기기 전에 등록된 문서)다.
   */
  src_folder_path: string | null;
}

export interface DocumentLibrary {
  folders: LibraryFolder[];
  documents: LibraryDocument[];
}

/**
 * 폴더와 문서를 **한 번에** 받는다. 나눠 부르면 그 사이에 수집이 끼었을 때
 * 트리에는 있는데 문서는 없는 화면이 뜬다.
 */
export function fetchDocumentLibrary(token: string) {
  return apiRequest<DocumentLibrary>('/team/documents/library/', { token });
}

/**
 * 색인을 다시 시킨다. **끝날 때까지 기다리지 않는다** — 한 건에 100초 남짓이라
 * 서버가 뒷작업으로 던지고 `202` 를 준다. 화면은 `index_status` 를 폴링한다.
 */
export function reindexTeamDocument(token: string, docId: string) {
  return apiRequest<{ doc_id: string; started: boolean }>(
    `/team/documents/${encodeURIComponent(docId)}/reindex/`,
    { method: 'POST', token },
  );
}

/** 색인이 어디까지 왔는가 — 숫자 넷. 전역 진행 표시가 폴링한다. */
export interface IndexingProgress {
  total: number;
  ready: number;
  /** 스스로 끝나지 않는다. 남은 것에서 빼야 진행이 멈춘 것처럼 안 보인다. */
  failed: number;
  /** 지금 워커에서 도는 것. `total - ready - failed` 로 계산하면 「아직 시작 안 한 것」과 뭉친다. */
  running: number;
}

/**
 * 문서 목록을 통째로 받지 않는다. 화면 어디에 있든 도는 폴링이라, 여기서
 * 목록을 실어 보내면 팀 문서 전부가 주기적으로 오간다.
 */
export function fetchIndexingProgress(token: string) {
  return apiRequest<IndexingProgress>('/team/documents/indexing/', { token });
}
