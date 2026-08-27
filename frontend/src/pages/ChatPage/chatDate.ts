const SEOUL_TIME_ZONE = 'Asia/Seoul';

function validDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function seoulDateKey(value: string | null | undefined): string | null {
  const date = validDate(value);
  if (!date) return null;
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: SEOUL_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date);
}

function seoulYear(value: string | null | undefined): string | null {
  const date = validDate(value);
  if (!date) return null;
  return new Intl.DateTimeFormat('en', {
    timeZone: SEOUL_TIME_ZONE,
    year: 'numeric',
  }).format(date);
}

/**
 * 메시지 아래에는 읽는 데 필요한 정밀도만 보인다. 초는 정렬을 어지럽히므로
 * 툴팁에만 남기고, 날짜가 오늘과 다를 때만 날짜를 앞에 붙인다.
 */
export function formatMessageTime(
  value: string | null | undefined,
  now: Date = new Date(),
): string | null {
  const date = validDate(value);
  if (!date) return null;
  const dateKey = seoulDateKey(value);
  const todayKey = seoulDateKey(now.toISOString());
  const time = new Intl.DateTimeFormat('ko-KR', {
    timeZone: SEOUL_TIME_ZONE,
    hour: 'numeric',
    minute: '2-digit',
  }).format(date);
  if (dateKey === todayKey) return time;

  const sameYear = seoulYear(value) === seoulYear(now.toISOString());
  const day = new Intl.DateTimeFormat('ko-KR', {
    timeZone: SEOUL_TIME_ZONE,
    ...(sameYear ? {} : { year: 'numeric' as const }),
    month: 'long',
    day: 'numeric',
  }).format(date);
  return `${day} ${time}`;
}

export function formatMessageTimeFull(value: string | null | undefined): string | null {
  const date = validDate(value);
  if (!date) return null;
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: SEOUL_TIME_ZONE,
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
  }).format(date);
}

export function formatDateSeparator(dateKey: string): string {
  const [year, month, day] = dateKey.split('-').map(Number);
  if (!year || !month || !day) return dateKey;
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: SEOUL_TIME_ZONE,
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    weekday: 'long',
  }).format(new Date(Date.UTC(year, month - 1, day, 12)));
}

/** 표시 형식과 ISO형 날짜·24시간 표기를 모두 검색할 수 있게 만든다. */
export function searchableMessageTime(value: string | null | undefined): string {
  const date = validDate(value);
  const dateKey = seoulDateKey(value);
  if (!date || !dateKey) return '';
  const [year, month, day] = dateKey.split('-').map(Number);
  const hour24 = new Intl.DateTimeFormat('en-GB', {
    timeZone: SEOUL_TIME_ZONE,
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).format(date);
  return [
    dateKey,
    `${year}년 ${month}월 ${day}일`,
    `${month}월 ${day}일`,
    hour24,
    formatMessageTime(value),
    formatMessageTimeFull(value),
  ]
    .filter(Boolean)
    .join(' ')
    .toLocaleLowerCase('ko-KR');
}
