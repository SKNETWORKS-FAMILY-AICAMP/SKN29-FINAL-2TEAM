/**
 * 고를 수 있는 모델 — **한 곳에서만 적는다.**
 *
 * **최신 세대만 둔다.** 예전에는 5.4·5.5 까지 일곱 개를 늘어놓았는데, 사실상
 * 같은 일을 하는 모델이 겹쳐 있어 고르는 사람만 힘들었다. 제공자 둘 ×
 * 빠름·보통·느림 셋이면 필요한 선택은 다 된다(2026-08-12 PM 지적).
 *
 * 예전에는 Model 탭·에이전트 빌더·백엔드가 각각 다른 목록을 들고 있었다.
 * Model 탭에는 계정에 아예 없는 `gpt-5-mini` 가 「쿼터 제한」이라는 지어낸
 * 상태로 올라와 있었다(2026-08-12 확인).
 *
 * 여기 있는 것은 **계정에 있는 것이 아니라 우리 호출 방식으로 실제로 도는 것**
 * 이다 — `responses.create` + tools + reasoning 으로 하나씩 돌려 봤다.
 * `-pro` 계열은 `effort: low` 를 안 받아 400 이 나서 뺐다.
 *
 * ⚠ **`apps/agents/serializers.py` 의 `AGENT_MODELS` 와 같아야 한다.** 여기에만
 * 넣으면 화면에서는 고를 수 있는데 저장이 400 으로 거절된다.
 */
export interface ModelOption {
  value: string;
  /** 목록에 보이는 이름. */
  label: string;
  /**
   * 속도·비용 등급. **문장이 아니라 한 단어다.**
   *
   * `luna`·`sol`·`haiku`·`opus` 는 비개발자에게 아무 뜻이 없어서 등급은 있어야
   * 한다. 다만 「빠릅니다 · 짧은 판단」처럼 문장으로 쓰면 표에 설명을 깔게 된다
   * (2026-08-12 PM 지적).
   */
  tier: '빠름' | '보통' | '느림·비쌈';
}

export const MODEL_OPTIONS: ModelOption[] = [
  { value: 'gpt-5.6-luna', label: 'GPT-5.6 luna', tier: '빠름' },
  { value: 'gpt-5.6-terra', label: 'GPT-5.6 terra', tier: '보통' },
  { value: 'gpt-5.6-sol', label: 'GPT-5.6 sol', tier: '느림·비쌈' },
  { value: 'claude-haiku-4-5', label: 'Claude Haiku 4.5', tier: '빠름' },
  { value: 'claude-sonnet-4-5', label: 'Claude Sonnet 4.5', tier: '보통' },
  { value: 'claude-opus-4-5', label: 'Claude Opus 4.5', tier: '느림·비쌈' },
];

export const DEFAULT_MODEL = 'gpt-5.6-luna';

/** 셀렉트 박스가 쓰는 모양. 용도를 라벨에 붙여 한 줄로 보여준다. */
export const MODEL_SELECT_OPTIONS = MODEL_OPTIONS.map((model) => ({
  value: model.value,
  label: `${model.label} · ${model.tier}`,
}));
