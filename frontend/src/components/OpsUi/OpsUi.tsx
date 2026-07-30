import type { ReactNode, TableHTMLAttributes } from 'react';
import { Icon } from '../Icon/Icon';
import styles from './OpsUi.module.css';

export type OpsTone = 'neutral' | 'success' | 'warning' | 'danger' | 'info';

export function OpsPageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <div className={styles.pageHeader}>
      <div>
        <h1>{title}</h1>
        <p>{description}</p>
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
  detail: string;
  tone?: OpsTone;
  onClick?: () => void;
}) {
  const content = (
    <>
      <span className={styles.summaryLabel}>{label}</span>
      <strong>{value}</strong>
      <span className={styles[`summaryDetail_${tone}`]}>{detail}</span>
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

export function OpsDataTable({
  children,
  minWidth = 920,
  ...props
}: TableHTMLAttributes<HTMLTableElement> & { minWidth?: number }) {
  return (
    <div className={styles.tableWrap}>
      <table {...props} style={{ minWidth }}>
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
