import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { AppShell, Button, Icon, Modal, useToast } from '../../components';
import { PATHS } from '../../routes';
import { loadSessionToken } from '../../utils/session';
import {
  ApiError,
  confirmMessage,
  createSession,
  deleteSession,
  getSession,
  listSessions,
  setSessionToolRefs,
  streamMessage,
} from '../../api/chat';
import type { ChatEvent, ChatMessage, ChatSession, JiraIssueEdit } from '../../api/chat';
import { getAgentVersion, listAgentVersions } from '../../api/agentVersions';
import type { AgentVersionSummary } from '../../api/agentVersions';
import { listToolChoices } from '../../api/agents';
import type { ToolChoice } from '../../api/agents';
import { listMcpServers } from '../../api/mcp';
import type { McpServer } from '../../api/mcp';
import { listMyProjects } from '../../api/projects';
import type { Project } from '../../api/projects';
import { listConnectors } from '../../api/connectors';
import { listMySkills, listTeamSkills } from '../../api/skills';
import { AnswerText } from './AnswerText';
import { WelcomeTour } from './WelcomeTour';
import {
  AskFollowupCard,
  ConfirmCard,
  ErrorCard,
  JiraStatusCard,
  ProgressCard,
  ReasoningTrace,
  ResultCard,
} from './cards/ChatCards';
import { emptyLive, reduce, toCards, traceLine, unwrapToolProgress } from './liveChat';
import type { LiveChat } from './liveChat';
import { ToolPickerModal } from '../../components';
import styles from './ChatPage.module.css';
import cardStyles from './cards/cards.module.css';

/**
 * 대화 한 턴 — 사람의 발화 하나와 그에 딸린 에이전트의 답.
 *
 * `live` 가 null 인 것은 **아직 답이 오기 전**이다(방금 보낸 발화).
 */
interface Turn {
  user: string;
  live: LiveChat | null;
}

/**
 * "/스킬이름"으로 채팅 입력창에서 바로 부를 수 있는 스킬 하나.
 *
 * **팀 스킬이 이긴다** — 서버(`services/agent_runtime/skills/invocation.py`)가
 * 이름이 겹치면 팀 스킬을 먼저 찾으므로("/이름"이 실제로 부르는 것과 같은
 * 우선순위, 자동 호출에서 팀이 개인을 가리는 것과 같은 근거), 자동완성
 * 목록도 같은 우선순위로 합친다 — 안 그러면 자동완성에 뜨는 스킬과 실제로
 * 불려지는 스킬이 다른 모순이 생긴다.
 */
interface SlashSkillOption {
  name: string;
  description: string;
  scope: 'personal' | 'team';
}

/**
 * 저장된 메시지를 턴으로 자른다.
 *
 * **턴 경계는 `user` 메시지다.** agent 메시지는 실행 1회당 하나씩 쌓이는데
 * (`_persist`), 승인 흐름은 실행이 두 번이다 — 발화 → `awaiting_confirmation`,
 * 승인 → `result`. 승인 쪽은 user 메시지를 남기지 않으므로 **한 턴에 agent
 * 메시지가 둘 이상 붙는다.** 하나만 접으면 등록 결과가 복원에서 사라진다.
 */
function toTurns(messages: ChatMessage[]): Turn[] {
  const turns: Turn[] = [];
  let events: ChatEvent[] = [];

  const flush = () => {
    if (turns.length === 0) return;
    turns[turns.length - 1].live = events.length
      ? events.reduce(reduce, { ...emptyLive(), running: false })
      : null;
  };

  for (const message of messages) {
    if (message.role === 'user') {
      flush();
      events = [];
      turns.push({ user: message.content.text ?? '', live: null });
    } else if (message.role === 'agent') {
      // 첫 발화보다 앞선 agent 메시지는 붙일 턴이 없다. 버린다.
      if (turns.length === 0) continue;
      events = [...events, ...(message.content.events ?? [])];
    }
  }
  flush();
  return turns;
}

/**
 * Chat 홈. **서버와만 말한다** — mock 은 없다(개발지시_3차 단계 1).
 *
 * 이벤트를 카드 상태로 접는 규칙은 `liveChat.ts` 에 있다. 핵심은 `stage` 가 두
 * 층에서 온다는 것 — `tool_ref` 가 있으면 그 도구의 진행, 없으면 Loop 회전이다.
 *
 * 화면은 **턴의 배열**을 그린다(6차 단계 1). 발화 하나만 들고 있던 때는 두
 * 번째 발화가 첫 턴을 덮어써서, 이름만 Chat 이고 실제로는 1회용 실행기였다.
 */
/**
 * 대화 목록의 한 줄. 프로젝트에 속한 것과 아닌 것이 **같은 모양**이어야 해서
 * 컴포넌트로 뺐다 — 두 벌로 두면 한쪽만 고쳐진다.
 */
function SessionRow({
  session,
  active,
  onOpen,
  onRemove,
}: {
  session: ChatSession;
  active: boolean;
  onOpen: (id: string) => void;
  /** 바로 지우지 않는다 — 확인 모달을 연다. */
  onRemove: (session: ChatSession) => void;
}) {
  const title = session.title ?? '제목 없는 대화';
  return (
    <span className={styles.sessionRow}>
      <button
        type="button"
        onClick={() => onOpen(session.session_id)}
        className={[styles.session, active ? styles.sessionActive : ''].filter(Boolean).join(' ')}
        // 한 줄로 자르므로 전체는 툴팁으로 남긴다.
        title={title}
      >
        {title}
      </button>
      <button
        type="button"
        className={styles.sessionDelete}
        aria-label={`${title} 삭제`}
        onClick={() => onRemove(session)}
      >
        <Icon name="x" size={13} color="var(--color-placeholder)" />
      </button>
    </span>
  );
}

/** 소개를 봤는가. `sessionStorage` 가 아니라 `localStorage` 다 — 탭을 닫아도 기억한다. */
const TOUR_SEEN_KEY = 'halil.tourSeen';

export default function ChatPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  /**
   * **주소가 정본이다.** 대화를 여는 곳은 전부 `navigate` 를 하고, 실제로 여는 것은
   * 아래 동기화 effect 하나다 — 두 경로가 생기면 목록에서 연 대화와 주소가 어긋난다.
   */
  const { sessionId: routeSessionId } = useParams();
  const token = loadSessionToken();

  const [agents, setAgents] = useState<AgentVersionSummary[]>([]);
  const [agentId, setAgentId] = useState<string | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  /**
   * 지금 쓰고 있는 대화가 속한 프로젝트. 상단바 선택기를 대신한다 —
   * 사이드바에서 어느 프로젝트 밑의 「+」를 눌렀는지, 또는 연 대화가 어디
   * 소속인지가 이 값이다. `null` 은 프로젝트에 속하지 않는 대화다(허용한다).
   */
  const [projId, setProjId] = useState<string | null>(null);
  /**
   * 연결된 자리. 첫 화면이 「시작하기」인지 「무엇을 도와드릴까요?」인지를 가른다.
   *
   * **가입 직후에는 팀이 없어서 Chat 이 통째로 죽어 있다** — 에이전트가 0건이라
   * 무엇을 물어도 답할 주체가 없다. 그 위에 배너 한 줄을 붙이는 것으로는 부족하고
   * (죽은 화면은 그대로 죽은 화면이다), 빈 상태 자리를 아예 다음 행동으로
   * 바꾼다(2026-08-12 PM 지적 · 홈화면 정의 §0 원칙 3).
   *
   * `null` 은 아직 모르는 상태다. 모르는 동안 「연결하세요」를 띄우면 이미 연결한
   * 사람에게 한 번 깜빡인다.
   */
  const [connected, setConnected] = useState<Set<string> | null>(null);
  /** 에이전트를 못 읽었다. 팀이 없어서인 경우가 많아 오류로 떠들지 않는다. */
  const [agentsFailed, setAgentsFailed] = useState(false);
  const { showToast } = useToast();
  /**
   * 도구·MCP 켜고 끄기(2026-08-18). **이 대화에서만** 적용되고 에이전트
   * 원본은 안 건드린다 — 여러 사람이 같은 에이전트로 동시에 대화할 때 한
   * 사람이 도구를 껐다고 남의 대화까지 바뀌면 안 된다(지훈 확인, 처음엔
   * 기본 챗만 대상으로 에이전트 자체를 새 버전 발행하는 방식이었는데,
   * "원본에 영향 없이 세션별로"로 범위를 넓혔다). `chat_session
   * .tool_refs_override`에 저장되고, 실행 시점에
   * `executor.run(tool_refs_override=...)`가 그 자리에서 정의에 얹는다.
   */
  const [toolPickerOpen, setToolPickerOpen] = useState(false);
  /** 이 세션의 커스터마이즈. `null` = 아직 안 건드림(에이전트 원래 도구를 씀). */
  const [sessionToolOverride, setSessionToolOverride] = useState<string[] | null>(null);
  /** 지금 고른 에이전트 자신의 도구 — 커스터마이즈 전 picker 초기값으로 쓴다. */
  const [agentOwnToolRefs, setAgentOwnToolRefs] = useState<string[]>([]);
  const [toolChoices, setToolChoices] = useState<ToolChoice[]>([]);
  const [mcpServers, setMcpServers] = useState<McpServer[]>([]);
  const [togglingTool, setTogglingTool] = useState(false);
  const [tourSeen, setTourSeen] = useState(() => localStorage.getItem(TOUR_SEEN_KEY) === '1');
  const [utterance, setUtterance] = useState('');
  /** "/스킬이름" 자동완성 목록 — 개인+팀을 합쳐 한 번만 불러온다(2026-08-22). */
  const [skillOptions, setSkillOptions] = useState<SlashSkillOption[]>([]);
  /** 자동완성에서 키보드로 고른 항목의 인덱스. */
  const [slashIndex, setSlashIndex] = useState(0);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  /**
   * 승인할 호출의 인덱스(2026-08-21, 병렬실행 Phase 2). 확인 카드에 호출이
   * 여러 개 걸렸을 때만 쓴다 — 카드가 뜨는 순간 **전부 승인**으로 시작하고
   * (예전 동작이 곧 전체 승인이었으므로 기본값을 바꾸지 않는다), 사용자가
   * 개별로 끈다.
   */
  const [approvedActions, setApprovedActions] = useState<number[]>([]);
  /**
   * 확인 카드가 지금 승인 처리 중인지 거절 처리 중인지(2026-08-24 UX
   * 점검). `approve()`/`reject()`가 시작할 때 세팅하고 끝나면 지운다 —
   * `ConfirmCard`가 이 값으로 "등록하는 중…"과 "거절하는 중…"을 가른다
   * (전에는 거절을 눌러도 승인 버튼 쪽에 "등록하는 중…"이 떠서 마치 승인이
   * 진행 중인 것처럼 보였다).
   */
  const [pendingAction, setPendingAction] = useState<'approve' | 'reject' | null>(null);
  /** 스킬 등록 카드에서 「다시 설명하기」를 누른 뒤 표시할 입력 단계. */
  const [skillReexplain, setSkillReexplain] = useState(false);
  const [fatal, setFatal] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  /** React가 busy 상태를 다시 그리기 전의 연속 클릭도 즉시 막는다. */
  const confirmRequestRef = useRef(false);
  /**
   * 방금 떠난 대화의 id. 주소가 `/chat` 으로 따라오면 즉시 비운다.
   * 왜 필요한지는 아래 주소 동기화 effect 에 적었다.
   */
  const leftRef = useRef<string | null>(null);
  const streamRef = useRef<HTMLDivElement | null>(null);
  const lastTurnRef = useRef<HTMLDivElement | null>(null);
  /** 새 질문이나 저장된 대화를 열었을 때 마지막 턴의 시작점을 한 번 맞춘다. */
  const anchorLastTurn = useRef(false);
  /** 사용자가 맨 아래를 선택한 동안에만 새 내용을 따라간다. */
  const stickToBottom = useRef(true);
  const [showLatestButton, setShowLatestButton] = useState(false);
  /** "/스킬이름" 자동완성에서 고른 뒤 입력창에 포커스를 되돌리는 데 쓴다. */
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  /** "/" 자동완성 목록 — 한 번만 불러와 둔다. 팀이 아직 없으면(가입 직후)
      `listTeamSkills`가 실패할 수 있어 조용히 빈 목록으로 넘어간다(다른
      목록 로더들과 같은 관례, 위 `listConnectors`/`listAgentVersions` 참고). */
  useEffect(() => {
    if (!token) return;
    Promise.all([listMySkills(token).catch(() => []), listTeamSkills(token).catch(() => [])]).then(
      ([mine, team]) => {
        // 이름이 겹치면 팀이 이긴다 — 실제 호출(서버)과 같은 우선순위를
        // 자동완성에도 맞춘다(위 `SlashSkillOption` docstring 참고).
        const merged = new Map<string, SlashSkillOption>();
        mine.forEach((skill) =>
          merged.set(skill.name, { name: skill.name, description: skill.description, scope: 'personal' }),
        );
        team.forEach((skill) =>
          merged.set(skill.name, { name: skill.name, description: skill.description, scope: 'team' }),
        );
        setSkillOptions(Array.from(merged.values()).sort((a, b) => a.name.localeCompare(b.name)));
      },
    );
  }, [token]);

  useEffect(() => {
    if (!token) return;
    listConnectors(token)
      .then((rows) => setConnected(new Set(rows.map((row) => row.connector_type))))
      // 못 읽으면 「연결하세요」를 띄우지 않는다. 이미 연결한 사람에게 틀린 안내를
      // 하느니, 원래 화면을 보여주고 조용히 넘어가는 편이 낫다.
      .catch(() => setConnected(null));
  }, [token]);

  useEffect(() => {
    if (!token) return;
    listAgentVersions(token)
      .then((rows) => {
        // 목록 API 는 이제 팀의 DRAFT·DISABLED 도 돌려준다(관리 화면이 그걸
        // 보여줘야 해서) — Chat 은 ACTIVE 와 **내** DRAFT만 후보로 본다.
        // DRAFT는 서버(`list_for_team`)가 이미 본인 것만 내려주므로, 여기 있는
        // DRAFT는 전부 내 것이다(2026-08-18 — 활성화 없이 "개인" 탭 에이전트를
        // 직접 테스트할 방법이 없어서 열었다). 남의 DISABLED는 여전히 제외.
        const usable = rows.filter((row) => row.status === 'ACTIVE' || row.status === 'DRAFT');
        setAgents(usable);
        // **팀의 기본 챗 에이전트(`is_default_chat`)를 고른다.**
        //
        // 팀 생성 시 자동으로 하나씩 생기는 에이전트다(2026-08-15,
        // provision_default_chat_agent). 사용자가 드롭다운에서 직접 다른
        // 에이전트를 고르면 그 값이 우선한다 — `prev`가 있으면 덮지 않는다.
        setAgentId(
          (prev) => prev ?? usable.find((row) => row.is_default_chat)?.agent_id ?? usable[0]?.agent_id ?? null,
        );
      })
      // **팀이 없으면 이 실패는 당연한 것이라 말하지 않는다.** 가입 직후에는
      // 팀이 없어서 이 호출이 반드시 실패하는데, 첫 화면 맨 위에 빨간 오류가
      // 뜨면 뭔가 고장난 것처럼 보인다. 그 상황은 「시작할 준비를 해요」가 이미
      // 설명하고 있다(2026-08-12).
      .catch(() => setAgentsFailed(true));
    listSessions(token).then(setSessions).catch(() => undefined);
    // 프로젝트가 하나도 없어도 화면을 막지 않는다 — 「프로젝트 없음」 묶음에서
    // 그냥 대화할 수 있다.
    listMyProjects(token).then(setProjects).catch(() => undefined);
  }, [token]);

  /** 「+」를 누르면 이 대화의 지금 도구 상태(커스터마이즈 안 했으면 에이전트
   * 원래 도구)를 picker 초기값으로 채운다. */
  async function openToolPicker() {
    if (!token || !agentId) return;
    try {
      const [detail, tools, servers] = await Promise.all([
        getAgentVersion(token, agentId),
        toolChoices.length > 0 ? Promise.resolve(toolChoices) : listToolChoices(token),
        mcpServers.length > 0 ? Promise.resolve(mcpServers) : listMcpServers(token),
      ]);
      setAgentOwnToolRefs(detail.tool_refs);
      setToolChoices(tools);
      setMcpServers(servers);
      setToolPickerOpen(true);
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '도구 목록을 불러오지 못했습니다.', 'error');
    }
  }

  /**
   * 실제 저장 — 세션이 있으면 서버에 반영하고, 없으면(아직 대화를 시작 안
   * 했으면) 로컬에만 담아 둔다. 대화는 원래 첫 메시지를 보낼 때 그 자리에서
   * 만들어진다(사람이 아무 말도 안 하고 나가면 빈 대화가 안 남게 하려는
   * 설계, 다른 화면과 같은 원칙) — 여기서 미리 세션을 만들면 도구만 고르고
   * 말은 안 건 빈 대화가 사이드바에 쌓인다. 골라 둔 값은 `sendText()`가
   * 세션을 만든 직후 같이 저장한다.
   */
  async function applySessionToolRefs(nextList: string[]) {
    if (!token) return;
    if (!sessionId) {
      setSessionToolOverride(nextList);
      return;
    }

    setTogglingTool(true);
    try {
      const updated = await setSessionToolRefs(token, sessionId, nextList);
      setSessionToolOverride(updated.tool_refs_override ?? nextList);
      setSessions((prev) =>
        prev.map((item) => (item.session_id === sessionId ? { ...item, tool_refs_override: updated.tool_refs_override } : item)),
      );
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '도구를 바꾸지 못했습니다.', 'error');
    } finally {
      setTogglingTool(false);
    }
  }

  /**
   * 켜고 끄기 = 이 세션에 override를 저장(`chat_session.tool_refs_override`).
   * 에이전트 원본은 안 건드린다 — 다른 대화·다른 사람에게 영향 없음.
   */
  async function toggleSessionTool(ref: string) {
    if (!token || togglingTool) return;
    const current = sessionToolOverride ?? agentOwnToolRefs;
    const next = current.includes(ref) ? current.filter((item) => item !== ref) : [...current, ref];
    await applySessionToolRefs(next);
  }

  /**
   * 도구 선택 화면의 그룹(카테고리) 마스터 체크박스용(2026-08-18) — 그룹에
   * 속한 도구 여러 개를 **한 번의 저장으로** 켜거나 끈다. `onToggle`을
   * 그룹 크기만큼 연달아 부르면 `sessionToolOverride`가 아직 안 바뀐
   * 상태에서 매번 같은 `current`를 다시 읽어(리렌더가 그 사이에 안 끼기
   * 때문에) 마지막 호출만 반영되고 나머지는 덮어써진다 — 그래서 배열
   * 하나를 통째로 계산해 한 번만 저장한다.
   */
  async function toggleSessionToolGroup(refs: string[], turnOn: boolean) {
    if (!token || togglingTool) return;
    const current = sessionToolOverride ?? agentOwnToolRefs;
    const next = turnOn
      ? [...current, ...refs.filter((ref) => !current.includes(ref))]
      : current.filter((item) => !refs.includes(item));
    await applySessionToolRefs(next);
  }

  /**
   * 다른 화면에서 넘어온 요청. `?proj=PJ001&ask=...` 로 들어온다.
   *
   * 프로젝트에서 기준 문서를 정하고 「업무 뽑기」를 누르면 여기로 온다 —
   * **프로젝트 → 문서 → 업무**의 마지막 걸음이다.
   *
   * **바로 실행한다.** 입력창에 채워만 두면 사람이 한 번 더 눌러야 하는데,
   * 그건 이미 버튼으로 시킨 일을 두 번 시키는 것이다. 그리고 등록까지 가려면
   * 확인 카드가 필요하고 그 카드는 이 대화 안에서만 뜬다 — 추출을 다른 데서
   * 하면 그 결과가 버려지고 여기서 다시 뽑게 된다.
   *
   * 쿼리는 읽자마자 지운다. 안 지우면 새로고침할 때마다 다시 실행된다.
   */
  const [pendingAsk, setPendingAsk] = useState<string | null>(null);
  /** 목록 하단 「새 대화」의 프로젝트 고르기가 열려 있는가. */
  const [newMenuOpen, setNewMenuOpen] = useState(false);
  /**
   * 대화 목록의 에이전트별 묶음 중 펼쳐진 것(2026-08-18 — "같은 에이전트랑
   * 나눈 대화가 많아지니 토글로 접었다 펴고 싶다"). 키는
   * `${proj_id ?? 'loose'}:${agent_id}` — 같은 에이전트라도 프로젝트마다
   * 따로 접고 펼 수 있게 프로젝트 범위를 키에 같이 넣는다.
   */
  const [openAgentGroups, setOpenAgentGroups] = useState<Set<string>>(new Set());
  /**
   * 삭제를 기다리는 대화. **되돌릴 수 없어서 한 번 묻는다** — 서버가
   * chat_message 까지 함께 지우고(`ChatSessionRepository.delete`), 목록의
   * X 는 대화 제목 바로 옆이라 잘못 누르기 쉽다.
   */
  const [pendingDelete, setPendingDelete] = useState<ChatSession | null>(null);

  useEffect(() => {
    const proj = params.get('proj');
    const ask = params.get('ask');
    // 에이전트 목록 화면에서 카드를 눌러 들어온 경우(2026-08-18) — 그
    // 에이전트가 골라진 채로 챗을 연다. 방금 라우트가 바뀌어 이 화면이 막
    // 마운트된 시점이라 sessionId·turns는 이미 초기값이라 startNew()까지는
    // 안 불러도 된다 — agentId만 정해 주면 된다(아래 기본 에이전트 선택
    // effect는 `prev ?? ...`라 이미 값이 있으면 안 덮어쓴다).
    const agent = params.get('agent');
    if (!proj && !ask && !agent) return;
    if (proj) setProjId(proj);
    if (ask) setPendingAsk(ask);
    if (agent) setAgentId(agent);
    setParams({}, { replace: true });
  }, [params, setParams]);

  // 에이전트 목록이 와야 보낼 수 있다(`agentId` 가 정해진 뒤). 목록 조회가
  // 끝나기 전에 눌린 요청을 여기서 흘려보낸다.
  useEffect(() => {
    if (!pendingAsk || !agentId || !token) return;
    setPendingAsk(null);
    void sendText(pendingAsk);
    // sendText 는 매 렌더 새로 만들어진다. 의존성에 넣으면 매번 다시 돈다 —
    // 트리거는 pendingAsk 하나다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingAsk, agentId, token]);

  // 화면을 떠나면 스트림을 끊는다. 서버는 그 run 을 FAILED 로 닫으므로
  // RUNNING 으로 남지 않는다.
  useEffect(() => () => abortRef.current?.abort(), []);

  // 새 질문을 보내거나 저장된 대화를 열면 **마지막 턴의 시작점**을 한 번 보여준다.
  // 답변 맨 아래로 보내면 긴 답을 처음부터 읽기 위해 다시 올려야 한다.
  useEffect(() => {
    const node = streamRef.current;
    const turn = lastTurnRef.current;
    if (!node || !turn || !anchorLastTurn.current) return;
    anchorLastTurn.current = false;
    const nodeTop = node.getBoundingClientRect().top;
    const turnTop = turn.getBoundingClientRect().top;
    node.scrollTop = Math.max(0, node.scrollTop + turnTop - nodeTop - 16);
    stickToBottom.current = false;
    setShowLatestButton(node.scrollHeight - node.scrollTop - node.clientHeight > 24);
  }, [turns.length, sessionId]);

  // 사용자가 직접 맨 아래로 내려간 뒤에만 실시간 출력을 따라간다. 읽기 시작한
  // 답변은 고정하고, 아래에 새 내용이 생기면 버튼으로 선택권을 돌려준다.
  useEffect(() => {
    const node = streamRef.current;
    if (!node) return;
    if (stickToBottom.current) {
      node.scrollTop = node.scrollHeight;
      setShowLatestButton(false);
      return;
    }
    setShowLatestButton(node.scrollHeight - node.scrollTop - node.clientHeight > 24);
  }, [turns]);

  function jumpToLatest() {
    const node = streamRef.current;
    if (!node) return;
    stickToBottom.current = true;
    node.scrollTop = node.scrollHeight;
    setShowLatestButton(false);
  }

  const openSession = useCallback(
    async (id: string) => {
      if (!token) return;
      abortRef.current?.abort();
      setSessionId(id);
      setFatal(null);
      setSkillReexplain(false);
      try {
        const detail = await getSession(token, id);
        setAgentId(detail.agent_id);
        // 대화가 속한 프로젝트를 따라간다 — 사이드바의 어느 묶음에서 열었든
        // 문맥은 대화 자신이 갖고 있는 값이다.
        setProjId(detail.proj_id ?? null);
        setSessionToolOverride(detail.tool_refs_override ?? null);
        // 새로고침 재현 — 저장된 대화를 **전부** 다시 접는다. 서버는 처음부터
        // 모든 턴을 갖고 있었고, 화면이 마지막 답 하나만 쓰고 버리던 것이다.
        const restored = toTurns(detail.messages);
        setTurns(restored);
        anchorLastTurn.current = true;
        stickToBottom.current = false;
        // 체크 상태는 **마지막 턴에만** 의미가 있다. 과거 턴의 확인 카드는
        // 읽기 전용이다.
        const lastLive = restored[restored.length - 1]?.live ?? null;
        setSelected(lastLive ? lastLive.tasks.map((_, index) => index) : []);
        // 새로고침으로 복원된 승인 대기 카드도 전부 승인으로 시작한다
        // (2026-08-21) — 라이브에서 카드가 처음 뜰 때와 같은 기본값이라야
        // 복원 화면과 라이브 화면이 어긋나지 않는다.
        setApprovedActions(
          lastLive?.confirm ? lastLive.confirm.actions.map((_, index) => index) : [],
        );
      } catch (error) {
        setFatal(error instanceof ApiError ? error.message : '대화를 불러오지 못했습니다.');
        // 없는 대화이거나 남의 것이다(서버의 `_require_session` 이 팀을 확인한다).
        // 주소에 그대로 두면 새로고침마다 같은 오류를 다시 만난다.
        setSessionId(null);
        navigate(PATHS.chat, { replace: true });
      }
    },
    [token, navigate],
  );

  /**
   * 주소가 가리키는 대화를 연다. 새로고침·딥링크가 이 경로로 들어온다 —
   * 예전에는 URL 이 `/chat` 뿐이라 새로고침하면 빈 화면으로 떨어졌다(2026-08-12 QA).
   */
  useEffect(() => {
    if (!token) return;
    if (!routeSessionId) {
      // 주소가 따라왔다. 아래 「방금 떠난 대화」 표식을 여기서 푼다 — 그래야
      // 뒤로 가기로 그 대화에 돌아올 수 있다.
      leftRef.current = null;
      return;
    }
    // **한 박자 늦은 주소를 무시한다.** react-router v7 은 `navigate` 를
    // transition 으로 처리해서, 「새 대화」가 상태를 비운 직후의 이 effect 는
    // **아직 옛 주소**를 본다. 그대로 두면 방금 떠난 대화를 다시 열어서,
    // 주소는 `/chat` 인데 화면에는 옛 대화가 남는다(2026-08-15 브라우저 확인).
    if (routeSessionId === leftRef.current) return;
    if (routeSessionId === sessionId) return;
    void openSession(routeSessionId);
  }, [routeSessionId, sessionId, token, openSession]);

  /** 지금 연 대화가 속한 에이전트 토글은 항상 펼쳐 둔다 — 접힌 채로 자기가
   * 보고 있는 대화가 목록에서 숨어 있으면 안 된다. */
  useEffect(() => {
    if (!sessionId) return;
    const current = sessions.find((row) => row.session_id === sessionId);
    if (!current) return;
    const key = `${current.proj_id ?? 'loose'}:${current.agent_id}`;
    setOpenAgentGroups((prev) => (prev.has(key) ? prev : new Set(prev).add(key)));
  }, [sessionId, sessions]);

  /** 목록에서 대화를 연다. **여는 것은 주소가 하고**, 읽어 오는 것은 위 effect 다. */
  function openFromList(id: string) {
    navigate(`${PATHS.chat}/${id}`);
  }

  /** 새 대화를 연다. 어느 프로젝트 밑에서 시작하는지를 함께 받는다. */
  function startNew(nextProjId: string | null) {
    abortRef.current?.abort();
    setSessionId(null);
    // 주소도 함께 비운다. 떠난 id 를 남겨 두는 이유는 위 effect 의 주석에 있다.
    if (routeSessionId) {
      leftRef.current = routeSessionId;
      navigate(PATHS.chat);
    }
    setProjId(nextProjId);
    setTurns([]);
    setSkillReexplain(false);
    setSelected([]);
    // 호출별 승인 상태도 같이 비운다(2026-08-21) — 안 비우면 앞 카드에서
    // 끈 항목이 다음 카드의 다른 호출에 그대로 붙는다.
    setApprovedActions([]);
    setFatal(null);
    // 새 대화는 아직 만든 적 없는 세션이라 커스터마이즈도 없다 — 옛 대화의
    // override를 새 대화에 들고 오면 안 된다.
    setSessionToolOverride(null);
    stickToBottom.current = true;
  }

  async function remove(id: string) {
    if (!token) return;
    setPendingDelete(null);
    try {
      await deleteSession(token, id);
      setSessions((prev) => prev.filter((session) => session.session_id !== id));
      if (id === sessionId) startNew(projId);
    } catch (error) {
      setFatal(error instanceof ApiError ? error.message : '대화를 삭제하지 못했습니다.');
    }
  }

  function send() {
    return sendText(utterance);
  }

  /**
   * 발화 한 건을 보낸다. 입력창에서 오든 다른 화면이 시킨 것이든 **같은 경로**다
   * — 자동 실행이 별도 경로를 타면 세션 생성·문맥 주입이 두 벌이 된다.
   */
  async function sendText(raw: string) {
    if (!token || !raw.trim() || !agentId) return;
    const text = raw.trim();
    setSkillReexplain(false);
    setUtterance('');
    // 덧붙인다. 덮어쓰면 앞 턴이 화면에서 사라진다 — 서버는 지우지 않는데
    // 화면만 잊는 상태가 된다.
    setTurns((prev) => [...prev, { user: text, live: null }]);
    setSelected([]);
    // 호출별 승인 상태도 같이 비운다(2026-08-21) — 안 비우면 앞 카드에서
    // 끈 항목이 다음 카드의 다른 호출에 그대로 붙는다.
    setApprovedActions([]);
    setFatal(null);
    anchorLastTurn.current = true;
    stickToBottom.current = false;
    setShowLatestButton(false);

    let id = sessionId;
    try {
      if (!id) {
        // 사이드바에서 시작한 프로젝트가 이 대화의 문맥이 된다. 프로젝트 없이
        // 시작하면 null 이고, 그때 업무 추출은 "프로젝트를 먼저 고르세요"로
        // 끝난다 — 기준 문서를 모델이 고르게 하지 않기로 한 결정의 연장이다.
        const created = await createSession(token, {
          agent_id: agentId,
          proj_id: projId,
          title: text.slice(0, 60),
        });
        id = created.session_id;
        setSessionId(id);
        setSessions((prev) => [created, ...prev]);
        // 방금 만든 대화도 주소를 갖는다. `replace` 인 이유는 이것이 이동이 아니라
        // **같은 자리의 이름이 정해진 것**이기 때문이다 — 뒤로 가기가 빈 대화로
        // 돌아가면 안 된다.
        navigate(`${PATHS.chat}/${id}`, { replace: true });

        // 대화를 시작하기 전에 "+"로 미리 골라 둔 도구가 있으면(세션이 없어
        // `toggleSessionTool()`이 로컬에만 담아 뒀던 값) 방금 만든 세션에
        // 지금 저장한다 — 못 저장해도 대화 자체는 이미 열렸으니 조용히
        // 넘어간다(도구 없이도 말은 할 수 있어야 한다).
        if (sessionToolOverride !== null) {
          try {
            const updated = await setSessionToolRefs(token, id, sessionToolOverride);
            setSessions((prev) =>
              prev.map((item) => (item.session_id === id ? { ...item, tool_refs_override: updated.tool_refs_override } : item)),
            );
          } catch {
            showToast('고른 도구를 대화에 저장하지 못했습니다.', 'error');
          }
        }
      }
    } catch (error) {
      setFatal(error instanceof ApiError ? error.message : '대화를 열지 못했습니다.');
      return;
    }

    await run(
      (onEvent, signal) => streamMessage(token, id as string, text, onEvent, signal),
      emptyLive(),
      // **`sessionId` 상태를 쓰면 안 된다.** 방금 만든 대화는 이 호출 안에서만
      // `id` 로 존재하고, 상태는 다음 렌더에나 반영된다 — `run` 의 클로저는
      // 아직 null 을 본다. 제목이 그 대화에 안 붙는 이유가 이것이었다.
      id as string,
    );
  }

  async function approve(editedJiraIssues?: JiraIssueEdit[]) {
    if (!token || !sessionId || confirmRequestRef.current) return;
    confirmRequestRef.current = true;
    setPendingAction('approve');
    // **인덱스만 보낸다.** 실행할 인자는 서버가 저장해 둔 것을 쓴다 — 화면이
    // 인자를 보내면 승인 게이트가 아무것도 막지 못한다.
    //
    // 고를 목록이 없는 카드(추출을 안 거친 도구 — 아래 `live.tasks.length === 0`
    // 분기)의 「승인」은 **전부 승인**이라는 뜻이다. 그때도 `selected`(빈 배열)를
    // 그대로 보내면 서버는 「0건만 남기고 지워 달라」로 읽어, 승인했는데 아무것도
    // 등록되지 않는다 — 화면은 성공처럼 보이고 결과는 비는 최악의 조합이다.
    const indices = lastLive && lastLive.tasks.length > 0 ? selected : undefined;
    // 호출이 2건 이상 걸린 카드에서만 호출별 결정을 보낸다(2026-08-21,
    // 병렬실행 Phase 2). 1건짜리는 예전 그대로 — 보낼 것이 없다.
    // 서버는 **모든 호출을 빠짐없이** 덮으라고 요구하므로(빠진 걸 조용히
    // 승인하면 사용자가 안 본 게 실행된다) 전체 길이만큼 만들어 보낸다.
    const actionCount = lastLive?.confirm?.actions.length ?? 0;
    const decisions =
      editedJiraIssues
        ? [
            {
              action_index: 0,
              type: 'edit' as const,
              edited_issues: editedJiraIssues,
            },
          ]
        : actionCount > 1
        ? Array.from({ length: actionCount }, (_, index) => ({
            action_index: index,
            type: (approvedActions.includes(index) ? 'approve' : 'reject') as
              | 'approve'
              | 'reject',
          }))
        : undefined;
    // 빈 상태에서 다시 시작하지 않고 **이 턴을 이어서 접는다.** 재개는 실행이
    // 두 번째일 뿐 같은 턴이고, 새로고침 복원도 두 실행의 이벤트를 이어 붙인다
    // (`toTurns`). 리셋하면 방금 승인한 목록이 화면에서 사라지고, 복원한 화면과
    // 라이브 화면이 서로 달라진다.
    const carried = lastLive ? { ...lastLive, running: true, error: null } : emptyLive();
    try {
      await run(
        (onEvent, signal) =>
          confirmMessage(token, sessionId, indices, onEvent, signal, decisions),
        carried,
        sessionId,
      );
    } finally {
      confirmRequestRef.current = false;
      setPendingAction(null);
    }
  }

  async function reject() {
    if (
      !token ||
      !sessionId ||
      confirmRequestRef.current ||
      (lastLive?.confirm?.actions.length ?? 0) !== 1
    )
      return;
    confirmRequestRef.current = true;
    setPendingAction('reject');
    const reexplainSkill = Boolean(lastLive?.confirm?.skillPreview);
    const carried = lastLive ? { ...lastLive, running: true, error: null } : emptyLive();
    try {
      await run(
        (onEvent, signal) =>
          confirmMessage(token, sessionId, undefined, onEvent, signal, [
            { action_index: 0, type: 'reject' },
          ]),
        carried,
        sessionId,
      );
      if (reexplainSkill) {
        // 설정 > 스킬의 cancelled 단계와 같은 동작이다. 거절 뒤 모델이 만든
        // "등록되지 않았습니다" 문구를 최종 답으로 보여주지 않고, 곧바로
        // 수정 설명을 받는다. interrupt에서 멈춘 도구 로그도 취소 상태로
        // 닫아 스피너가 계속 돌지 않게 한다.
        updateLastLive((prev) =>
          prev
            ? {
                ...prev,
                running: false,
                confirm: null,
                answer: '',
                toolName: null,
                timeline: prev.timeline.map((entry) =>
                  entry.kind === 'tool' && entry.status === 'RUNNING'
                    ? { ...entry, status: 'REJECTED' as const }
                    : entry,
                ),
              }
            : prev,
        );
        setSkillReexplain(true);
        stickToBottom.current = true;
      }
    } finally {
      confirmRequestRef.current = false;
      setPendingAction(null);
    }
  }

  /** 거절한 스킬 초안에 대한 새 설명을 같은 대화의 다음 턴으로 보낸다. */
  async function continueSkillCreation(answer: string) {
    setSkillReexplain(false);
    await sendText(answer);
  }

  /**
   * 스킬 생성 되묻기 카드(2026-08-24)의 답변 제출. `approve()`/`reject()`와
   * 같은 자리(단일 호출 확인 카드)를 쓰지만 결정 타입이 다르다 —
   * `type: 'respond'`는 도구를 실행하지 않고 `answer`를 그 도구 호출의
   * 결과인 것처럼 모델에게 돌려준다(`ConfirmDecision.message` 참고).
   * 이 카드는 항상 호출 1건짜리다(`liveChat.ts`의 `askQuestion` 계산 —
   * 2건 이상이면 애초에 이 카드가 아니라 평소 승인 카드로 떨어진다).
   */
  async function respondToQuestion(answer: string) {
    if (!token || !sessionId || confirmRequestRef.current) return;
    confirmRequestRef.current = true;
    // `confirm: null`을 여기서 명시적으로 지운다 — `approve()`/`reject()`는
    // 승인 카드를 "등록하는 중…"으로 살려 두는 게 맞지만(뭘 승인했는지
    // 보여주는 의미가 있다), 되묻기 카드는 답을 보낸 순간 그 질문은
    // 끝난 것이라 계속 보일 이유가 없다(2026-08-24 QA — 로딩 중에도 이전
    // 질문이 그대로 떠 있었다). 새 질문이 오면 `awaiting_confirmation`
    // 리듀서가 새 `confirm`을 다시 채워 새 카드를 띄운다.
    const carried = lastLive ? { ...lastLive, running: true, error: null, confirm: null } : emptyLive();
    try {
      await run(
        (onEvent, signal) =>
          confirmMessage(token, sessionId, undefined, onEvent, signal, [
            { action_index: 0, type: 'respond', message: answer },
          ]),
        carried,
        sessionId,
      );
    } finally {
      confirmRequestRef.current = false;
    }
  }

  /** 마지막 턴의 `live` 만 갱신한다. 앞 턴들은 그대로 둔다. */
  function updateLastLive(next: (previous: LiveChat | null) => LiveChat | null) {
    setTurns((prev) =>
      prev.map((turn, index) => (index === prev.length - 1 ? { ...turn, live: next(turn.live) } : turn)),
    );
  }

  async function run(
    start: (onEvent: Parameters<typeof streamMessage>[3], signal: AbortSignal) => Promise<void>,
    initial: LiveChat,
    /** 이 스트림이 속한 대화. 방금 만든 대화는 아직 `sessionId` 상태에 없다. */
    streamingId: string,
  ) {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    // 2026-08-24 버그 수정. 서버의 `duration_ms`는 백엔드가 `agent_started`
    // 이벤트를 낸 시점부터 잰다 — 요청 전송·네트워크 왕복·에이전트 시작 전
    // 백엔드 처리(메모리 조회 등)는 빠진다. 그런데 화면의 "생각하는 중"
    // 스피너는 이 함수가 불리는 순간(=`live.running`이 true가 되는 순간)
    // 바로 뜬다 — 사용자가 실제로 체감하는 대기 시간은 여기서부터다. 그래서
    // 서버 값 대신 **클라이언트에서 잰 왕복 시간**을 최종 값으로 쓴다(아래
    // `finally`). `reduce()`가 스트림 도중 담는 서버 값은 그대로 두되(복원된
    // 과거 턴에는 여전히 서버 값이 쓰인다 — 그쪽은 이 함수를 거치지 않는다),
    // 이 실행이 끝나는 순간 클라이언트 값으로 덮어써 화면에 보이는 숫자와
    // 실제 체감 대기 시간이 어긋나지 않게 한다.
    const startedAt = Date.now();
    let state = initial;
    updateLastLive(() => state);
    try {
      await start((event) => {
        state = reduce(state, event);
        updateLastLive(() => ({ ...state }));
        // tool_progress로 감싸져 올 수 있다(2026-08-18) — reduce()와 같은
        // 포장을 여기서도 풀어야 한다(liveChat.ts의 unwrapToolProgress 참고).
        const unwrapped = unwrapToolProgress(event);
        if (unwrapped.type === 'task_extraction_result') {
          setSelected(toCards(unwrapped.result).map((_, index) => index));
        }
        // 확인 카드가 뜨면 호출별 승인 상태를 **전부 승인**으로 시작한다
        // (2026-08-21, 병렬실행 Phase 2) — 예전 동작이 곧 전체 승인이었으므로
        // 기본값을 바꾸지 않는다. 사용자가 여기서 하나씩 끈다.
        if (unwrapped.type === 'awaiting_confirmation') {
          const count =
            'action_requests' in unwrapped ? unwrapped.action_requests.length : 1;
          setApprovedActions(Array.from({ length: count }, (_, index) => index));
        }
        // 첫 답이 끝나면 서버가 이 대화의 이름을 지어 보낸다. 사이드바만
        // 바뀌는 일이라 대화 상태(`reduce`)에는 넣지 않는다.
        if (event.type === 'session_title') {
          const named = event.title;
          setSessions((prev) =>
            prev.map((row) => (row.session_id === streamingId ? { ...row, title: named } : row)),
          );
        }
      }, controller.signal);
    } catch (error) {
      if (controller.signal.aborted) return;
      // **이 발화에 대한 실패는 이 턴 안에 그린다.** `fatal` 은 대화 목록 맨 위에
      // 뜨는 자리라, 방금 보낸 발화가 왜 막혔는지가 **화면 최상단**에 나타났다
      // (2026-08-20 PM 지적 — 가드레일이 막은 문구가 옛 대화 위에 떴다). 스트림
      // 중에 난 실패는 이미 여기 그려지고 있었다(`live.error` → `ErrorCard`).
      updateLastLive((prev) =>
        prev
          ? {
              ...prev,
              error: {
                // **머리말을 안 그린다**(2026-08-24 PM 지적). 이 갈래는 사유
                // 한 줄이 이미 무슨 일이 있었는지 다 말한다 — 그 위에 「보내지
                // 못했습니다」를 얹으면 같은 말을 두 번 한다.
                title: null,
                detail: error instanceof ApiError ? error.message : '요청을 보내지 못했습니다.',
              },
            }
          : prev,
      );
    } finally {
      // 취소(사용자가 다른 발화를 보내 이전 스트림을 abort한 경우)는 실제로
      // 끝까지 안 갔으므로 시간을 재지 않는다 — 재지 않은 실행에 값을 지어
      // 붙이면 "쟀는데 0초"류 문제가 그대로 재현된다.
      const elapsedMs = controller.signal.aborted ? null : Date.now() - startedAt;
      updateLastLive((prev) =>
        prev
          ? {
              ...prev,
              running: false,
              durationMs: elapsedMs ?? prev.durationMs,
            }
          : prev,
      );
    }
  }

  const isEmpty = turns.length === 0;
  /**
   * 사람 정보가 없으면 팀이 없고, 팀이 없으면 Chat 이 할 수 있는 일이 하나도
   * 없다. 상태를 아직 못 읽었으면(`null`) 원래 화면을 보여준다 — 모르는 동안
   * 「연결하세요」를 띄우면 이미 연결한 사람에게 한 번 깜빡인다.
   */
  const needsPeopleDb = connected !== null && !connected.has('PEOPLE_DB');
  /**
   * 소개는 **처음 온 사람에게 한 번만** 뜬다.
   *
   * 연결이 하나도 없을 때만 자동으로 연다 — 이미 쓰고 있는 사람에게 뜨면
   * 방해다. 닫으면 기록해서 다시 열지 않는다(계정을 지웠다 다시 만들면 또
   * 뜨는데, 그건 실제로 처음 오는 것이라 맞다).
   */
  const showTour = needsPeopleDb && !tourSeen;
  const lastLive = turns[turns.length - 1]?.live ?? null;
  const streaming = Boolean(lastLive?.running);
  const waitingConfirm = Boolean(lastLive?.confirm);

  /**
   * 사이드바 계층 — 프로젝트 > 대화.
   *
   * **대화가 있는 프로젝트만 보여 준다.** 사이드바는 돌아갈 대화를 찾는 곳이고,
   * 빈 프로젝트는 돌아갈 것이 없다. 프로젝트 목록은 「프로젝트」 화면이 맡는다.
   *
   * 프로젝트에 속하지 않는 대화는 **머리말 없이** 맨 위에 둔다. 「프로젝트 없음」
   * 이라는 머리말을 달면 그런 이름의 프로젝트처럼 읽힌다.
   *
   * 목록에 없는 프로젝트를 가리키는 대화(지워졌거나 조회가 실패한 경우)도 그쪽에
   * 담긴다 — 안 그러면 사이드바에서 조용히 사라진다.
   */
  const known = new Set(projects.map((item) => item.proj_id));
  const loose = sessions.filter((row) => !row.proj_id || !known.has(row.proj_id));
  const groups = projects
    .map((item) => ({
      proj_id: item.proj_id,
      name: item.name,
      rows: sessions.filter((row) => row.proj_id === item.proj_id),
    }))
    .filter((group) => group.rows.length > 0);
  const currentProject = projects.find((item) => item.proj_id === projId) ?? null;

  function toggleAgentGroup(key: string) {
    setOpenAgentGroups((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  /**
   * 같은 프로젝트(또는 loose) 범위 안에서 대화를 에이전트별로 다시 묶는다.
   * **프로젝트가 상위, 에이전트가 그 안의 토글**(지훈 확인, 2026-08-18) —
   * 처음 요청은 반대(에이전트가 상위)였지만 "프로젝트 안에 에이전트"로
   * 정정됐다. 한 에이전트로 대화를 여러 번 열면 목록이 금방 길어지는데,
   * 접어 두면 "이 에이전트랑 나눈 대화가 뭐가 있었지"를 필요할 때만 편다.
   */
  function renderAgentGroups(rows: ChatSession[], scope: string) {
    const byAgent = new Map<string, { agent_name: string; rows: ChatSession[] }>();
    for (const row of rows) {
      const bucket = byAgent.get(row.agent_id);
      if (bucket) bucket.rows.push(row);
      else byAgent.set(row.agent_id, { agent_name: row.agent_name ?? '이름 없는 에이전트', rows: [row] });
    }
    return Array.from(byAgent.entries()).map(([agentId, agentGroup]) => {
      const key = `${scope}:${agentId}`;
      const open = openAgentGroups.has(key);
      return (
        <div key={key} className={styles.agentGroup}>
          <button
            type="button"
            className={styles.agentToggle}
            onClick={() => toggleAgentGroup(key)}
            aria-expanded={open}
          >
            <Icon name={open ? 'chevron-down' : 'chevron-right'} size={13} color="var(--color-muted)" />
            <span className={styles.agentToggleName} title={agentGroup.agent_name}>
              {agentGroup.agent_name}
            </span>
            <span className={styles.agentToggleCount}>{agentGroup.rows.length}</span>
          </button>
          {open &&
            agentGroup.rows.map((session) => (
              <SessionRow
                key={session.session_id}
                session={session}
                active={session.session_id === sessionId}
                onOpen={openFromList}
                onRemove={setPendingDelete}
              />
            ))}
        </div>
      );
    });
  }

  /** 대화 목록 — AppShell 사이드바의 nav 아래에 붙는다(2026-08-18, "오른쪽에
   * 따로 있지 않고 사이드바에 붙어야 한다"는 요청). 예전엔 이 화면 안에서
   * 폭을 끌어 조절하는 독립 패널이었는데, 사이드바에 합치면서 그 폭
   * 조절(`resizer`)과 좁은 화면 전용 덮개 열기(`listToggle`/`listScrim`)는
   * 뜻을 잃었다 — 사이드바 자체의 접기·모바일 드로어가 그 역할을 대신한다. */
  const sessionsPanel = (
    <>
      <span className={styles.sessionsTitle}>대화 목록</span>

      {/* 프로젝트에 안 속한 대화. 머리말을 달지 않는다 — 「프로젝트 없음」이라고
          쓰면 그런 이름의 프로젝트가 있는 것처럼 읽힌다. 그 안에서 다시
          에이전트별 토글로 묶는다. */}
      {renderAgentGroups(loose, 'loose')}

      {groups.map((group) => (
        <div key={group.proj_id} className={styles.projectGroup}>
          <span className={styles.projectRow}>
            <span className={styles.projectName} title={group.name}>
              <Icon name="folder" size={13} color="var(--color-muted)" />
              <span className={styles.projectNameText}>{group.name}</span>
            </span>
            <button
              type="button"
              className={styles.projectNew}
              aria-label={`${group.name}에서 새 대화`}
              title="새 대화"
              onClick={() => startNew(group.proj_id)}
            >
              <Icon name="plus" size={13} color="var(--color-muted)" />
            </button>
          </span>

          {renderAgentGroups(group.rows, group.proj_id)}
        </div>
      ))}

      {sessions.length === 0 && <p className={styles.groupEmpty}>아직 대화가 없습니다</p>}

      {/* **프로젝트를 고르면서 새 대화를 여는 유일한 입구.**
          빈 프로젝트를 목록에서 걷어내면서 그 프로젝트의 첫 대화를 시작할
          길이 사라졌다. 목록 맨 아래에 둔 이유는 위쪽은 「돌아갈 곳」이고
          여기는 「새로 만드는 곳」이라 섞이지 않게 하려는 것이다. */}
      <div className={styles.listFoot}>
        {newMenuOpen && (
          <div className={styles.newMenu}>
            {/* **범위로 부른다.**
                「프로젝트 없이」는 결함처럼 읽히고, 「일반 대화」는 아무거나
                물어봐도 되는 대화를 약속하는데 이 제품은 그걸 안 한다 —
                실제로 그 대화에서 "일반 대화는 지원하지 않는다"고 답했다.
                프로젝트를 안 고르면 문서 검색이 **팀 문서 전체**를 본다.
                없어지는 게 아니라 넓어지는 것이라 그렇게 적는다. */}
            <button
              type="button"
              className={styles.newMenuItem}
              onClick={() => {
                startNew(null);
                setNewMenuOpen(false);
              }}
            >
              <Icon name="users" size={13} color="var(--color-muted)" />
              <span className={styles.newMenuName}>팀 전체 문서</span>
            </button>
            {projects.length > 0 && <span className={styles.newMenuDivider} />}
            {projects.map((project) => (
              <button
                key={project.proj_id}
                type="button"
                className={styles.newMenuItem}
                title={project.name}
                onClick={() => {
                  startNew(project.proj_id);
                  setNewMenuOpen(false);
                }}
              >
                <Icon name="folder" size={13} color="var(--color-muted)" />
                <span className={styles.newMenuName}>{project.name}</span>
              </button>
            ))}
          </div>
        )}
        <button
          type="button"
          className={styles.newChat}
          onClick={() => setNewMenuOpen((prev) => !prev)}
          aria-expanded={newMenuOpen}
        >
          <Icon name="plus" size={15} />
          새 대화
        </button>
      </div>
    </>
  );

  /**
   * "/스킬이름"을 치는 동안만 연다 — 공백이 들어가면(사용자가 이제 요청
   * 본문을 적는 단계로 넘어간 것) 자동완성을 닫는다. 클로드의 슬래시
   * 커맨드와 같은 UX(2026-08-22, 사용자 요청).
   */
  const slashQuery = /^\/([a-z0-9-]*)$/.exec(utterance)?.[1] ?? null;
  const slashOpen = slashQuery !== null;
  const slashMatches =
    slashQuery !== null
      ? skillOptions.filter((skill) => skill.name.startsWith(slashQuery.toLowerCase()))
      : [];

  function selectSlashSkill(name: string) {
    setUtterance(`/${name} `);
    setSlashIndex(0);
    inputRef.current?.focus();
  }

  return (
    <AppShell variant="flush" sidebarExtra={sessionsPanel}>
      <div className={styles.chat}>
        <div className={styles.main}>
          {/*
            2026-08-15부터 다시 넣었다. 예전엔 "무엇으로 답할지는 말하면
            정해지는 것"이라는 이유로 없앴었지만, 레거시 정문(agent:* 와일드카드
            위임)과 달리 새 버전 스키마 에이전트는 팀이 만든 다른 에이전트로
            자동 위임하지 않는다 — 사용자가 이 선택기에서 직접 고르지 않으면
            기본 챗 말고는 아예 닿을 방법이 없다. 2026-08-22에 레거시 정문을
            완전히 걷어내면서 이 선택기가 "과도기용"이 아니라 유일한 경로가
            됐다 — 없앨 계획이 없다.
          */}
          <header className={styles.agentBar}>
            {agents.length > 0 && (
              <select
                className={styles.agentSelect}
                value={agentId ?? ''}
                aria-label="대화 상대 에이전트"
                onChange={(event) => {
                  setAgentId(event.target.value);
                  // 읽던 대화가 있었으면 **말하고 넘어간다**(2026-08-25).
                  // 셀렉트를 한 번 건드렸을 뿐인데 화면이 빈 대화로 바뀌어,
                  // 읽던 답이 사라진 것인지 지워진 것인지 알 수 없었다.
                  // 지워지지는 않으므로(목록에 남는다) 어디로 갔는지만 알려
                  // 주면 된다.
                  if (turns.length > 0) {
                    showToast('새 대화로 넘어갔습니다. 읽던 대화는 왼쪽 목록에 있습니다.', 'info');
                  }
                  // 에이전트를 바꾸는 순간 새 대화로 넘어간다 — 대화 하나는
                  // 만들어질 때 고른 에이전트에 묶여서, 중간에 못 바꾼다.
                  startNew(projId);
                }}
              >
                {agents.map((agent) => (
                  <option key={agent.agent_id} value={agent.agent_id}>
                    {agent.name}
                    {agent.is_default_chat ? ' (기본)' : ''}
                    {agent.status === 'DRAFT' ? ' (개인·미공유)' : ''}
                  </option>
                ))}
              </select>
            )}
            {/* 이 대화가 무엇을 근거로 답하는가. 「프로젝트 없음」처럼 빠진
                상태로 쓰지 않고 **범위**로 쓴다 — 프로젝트를 안 고르면 문서
                검색이 팀 문서 전체를 본다. */}
            <span className={styles.chatWhere}>
              {currentProject ? (
                <>
                  <Icon name="folder" size={14} color="var(--color-muted)" />
                  {currentProject.name}
                </>
              ) : (
                <>
                  <Icon name="users" size={14} color="var(--color-muted)" />
                  팀 전체 문서
                </>
              )}
            </span>
            <Button size="sm" variant="outline" onClick={() => startNew(projId)}>
              새 대화
            </Button>
          </header>

          <div
            className={styles.stream}
            ref={streamRef}
            onScroll={(event) => {
              const node = event.currentTarget;
              // 스트리밍이 만드는 미세한 높이 오차만 무시한다. 사용자가 조금만
              // 위로 이동해도 최신 위치로 돌아가는 컨트롤을 보여 준다.
              const nearBottom = node.scrollHeight - node.scrollTop - node.clientHeight <= 24;
              stickToBottom.current = nearBottom;
              setShowLatestButton(!nearBottom);
            }}
          >
            {fatal && <p className={styles.fatal}>{fatal}</p>}

            <WelcomeTour
              open={showTour}
              onClose={() => {
                localStorage.setItem(TOUR_SEEN_KEY, '1');
                setTourSeen(true);
              }}
              onStart={() => {
                localStorage.setItem(TOUR_SEEN_KEY, '1');
                setTourSeen(true);
                navigate(PATHS.settingsConnectors);
              }}
            />

            {isEmpty && needsPeopleDb && (
              <div className={styles.empty}>
                <div className={styles.emptyIntro}>
                  <h2>시작할 준비를 해요</h2>
                  <p>데이터를 가져올 자리를 연결하면 그때부터 대화로 일할 수 있습니다.</p>
                </div>

                {/* **①과 ②③을 갈라 놓는다.** 셋을 한 줄로 세우면 「셋 다 해야
                    한다」로 읽히는데, 필수는 사람 정보 하나뿐이다 — 그것만 있어도
                    팀원 조회·부하 리포트·부재 조회는 돈다. */}
                <div className={styles.setup}>
                  <span className={styles.setupLabel}>먼저 이것부터</span>
                  <div className={styles.setupStep}>
                    <div>
                      <strong>인사 시스템</strong>
                      <p>연결하면 팀이 만들어집니다. 이게 있어야 나머지가 붙습니다.</p>
                    </div>
                    <Button size="sm" onClick={() => navigate(PATHS.settingsConnectors)}>
                      연결하기
                    </Button>
                  </div>

                  <span className={styles.setupLabel}>그다음, 필요한 만큼</span>
                  <div className={styles.setupStepMuted}>
                    <strong>문서 저장소</strong>
                    <p>문서에서 업무를 뽑고 근거를 찾습니다.</p>
                  </div>
                  <div className={styles.setupStepMuted}>
                    <strong>업무 기록소</strong>
                    <p>진행 상황과 팀 부하를 봅니다.</p>
                  </div>
                </div>
              </div>
            )}

            {isEmpty && !needsPeopleDb && (
              <div className={styles.empty}>
                <div className={styles.emptyIntro}>
                  <h2>무엇을 도와드릴까요?</h2>
                  <p>필요한 작업을 입력하세요.</p>
                  {/* 무엇을 근거로 답하는지가 답의 전제라 먼저 말한다. */}
                  <p className={styles.projectContext}>
                    {currentProject ? (
                      <>
                        <Icon name="folder" size={14} color="var(--color-muted)" />
                        <span>
                          <strong>{currentProject.name}</strong> 프로젝트의 문서를 근거로 답합니다.
                        </span>
                      </>
                    ) : (
                      <>
                        <Icon name="users" size={14} color="var(--color-muted)" />
                        <span>
                          <strong>팀 전체 문서</strong>를 근거로 답합니다. 업무 추출처럼 기준 문서가
                          기준 문서가 필요한 작업은 프로젝트를 선택한 뒤 시작하세요.
                        </span>
                      </>
                    )}
                  </p>
                </div>

                {/* 팀은 있는데 시드가 안 된 경우다. 팀 자체가 없는 경우는 위쪽
                    「시작할 준비를 해요」가 맡으므로 여기까지 오지 않는다. */}
                {agents.length === 0 && !agentsFailed && (
                  <p className={styles.onboardingBanner}>
                    <Icon name="info" size={15} color="var(--color-info)" />
                    이 팀에 쓸 수 있는 에이전트가 없습니다. 관리자가 백필 스크립트를
                    돌리거나 에이전트를 활성화해야 합니다.
                    <button type="button" onClick={() => navigate(PATHS.agentVersions)}>
                      에이전트로 이동 →
                    </button>
                  </p>
                )}
              </div>
            )}

            {turns.map((turn, turnIndex) => {
              const live = turn.live;
              // 승인·체크는 **마지막 턴에만** 열려 있다. 지나간 턴의 확인 카드를
              // 다시 누를 수 있으면, 그 사이에 무엇이 바뀌었는지 모르는 채로
              // 남의 Jira 에 이슈가 만들어진다.
              const isLast = turnIndex === turns.length - 1;
              // 접고 나서도 confirm 이 남아 있는데 마지막 턴이 아니면, 승인하지
              // 않고 다음 발화로 넘어간 것이다(`result` 가 confirm 을 닫는다).
              const abandoned = Boolean(live?.confirm) && !isLast;

              return (
                <div key={turnIndex} className={styles.turn} ref={isLast ? lastTurnRef : undefined}>
                  <div className={styles.userMessage}>
                    <span>{turn.user}</span>
                  </div>

                  {live && (
                    <>
                      {(() => {
                        // `toolName`을 조건에 넣는다(2026-08-25). 전에는 도는 동안만
                        // 참이고 끝나면 거짓이 되는 경로가 있었다 — 단계를 따로 안
                        // 쌓는 도구(`프로젝트 조회` 등)는 `steps`가 비어서, 실행 중엔
                        // 「프로젝트 조회 실행 중」이 보이다가 **끝나는 순간 카드가
                        // 통째로 사라지고** 접힌 「생각 과정」 한 줄만 남았다. 무슨
                        // 도구를 썼는지가 답변 옆에서 사라지는 셈이라, 끝난 뒤에도
                        // 「… 완료」로 남긴다.
                        const showProgress =
                          live.running ||
                          live.steps.length > 0 ||
                          live.subagents.length > 0 ||
                          live.toolName !== null;
                        const showReasoning = live.timeline.length > 0;
                        if (!showProgress && !showReasoning) return null;
                        const toolCount = live.timeline.filter((entry) => entry.kind === 'tool').length;
                        const durationLabel =
                          !live.running && live.durationMs != null
                            ? ` · ${(live.durationMs / 1000).toFixed(1)}초`
                            : '';
                        const countLabel = !live.running && toolCount > 0 ? ` · 도구 ${toolCount}회` : '';
                        // **진행 카드와 생각 과정을 한 카드로 묶는다**(2026-08-19) —
                        // 흰 박스 두 개로 따로 떠서 "왜 나뉘어 있냐"는 지적으로
                        // 합쳤다. 바깥 `<section className={cardStyles.card}>`를
                        // 여기서 한 번만 두르고, 안쪽 둘은 `bare`로 테두리를 안
                        // 그린다(같은 `cards.module.css`를 써야 카드 하나로 보인다).
                        // 어느 한쪽만 있을 수도 있다(예: 도구 없이 생각만 한 턴) —
                        // 그때만 있는 쪽만 그리고 경계선은 안 넣는다.
                        return (
                          <section className={cardStyles.card}>
                            {showProgress && (
                              <ProgressCard
                                bare
                                steps={live.steps}
                                queries={live.queries}
                                sources={live.sources}
                                subagents={live.subagents}
                                evidenceCount={live.evidenceCount}
                                running={live.running}
                                title={(() => {
                                  // 위임이 걸려 있으면(2026-08-18) 그동안 화면이 멈춘 것처럼
                                  // 보이던 문제를 고치려고 이 상태를 최우선으로 보여준다 —
                                  // 루트가 도구를 직접 호출 중이 아니라 다른 에이전트가
                                  // 일하는 중이라는 게 지금 사실과 더 가깝다.
                                  const active = live.subagents.find((run) => run.status === 'RUNNING');
                                  if (active) return `${active.name ?? active.alias ?? '다른 에이전트'}에게 위임 중`;
                                  if (live.running) return live.toolName ? `${live.toolName} 실행 중` : '생각하는 중';
                                  // 실패한 호출에 「완료」라고 쓰지 않는다
                                  // (2026-08-25). 사유는 답변 본문이 말하고,
                                  // 여기서는 성공이 아니었다는 사실만 밝힌다.
                                  if (live.toolFailed && live.toolName) {
                                    return `${live.toolName} 실패${countLabel}${durationLabel}`;
                                  }
                                  return live.toolName
                                    ? `${live.toolName} 완료${countLabel}${durationLabel}`
                                    : `정리 완료${countLabel}${durationLabel}`;
                                })()}
                                failed={live.toolFailed}
                              />
                            )}

                            {showProgress && showReasoning && <div className={cardStyles.cardDivider} />}

                            {/* **접은 채로 시작한다**(2026-08-18, PM: 「뭘 생각하는지만
                                알면 된다」). OpenAI가 보내는 reasoning 요약은
                                system_prompt의 언어 지시를 따르지 않아(2026-08-18
                                재확인) 한국어로 만들 수단이 없다 — 도는 동안 자동으로
                                펼치면 기다리는 내내 모델의 영어 독백이 화면 한가운데
                                있게 된다. 지금 무엇을 하는지는 위 진행 카드가 한국어로
                                말한다 — 「업무 등록 실행 중」·「생각하는 중」.
                                `defaultOpen`을 `live.running`이 아니라 고정 `false`로
                                둔 것만 그 커밋과 다르다 — 펼치면(2026-08-18 타임라인
                                기능) 그 뒤로는 실시간 로그처럼 흐르고 도구 반환값도
                                클릭해서 볼 수 있으니, 자동으로 펼치지만 않으면 두
                                요구가 부딪히지 않는다. */}
                            {showReasoning && (
                              <ReasoningTrace
                                bare
                                entries={live.timeline}
                                defaultOpen={false}
                                running={live.running}
                                // 실행 중에는 진행 카드의 `검색 결과` 한 곳에만
                                // 보여 주고, 완료 뒤에는 작업 과정 상세로 옮긴다.
                                queries={live.running ? [] : live.queries}
                                sources={live.running ? [] : live.sources}
                              />
                            )}
                          </section>
                        );
                      })()}

                      {live.jira && (
                        <JiraStatusCard
                          projectName={currentProject?.name}
                          projectKey={live.jira.projectKey}
                          counts={live.jira.counts}
                          issues={live.jira.issues}
                        />
                      )}

                      {live.tasks.length > 0 && (
                        <ConfirmCard
                          tasks={live.tasks}
                          warnings={live.extraction?.warnings}
                          trace={live.extraction ? traceLine(live.extraction) : undefined}
                          selected={isLast ? selected : live.tasks.map((_, index) => index)}
                          onSelectedChange={isLast ? setSelected : () => undefined}
                          onApprove={isLast && live.confirm ? approve : undefined}
                          onReject={isLast && live.confirm ? reject : undefined}
                          busy={live.running}
                          pendingAction={isLast ? pendingAction : null}
                          onAbort={isLast && live.running ? () => abortRef.current?.abort() : undefined}
                        />
                      )}

                      {/* 2026-08-24, skill-creator 되묻기 — `askQuestion`이 있으면
                          이 카드가 승인/거절 카드를 대신한다. 아래 일반
                          확인 카드 조건에 `askQuestion == null`을 더해
                          두 카드가 동시에 뜨는 일이 없게 한다. */}
                      {live.confirm && live.confirm.askQuestion != null && (
                        <AskFollowupCard
                          question={live.confirm.askQuestion}
                          onSubmit={isLast ? respondToQuestion : undefined}
                          busy={live.running}
                        />
                      )}

                      {isLast && skillReexplain && (
                        <AskFollowupCard
                          title="스킬을 다시 설명해 주세요"
                          question="어떤 내용을 바꾸고 싶은지 알려주세요."
                          onSubmit={continueSkillCreation}
                          busy={live.running}
                        />
                      )}

                      {live.confirm && live.confirm.askQuestion == null && live.tasks.length === 0 && (
                        <ConfirmCard
                          tasks={[]}
                          // 「무엇을 · 몇 건」. `warnings` 로 넘기던 것을 옮겼다
                          // — 그 prop 은 2026-08-11 에 배너를 걷으면서 **그려지지
                          // 않게 됐는데** 넘기는 쪽만 남아, 이 카드는 무엇을
                          // 승인하는지 한 마디도 안 하고 있었다(2026-08-18 QA).
                          // 건수는 있을 때만 붙인다 — 목록형 인자가 아니면
                          // `count` 가 0 이라 「대상 0건」이 거짓이 된다.
                          subject={
                            live.confirm.count > 0
                              ? `${live.confirm.toolName} · 대상 ${live.confirm.count}건`
                              : live.confirm.toolName
                          }
                          // 2026-08-24 — `skill_register` 확인 카드는 도구
                          // 이름 대신 등록할 스킬의 실제 이름·설명을 보여준다
                          // (`ConfirmCard`가 있으면 `subject` 줄 대신 이걸 그린다).
                          skillPreview={live.confirm.skillPreview}
                          jiraPreview={live.confirm.jiraPreview}
                          jiraProjectName={currentProject?.name}
                          jiraAssigneeMode={live.confirm.jiraAssigneeMode}
                          selected={isLast ? selected : []}
                          onSelectedChange={isLast ? setSelected : () => undefined}
                          onApprove={isLast ? approve : undefined}
                          onReject={isLast ? reject : undefined}
                          busy={live.running}
                          // 2026-08-21, 병렬실행 Phase 2 — 호출이 여러 개면
                          // 카드가 전부 보여주고 하나씩 켜고 끌 수 있게 한다.
                          actions={live.confirm.actions}
                          approvedActions={
                            isLast
                              ? approvedActions
                              : live.confirm.actions.map((_, index) => index)
                          }
                          onApprovedActionsChange={isLast ? setApprovedActions : undefined}
                          pendingAction={isLast ? pendingAction : null}
                          onAbort={isLast && live.running ? () => abortRef.current?.abort() : undefined}
                        />
                      )}

                      {abandoned && (
                        <p className={styles.warnLine}>
                          <Icon name="triangle-alert" size={14} color="var(--color-warning-text)" />
                          승인하지 않고 넘어갔습니다. 이 요청은 실행되지 않았습니다.
                        </p>
                      )}

                      {(live.created.length > 0 || live.failures.length > 0) && (
                        <ResultCard created={live.created} failures={live.failures} />
                      )}

                      {live.answer && (
                        <div className={styles.agentMessage}>
                          <AnswerText text={live.answer} />
                        </div>
                      )}

                      {live.stoppedReason && (
                        <p className={styles.warnLine}>
                          <Icon name="triangle-alert" size={14} color="var(--color-warning-text)" />
                          끝까지 마치지 못했습니다 ({live.stoppedReason}). 위 결과는 여기까지 확인한 것입니다.
                        </p>
                      )}

                      {/* 사람이 「중단」을 누른 경우(2026-08-25). 전에는 스피너만
                          조용히 꺼져서, 멈춘 것인지 답이 안 오는 것인지 화면만
                          봐서는 구분할 수 없었다. 위 `stoppedReason`과 문구를
                          나누는 이유는 다음 행동이 다르기 때문이다 — 그쪽은
                          "여기까지가 확인된 것"이고, 이쪽은 다시 물으면 된다. */}
                      {live.abortedByUser && (
                        <p className={styles.warnLine}>
                          <Icon name="triangle-alert" size={14} color="var(--color-warning-text)" />
                          중단했습니다. 위까지만 진행됐고, 다시 물어보시면 처음부터 다시 합니다.
                        </p>
                      )}

                      {live.error && (
                        <ErrorCard
                          detail={live.error.detail}
                          title={live.error.title}
                          answered={Boolean(live.answer)}
                          errorCode={live.error.errorCode}
                          onOpenSettings={() => navigate(PATHS.settingsConnectors)}
                        />
                      )}

                      {/*
                        2026-08-19 §12순위. `live.running`이 아직 true면(스트림
                        도중 새로고침 복원 등) 값이 있어도 안 보여준다 — 실행이
                        끝나기 전 시간은 "총 걸린 시간"이 아니라 지금까지
                        흐른 시간이라 오해를 준다. 재개(resume) 스트림은
                        서버가 `duration_ms`를 아예 안 붙이므로(의도된 한계)
                        `durationMs`가 `null`이라 자연히 표시가 생략된다.
                      */}
                      {!live.running &&
                        live.durationMs != null &&
                        live.steps.length === 0 &&
                        live.subagents.length === 0 &&
                        live.toolName === null && (
                        <p className={styles.durationLine}>
                          {(live.durationMs / 1000).toFixed(1)}초 만에 답변
                        </p>
                      )}
                    </>
                  )}
                </div>
              );
            })}
          </div>

          <div className={styles.inputBar}>
            <button
              type="button"
              className={
                showLatestButton
                  ? `${styles.latestButton} ${styles.latestButtonVisible}`
                  : styles.latestButton
              }
              onClick={jumpToLatest}
              aria-label="최신 답변으로 이동"
              aria-hidden={!showLatestButton}
              tabIndex={showLatestButton ? 0 : -1}
              title={showLatestButton ? '최신 답변으로 이동' : undefined}
            >
              {streaming ? (
                <span className={styles.latestPending} aria-hidden="true">
                  <i />
                  <i />
                  <i />
                </span>
              ) : (
                <Icon name="chevron-down" size={17} color="var(--color-primary)" />
              )}
            </button>
            {/* "/스킬이름"을 치는 동안 뜬다(2026-08-22) — 클로드의 슬래시
                커맨드와 같은 방식. 화살표로 고르고 Enter/Tab으로 넣는다,
                Esc로 지운다. 채팅을 보낼 Enter와 겹치지 않게 이 메뉴가 열려
                있을 때는 아래 입력창의 onKeyDown이 먼저 가로챈다. */}
            {slashOpen && (
              <div className={styles.slashMenu} role="listbox">
                {skillOptions.length === 0 ? (
                  <p className={styles.slashEmpty}>등록된 스킬이 없습니다</p>
                ) : slashMatches.length === 0 ? (
                  <p className={styles.slashEmpty}>일치하는 스킬이 없습니다</p>
                ) : (
                  slashMatches.map((skill, index) => (
                    <button
                      key={`${skill.scope}-${skill.name}`}
                      type="button"
                      role="option"
                      aria-selected={index === slashIndex}
                      className={
                        index === slashIndex
                          ? `${styles.slashItem} ${styles.slashItemActive}`
                          : styles.slashItem
                      }
                      onMouseEnter={() => setSlashIndex(index)}
                      onClick={() => selectSlashSkill(skill.name)}
                    >
                      <span className={styles.slashName}>/{skill.name}</span>
                      <span className={styles.slashScope}>{skill.scope === 'team' ? '팀' : '개인'}</span>
                      <span className={styles.slashDesc}>{skill.description}</span>
                    </button>
                  ))
                )}
              </div>
            )}
            {/* 에이전트만 골라져 있으면 뜬다(2026-08-18) — 대화를 시작하기
                전에도 도구를 미리 골라 둘 수 있다. 세션이 아직 없으면
                `toggleSessionTool()`이 로컬에만 담아 두고, 첫 메시지로
                세션이 만들어질 때 `sendText()`가 같이 저장한다. */}
            {agentId && (
              <button
                type="button"
                className={styles.attachTools}
                onClick={openToolPicker}
                aria-label="이 대화에 사용할 도구 선택"
                title="이 대화에 사용할 도구 선택"
              >
                <Icon name="plus" size={16} color="var(--color-body)" />
              </button>
            )}
            {/* 승인 대기 중에도 **말할 수 있다**(6차 단계 1-5 · 확정 ③).
                체크박스로만 소통하게 두면 "3번은 빼고 다시 뽑아줘"를 할 방법이
                없어 폼 위저드가 된다. 전용 「다시 정리해줘」 버튼을 만들지 않고
                대화로 푸는 것이 이 제품의 성격에도 맞다.
                서버는 pending 을 무시하고 새 턴을 시작한다(실측 — 결과 블록). */}
            <textarea
              ref={inputRef}
              className={styles.input}
              rows={1}
              value={utterance}
              onChange={(event) => {
                setUtterance(event.target.value);
                setSlashIndex(0);
              }}
              onKeyDown={(event) => {
                if (slashOpen && slashMatches.length > 0) {
                  if (event.key === 'ArrowDown') {
                    event.preventDefault();
                    setSlashIndex((prev) => (prev + 1) % slashMatches.length);
                    return;
                  }
                  if (event.key === 'ArrowUp') {
                    event.preventDefault();
                    setSlashIndex((prev) => (prev - 1 + slashMatches.length) % slashMatches.length);
                    return;
                  }
                  if (
                    ((event.key === 'Enter' && !event.shiftKey) || event.key === 'Tab') &&
                    !event.nativeEvent.isComposing
                  ) {
                    event.preventDefault();
                    selectSlashSkill(slashMatches[slashIndex]?.name ?? slashMatches[0].name);
                    return;
                  }
                }
                if (slashOpen && event.key === 'Escape') {
                  event.preventDefault();
                  setUtterance('');
                  return;
                }
                if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                  event.preventDefault();
                  if (!streaming) send();
                }
              }}
              disabled={!agentId}
              placeholder={
                waitingConfirm
                  ? '위에서 선택해 승인하거나, 고쳐서 다시 요청해 보세요'
                  : '무엇을 도와드릴까요? ("/"로 등록된 스킬을 바로 불러올 수 있어요)'
              }
            />
            {streaming ? (
              <Button
                variant="outline"
                iconLeft={<Icon name="x" size={14} />}
                // 표시를 `run()`의 `finally`가 아니라 **여기서** 남긴다
                // (2026-08-25). 그 자리는 새 발화가 이전 스트림을 abort 하는
                // 경우도 함께 지나가는데, 그때 마지막 턴은 이미 방금 만든 새
                // 턴이라 갓 시작한 발화에 「중단했습니다」가 붙는다. 버튼은
                // 자기가 사람 손인 것을 알고, 지금 도는 그 턴을 가리킨다.
                onClick={() => {
                  abortRef.current?.abort();
                  updateLastLive((prev) =>
                    prev ? { ...prev, running: false, abortedByUser: true } : prev,
                  );
                }}
              >
                중단
              </Button>
            ) : (
              <Button aria-label="보내기" onClick={send} disabled={!utterance.trim()}>
                <Icon name="arrow-right" size={16} />
              </Button>
            )}
          </div>
        </div>

      </div>

      {/* 되돌릴 수 없는 삭제라 한 번 묻는다. 서버가 대화와 함께 메시지도
          지운다 — 실행 기록(agent_run·tool_call)은 남지만 대화는 복구할 수 없다. */}
      <Modal
        open={Boolean(pendingDelete)}
        onClose={() => setPendingDelete(null)}
        title="이 대화를 삭제할까요?"
        width={420}
        footer={
          <>
            <Button variant="outline" size="sm" onClick={() => setPendingDelete(null)}>
              취소
            </Button>
            <Button
              size="sm"
              variant="danger"
              onClick={() => pendingDelete && void remove(pendingDelete.session_id)}
            >
              삭제
            </Button>
          </>
        }
      >
        <p className={styles.deleteBody}>
          <strong>{pendingDelete?.title ?? '제목 없는 대화'}</strong>
          <span>주고받은 내용이 함께 삭제됩니다. 되돌릴 수 없습니다.</span>
        </p>
      </Modal>

      <ToolPickerModal
        open={toolPickerOpen}
        onClose={() => setToolPickerOpen(false)}
        builtinTools={toolChoices.filter((tool) => !tool.tool_ref.startsWith('mcp:'))}
        mcpServers={mcpServers}
        toolRefs={sessionToolOverride ?? agentOwnToolRefs}
        onToggle={(ref) => void toggleSessionTool(ref)}
        onToggleGroup={(refs, turnOn) => void toggleSessionToolGroup(refs, turnOn)}
      />
    </AppShell>
  );
}
