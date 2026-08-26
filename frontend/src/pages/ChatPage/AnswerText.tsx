import { useState } from 'react';
import type { ComponentPropsWithoutRef } from 'react';
import Markdown, { type Components } from 'react-markdown';
import remarkCjkFriendly from 'remark-cjk-friendly';
import remarkCjkFriendlyGfmStrikethrough from 'remark-cjk-friendly-gfm-strikethrough';
import remarkGfm from 'remark-gfm';
import { Icon } from '../../components/Icon/Icon';
import { Modal } from '../../components/Modal/Modal';
import styles from './AnswerText.module.css';

/**
 * 에이전트의 최종 답변을 안전한 Markdown으로 그린다.
 *
 * 답변에는 문서 원문과 외부 도구 결과가 섞일 수 있으므로 raw HTML은 실행하지
 * 않는다. `react-markdown`이 만든 React 노드만 사용하고 `rehype-raw`와
 * `dangerouslySetInnerHTML`은 쓰지 않는다. 외부 이미지는 브라우저가 임의의
 * 서버에 직접 요청하면서 사용자 IP를 노출할 수 있어 표시하지 않는다.
 *
 * 실행 상태·승인·Jira 결과 같은 구조화 데이터는 이 컴포넌트가 아니라 기존
 * 전용 카드가 담당한다. 여기서는 모델의 최종 답변 문자열만 표현한다.
 */

function safeUrl(url: string): string {
  return /^https?:\/\//i.test(url) ? url : '';
}

function ExternalLink({ href, children, ...props }: ComponentPropsWithoutRef<'a'>) {
  if (!href) return <span>{children}</span>;
  return (
    <a
      {...props}
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={styles.link}
    >
      {children}
    </a>
  );
}

function MarkdownTable({ children, ...props }: ComponentPropsWithoutRef<'table'>) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className={styles.tableBlock}>
      <button
        type="button"
        className={styles.tableExpand}
        onClick={() => setExpanded(true)}
        aria-label="표 펼치기"
        title="표 펼치기"
      >
        <Icon name="expand" size={15} />
        <span>표 펼치기</span>
      </button>
      <div className={styles.tableScroll} role="region" aria-label="답변 표, 가로로 스크롤 가능" tabIndex={0}>
        <table {...props} className={styles.table}>{children}</table>
      </div>
      <Modal open={expanded} onClose={() => setExpanded(false)} title="표 전체 보기" width={1200}>
        <div className={`${styles.tableScroll} ${styles.tableExpanded}`} role="region" aria-label="확장된 답변 표" tabIndex={0}>
          <table {...props} className={styles.table}>{children}</table>
        </div>
      </Modal>
    </div>
  );
}

const components: Components = {
  h1: ({ node: _node, ...props }) => <h2 {...props} className={`${styles.heading} ${styles.heading1}`} />,
  h2: ({ node: _node, ...props }) => <h3 {...props} className={`${styles.heading} ${styles.heading2}`} />,
  h3: ({ node: _node, ...props }) => <h4 {...props} className={`${styles.heading} ${styles.heading3}`} />,
  h4: ({ node: _node, ...props }) => <h5 {...props} className={`${styles.heading} ${styles.heading3}`} />,
  p: ({ node: _node, ...props }) => <p {...props} className={styles.paragraph} />,
  ul: ({ node: _node, ...props }) => <ul {...props} className={styles.list} />,
  ol: ({ node: _node, ...props }) => <ol {...props} className={`${styles.list} ${styles.orderedList}`} />,
  blockquote: ({ node: _node, ...props }) => <blockquote {...props} className={styles.quote} />,
  pre: ({ node: _node, ...props }) => <pre {...props} className={styles.pre} />,
  code: ({ node: _node, ...props }) => <code {...props} className={styles.code} />,
  a: ({ node: _node, ...props }) => <ExternalLink {...props} />,
  table: ({ node: _node, ...props }) => <MarkdownTable {...props} />,
  img: ({ node: _node, alt }) => (
    <span className={styles.imageOmitted}>{alt ? `이미지: ${alt}` : '외부 이미지'} (표시하지 않음)</span>
  ),
};

export function AnswerText({ text }: { text: string }) {
  return (
    <div className={styles.answer}>
      <Markdown
        remarkPlugins={[remarkGfm, remarkCjkFriendly, remarkCjkFriendlyGfmStrikethrough]}
        components={components}
        skipHtml
        urlTransform={safeUrl}
      >
        {text}
      </Markdown>
    </div>
  );
}
