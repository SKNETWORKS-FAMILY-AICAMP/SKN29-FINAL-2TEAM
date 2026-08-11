import { apiRequest } from './client';

/**
 * 문서 한 건. **`state`는 서버가 정한다** — 화면이 extract_status·search_ready
 * 조합을 해석하면 같은 규칙이 두 곳에 생기고, 한쪽만 고쳐졌을 때 목록과 검색이
 * 다른 말을 한다.
 */
export type DocState = '준비됨' | '메타만' | '대기' | '실패' | '미지원 형식';

export interface TeamDocument {
  doc_id: string;
  file_name: string;
  mime_type: string | null;
  proj_id: string | null;
  doc_role: string | null;
  src_modified_at: string | null;
  summary: string | null;
  doc_type: string | null;
  keywords: string[];
  state: DocState;
  extract_status: string | null;
  search_ready: boolean;
  /** 원문이 저장소에 있는가. 없으면 메타를 만들 수 없다(「다시 처리」 비활성). */
  has_source: boolean;
}

export interface DocumentListResponse {
  documents: TeamDocument[];
  removed: { doc_id: string; file_name: string }[];
}

export interface DocumentMetaBuildResponse {
  built: { doc_id: string; extract_status: string; detail: string }[];
  failed: { doc_id: string; detail: string }[];
  status_counts: Record<string, number>;
}

export function listTeamDocuments(token: string) {
  return apiRequest<DocumentListResponse>('/team/documents/meta/', { token });
}

/**
 * 문서 메타를 만든다(CPU 추출 → 요약 → 요약 임베딩).
 *
 * `doc_ids`를 주면 그것만, 없으면 아직 메타가 없는 팀 문서 전부. 문서당 LLM
 * 1회 + 임베딩 1개라 건수가 많으면 그만큼 걸린다.
 */
export function buildDocumentMeta(token: string, docIds?: string[]) {
  return apiRequest<DocumentMetaBuildResponse>('/team/documents/meta/', {
    method: 'POST',
    body: docIds ? { doc_ids: docIds } : {},
    token,
  });
}
