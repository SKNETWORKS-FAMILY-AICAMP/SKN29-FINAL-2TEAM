import type { PersonWorkload, WorkloadResult } from '../../api/projects';
import styles from './TeamDashboard.module.css';

const BLOCKED_LABEL: Record<string, string> = {
  NO_SCHEDULE: '근무조건 없음',
  ON_LEAVE: '휴직',
  NO_EFFECTIVE_CAPACITY: '가용 없음',
};

function label(iso: string): string {
  return iso.slice(5).replace('-', '/');
}

/** 막대 색. 색이 뜻하는 것은 「용량 대비 어디까지 찼나」 하나뿐이다. */
function fillClass(ratio: number): string {
  if (ratio > 1) return styles.fillOver;
  if (ratio >= 0.8) return styles.fillHigh;
  return styles.fillNormal;
}

/**
 * 합계 뱃지의 짙기. 숫자가 클수록 진하다.
 *
 * 한 색의 농담이다. 초록·주황·빨강을 쓰지 않는 이유는, 잔여 시간이 많다는 것이
 * 그 자체로 나쁜 것은 아니기 때문이다 — 200h를 들고도 여유가 있는 사람이 있다.
 * 위험 여부는 옆의 주별 막대가 말한다.
 *
 * 경계는 만근 한 주(40h)를 단위로 잡았다. 1주 미만 / 1~2주 / 2~5주 / 5주 이상.
 */
function totalClass(hours: number): string {
  if (hours >= 200) return styles.totalS4;
  if (hours >= 100) return styles.totalS3;
  if (hours >= 40) return styles.totalS2;
  return styles.totalS1;
}

/**
 * 한 칸 = 시간(숫자) + 용량 대비(막대).
 *
 * 예전에는 칸을 통째로 칠하고 그 안에 시간을 적었는데, **한 칸이 서로 다른 두 값을
 * 말하고 있었다** — 숫자는 절대 시간이고 색은 그 사람 용량 대비 비율이라, 임준의
 * 100h는 빨강이고 김지훈의 48h는 회색이었다. 같은 열에서 숫자가 큰 쪽과 위험한
 * 쪽이 어긋나니 매번 머리로 나눠 읽어야 했다.
 *
 * 지금은 채널을 갈라 뒀다. 숫자는 잉크로 늘 읽히고, 비율은 그 아래 얇은 막대가
 * 맡는다. 큰 색 블록이 사라져서 훑을 때 눈에 남는 것은 막대가 끝까지 간 칸뿐이다.
 */
function WeekCell({ week, now }: { week: PersonWorkload['by_week'][number]; now: boolean }) {
  const known = week.capacity !== null && week.capacity > 0;
  const ratio = known ? week.hours / (week.capacity as number) : 0;

  return (
    <span
      className={`${styles.cell} ${now ? styles.cellNow : ''}`}
      title={`${label(week.week_start)} 주 · ${week.hours}h${
        known ? ` / 가용 ${week.capacity}h (${Math.round(ratio * 100)}%)` : ' · 가용 시간 모름'
      }`}
    >
      <span className={week.hours === 0 ? styles.cellZero : styles.cellValue}>
        {week.hours === 0 ? '·' : Math.round(week.hours)}
      </span>
      {/* 용량을 모르면 빗금만 둔다 — 모르는 것을 여유로 보이게 하지 않는다. */}
      <span className={`${styles.cellTrack} ${known ? '' : styles.trackUnknown}`}>
        {known && week.hours > 0 && (
          <span
            className={`${styles.cellFill} ${fillClass(ratio)}`}
            style={{ width: `${Math.min(100, ratio * 100)}%` }}
          />
        )}
      </span>
    </span>
  );
}

function PersonWeeks({ person, thisWeek }: { person: PersonWorkload; thisWeek: number }) {
  const total =
    Math.round((person.current_allocation + person.unscheduled_backlog_hours) * 10) / 10;

  return (
    <div className={styles.weekRow}>
      <div className={styles.weekName}>
        <span className={styles.memberName}>{person.name ?? person.person_id}</span>
        {person.job_role && <span className={styles.memberRole}>{person.job_role}</span>}
      </div>

      {person.by_week.map((week, index) => (
        <WeekCell key={week.week_start} week={week} now={index === thisWeek} />
      ))}

      {/* 조회 기간 뒤 마감은 칸이 없다. 합계가 어긋나 보이지 않도록 따로 적는다. */}
      <span className={styles.weekLater}>
        {person.later_hours > 0 ? `+${Math.round(person.later_hours)}h` : '—'}
      </span>

      <span className={styles.weekTotal}>
        {person.blocked_reason ? (
          <span className={styles.weekBlocked}>
            {BLOCKED_LABEL[person.blocked_reason] ?? person.blocked_reason}
          </span>
        ) : (
          <span className={`${styles.totalBadge} ${totalClass(total)}`}>
            {Math.round(total)}h
          </span>
        )}
      </span>
    </div>
  );
}

/**
 * 팀원별 주간 업무 시간.
 *
 * 부하율 막대를 대신한다. 막대는 "이 기간 평균 몇 %"만 말해서, 122.5%가 사실은
 * 셋째 주에 100h가 겹친 것이라는 사실이 보이지 않았다. 마감이 속한 주에 공수를
 * 얹어 두면 **합계와 몰리는 시점이 한 그림에** 들어온다.
 *
 * 여유 있는 주는 칠하지 않는다. 전부 색이 있으면 어느 칸이 문제인지 세어 봐야
 * 알게 되고, 그러면 한눈에 보라고 만든 격자가 제 일을 못 한다.
 *
 * 업무를 며칠에 걸쳐 어떻게 쪼갤지는 우리가 알 수 없다. 아는 것은 "그때까지
 * 끝나야 한다"뿐이라 마감 주에 통째로 얹는다.
 */
export function TeamWeekPanel({ workload }: { workload: WorkloadResult }) {
  const weeks = workload.people[0]?.by_week ?? [];

  // 조회 기간은 오늘부터 시작하므로 첫 칸이 이번 주다. 그래도 찾아서 쓰는 이유는,
  // 기간을 뒤로 미뤄 보는 순간 첫 칸이 이번 주가 아니게 되기 때문이다.
  const thisWeek = weeks.findIndex((week) => {
    const start = new Date(`${week.week_start}T00:00:00`);
    const end = new Date(start);
    end.setDate(end.getDate() + 7);
    const now = new Date();
    return now >= start && now < end;
  });
  const people = [...workload.people].sort(
    (a, b) =>
      b.current_allocation + b.unscheduled_backlog_hours -
      (a.current_allocation + a.unscheduled_backlog_hours),
  );

  return (
    <div className={styles.card} style={{ ["--weeks" as string]: weeks.length }}>
      <div className={styles.cardHeader}>
        <p className={styles.cardTitle}>팀원별 주간 업무 시간</p>
        {/* 매핑이 안 된 담당자의 업무는 아무 행에도 안 들어간다. 그 사실은 빠진
            자리에 적어야 한다 — 화면 아래 각주로 빼면 격자만 보고 지나간다. */}
        <span className={styles.cardNote}>
          마감이 속한 주에 쌓았습니다
          {workload.unmapped_assignee_count > 0 &&
            ` · 담당자 미매핑 ${workload.unmapped_assignee_count}건 제외`}
        </span>
        {/* 막대 색이 무엇을 뜻하는지 글로도 적는다. 색만으로 상태를 말하면 색을
            구분하지 못하는 사람에게는 아무 말도 안 한 것이 된다. */}
        <span className={styles.legend}>
          {[
            { cls: styles.fillNormal, text: '여유' },
            { cls: styles.fillHigh, text: '빠듯' },
            { cls: styles.fillOver, text: '초과' },
          ].map((item) => (
            <span key={item.text} className={styles.legendItem}>
              <span className={`${styles.legendDot} ${item.cls}`} />
              {item.text}
            </span>
          ))}
        </span>
      </div>

      <div className={styles.weekHead}>
        <span />
        {weeks.map((week, index) => (
          <span
            key={week.week_start}
            className={`${styles.weekLabel} ${index === thisWeek ? styles.weekLabelNow : ''}`}
          >
            {index === thisWeek ? '이번 주' : label(week.week_start)}
          </span>
        ))}
        <span className={styles.weekLabel}>이후</span>
        <span className={styles.weekLabel}>합계</span>
      </div>

      <div className={styles.weekList}>
        {people.map((person) => (
          <PersonWeeks key={person.person_id} person={person} thisWeek={thisWeek} />
        ))}
        {people.length === 0 && <p className={styles.empty}>팀원이 없습니다.</p>}
      </div>
    </div>
  );
}

export default TeamWeekPanel;
