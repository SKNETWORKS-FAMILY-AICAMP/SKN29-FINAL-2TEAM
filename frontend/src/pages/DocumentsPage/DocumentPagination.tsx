import { Button } from '../../components';
import styles from './DocumentsPage.module.css';

interface DocumentPaginationProps {
  page: number;
  pageCount: number;
  onPageChange: (page: number) => void;
}

/** 현재 쪽을 중심으로 최대 5개의 연속된 쪽 번호를 보여 준다. */
function visiblePages(page: number, pageCount: number): number[] {
  const visibleCount = Math.min(5, pageCount);
  let start = Math.max(1, page - Math.floor(visibleCount / 2));
  const end = Math.min(pageCount, start + visibleCount - 1);
  start = Math.max(1, end - visibleCount + 1);
  return Array.from({ length: end - start + 1 }, (_, index) => start + index);
}

/** 문서 표가 공통으로 쓰는 중앙 정렬 번호형 페이지네이션. */
export function DocumentPagination({ page, pageCount, onPageChange }: DocumentPaginationProps) {
  if (pageCount <= 1) return null;

  return (
    <nav className={styles.pager} aria-label="문서 목록 페이지">
      <div className={styles.pagerButtons}>
        <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => onPageChange(1)}>
          처음
        </Button>
        <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
          이전
        </Button>

        {visiblePages(page, pageCount).map((pageNumber) => {
          const current = pageNumber === page;
          return (
            <Button
              key={pageNumber}
              size="sm"
              variant={current ? 'primary' : 'outline'}
              className={styles.pagerNumber}
              aria-label={`${pageNumber}페이지`}
              aria-current={current ? 'page' : undefined}
              onClick={() => onPageChange(pageNumber)}
            >
              {pageNumber}
            </Button>
          );
        })}

        <Button
          size="sm"
          variant="outline"
          disabled={page >= pageCount}
          onClick={() => onPageChange(page + 1)}
        >
          다음
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={page >= pageCount}
          onClick={() => onPageChange(pageCount)}
        >
          맨 끝
        </Button>
      </div>
    </nav>
  );
}
