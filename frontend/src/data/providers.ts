/**
 * OpenAI 호환 주소를 **우리가 들고 있는다.**
 *
 * 사용자가 「호환 엔드포인트 base_url」을 제공자 문서에서 찾아 붙여넣게 두면,
 * 모델 이름을 외워 적게 했던 것과 같은 잘못이다 — 실제로 Google 은 AI Studio
 * 화면에 이 주소를 보여주지 않아 API 문서를 뒤져야 한다(2026-08-12 PM 지적).
 *
 * **주소가 틀리면 「모델 불러오기」가 그 자리에서 실패한다.** 목록을 못 받으면
 * 등록이 안 되므로, 잘못된 프리셋이 조용히 저장되는 일은 없다.
 *
 * **OpenAI 는 프리셋에 없다.** 우리가 이미 GPT 를 제공하므로 여기 등록하면 메인
 * 모델 표에 같은 이름이 두 줄 생기고 어느 쪽으로 도는지 알 수 없어진다. 자기
 * OpenAI 계약을 써야 하면 「직접 입력」으로 붙이되, 이미 제공하는 모델 이름은
 * 서버가 거절한다(2026-08-12 PM 지적).
 */
export interface ProviderPreset {
  id: string;
  label: string;
  /** 빈 문자열이면 사용자가 직접 적는다(사내 vLLM 등). */
  baseUrl: string;
  /** 키를 어디서 받는지. 이것도 안 적어 주면 또 헤맨다. */
  keyHint: string;
}

export const PROVIDER_PRESETS: ProviderPreset[] = [
  {
    id: 'openrouter',
    label: 'OpenRouter',
    baseUrl: 'https://openrouter.ai/api/v1',
    keyHint: 'openrouter.ai > Keys',
  },
  {
    id: 'gemini',
    label: 'Google Gemini',
    baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai/',
    keyHint: 'Google AI Studio > API keys',
  },
  {
    id: 'groq',
    label: 'Groq',
    baseUrl: 'https://api.groq.com/openai/v1',
    keyHint: 'console.groq.com > API Keys',
  },
  {
    id: 'together',
    label: 'Together AI',
    baseUrl: 'https://api.together.xyz/v1',
    keyHint: 'api.together.ai > Settings > API Keys',
  },
  {
    id: 'custom',
    label: '직접 입력 (사내 서버 등)',
    baseUrl: '',
    keyHint: '사내 관리자에게 문의',
  },
];
