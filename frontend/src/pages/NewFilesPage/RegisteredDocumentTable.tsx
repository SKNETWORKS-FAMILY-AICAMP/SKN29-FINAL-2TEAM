import { Badge, Button } from '../../components';
import type { PipelineDocument } from '../../api/projects';
import styles from './RegisteredDocumentTable.module.css';

export interface RegisteredDocumentTableProps {
  documents: PipelineDocument[];
  onProcessPending: () => void;
  processing: boolean;
}

function statusOf(document: PipelineDocument): { label: string; ready: boolean } {
  if (document.search_ready) return { label: '검색 준비 완료', ready: true };
  if (document.downloaded) return { label: '처리 실패', ready: false };
  return { label: '원문 미수신', ready: false };
}

/**
 * 등록돼 있는 팀 문서와 그 준비 상태.
 *
 * **등록된 문서는 전부 검색 가능해야 한다.** 그래서 여기에 고르는 칸이 없다 —
 * 등록이 원문 수신·파싱·청킹·임베딩까지 끝내고, 이 목록은 그 결과를 확인하는
 * 곳이다. 「처리 필요」로 남는 것은 등록 중 실패한 문서뿐이라 다시 시도만 한다.
 *
 * 이 목록이 없어서 등록한 문서가 화면에서 사라졌고, 문서를 준비시키는 일이
 * 「신규 프로젝트 업무 추출」 화면에 얹혀 있었다. 문서가 준비됐는지는 문서의
 * 상태이지 프로젝트의 상태가 아니다.
 */
export function RegisteredDocumentTable({
  documents,
  onProcessPending,
  processing,
}: RegisteredDocumentTableProps) {
  const pending = documents.filter((document) => !document.search_ready);

  return (
    <section className={styles.card}>
      <div className={styles.head}>
        <div>
          <h2>등록된 문서 {documents.length}건</h2>
          <p>
            {pending.length === 0
              ? '모두 검색할 수 있습니다'
              : `${pending.length}건이 준비되지 않았습니다`}
          </p>
        </div>
        {pending.length > 0 && (
          <Button variant="primary" disabled={processing} onClick={onProcessPending}>
            {processing ? '처리 중…' : `${pending.length}건 다시 처리`}
          </Button>
        )}
      </div>

      <div className={styles.table}>
        <div className={styles.headRow}>
          <span>문서</span>
          <span>상태</span>
        </div>

        {documents.map((document) => {
          const status = statusOf(document);
          return (
            <div key={document.doc_id} className={styles.row}>
              <span className={styles.name}>
                {document.file_name ?? document.doc_id}
                {document.proj_id && (
                  <Badge tone="neutral">
                    {document.doc_role === 'PRIMARY' ? '기준 문서' : '근거 문서'}
                  </Badge>
                )}
              </span>
              <span className={status.ready ? styles.ready : styles.pending}>{status.label}</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
