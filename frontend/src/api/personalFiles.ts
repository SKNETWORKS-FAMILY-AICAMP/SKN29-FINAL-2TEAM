import { apiRequest, apiUpload, ApiError } from './client';

/**
 * 「내 파일」 — 내가 올린 개인 소유 문서(M④ · 2026-08-18).
 *
 * 커넥터 문서와 갈리는 것은 **「누구 것이냐」**다. 팀 문서는 폴더를 정하면
 * 시스템이 알아서 받아들이고, 여기 올린 파일은 내 것이라 **내가 켜고 끈다.**
 */
export interface PersonalFile {
  doc_id: string;
  file_name: string;
  mime_type: string;
  /** 내 검색 범위에 넣을 것인가. **색인 여부와 다르다**(아래 참조). */
  search_enabled: boolean;
  /** 본문까지 색인됐는가. 이건 상태이지 의도가 아니다 — 끈 파일도 색인은 남는다. */
  search_ready: boolean;
  summary: string | null;
  doc_type: string | null;
  keywords: string[];
  /** null(아직 읽는 중) / OK / FAILED / UNSUPPORTED. 넷은 할 행동이 다르다. */
  extract_status: string | null;
  uploaded_at: string | null;
}

export function listPersonalFiles(token: string) {
  return apiRequest<PersonalFile[]>('/me/files/', { token });
}

/** 올린다. multipart 처리는 `apiUpload` 가 한다(401 이면 세션도 정리한다). */
export function uploadPersonalFile(token: string, file: File) {
  return apiUpload<{ doc_id: string; file_name: string; processing: boolean }>(
    '/me/files/',
    file,
    { method: 'POST', token },
  );
}

/** 검색 범위에 넣고 뺀다. **색인은 안 건드린다** — 다시 켤 때 또 파싱하지 않는다. */
export function setPersonalFileSearch(token: string, docId: string, enabled: boolean) {
  return apiRequest<{ doc_id: string; search_enabled: boolean }>(`/me/files/${docId}/`, {
    method: 'PATCH',
    body: { search_enabled: enabled },
    token,
  });
}

/** **되살릴 수 없다.** 원본이 우리뿐이라 행·색인·원문을 함께 지운다. */
export function deletePersonalFile(token: string, docId: string) {
  return apiRequest<void>(`/me/files/${docId}/`, { method: 'DELETE', token });
}

export { ApiError };
