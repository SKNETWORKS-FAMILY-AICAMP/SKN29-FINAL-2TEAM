import {
  downloadDocuments,
  fetchDocumentProcessing,
  startDocumentProcessing,
  TERMINAL_PROCESSING_STATUS,
} from '../api/projects';
import type { DocumentProcessingRun } from '../api/projects';

/** 원문 수신은 RunPod job 이 아니라 우리 쪽 단계다. 상태값에 섞어 하나로 다룬다. */
export type ProcessingStage = 'DOWNLOADING' | DocumentProcessingRun['status'];

/**
 * 상태 코드는 RunPod 것이다. 화면에 `IN_QUEUE` 를 그대로 내보내지 않는다.
 */
export const PROCESSING_LABEL: Record<string, string> = {
  DOWNLOADING: '원문 받는 중',
  IN_QUEUE: '대기 중',
  IN_PROGRESS: '처리 중',
  RUNNING: '처리 중',
  COMPLETED: '완료',
  FAILED: '실패',
  CANCELLED: '취소됨',
  TIMED_OUT: '시간 초과',
};

export function stageLabel(stage: string): string {
  return PROCESSING_LABEL[stage] ?? stage;
}

/** 처리가 끝났지만 성공이 아닌 경우. 요청 자체의 실패(`ApiError`)와 구분한다. */
export class DocumentProcessingFailure extends Error {}

interface ProcessOptions {
  token: string;
  docId: string;
  /** 원문을 이미 받아 뒀는가. 아니면 파싱 전에 받는다. */
  downloaded: boolean;
  onStage?: (stage: ProcessingStage) => void;
}

/**
 * 문서 하나를 검색 가능한 상태까지 끌고 간다 — 원문 수신 → 파싱·청킹·임베딩.
 *
 * 문서 관리와 기준 문서 선택 화면이 같이 쓴다. polling 종료 조건과 실패 판정을
 * 양쪽에 따로 두면 한쪽만 고쳐지고 갈라진다.
 */
export async function processDocument({
  token,
  docId,
  downloaded,
  onStage,
}: ProcessOptions): Promise<DocumentProcessingRun> {
  if (!downloaded) {
    onStage?.('DOWNLOADING');
    const fetched = await downloadDocuments(token, [docId]);
    const failure = fetched.failed[0];
    if (failure) {
      throw new DocumentProcessingFailure(`원문을 받지 못했습니다 — ${failure.detail}`);
    }
  }

  onStage?.('IN_QUEUE');
  const run = await startDocumentProcessing(token, docId);
  let current = run;
  onStage?.(current.status);

  while (!TERMINAL_PROCESSING_STATUS.includes(current.status)) {
    await new Promise((resolve) => setTimeout(resolve, 3000));
    current = await fetchDocumentProcessing(token, docId, run.job_id);
    onStage?.(current.status);
  }

  if (current.status !== 'COMPLETED') {
    throw new DocumentProcessingFailure(current.error || '문서 처리에 실패했습니다');
  }
  return current;
}
