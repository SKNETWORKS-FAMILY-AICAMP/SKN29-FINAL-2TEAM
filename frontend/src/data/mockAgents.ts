/**
 * Builder·Chat이 함께 쓰는 Agent mock.
 *
 * 백엔드 단계 1의 `agent`·`agent_tool` 테이블은 이미 있지만 API(단계 2~)가
 * 아직이라 화면은 이 배열을 본다. API가 붙으면 이 파일만 교체한다 — 필드
 * 이름은 스키마(agent: name·description·instruction·model·is_prebuilt)에
 * 맞춰 두었다.
 */
export type AgentModelId = 'luna' | 'sol' | 'mini';

export interface AgentToolRef {
  id: string;
  name: string;
  desc: string;
  /** 내장 Tool인지, 어느 MCP 서버가 주는 Tool인지 */
  source: string;
}

export interface MockAgent {
  id: string;
  name: string;
  description: string;
  instruction: string;
  model: AgentModelId;
  isPrebuilt: boolean;
  /** 팀 공유 여부. v1은 팀 공유 고정이라 UI 토글은 두지 않는다(멘토링 대기). */
  shared: boolean;
  toolIds: string[];
  owner: string;
  updatedAt: string;
}

export const AGENT_MODELS: { value: AgentModelId; label: string }[] = [
  { value: 'luna', label: 'gpt-5.6 luna — 검색어 생성 · 짧은 판단 (low)' },
  { value: 'sol', label: 'gpt-5.6 sol — 근거 정리 · 긴 추론 (xhigh)' },
  { value: 'mini', label: 'gpt-5-mini — 가벼운 요약 · 분류' },
];

/**
 * 내장 Tool 2종 + MCP Tool. MCP 쪽은 Settings > MCP의 mock과 짝이 맞다.
 *
 * `id`는 화면 편의값이 아니라 **`agent_tool.tool_ref`에 그대로 들어가는 값**이다
 * (DB/migrations/2026-08-11_agent_platform.sql 주석 · 개발지시_1차 단계 2-3).
 * 내장 tool 은 식별자 그대로, MCP tool 은 `mcp:<mcp_tool.mcp_tool_id>` 형식이라
 * mock 도 같은 모양을 쓴다 — API 가 붙을 때 이 파일만 갈아 끼우려면 id 부터
 * 계약이어야 한다. MT001·MT002 는 mcp_tool PK 자리를 채운 가짜 값이다.
 */
export const AVAILABLE_TOOLS: AgentToolRef[] = [
  { id: 'document_search', name: '문서 검색', desc: '팀에 등록된 문서에서 근거를 찾습니다', source: '기본 제공' },
  { id: 'workload_report', name: '부하 리포트 생성', desc: '팀원별 주간 업무 시간을 계산합니다', source: '기본 제공' },
  // 자체 Jira MCP 서버의 jira_create_issues(벌크) — 개발지시_1차 단계 6-3
  { id: 'mcp:MT001', name: 'Jira 이슈 생성', desc: '확인받은 업무를 Jira에 등록합니다', source: 'MCP · Jira' },
  // 같은 서버의 jira_get_issues
  { id: 'mcp:MT002', name: 'Jira 이슈 조회', desc: '기존 이슈와 진행 상황을 읽습니다', source: 'MCP · Jira' },
];

export const MOCK_AGENTS: MockAgent[] = [
  {
    id: 'AG001',
    name: '업무 추출 에이전트',
    description: '기준 문서를 읽고 업무 후보를 뽑아 근거와 함께 정리합니다. Jira 등록까지 이어집니다.',
    instruction: '기준 문서에서 업무를 뽑고, 각 업무마다 원문 근거를 붙인다. 근거가 없는 항목은 지어내지 말고 비운다.',
    model: 'sol',
    isPrebuilt: true,
    shared: true,
    toolIds: ['document_search', 'mcp:MT001'],
    owner: 'halil 제공',
    updatedAt: '단계별 luna/sol',
  },
  {
    id: 'AG002',
    name: '부하 리포트 에이전트',
    description: '팀원별 주간 업무 시간과 여유를 정리해 리포트 카드로 보여줍니다.',
    instruction: 'People DB의 근무 기준과 Jira 잔여 공수를 합쳐 주차별로 정리한다. 근무 조건이 없으면 판정을 보류한다.',
    model: 'luna',
    isPrebuilt: true,
    shared: true,
    toolIds: ['workload_report'],
    owner: 'halil 제공',
    updatedAt: '단계별 luna/sol',
  },
  {
    id: 'AG003',
    name: '회의록 정리 에이전트',
    description: '회의록에서 결정사항과 액션 아이템만 뽑아 담당자별로 묶어 줍니다.',
    instruction:
      '회의록을 읽고 (1) 결정된 것 (2) 해야 할 일 (3) 아직 안 정해진 것 세 가지로 나눠서 정리해줘.\n\n해야 할 일은 담당자별로 묶고, 담당자가 회의록에 없으면 지어내지 말고 "미지정"으로 남겨. 날짜가 언급된 것만 마감일을 적어.',
    model: 'sol',
    isPrebuilt: false,
    shared: true,
    toolIds: ['document_search'],
    owner: '김서준',
    updatedAt: '2026.08.09 수정',
  },
  {
    id: 'AG004',
    name: 'RFP 요구사항 대조',
    description: '제안요청서와 우리 산출물을 대조해 빠진 요구사항을 찾습니다.',
    instruction: 'RFP의 요구사항 목록과 우리 산출물을 항목 단위로 대조하고, 빠진 것만 남긴다.',
    model: 'sol',
    isPrebuilt: false,
    shared: true,
    toolIds: ['document_search'],
    owner: '박도윤',
    updatedAt: '2026.08.07 수정',
  },
];

export function findMockAgent(id: string | undefined): MockAgent | undefined {
  if (!id) return undefined;
  return MOCK_AGENTS.find((agent) => agent.id === id);
}
