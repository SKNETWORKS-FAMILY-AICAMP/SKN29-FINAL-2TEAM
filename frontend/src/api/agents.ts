import { apiRequest } from './client';

/**
 * 에이전트를 만들 때 **고를 수 있는 것들** — 내장·MCP 도구 목록과 팀이 등록한
 * 커스텀 모델.
 *
 * 2026-08-22까지 이 파일에는 레거시 비버전 스키마(`agent`/`agent_tool`)의
 * 에이전트 CRUD와 빌더 테스트 실행도 같이 있었다. 레거시 폐기와 함께 그쪽은
 * 전부 지웠고(에이전트 CRUD는 `api/agentVersions.ts` 하나로 통일), 두 스키마가
 * 공유하던 이 카탈로그 조회만 남았다.
 */

/**
 * 편집 화면이 고를 수 있는 도구.
 *
 * **목록은 서버가 준다** — 화면이 내장 도구를 적어 두면 Registry 가 바뀔 때
 * 화면만 옛 목록으로 남는다(실제로 tool id 계약이 두 번 바뀌었다).
 */
export interface ToolChoice {
  tool_ref: string;
  name: string;
  description: string;
  /** '기본 제공' 또는 'MCP · <서버명>'. */
  source: string;
  /**
   * 도구 선택 화면이 묶어 보여줄 단위(예: "Jira", "문서") — 기본 제공
   * 도구만 갖는다(2026-08-18). MCP 도구는 아직 서버 단위로만 묶는다.
   */
  category?: string;
  /** 기본 제공 Tool의 실행 대상 또는 연결 서비스. */
  provider?: string;
  /** 검색·목록·등록처럼 Tool이 수행하는 행동. */
  capability?: string;
  /** 사용하기 전에 사용자별 외부 서비스 연결이 필요한가. */
  requires_connection?: boolean;
  required_model_capability?: 'image_input' | null;
  /** 승인 게이트를 타는 도구인가. 화면이 「승인 필요」를 표시한다. */
  side_effect: boolean;
  /** 채팅 「+」의 「기본값으로 초기화」가 되돌리는 고정 집합에 드는 도구인가(기본 제공 도구만). */
  is_default?: boolean;
  server_status?: string;
  /** 기본 제공·MCP 도구 모두 갖는다. 「도구 확인」 패널이 입력 폼을 만드는 데 쓴다. */
  input_schema?: {
    properties?: Record<string, { type?: string; description?: string; default?: unknown }>;
    required?: string[];
  };
}

export function listToolChoices(token: string) {
  return apiRequest<ToolChoice[]>('/agents/tools/', { token });
}

/** 팀이 등록한 커스텀 모델 API 한 건. **키는 서버가 돌려주지 않는다.** */
export interface CustomModel {
  conn_id: string;
  label: string;
  base_url: string;
  model: string;
  supports_image_input: boolean;
  connected_at: string | null;
}

export function listCustomModels(token: string) {
  return apiRequest<CustomModel[]>('/agents/custom-models/', { token });
}
