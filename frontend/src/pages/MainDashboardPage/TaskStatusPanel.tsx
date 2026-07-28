import { useState } from 'react';
import styles from './TaskStatusPanel.module.css';

type Tone = 'info' | 'warning' | 'success' | 'danger';

interface KpiCard {
  label: string;
  value: string;
  delta: string;
  tone: Tone;
}

interface StatusSegment {
  key: string;
  label: string;
  pct: number;
  tone: Tone;
}

interface DonutLegendItem {
  label: string;
  value: string;
  pct: number;
  tone: Tone;
}

const KPI_CARDS: KpiCard[] = [
  { label: '진행중 태스크', value: '13건', delta: '+2건', tone: 'info' },
  { label: '태스크 완료율', value: '36%', delta: '+4%', tone: 'success' },
  { label: '지연된 태스크', value: '4건', delta: '-1건', tone: 'danger' },
];

const STATUS_SEGMENTS: StatusSegment[] = [
  { key: 'progress', label: '진행중', pct: 42, tone: 'info' },
  { key: 'waiting', label: '대기', pct: 28, tone: 'warning' },
  { key: 'done', label: '완료', pct: 20, tone: 'success' },
  { key: 'delayed', label: '지연', pct: 10, tone: 'danger' },
];

const DONUT_LEGEND: DonutLegendItem[] = [
  { label: 'UI/UX 디자인', value: 'D-1 이하 (50%)', pct: 50, tone: 'info' },
  { label: '기능 개발', value: 'D-3 이하 (33%)', pct: 33, tone: 'warning' },
  { label: '운영 및 테스트', value: '여유 (17%)', pct: 17, tone: 'success' },
];

const SEG_BG_CLASS: Record<Tone, string> = {
  info: styles.bgInfo,
  warning: styles.bgWarning,
  success: styles.bgSuccess,
  danger: styles.bgDanger,
};

const DELTA_CLASS: Record<Tone, string> = {
  info: styles.deltaInfo,
  warning: styles.deltaWarning,
  success: styles.deltaSuccess,
  danger: styles.deltaDanger,
};

const TEXT_CLASS: Record<Tone, string> = {
  info: styles.textInfo,
  warning: styles.textWarning,
  success: styles.textSuccess,
  danger: styles.textDanger,
};

const TONE_BG_VAR: Record<Tone, string> = {
  info: 'var(--color-info)',
  warning: 'var(--color-warning)',
  success: 'var(--color-success)',
  danger: 'var(--color-danger)',
};

export function TaskStatusPanel() {
  const [activeSeg, setActiveSeg] = useState<string | null>(null);

  function toggleSeg(key: string) {
    setActiveSeg((prev) => (prev === key ? null : key));
  }

  let acc = 0;
  const donutStops = DONUT_LEGEND.map((item) => {
    const start = acc;
    acc += item.pct;
    return `${TONE_BG_VAR[item.tone]} ${start}% ${acc}%`;
  }).join(', ');

  return (
    <>
      <div className={styles.panelHeaderCol}>
        <p className={styles.panelTitle}>Task 현황</p>
        <p className={styles.panelSubtitle}>실시간 프로젝트 태스크 진행 지표</p>
      </div>

      <div className={styles.summaryRow}>
        {KPI_CARDS.map((card) => (
          <div key={card.label} className={styles.summaryCard}>
            <p className={styles.summaryLabel}>{card.label}</p>
            <div className={styles.summaryValueRow}>
              <p className={styles.summaryValue}>{card.value}</p>
              <span className={[styles.delta, DELTA_CLASS[card.tone]].join(' ')}>{card.delta}</span>
            </div>
          </div>
        ))}
      </div>

      <div className={styles.card}>
        <p className={styles.cardTitle}>상태별 업무 현황</p>
        <div className={styles.statusBar}>
          {STATUS_SEGMENTS.map((seg) => (
            <div
              key={seg.key}
              className={[styles.statusSeg, SEG_BG_CLASS[seg.tone]].join(' ')}
              style={{
                width: `${seg.pct}%`,
                opacity: activeSeg === null || activeSeg === seg.key ? 1 : 0.25,
              }}
            />
          ))}
        </div>
        <div className={styles.statusLegend}>
          {STATUS_SEGMENTS.map((seg) => (
            <button
              type="button"
              key={seg.key}
              className={[styles.legendItem, activeSeg !== null && activeSeg !== seg.key ? styles.dimmed : '']
                .filter(Boolean)
                .join(' ')}
              onClick={() => toggleSeg(seg.key)}
            >
              <span className={[styles.legendDot, SEG_BG_CLASS[seg.tone]].join(' ')} />
              {seg.label} ({seg.pct}%)
            </button>
          ))}
        </div>
      </div>

      <div className={styles.donutCard}>
        <div className={styles.donut} style={{ background: `conic-gradient(${donutStops})` }}>
          <div className={styles.donutCenter}>
            <p className={styles.donutEta}>ETA</p>
            <p className={styles.donutSub}>업무그룹별</p>
          </div>
        </div>
        <div className={styles.donutInfo}>
          <p className={styles.cardTitle}>업무 그룹별 기한 준수율</p>
          <div className={styles.donutLegend}>
            {DONUT_LEGEND.map((item) => (
              <div key={item.label} className={styles.donutLegendRow}>
                <p className={styles.donutLegendLabel}>{item.label}</p>
                <p className={[styles.donutLegendValue, TEXT_CLASS[item.tone]].join(' ')}>{item.value}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}

export default TaskStatusPanel;
