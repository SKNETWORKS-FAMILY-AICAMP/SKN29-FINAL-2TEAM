import type { ReactElement } from 'react';
import styles from './Icon.module.css';

export type IconName =
  | 'send'
  | 'eye'
  | 'eye-off'
  | 'chevron-down'
  | 'chevron-right'
  | 'arrow-left'
  | 'arrow-right'
  | 'arrow-up'
  | 'arrow-down'
  | 'calendar'
  | 'folder'
  | 'folder-open'
  | 'file-text'
  | 'file-spreadsheet'
  | 'file-image'
  | 'circle-x'
  | 'circle-help'
  | 'check'
  | 'check-circle'
  | 'loader'
  | 'refresh'
  | 'triangle-alert'
  | 'bell'
  | 'search'
  | 'database'
  | 'app-window'
  | 'chart-network'
  | 'x'
  | 'stop'
  | 'expand'
  | 'copy'
  | 'info'
  | 'sparkles'
  | 'user'
  | 'users'
  | 'link'
  | 'sliders'
  | 'wrench'
  | 'shield-check'
  | 'lock'
  | 'message-square'
  | 'plus'
  | 'menu'
  | 'sidebar'
  | 'more-horizontal'
  | 'edit'
  | 'trash'
  | 'star'
  | 'star-filled';

export interface IconProps {
  name: IconName;
  size?: number;
  color?: string;
  spin?: boolean;
  className?: string;
}

function renderPaths(name: IconName, color: string): ReactElement {
  switch (name) {
    case 'send':
      return (
        <>
          <path d="m22 2-7 20-4-9-9-4Z" />
          <path d="M22 2 11 13" />
        </>
      );
    case 'eye':
      return (
        <>
          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8Z" />
          <circle cx="12" cy="12" r="3" />
        </>
      );
    case 'eye-off':
      return (
        <>
          <path d="M17.94 17.94A10.94 10.94 0 0 1 12 20c-7 0-11-8-11-8a18.5 18.5 0 0 1 5.06-5.94" />
          <path d="M9.9 4.24A10.94 10.94 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
          <path d="M14.12 14.12a3 3 0 1 1-4.24-4.24" />
          <line x1="1" y1="1" x2="23" y2="23" />
        </>
      );
    case 'chevron-down':
      return <polyline points="6 9 12 15 18 9" />;
    case 'chevron-right':
      return <polyline points="9 18 15 12 9 6" />;
    case 'arrow-left':
      return (
        <>
          <line x1="19" y1="12" x2="5" y2="12" />
          <polyline points="12 19 5 12 12 5" />
        </>
      );
    case 'arrow-right':
      return (
        <>
          <line x1="5" y1="12" x2="19" y2="12" />
          <polyline points="12 5 19 12 12 19" />
        </>
      );
    case 'folder':
      return <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />;
    case 'folder-open':
      return (
        <path d="M6 14 3.4 19.6a1 1 0 0 0 .9 1.4H21a1 1 0 0 0 1-1.2l-1.4-7A2 2 0 0 0 18.6 11H6.2a2 2 0 0 0-1.8 1.4L3 17.3V6a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2v2" />
      );
    case 'file-text':
      return (
        <>
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
          <line x1="16" y1="13" x2="8" y2="13" />
          <line x1="16" y1="17" x2="8" y2="17" />
          <line x1="10" y1="9" x2="8" y2="9" />
        </>
      );
    case 'file-spreadsheet':
      return (
        <>
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
          <path d="M8 13h8" />
          <path d="M8 17h8" />
          <path d="M11 13v8" />
        </>
      );
    case 'file-image':
      return (
        <>
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
          <circle cx="10" cy="13" r="1.5" />
          <path d="m20 17-2.5-2.5a1.5 1.5 0 0 0-2.12 0L8 22" />
        </>
      );
    case 'circle-x':
      return (
        <>
          <circle cx="12" cy="12" r="10" />
          <line x1="15" y1="9" x2="9" y2="15" />
          <line x1="9" y1="9" x2="15" y2="15" />
        </>
      );
    case 'circle-help':
      return (
        <>
          <circle cx="12" cy="12" r="10" />
          <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </>
      );
    case 'check':
      return <polyline points="20 6 9 17 4 12" />;
    case 'check-circle':
      return (
        <>
          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
          <polyline points="22 4 12 14.01 9 11.01" />
        </>
      );
    case 'loader':
      return <path d="M21 12a9 9 0 1 1-6.219-8.56" />;
    case 'refresh':
      return (
        <>
          <path d="M3 12a9 9 0 0 1 15.5-6.3L21 8" />
          <path d="M21 3v5h-5" />
          <path d="M21 12a9 9 0 0 1-15.5 6.3L3 16" />
          <path d="M3 21v-5h5" />
        </>
      );
    case 'triangle-alert':
      return (
        <>
          <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
          <line x1="12" y1="9" x2="12" y2="13" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </>
      );
    case 'bell':
      return (
        <>
          <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </>
      );
    case 'search':
      return (
        <>
          <circle cx="11" cy="11" r="8" />
          <line x1="21" y1="21" x2="16.65" y2="16.65" />
        </>
      );
    case 'database':
      return (
        <>
          <ellipse cx="12" cy="5" rx="9" ry="3" />
          <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
          <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
        </>
      );
    case 'app-window':
      return (
        <>
          <rect x="2" y="4" width="20" height="16" rx="2" />
          <line x1="2" y1="9" x2="22" y2="9" />
          <line x1="6" y1="6.5" x2="6.01" y2="6.5" />
          <line x1="9" y1="6.5" x2="9.01" y2="6.5" />
        </>
      );
    case 'chart-network':
      return (
        <>
          <circle cx="12" cy="5" r="2" />
          <circle cx="5" cy="19" r="2" />
          <circle cx="19" cy="19" r="2" />
          <path d="M12 7v5" />
          <path d="M12 12 5 17" />
          <path d="M12 12 19 17" />
        </>
      );
    case 'x':
      return (
        <>
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </>
      );
    case 'more-horizontal':
      return (
        <>
          <circle cx="5" cy="12" r="1.45" fill={color} stroke="none" />
          <circle cx="12" cy="12" r="1.45" fill={color} stroke="none" />
          <circle cx="19" cy="12" r="1.45" fill={color} stroke="none" />
        </>
      );
    case 'edit':
      return (
        <>
          <path d="M12 20h9" />
          <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
        </>
      );
    case 'trash':
      return (
        <>
          <polyline points="3 6 5 6 21 6" />
          <path d="M19 6l-1 14H6L5 6m3 0V4h8v2" />
        </>
      );
    case 'arrow-up':
      return (
        <>
          <line x1="12" y1="19" x2="12" y2="5" />
          <polyline points="5 12 12 5 19 12" />
        </>
      );
    case 'arrow-down':
      return (
        <>
          <line x1="12" y1="5" x2="12" y2="19" />
          <polyline points="19 12 12 19 5 12" />
        </>
      );
    case 'calendar':
      return (
        <>
          <rect x="3" y="5" width="18" height="16" rx="2" />
          <line x1="16" y1="3" x2="16" y2="7" />
          <line x1="8" y1="3" x2="8" y2="7" />
          <line x1="3" y1="11" x2="21" y2="11" />
        </>
      );
    case 'copy':
      return (
        <>
          <rect x="9" y="9" width="13" height="13" rx="2" />
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
        </>
      );
    case 'stop':
      // 아이콘의 바깥 영역은 다른 채팅 액션과 같은 16px로 두고, 실제 정지
      // 도형은 그 안에서 8px 정도만 차지하게 한다. 16px를 전부 채우면 선으로
      // 그린 화살표보다 훨씬 무겁게 보여 버튼이 바뀔 때 시각적으로 튄다.
      return <rect x="4.5" y="4.5" width="15" height="15" rx="1.5" fill={color} stroke="none" />;
    case 'expand':
      return (
        <>
          <path d="M8 3H3v5" />
          <path d="m3 3 6 6" />
          <path d="M16 21h5v-5" />
          <path d="m21 21-6-6" />
        </>
      );
    case 'info':
      return (
        <>
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="16" x2="12" y2="12" />
          <line x1="12" y1="8" x2="12.01" y2="8" />
        </>
      );
    case 'sparkles':
      return (
        <path d="M9.94 15.5A2 2 0 0 0 8.5 14.06l-6.15-1.58a.5.5 0 0 1 0-.96l6.15-1.58A2 2 0 0 0 9.94 8.5l1.58-6.15a.5.5 0 0 1 .96 0l1.58 6.15a2 2 0 0 0 1.44 1.44l6.15 1.58a.5.5 0 0 1 0 .96l-6.15 1.58a2 2 0 0 0-1.44 1.44l-1.58 6.15a.5.5 0 0 1-.96 0z" />
      );
    case 'user':
      return (
        <>
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
          <circle cx="12" cy="7" r="4" />
        </>
      );
    case 'users':
      return (
        <>
          <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
          <circle cx="9" cy="7" r="4" />
          <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
          <path d="M16 3.13a4 4 0 0 1 0 7.75" />
        </>
      );
    case 'link':
      return (
        <>
          <path d="M9 17H7A5 5 0 0 1 7 7h2" />
          <path d="M15 7h2a5 5 0 1 1 0 10h-2" />
          <line x1="8" y1="12" x2="16" y2="12" />
        </>
      );
    case 'wrench':
      // 운영자 콘솔의 커스텀 도구 등록. lucide 의 wrench 를 이 파일의
      // 규칙(stroke 전용 · 24 격자)에 맞춰 옮겼다.
      return (
        <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
      );

    case 'sliders':
      return (
        <>
          <line x1="21" y1="4" x2="14" y2="4" />
          <line x1="10" y1="4" x2="3" y2="4" />
          <line x1="21" y1="12" x2="12" y2="12" />
          <line x1="8" y1="12" x2="3" y2="12" />
          <line x1="21" y1="20" x2="16" y2="20" />
          <line x1="12" y1="20" x2="3" y2="20" />
          <line x1="14" y1="2" x2="14" y2="6" />
          <line x1="8" y1="10" x2="8" y2="14" />
          <line x1="16" y1="18" x2="16" y2="22" />
        </>
      );
    case 'shield-check':
      return (
        <>
          <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
          <path d="m9 12 2 2 4-4" />
        </>
      );
    case 'lock':
      return (
        <>
          <rect x="3" y="11" width="18" height="11" rx="2" />
          <path d="M7 11V7a5 5 0 0 1 10 0v4" />
        </>
      );
    case 'message-square':
      return <path d="M22 17a2 2 0 0 1-2 2H6l-4 4V5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2z" />;
    case 'plus':
      return (
        <>
          <line x1="5" y1="12" x2="19" y2="12" />
          <line x1="12" y1="5" x2="12" y2="19" />
        </>
      );
    case 'menu':
      return (
        <>
          <line x1="4" y1="7" x2="20" y2="7" />
          <line x1="4" y1="12" x2="20" y2="12" />
          <line x1="4" y1="17" x2="20" y2="17" />
        </>
      );
    case 'sidebar':
      return (
        <>
          <rect x="3" y="3" width="18" height="18" rx="3" />
          <line x1="9" y1="3" x2="9" y2="21" />
        </>
      );
    case 'star':
      return (
        <path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z" />
      );
    case 'star-filled':
      // 다른 아이콘과 달리 안을 채운다 — `fill`은 부모 `<svg>`의 `stroke={color}`를
      // 안 타므로(별개 속성), 여기서 직접 같은 `color`를 넣는다. `fill="currentColor"`
      // 로 뒀더니 이 svg엔 CSS `color`를 안 줘서 기본값(검정)으로 채워지던 버그였다.
      return (
        <path
          fill={color}
          d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z"
        />
      );
    default:
      return <circle cx="12" cy="12" r="10" />;
  }
}

export function Icon({ name, size = 20, color = 'currentColor', spin = false, className }: IconProps) {
  const classes = [spin ? styles.spin : '', className ?? ''].filter(Boolean).join(' ');

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={classes || undefined}
      aria-hidden="true"
    >
      {renderPaths(name, color)}
    </svg>
  );
}
