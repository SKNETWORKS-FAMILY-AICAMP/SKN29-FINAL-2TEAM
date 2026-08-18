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
  /** 팀에 공유했는가. **소유는 안 옮긴다** — 보여 주는 것이지 넘기는 것이 아니다. */
  shared: boolean;
  /** 공유 받은 목록에만 있다. 누가 올렸는지 모르면 내용을 믿을 근거가 없다. */
  owner_name: string | null;
}

export function listPersonalFiles(token: string) {
  return apiRequest<PersonalFile[]>('/me/files/', { token });
}

/** 팀원이 공유한 파일. **내가 올린 것은 안 나온다** — 「내 파일」에 이미 있다. */
export function listSharedFiles(token: string) {
  return apiRequest<PersonalFile[]>('/me/files/shared/', { token });
}

/** 올린다. multipart 처리는 `apiUpload` 가 한다(401 이면 세션도 정리한다). */
export function uploadPersonalFile(token: string, file: File) {
  return apiUpload<{ doc_id: string; file_name: string; processing: boolean }>(
    '/me/files/',
    file,
    { method: 'POST', token },
  );
}

/**
 * 켜고 끈다. 두 값은 **다른 것**이다 —
 *
 * - `search_enabled` … 내 검색에 쓴다. 끄면 색인은 남고 범위에서만 빠진다.
 * - `shared` … 팀이 봐도 된다. 거두면 팀원 목록에서 바로 사라진다.
 *
 * 내 검색에서 빼 두고 팀에는 공유하는 것도, 그 반대도 말이 된다.
 */
export function setPersonalFileFlags(
  token: string,
  docId: string,
  flags: { search_enabled?: boolean; shared?: boolean },
) {
  return apiRequest<{ doc_id: string; search_enabled: boolean | null; shared: boolean | null }>(
    `/me/files/${docId}/`,
    { method: 'PATCH', body: flags, token },
  );
}

/** **되살릴 수 없다.** 원본이 우리뿐이라 행·색인·원문을 함께 지운다. */
export function deletePersonalFile(token: string, docId: string) {
  return apiRequest<void>(`/me/files/${docId}/`, { method: 'DELETE', token });
}

export { ApiError };
