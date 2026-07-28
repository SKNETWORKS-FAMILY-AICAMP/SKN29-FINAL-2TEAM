import { useMemo, useState } from 'react';
import { Icon } from '../../components';
import styles from './CalendarWidget.module.css';

interface YearMonth {
  year: number;
  month: number; // 0-indexed
}

interface SelectedDay extends YearMonth {
  day: number;
}

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];
const HIGHLIGHT_DAYS = [2, 13, 14]; // only meaningful for Nov 2023 (matches design)

export function CalendarWidget() {
  const [current, setCurrent] = useState<YearMonth>({ year: 2023, month: 10 });
  const [selectedDay, setSelectedDay] = useState<SelectedDay>({ year: 2023, month: 10, day: 8 });

  const cells = useMemo(() => {
    const firstWeekday = new Date(current.year, current.month, 1).getDay();
    const daysInMonth = new Date(current.year, current.month + 1, 0).getDate();
    const result: Array<number | null> = [];
    for (let i = 0; i < firstWeekday; i += 1) result.push(null);
    for (let d = 1; d <= daysInMonth; d += 1) result.push(d);
    return result;
  }, [current]);

  const rows = useMemo(() => {
    const result: Array<Array<number | null>> = [];
    for (let i = 0; i < cells.length; i += 7) {
      result.push(cells.slice(i, i + 7));
    }
    return result;
  }, [cells]);

  const isNov2023 = current.year === 2023 && current.month === 10;

  function goPrev() {
    setCurrent((prev) => {
      const month = prev.month - 1;
      return month < 0 ? { year: prev.year - 1, month: 11 } : { year: prev.year, month };
    });
  }

  function goNext() {
    setCurrent((prev) => {
      const month = prev.month + 1;
      return month > 11 ? { year: prev.year + 1, month: 0 } : { year: prev.year, month };
    });
  }

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <p className={styles.title}>
          {current.year}년 {current.month + 1}월 업무 일정
        </p>
        <div className={styles.nav}>
          <button type="button" className={styles.chevronBtn} aria-label="이전 달" onClick={goPrev}>
            <Icon name="arrow-left" size={16} />
          </button>
          <button type="button" className={styles.chevronBtn} aria-label="다음 달" onClick={goNext}>
            <Icon name="arrow-right" size={16} />
          </button>
        </div>
      </div>

      <div className={styles.weekdays}>
        {WEEKDAYS.map((wd) => (
          <span key={wd} className={styles.weekday}>
            {wd}
          </span>
        ))}
      </div>

      <div className={styles.grid}>
        {rows.map((row, rowIdx) => (
          <div key={rowIdx} className={styles.row}>
            {row.map((day, idx) => {
              if (day === null) {
                return <span key={idx} className={[styles.dayCell, styles.empty].join(' ')} />;
              }
              const isHighlight = isNov2023 && HIGHLIGHT_DAYS.includes(day);
              const isSelected =
                current.year === selectedDay.year && current.month === selectedDay.month && day === selectedDay.day;
              const classes = [
                styles.dayCell,
                isHighlight ? styles.highlight : '',
                isSelected ? styles.selected : '',
              ]
                .filter(Boolean)
                .join(' ');
              return (
                <button
                  key={idx}
                  type="button"
                  className={classes}
                  onClick={() => setSelectedDay({ year: current.year, month: current.month, day })}
                >
                  {day}
                </button>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

export default CalendarWidget;
