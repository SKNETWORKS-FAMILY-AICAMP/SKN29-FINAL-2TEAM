import { siAsana, siConfluence, siGoogledrive, siJira, siLinear, siNotion, siTrello } from 'simple-icons';

/**
 * 제품 로고. **`Icon` 과 일부러 나눠 둔다.**
 *
 * `Icon` 은 선으로 그린 글리프라 색을 우리가 정한다(`var(--color-primary)`). 로고는
 * 반대다 — 면으로 채워져 있고 색이 그 제품의 것이다. 한 컴포넌트에 섞으면 둘 중
 * 하나는 반드시 틀린 대접을 받는다.
 *
 * **로고를 손으로 그리지 않는다.** 기억으로 그린 로고는 비율·곡선이 미묘하게 어긋나
 * 「비슷한데 아닌 것」이 되고, 그건 일반 글리프보다 나쁘다 — 남의 상표를 잘못 그린
 * 것이기도 하다. `simple-icons`(CC0-1.0)가 공식 마크를 단일 path 로 관리한다.
 *
 * **못 고르는 항목이라고 브랜드 색을 우리 색으로 바꾸지 않는다.** 그러면 Jira 와
 * Google Drive 가 같은 파랑이 되어, 골라 쓰라고 만든 화면에서 구분이 사라진다.
 * 흐리게 할 때는 색을 갈아끼우는 대신 회색 하나로 눕힌다.
 *
 * ⚠ **여기 없는 제품이 있다.** SharePoint·Workday 는 `simple-icons` 에 없다(상표권
 * 요청으로 빠지는 일이 있다). 그런 자리는 `Icon` 의 일반 글리프로 남긴다 — 없는 것을
 * 지어내는 것보다 낫다.
 */

const BRANDS = {
  'google-drive': siGoogledrive,
  notion: siNotion,
  confluence: siConfluence,
  jira: siJira,
  asana: siAsana,
  linear: siLinear,
  trello: siTrello,
} as const;

export type BrandName = keyof typeof BRANDS;

export interface BrandIconProps {
  name: BrandName;
  size?: number;
  /** 지금 고를 수 없는 항목. 브랜드 색 대신 회색으로 눕힌다. */
  muted?: boolean;
}

export function BrandIcon({ name, size = 22, muted = false }: BrandIconProps) {
  const brand = BRANDS[name];
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={muted ? 'var(--color-placeholder)' : `#${brand.hex}`}
      // 옆에 제품 이름이 늘 글자로 있다. 여기서 또 읽으면 두 번 들린다.
      aria-hidden="true"
      focusable="false"
    >
      <path d={brand.path} />
    </svg>
  );
}
