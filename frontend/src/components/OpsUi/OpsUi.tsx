import { useEffect, useRef } from 'react';
import type { ReactNode, TableHTMLAttributes } from 'react';
import { useNarrowViewport } from '../../utils/viewport';
import { Icon } from '../Icon/Icon';
import styles from './OpsUi.module.css';

export type OpsTone = 'neutral' | 'success' | 'warning' | 'danger' | 'info';

/**
 * 화면 제목.
 *
 * **설명은 선택이다**(2026-08-18 PM — 「이런 거 다 빼라」). 운영자 콘솔의 설명
 * 문구는 제목이 이미 하는 말을 늘려 쓴 것이 대부분이었다(「팀 현황 — 팀 목록과
 * 상태를 확인합니다」). 매일 보는 화면에서는 그 한 줄이 매번 자리만 차지한다.
 *
 * 안 주면 그 줄을 **아예 안 그린다** — 빈 문자열을 넘겨 빈 줄을 남기지 않는다.
 */
export function OpsPageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className={styles.pageHeader}>
      <div>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className={styles.headerActions}>{actions}</div>}
    </div>
  );
}

export function OpsSummaryGrid({ children }: { children: ReactNode }) {
  return <div className={styles.summaryGrid}>{children}</div>;
}

export function OpsSummaryCard({
  label,
  value,
  detail,
  tone = 'neutral',
  onClick,
}: {
  label: string;
  value: string | number;
  detail?: string;
  tone?: OpsTone;
  onClick?: () => void;
}) {
  const content = (
    <>
      <span className={styles.summaryLabel}>{label}</span>
      <strong>{value}</strong>
      {detail && <span className={styles[`summaryDetail_${tone}`]}>{detail}</span>}
    </>
  );

  return onClick ? (
    <button type="button" className={styles.summaryCard} onClick={onClick}>
      {content}
    </button>
  ) : (
    <div className={styles.summaryCard}>{content}</div>
  );
}

export function OpsStatusBadge({ children, tone = 'neutral' }: { children: ReactNode; tone?: OpsTone }) {
  return <span className={[styles.badge, styles[`badge_${tone}`]].join(' ')}>{children}</span>;
}

export function OpsFilterBar({ children }: { children: ReactNode }) {
  return <div className={styles.filterBar}>{children}</div>;
}

export function OpsSearchField({
  value,
  onChange,
  placeholder,
  ariaLabel,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  ariaLabel?: string;
}) {
  return (
    <label className={styles.searchField}>
      <Icon name="search" size={16} />
      <input
        type="search"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        aria-label={ariaLabel ?? placeholder}
      />
    </label>
  );
}

/**
 * 운영자 표가 쌓이기 시작하는 폭.
 *
 * 720px 아래에서는 운영자 셸의 사이드바가 가로 내비게이션으로 내려가 폭을 다
 * 내주지만, 그 위 구간에서는 아직 200~240px 을 쥐고 있다. 화면 폭만 보면
 * 768px 이 「넓은 화면」으로 분류돼 칸이 뭉개진다.
 */
const OPS_STACK_WIDTH = 980;

export function OpsDataTable({
  children,
  minWidth = 920,
  maxHeight = 560,
  ...props
}: TableHTMLAttributes<HTMLTableElement> & { minWidth?: number; maxHeight?: number }) {
  const narrow = useNarrowViewport(OPS_STACK_WIDTH);
  const ref = useRef<HTMLTableElement>(null);

  /**
   * 열 이름을 각 칸에 심는다. 좁은 화면에서 줄을 쌓으면 머리글이 멀어지므로
   * 값만 남으면 그게 무슨 값인지 알 수 없다 — CSS 가 이 값을 앞에 그린다.
   *
   * **여기서 하는 이유는 한 곳이기 때문이다.** 운영자 표는 8종이고 열이
   * 5~9개라, 페이지마다 손으로 붙이면 한 곳만 빠져도 그 칸이 이름을 잃는다.
   *
   * 의존성을 두지 않는다 — 행은 검색·필터로 계속 바뀌고, 하는 일은 속성을
   * 다시 쓰는 것뿐이라 비용이 거의 없다.
   */
  useEffect(() => {
    const table = ref.current;
    if (!table) return;
    const labels = Array.from(table.querySelectorAll('thead th'), (th) => th.textContent?.trim() ?? '');
    for (const row of table.querySelectorAll('tbody tr')) {
      Array.from(row.children).forEach((cell, index) => {
        if (labels[index]) cell.setAttribute('data-label', labels[index]);
      });
    }
  });

  return (
    // 좁을 때는 높이도 폭도 묶지 않는다. 쌓인 줄은 길어지고, 최소 폭이 남아
    // 있으면 결국 옆으로 흐른다 — 그걸 없애려고 쌓는 것이다.
    <div className={styles.tableWrap} style={{ maxHeight: narrow ? undefined : maxHeight }}>
      <table ref={ref} {...props} style={{ minWidth: narrow ? undefined : minWidth }}>
        {children}
      </table>
    </div>
  );
}

export function OpsDetailPanel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className={styles.detailPanel}>
      <h2>{title}</h2>
      {children}
    </section>
  );
}

export function OpsSectionCard({
  title,
  subtitle,
  actions,
  children,
  className,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={[styles.sectionCard, className ?? ''].filter(Boolean).join(' ')}>
      <div className={styles.sectionHeader}>
        <div>
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {actions && <div className={styles.sectionActions}>{actions}</div>}
      </div>
      {children}
    </section>
  );
}

export function OpsEmpty({ message }: { message: string }) {
  return <div className={styles.empty}>{message}</div>;
}
