import { useState } from 'react';
import type { ReactNode } from 'react';
import { Button, Modal } from '../../components';
import styles from './WelcomeTour.module.css';

/**
 * 처음 온 사람에게 이 제품이 무엇인지 넉 장으로 설명한다.
 *
 * **왜 모달인가.** 가입 직후 화면은 팀도 문서도 없어서 보여줄 것이 없다. 빈
 * 화면에 안내를 흩어 놓으면 읽히지 않는데, 이 순간은 사람이 「이게 뭐지」를
 * 궁금해하는 유일한 때라 오히려 설명이 먹힌다.
 *
 * **그림은 전부 인라인 SVG 다.** 화면 캡처를 넣으면 화면이 바뀔 때마다 거짓이
 * 되고(오늘만 해도 여러 번 바뀌었다), 이미지 파일은 테마를 못 따라간다.
 * 여기 그림은 `tokens.css` 변수를 그대로 쓰므로 항상 지금 색과 같다.
 *
 * 마지막 장은 **다음 행동으로 이어진다** — 「좋아요, 시작할게요」가 인사 시스템
 * 연결로 간다. 설명만 하고 끝나면 사람은 다시 빈 화면 앞에 남는다.
 */

interface Slide {
  title: string;
  body: string;
  art: ReactNode;
}

/** 그림에 쓰는 색. 클래스로 주면 SVG 안에서 `currentColor` 를 두 번 못 쓴다. */
const INK = 'var(--color-heading)';
const SOFT = 'var(--color-border)';
const KEY = 'var(--color-primary)';

const SLIDES: Slide[] = [
  {
    title: '팀이 쓰는 AI를, 코딩 없이',
    body: '무슨 일을 하는지 적으면 팀 전체가 쓰는 에이전트가 됩니다. 답에는 늘 원문 근거가 붙습니다.',
    art: (
      <svg viewBox="0 0 240 120" role="img" aria-label="대화창에서 답과 근거가 나오는 그림">
        <rect x="18" y="18" width="150" height="84" rx="10" fill="none" stroke={SOFT} strokeWidth="2" />
        <rect x="32" y="34" width="86" height="8" rx="4" fill={SOFT} />
        <rect x="32" y="52" width="118" height="8" rx="4" fill={SOFT} />
        <rect x="32" y="70" width="64" height="8" rx="4" fill={KEY} />
        <rect x="150" y="60" width="72" height="46" rx="8" fill="var(--color-surface)" stroke={KEY} strokeWidth="2" />
        <rect x="160" y="72" width="42" height="6" rx="3" fill={KEY} />
        <rect x="160" y="86" width="52" height="6" rx="3" fill={SOFT} />
      </svg>
    ),
  },
  {
    title: '자리마다 하나씩 연결합니다',
    body: '인사 시스템·문서 저장소·업무 기록소. 인사 시스템만 필수이고, 나머지는 그 기능이 필요할 때 붙이면 됩니다.',
    art: (
      <svg viewBox="0 0 240 120" role="img" aria-label="세 자리가 가운데로 연결되는 그림">
        <circle cx="120" cy="60" r="22" fill="var(--color-surface)" stroke={KEY} strokeWidth="2" />
        <path d="M120 50v20M110 60h20" stroke={KEY} strokeWidth="2" strokeLinecap="round" />
        <path d="M62 30h30M62 60h36M62 90h30" stroke={SOFT} strokeWidth="2" strokeLinecap="round" />
        <rect x="14" y="20" width="48" height="20" rx="6" fill="none" stroke={KEY} strokeWidth="2" />
        <rect x="14" y="50" width="48" height="20" rx="6" fill="none" stroke={SOFT} strokeWidth="2" />
        <rect x="14" y="80" width="48" height="20" rx="6" fill="none" stroke={SOFT} strokeWidth="2" />
        <path d="M142 60h44" stroke={SOFT} strokeWidth="2" strokeLinecap="round" />
        <rect x="186" y="46" width="40" height="28" rx="6" fill="none" stroke={SOFT} strokeWidth="2" />
      </svg>
    ),
  },
  {
    title: '말하면 문서에서 업무를 뽑습니다',
    body: '기준 문서를 정해 두면 요구사항·산출물·담당 역할을 찾아 업무로 정리합니다. 근거를 못 찾은 항목은 채우지 않고 비워 둡니다.',
    art: (
      <svg viewBox="0 0 240 120" role="img" aria-label="문서에서 업무 목록이 만들어지는 그림">
        <rect x="20" y="16" width="66" height="88" rx="8" fill="none" stroke={SOFT} strokeWidth="2" />
        <path d="M32 36h42M32 50h42M32 64h30" stroke={SOFT} strokeWidth="2" strokeLinecap="round" />
        <path d="M96 60h26" stroke={KEY} strokeWidth="2" strokeLinecap="round" />
        <path d="M116 54l8 6-8 6" fill="none" stroke={KEY} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        <rect x="132" y="24" width="88" height="20" rx="6" fill="none" stroke={KEY} strokeWidth="2" />
        <rect x="132" y="50" width="88" height="20" rx="6" fill="none" stroke={SOFT} strokeWidth="2" />
        <rect x="132" y="76" width="88" height="20" rx="6" fill="none" stroke={SOFT} strokeWidth="2" />
        <path d="M142 34h30M142 60h44M142 86h24" stroke={SOFT} strokeWidth="2" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    title: '승인하기 전에는 아무것도 만들지 않습니다',
    body: '추출한 업무는 목록으로 먼저 표시됩니다. 체크한 것만 등록되고, 외부에 나가는 일은 한 번 더 확인합니다.',
    art: (
      <svg viewBox="0 0 240 120" role="img" aria-label="체크한 항목만 등록되는 확인 카드 그림">
        <rect x="30" y="16" width="180" height="88" rx="10" fill="none" stroke={SOFT} strokeWidth="2" />
        <rect x="44" y="34" width="14" height="14" rx="4" fill={KEY} />
        <path d="M47.5 41l3 3 5-5.5" stroke="#fff" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        <rect x="68" y="38" width="80" height="6" rx="3" fill={SOFT} />
        <rect x="44" y="58" width="14" height="14" rx="4" fill="none" stroke={SOFT} strokeWidth="2" />
        <rect x="68" y="62" width="62" height="6" rx="3" fill={SOFT} />
        <rect x="132" y="76" width="64" height="18" rx="9" fill={KEY} />
        <path d="M150 85h28" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
      </svg>
    ),
  },
];

export function WelcomeTour({ open, onClose, onStart }: { open: boolean; onClose: () => void; onStart: () => void }) {
  const [index, setIndex] = useState(0);
  const slide = SLIDES[index];
  const isLast = index === SLIDES.length - 1;

  function close() {
    setIndex(0);
    onClose();
  }

  return (
    <Modal open={open} onClose={close} width={520}>
      <div className={styles.tour}>
        <div className={styles.art}>{slide.art}</div>

        <h2 className={styles.title}>{slide.title}</h2>
        <p className={styles.body}>{slide.body}</p>

        <div className={styles.dots} role="tablist" aria-label="소개 슬라이드">
          {SLIDES.map((item, i) => (
            <button
              key={item.title}
              type="button"
              role="tab"
              aria-selected={i === index}
              aria-label={`${i + 1}번째 · ${item.title}`}
              className={i === index ? styles.dotActive : styles.dot}
              onClick={() => setIndex(i)}
            />
          ))}
        </div>

        <div className={styles.actions}>
          <Button variant="ghost" size="sm" onClick={close}>
            건너뛰기
          </Button>
          <div className={styles.nav}>
            {index > 0 && (
              <Button variant="outline" size="sm" onClick={() => setIndex((prev) => prev - 1)}>
                이전
              </Button>
            )}
            {isLast ? (
              <Button size="sm" onClick={onStart}>
                좋아요, 시작할게요
              </Button>
            ) : (
              <Button size="sm" onClick={() => setIndex((prev) => prev + 1)}>
                다음
              </Button>
            )}
          </div>
        </div>
      </div>
    </Modal>
  );
}
