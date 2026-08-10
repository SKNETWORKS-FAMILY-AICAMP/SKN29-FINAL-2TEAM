/**
 * Chat mock 시나리오. 실연동(NDJSON 스트림·확인 게이트 API)은 백엔드 단계 3
 * 이후이고, 그 전까지 카드 6종을 눈으로 확인할 수 있게 하는 용도다.
 *
 * 수치는 Figma 07 TO-BE의 데모 스토리와 한 벌로 맞춰져 있다 —
 * 업무 20건 추출 → 전체 선택 → 20건 등록 → 17/20(부분 실패) 또는 20/20(성공).
 * 새 상태를 추가할 때 이 숫자 라인에서 벗어나지 말 것.
 */
export type ChatState =
  | 'empty'
  | 'empty-onboarding'
  | 'doc-pick'
  | 'streaming'
  | 'confirm'
  | 'success'
  | 'partial'
  | 'error';

export const CHAT_STATE_LABELS: { value: ChatState; label: string }[] = [
  { value: 'empty', label: '빈 상태' },
  { value: 'empty-onboarding', label: '빈 상태 (온보딩 미완)' },
  { value: 'doc-pick', label: '문서 선택 되묻기 (STEP 2)' },
  { value: 'streaming', label: '스트리밍 중 (진행 카드)' },
  { value: 'confirm', label: '확인 대기 (근거·확인 카드)' },
  { value: 'success', label: '성공 결과 (STEP 9)' },
  { value: 'partial', label: '부분 실패' },
  { value: 'error', label: '오류' },
];

export const DEMO_UTTERANCE = '이번 프로젝트 문서를 참고해서 업무를 정리하고 Jira 프로젝트에 등록해줘.';

export interface ChatSession {
  id: string;
  title: string;
}

export const MOCK_SESSIONS: ChatSession[] = [
  { id: 'CS001', title: '8/10 업무 정리 · 통합포털' },
  { id: 'CS002', title: '8/9 부하 리포트' },
  { id: 'CS003', title: '8/7 회의록 요약' },
];

export interface StarterAgent {
  name: string;
  desc: string;
  example: string;
}

export const STARTER_AGENTS: StarterAgent[] = [
  {
    name: '업무 추출 에이전트',
    desc: '기준 문서를 읽고 업무 후보를 근거와 함께 정리합니다',
    example: DEMO_UTTERANCE,
  },
  {
    name: '부하 리포트 에이전트',
    desc: '팀원별 주간 업무 시간과 여유를 정리해 보여줍니다',
    example: '이번 주 팀 부하 리포트 만들어줘',
  },
];

/** 진행 카드 단계. 「문서를 읽는 중」은 온디맨드 처리 단계라 준비된 문서만 쓰면 건너뛴다. */
export type StepState = 'done' | 'doing' | 'todo';

export interface ProgressStep {
  state: StepState;
  label: string;
  meta?: string;
}

export const MOCK_STEPS: ProgressStep[] = [
  { state: 'done', label: '기준 문서 확인', meta: '2026 상반기 통합포털 개편 기획서' },
  { state: 'done', label: '문서를 읽는 중', meta: '처음 사용하는 문서 2건 준비' },
  { state: 'done', label: '업무 후보 찾기', meta: '근거 8건' },
  { state: 'doing', label: '역할·기술 근거를 검색하는 중', meta: 'React 접근성 요구사항 산출물' },
  { state: 'todo', label: '공수·일정·제약 검색' },
  { state: 'todo', label: '업무 정리' },
];

export interface Evidence {
  quote: string;
  meta: string;
  source: string;
}

export interface ExtractedTask {
  no: string;
  title: string;
  facts: { label: string; value: string }[];
  missing?: string;
  evidence: Evidence[];
  evidenceCount: number;
  checked: boolean;
}

export const MOCK_TASKS: ExtractedTask[] = [
  {
    no: '1',
    title: '통합포털 SSO 로그인 연동 설계',
    facts: [
      { label: '담당 역할', value: '백엔드 개발자' },
      { label: '공수', value: '32h' },
      { label: '마감', value: '2026.08.28' },
      { label: '우선순위', value: 'HIGH' },
    ],
    evidenceCount: 3,
    checked: true,
    evidence: [
      {
        quote: '포털 로그인은 사내 계정과 고객 계정을 동일한 화면에서 처리하며, 인증 실패 시 3회까지 재시도를 허용한다.',
        meta: 'E1 · DOC-2026-0142 · 역할·기술 · 유사도 87%',
        source: '「SSO 로그인 인증 요구사항」로 찾음',
      },
      {
        quote: '인증 설계는 8월 4주차까지 확정하여 개발 착수 전 검토를 받는다.',
        meta: 'E2 · DOC-2026-0139 · 공수·일정·제약 · 유사도 74%',
        source: '「인증 설계 일정 마감」로 찾음',
      },
    ],
  },
  {
    no: '2',
    title: '권한 등급별 메뉴 노출 규칙 정의',
    facts: [
      { label: '담당 역할', value: '프론트엔드 개발자' },
      { label: '공수', value: '24h' },
      { label: '마감', value: '2026.09.04' },
    ],
    evidenceCount: 2,
    checked: true,
    evidence: [],
  },
  {
    no: '3',
    title: '레거시 게시판 데이터 이관 검증',
    facts: [
      { label: '담당 역할', value: '데이터 엔지니어' },
      { label: '시작', value: '2026.09.07' },
    ],
    missing: '근거 없어 비움 · 공수 · 마감 · 우선순위',
    evidenceCount: 1,
    checked: true,
    evidence: [],
  },
];

export interface DocCandidate {
  name: string;
  meta: string;
  state: '준비됨' | '메타만 — 선택하면 읽습니다';
  selected: boolean;
}

export const MOCK_DOC_CANDIDATES: DocCandidate[] = [
  { name: '2026 상반기 통합포털 개편 기획서.docx', meta: '기획 문서 · 2026.08.03 등록', state: '준비됨', selected: true },
  {
    name: '고객사 제안요청서_RFP_v3.pdf',
    meta: '제안 문서 · 2026.07.28 등록',
    state: '메타만 — 선택하면 읽습니다',
    selected: false,
  },
  { name: '킥오프 회의록_2026-08-03.md', meta: '회의록 · 2026.08.03 등록', state: '준비됨', selected: false },
];

export interface CreatedIssue {
  key: string;
  title: string;
  meta: string;
  evidence: string;
}

export const MOCK_ISSUES: CreatedIssue[] = [
  { key: 'PORTAL-141', title: '통합포털 SSO 로그인 연동 설계', meta: '백엔드 개발자 · 32h', evidence: 'E1, E2, E7' },
  { key: 'PORTAL-142', title: '권한 등급별 메뉴 노출 규칙 정의', meta: '프론트엔드 개발자 · 24h', evidence: 'E3, E9' },
  { key: 'PORTAL-143', title: '레거시 게시판 데이터 이관 검증', meta: '데이터 엔지니어 · 공수 미상', evidence: 'E11' },
];

export const MOCK_FAILURES: { title: string; reason: string }[] = [
  { title: '레거시 게시판 데이터 이관 검증', reason: '필수 필드 누락 — 담당자(assignee) 미지정' },
  { title: '알림센터 발송 이력 정리', reason: 'Jira rate limit (429) — 잠시 후 재시도 가능' },
  { title: '접근성 점검 체크리스트 작성', reason: '필수 필드 누락 — 이슈 유형(issuetype) 미지정' },
];
