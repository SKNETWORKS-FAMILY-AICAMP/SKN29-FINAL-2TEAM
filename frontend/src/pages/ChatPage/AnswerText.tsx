import type { ReactNode } from 'react';
import styles from './AnswerText.module.css';

/**
 * 에이전트 답을 사람이 읽을 모양으로 그린다.
 *
 * **마크다운 라이브러리를 넣지 않는다.** 모델이 실제로 쓰는 문법은 몇 개뿐이고
 * (문단 · `- ` 목록 · `**굵게**` · `*기울임*` · 백틱 인라인 코드 · 링크), 그것만 그리면 의존성이 0이다. 그리고
 * `dangerouslySetInnerHTML` 을 쓰지 않으므로 도구 결과에 섞여 온 문자열이
 * HTML 로 실행될 여지가 없다 — 이 답에는 문서 원문이 들어온다.
 *
 * 그리지 않는 것(제목·표·코드블록)은 **그대로 글자로 보인다.** 잘못
 * 그리는 것보다 낫고, 모델에게는 그런 문법을 쓰지 말라고 스캐폴드가 이미
 * 말해 두었다(짧게 답하라 · 목록 남발 금지).
 */

/** 지원하는 짧은 인라인 문법만 처리한다. HTML은 실행하지 않는다. */
function inline(text: string, keyPrefix: string): ReactNode[] {
  // **굵게가 먼저다.** 순서를 바꾸면 `**굵게**` 의 앞 두 별표가 기울임으로 먼저
  // 잡혀서 `*굵게*` 로 깨진다.
  return text.split(/(\[[^\]\n]+\]\(https?:\/\/[^\s)]+\)|https?:\/\/[^\s<>()]+|\*\*[^*]+\*\*|\*[^*\n]+\*|`[^`]+`)/g).map((part, index) => {
    const key = `${keyPrefix}-${index}`;
    const markdownLink = part.match(/^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/);
    if (markdownLink) {
      return <a key={key} href={markdownLink[2]} target="_blank" rel="noreferrer" className={styles.link}>{markdownLink[1]}</a>;
    }
    if (/^https?:\/\//.test(part)) {
      return <a key={key} href={part} target="_blank" rel="noreferrer" className={styles.link}>{part}</a>;
    }
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return <strong key={key}>{part.slice(2, -2)}</strong>;
    }
    // 모델은 근거 표기를 기울임으로 쓴다(`*(근거: workload_report)*`). 안 그리면
    // 별표가 글자 그대로 보인다 — 근거는 거의 모든 답변에 붙으므로 늘 보인다.
    if (part.startsWith('*') && part.endsWith('*') && part.length > 2) {
      return <em key={key}>{part.slice(1, -1)}</em>;
    }
    // 모델은 도구 이름을 백틱으로 감싼다(`workload_report`). 안 그리면 백틱이
    // 글자 그대로 보인다 — 2026-08-12 QA §B-0 에서 나온 것이다.
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return (
        <code key={key} className={styles.code}>
          {part.slice(1, -1)}
        </code>
      );
    }
    return <span key={key}>{part}</span>;
  });
}

export function AnswerText({ text }: { text: string }) {
  const lines = text.split('\n');
  const blocks: ReactNode[] = [];
  let bullets: string[] = [];

  const flushBullets = () => {
    if (bullets.length === 0) return;
    const items = bullets;
    bullets = [];
    blocks.push(
      <ul key={`ul-${blocks.length}`} className={styles.list}>
        {items.map((item, index) => (
          <li key={index}>{inline(item, `li-${blocks.length}-${index}`)}</li>
        ))}
      </ul>,
    );
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    const bullet = line.match(/^\s*[-*]\s+(.*)$/);
    if (bullet) {
      bullets.push(bullet[1]);
      continue;
    }
    flushBullets();
    // 빈 줄은 문단 사이의 간격이다. 빈 <p> 를 만들지 않는다.
    if (!line.trim()) continue;
    blocks.push(
      <p key={`p-${blocks.length}`} className={styles.paragraph}>
        {inline(line, `p-${blocks.length}`)}
      </p>,
    );
  }
  flushBullets();

  return <div className={styles.answer}>{blocks}</div>;
}
