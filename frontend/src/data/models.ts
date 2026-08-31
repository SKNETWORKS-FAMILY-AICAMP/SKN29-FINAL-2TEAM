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
  supportsImageInput: boolean;
}

export const MODEL_OPTIONS: ModelOption[] = [
  { value: 'gpt-5.6-luna', label: 'GPT-5.6 luna', tier: '빠름', supportsImageInput: true },
  { value: 'gpt-5.6-terra', label: 'GPT-5.6 terra', tier: '보통', supportsImageInput: true },
  { value: 'gpt-5.6-sol', label: 'GPT-5.6 sol', tier: '느림·비쌈', supportsImageInput: true },
  { value: 'claude-haiku-4-5', label: 'Claude Haiku 4.5', tier: '빠름', supportsImageInput: true },
  { value: 'claude-sonnet-4-5', label: 'Claude Sonnet 4.5', tier: '보통', supportsImageInput: true },
  { value: 'claude-opus-4-5', label: 'Claude Opus 4.5', tier: '느림·비쌈', supportsImageInput: true },
];

export const DEFAULT_MODEL = 'gpt-5.6-luna';

/**
 * 팀이 Model 탭에서 등록한 커스텀 모델 API 중, 셀렉트에 필요한 것만.
 *
 * **export 하지 않는다.** 밖에서 쓰는 곳이 없고, 편집 화면은 자기 `CustomModel`
 * 을 쓴다(구조가 호환돼 그대로 넘어간다). export 해 두면 두 타입 중 어느 쪽이
 * 진짜인지 헷갈린다(2026-08-13).
 */
interface TeamModel {
  model: string;
  /** 제공자 이름(「Google Gemini」 등). 모델 이름만으로는 어디 것인지 모른다. */
  label: string;
  supports_image_input: boolean;
}

/**
 * 셀렉트 박스가 쓰는 목록 — **기본 제공 + 그 팀이 등록한 것**.
 *
 * 커스텀 모델은 등급(빠름/보통/느림)을 우리가 알 수 없다. 지어내지 않고 제공자
 * 이름을 대신 붙인다 — Model 탭 표에서 속도 칸을 `—` 로 두고 출처에 제공자를
 * 적는 것과 같은 규칙이다(2026-08-12).
 */
export function modelSelectOptions(customs: TeamModel[] = []) {
  return [
    ...MODEL_OPTIONS.map((model) => ({
      value: model.value,
      label: `${model.label} · ${model.tier}${model.supportsImageInput ? ' · 이미지' : ''}`,
    })),
    ...customs.map((custom) => ({
      value: custom.model,
      label: `${custom.model} · ${custom.label}${custom.supports_image_input ? ' · 이미지' : ''}`,
    })),
  ];
}

export function modelSupportsImageInput(model: string, customs: TeamModel[] = []): boolean {
  const builtin = MODEL_OPTIONS.find((item) => item.value === model);
  if (builtin) return builtin.supportsImageInput;
  return customs.find((item) => item.model === model)?.supports_image_input === true;
}
