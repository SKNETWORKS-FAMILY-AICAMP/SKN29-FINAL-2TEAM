import logoUrl from '../../assets/logo.png';
import markUrl from '../../assets/mark.png';
import styles from './Logo.module.css';

/**
 * 우리 로고. **한 곳에서만 그린다.**
 *
 * 예전에는 화면마다 제각각이었다 — 사이드바·랜딩은 「h」를 넣은 네모(`logoMark`),
 * 로그인·회원가입 계열 다섯 화면은 종이비행기(`send`) 아이콘, 운영자 콘솔은 굵은
 * 글씨. 같은 제품인데 첫 화면과 두 번째 화면의 로고가 달랐다(2026-08-13).
 *
 * `full` 이 기본이다. 이미지 자체가 「halil」 글자를 품은 워드마크라 **옆에 글자를
 * 또 쓰지 않는다** — 그러면 halil 이 두 번 보인다.
 *
 * `mark` 는 글자가 들어갈 자리가 없을 때만이다(사이드바 접힘). 타일을 벗긴 「a」라
 * 밝은 배경 위에서 쓴다 — 어두운 배경에 올리면 남색 글리프가 묻힌다. 어두운 자리가
 * 생기면 타일이 있는 `public/favicon.png` 쪽 모양을 써야 한다.
 */

export interface LogoProps {
  variant?: 'full' | 'mark';
  /** 그려질 높이(px). 폭은 비율대로 따라간다. */
  height?: number;
  className?: string;
}

export function Logo({ variant = 'full', height = 28, className }: LogoProps) {
  const mark = variant === 'mark';
  return (
    <img
      src={mark ? markUrl : logoUrl}
      // 로고 옆에는 대개 제품 이름이 또 없다. 읽어 줄 것이 이것뿐이라 alt 를 채운다.
      alt="halil"
      height={height}
      className={[styles.logo, className].filter(Boolean).join(' ')}
      style={{ height }}
      draggable={false}
    />
  );
}
