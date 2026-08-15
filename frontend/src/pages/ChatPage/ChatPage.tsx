import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { AppShell, Button, Icon, Modal } from '../../components';
import { PATHS } from '../../routes';
import { loadSessionToken } from '../../utils/session';
import { useNarrowViewport } from '../../utils/viewport';
import {
  ApiError,
  confirmMessage,
  createSession,
  deleteSession,
  getSession,
  listSessions,
  streamMessage,
} from '../../api/chat';
import type { ChatEvent, ChatMessage, ChatSession } from '../../api/chat';
import { listAgentVersions } from '../../api/agentVersions';
import type { AgentVersionSummary } from '../../api/agentVersions';
import { listMyProjects } from '../../api/projects';
import type { Project } from '../../api/projects';
import { listConnectors } from '../../api/connectors';
import { AnswerText } from './AnswerText';
import { WelcomeTour } from './WelcomeTour';
import { ConfirmCard, ErrorCard, JiraStatusCard, ProgressCard, ResultCard } from './cards/ChatCards';
import { emptyLive, memoryFilePath, MEMORY_PATH_PREFIX, reduce, toCards, traceLine } from './liveChat';
import type { LiveChat, ToolCallEntry } from './liveChat';
import styles from './ChatPage.module.css';

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

/** 대화 목록 너비 — 저장 키와 한계. 너무 좁으면 제목이 통째로 잘린다. */
const LIST_WIDTH_KEY = 'halil.chatListWidth';
/** 소개를 봤는가. `sessionStorage` 가 아니라 `localStorage` 다 — 탭을 닫아도 기억한다. */
const TOUR_SEEN_KEY = 'halil.tourSeen';
const LIST_MIN = 200;
const LIST_MAX = 460;

/**
 * deepagents 내장 파일 도구 → 사람이 읽을 동사. 매핑에 없는 값(내장 도구가
 * 버전업으로 늘거나 이름이 바뀌면)은 `tool_ref` 원문을 그대로 보여준다 —
 * 지어내지 않는다.
 */
const MEMORY_TOOL_LABEL: Record<string, string> = {
  read_file: '읽기',
  write_file: '쓰기',
  edit_file: '수정',
  ls: '목록 조회',
};

const MEMORY_STATUS_LABEL: Record<ToolCallEntry['status'], string> = {
  RUNNING: '진행 중',
  OK: '완료',
  FAILED: '실패',
};

export default function ChatPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  /**
   * **주소가 정본이다.** 대화를 여는 곳은 전부 `navigate` 를 하고, 실제로 여는 것은
   * 아래 동기화 effect 하나다 — 두 경로가 생기면 목록에서 연 대화와 주소가 어긋난다.
   */
  const { sessionId: routeSessionId } = useParams();
  /** 좁은 화면에서는 목록이 자리를 차지하지 않고 덮어서 열린다. */
  const narrow = useNarrowViewport();
  const [listOpen, setListOpen] = useState(false);
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
  const [tourSeen, setTourSeen] = useState(() => localStorage.getItem(TOUR_SEEN_KEY) === '1');
  const [utterance, setUtterance] = useState('');
  const [turns, setTurns] = useState<Turn[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [fatal, setFatal] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  /**
   * 방금 떠난 대화의 id. 주소가 `/chat` 으로 따라오면 즉시 비운다.
   * 왜 필요한지는 아래 주소 동기화 effect 에 적었다.
   */
  const leftRef = useRef<string | null>(null);
  const streamRef = useRef<HTMLDivElement | null>(null);
  /** 사용자가 위로 올려 읽는 중이면 따라가지 않는다. */
  const stickToBottom = useRef(true);

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
        // 보여줘야 해서) — Chat 은 ACTIVE 만 후보로 본다. 초안이 기본 에이전트로
        // 잘못 골리거나 "에이전트 없음" 배너 판단을 흐리면 안 된다.
        const active = rows.filter((row) => row.status === 'ACTIVE');
        setAgents(active);
        // **팀의 기본 챗 에이전트(`is_default_chat`)를 고른다.**
        //
        // 팀 생성 시 자동으로 하나씩 생기는 에이전트다(2026-08-15,
        // provision_default_chat_agent). 사용자가 드롭다운에서 직접 다른
        // 에이전트를 고르면 그 값이 우선한다 — `prev`가 있으면 덮지 않는다.
        setAgentId(
          (prev) => prev ?? active.find((row) => row.is_default_chat)?.agent_id ?? active[0]?.agent_id ?? null,
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
   * 삭제를 기다리는 대화. **되돌릴 수 없어서 한 번 묻는다** — 서버가
   * chat_message 까지 함께 지우고(`ChatSessionRepository.delete`), 목록의
   * X 는 대화 제목 바로 옆이라 잘못 누르기 쉽다.
   */
  const [pendingDelete, setPendingDelete] = useState<ChatSession | null>(null);

  /**
   * 대화 목록 너비. 사람마다 대화 제목 길이가 다르고 프로젝트 이름도 길다 —
   * 고정 260px 로는 어느 쪽도 안 맞는다. 값은 남겨서 매번 다시 끌지 않게 한다.
   */
  const [listWidth, setListWidth] = useState(() => {
    const saved = Number(localStorage.getItem(LIST_WIDTH_KEY));
    return saved >= LIST_MIN && saved <= LIST_MAX ? saved : 260;
  });

  function startResize(event: React.PointerEvent<HTMLDivElement>) {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = listWidth;

    function onMove(moveEvent: PointerEvent) {
      const next = Math.min(LIST_MAX, Math.max(LIST_MIN, startWidth + moveEvent.clientX - startX));
      setListWidth(next);
    }
    function onUp() {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      // 끌기가 끝날 때만 저장한다 — 매 픽셀 쓰면 드래그가 무거워진다.
      setListWidth((width) => {
        localStorage.setItem(LIST_WIDTH_KEY, String(width));
        return width;
      });
    }
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }

  useEffect(() => {
    const proj = params.get('proj');
    const ask = params.get('ask');
    if (!proj && !ask) return;
    if (proj) setProjId(proj);
    if (ask) setPendingAsk(ask);
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

  // 턴이 늘거나 답이 자라면 아래로 따라간다. 단 **사용자가 위로 올려 읽는
  // 중이면 붙잡지 않는다** — 근거를 읽고 있는데 화면이 끌려 내려가면 읽을 수가
  // 없다. 위로 올린 순간 `onScroll` 이 stick 을 끈다.
  useEffect(() => {
    const node = streamRef.current;
    if (!node || !stickToBottom.current) return;
    node.scrollTop = node.scrollHeight;
  }, [turns]);

  const openSession = useCallback(
    async (id: string) => {
      if (!token) return;
      abortRef.current?.abort();
      setSessionId(id);
      setFatal(null);
      try {
        const detail = await getSession(token, id);
        setAgentId(detail.agent_id);
        // 대화가 속한 프로젝트를 따라간다 — 사이드바의 어느 묶음에서 열었든
        // 문맥은 대화 자신이 갖고 있는 값이다.
        setProjId(detail.proj_id ?? null);
        // 새로고침 재현 — 저장된 대화를 **전부** 다시 접는다. 서버는 처음부터
        // 모든 턴을 갖고 있었고, 화면이 마지막 답 하나만 쓰고 버리던 것이다.
        const restored = toTurns(detail.messages);
        setTurns(restored);
        stickToBottom.current = true;
        // 체크 상태는 **마지막 턴에만** 의미가 있다. 과거 턴의 확인 카드는
        // 읽기 전용이다.
        const lastLive = restored[restored.length - 1]?.live ?? null;
        setSelected(lastLive ? lastLive.tasks.map((_, index) => index) : []);
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

  /** 목록에서 대화를 연다. **여는 것은 주소가 하고**, 읽어 오는 것은 위 effect 다. */
  function openFromList(id: string) {
    setListOpen(false);
    navigate(`${PATHS.chat}/${id}`);
  }

  /** 새 대화를 연다. 어느 프로젝트 밑에서 시작하는지를 함께 받는다. */
  function startNew(nextProjId: string | null) {
    setListOpen(false);
    abortRef.current?.abort();
    setSessionId(null);
    // 주소도 함께 비운다. 떠난 id 를 남겨 두는 이유는 위 effect 의 주석에 있다.
    if (routeSessionId) {
      leftRef.current = routeSessionId;
      navigate(PATHS.chat);
    }
    setProjId(nextProjId);
    setTurns([]);
    setSelected([]);
    setFatal(null);
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
      setFatal(error instanceof ApiError ? error.message : '대화를 지우지 못했습니다.');
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
    setUtterance('');
    // 덧붙인다. 덮어쓰면 앞 턴이 화면에서 사라진다 — 서버는 지우지 않는데
    // 화면만 잊는 상태가 된다.
    setTurns((prev) => [...prev, { user: text, live: null }]);
    setSelected([]);
    setFatal(null);
    stickToBottom.current = true;

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

  async function approve() {
    if (!token || !sessionId) return;
    // **인덱스만 보낸다.** 실행할 인자는 서버가 저장해 둔 것을 쓴다 — 화면이
    // 인자를 보내면 승인 게이트가 아무것도 막지 못한다.
    const indices = selected;
    // 빈 상태에서 다시 시작하지 않고 **이 턴을 이어서 접는다.** 재개는 실행이
    // 두 번째일 뿐 같은 턴이고, 새로고침 복원도 두 실행의 이벤트를 이어 붙인다
    // (`toTurns`). 리셋하면 방금 승인한 목록이 화면에서 사라지고, 복원한 화면과
    // 라이브 화면이 서로 달라진다.
    const carried = lastLive ? { ...lastLive, running: true, error: null } : emptyLive();
    await run(
      (onEvent, signal) => confirmMessage(token, sessionId, indices, onEvent, signal),
      carried,
      sessionId,
    );
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

    let state = initial;
    updateLastLive(() => state);
    try {
      await start((event) => {
        state = reduce(state, event);
        updateLastLive(() => ({ ...state }));
        if (event.type === 'task_extraction_result') {
          setSelected(toCards(event.result).map((_, index) => index));
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
      setFatal(error instanceof ApiError ? error.message : '요청을 보내지 못했습니다.');
    } finally {
      updateLastLive((prev) => (prev ? { ...prev, running: false } : prev));
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
  /**
   * 이 대화 전체(턴을 넘어)에서 `/memories/` 아래를 건드린 도구 호출을 시간
   * 순서로 편다(2026-08-15). 위임으로 서브 에이전트에 들어간 호출은
   * `liveChat.ts`의 reduce()가 애초에 `toolCalls`에 안 담는다(Child는
   * 메모리가 없다 — 장기메모리 설계 문서 §4).
   */
  const memoryOps = useMemo(
    () =>
      turns.flatMap((turn) =>
        (turn.live?.toolCalls ?? []).flatMap((call) => {
          const path = memoryFilePath(call.arguments);
          return path ? [{ call, path }] : [];
        }),
      ),
    [turns],
  );

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

  return (
    <AppShell variant="flush">
      <div className={styles.chat}>
        {listOpen && (
          <button
            type="button"
            className={styles.listScrim}
            onClick={() => setListOpen(false)}
            aria-label="대화 목록 닫기"
          />
        )}
        <aside
          className={[styles.sessions, listOpen ? styles.sessionsOpen : ''].filter(Boolean).join(' ')}
          /* 끌어서 정한 폭은 넓은 화면의 값이다. 좁은 화면에서 그대로 쓰면
             덮어 여는 패널이 화면을 넘거나 반만 덮는다 — 그때는 CSS 가 정한다. */
          style={narrow ? undefined : { width: listWidth }}
        >
          <span className={styles.sessionsTitle}>대화 목록</span>

          {/* 프로젝트에 안 속한 대화. 머리말을 달지 않는다 — 「프로젝트 없음」이라고
              쓰면 그런 이름의 프로젝트가 있는 것처럼 읽힌다. */}
          {loose.map((session) => (
            <SessionRow
              key={session.session_id}
              session={session}
              active={session.session_id === sessionId}
              onOpen={openFromList}
              onRemove={setPendingDelete}
            />
          ))}

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

              {group.rows.map((session) => (
                <SessionRow
                  key={session.session_id}
                  session={session}
                  active={session.session_id === sessionId}
                  onOpen={openFromList}
                  onRemove={setPendingDelete}
                />
              ))}
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
        </aside>

        {/* 목록과 대화 사이의 끌기 손잡이. 키보드로는 조절할 수 없다 —
            폭은 보조 설정이고, 목록 자체는 폭과 무관하게 읽고 쓸 수 있다. */}
        <div
          className={styles.resizer}
          onPointerDown={startResize}
          role="separator"
          aria-orientation="vertical"
          aria-label="대화 목록 너비 조절"
        />

        <div className={styles.main}>
          {/*
            2026-08-15부터 다시 넣었다. 예전엔 "무엇으로 답할지는 말하면
            정해지는 것"이라는 이유로 없앴었지만(정문이 agent:* 로 알아서
            위임), 새 버전 스키마 에이전트는 그 위임 경로를 안 타서 사용자가
            직접 고르지 않으면 아예 닿을 방법이 없다 — 재설계가 끝나 정문을
            걷어낼 때까지의 과도기 UI다(지훈 확인, task #16/#19).
          */}
          <header className={styles.agentBar}>
            {/* 좁은 화면에서만 나온다. 목록이 덮개로 들어가면 대화를 오갈
                길이 화면에서 사라진다. */}
            <button
              type="button"
              className={styles.listToggle}
              onClick={() => setListOpen(true)}
              aria-label="대화 목록 열기"
              aria-expanded={listOpen}
            >
              <Icon name="message-square" size={16} color="var(--color-body)" />
              대화 목록
            </button>
            {agents.length > 0 && (
              <select
                className={styles.agentSelect}
                value={agentId ?? ''}
                aria-label="대화 상대 에이전트"
                onChange={(event) => {
                  setAgentId(event.target.value);
                  // 에이전트를 바꾸는 순간 새 대화로 넘어간다 — 대화 하나는
                  // 만들어질 때 고른 에이전트에 묶여서, 중간에 못 바꾼다.
                  startNew(projId);
                }}
              >
                {agents.map((agent) => (
                  <option key={agent.agent_id} value={agent.agent_id}>
                    {agent.name}
                    {agent.is_default_chat ? ' (기본)' : ''}
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
              // 바닥에서 40px 안쪽이면 "따라가는 중"으로 본다. 스트리밍이
              // 만드는 미세한 오차를 감안한 여유다.
              stickToBottom.current = node.scrollHeight - node.scrollTop - node.clientHeight < 40;
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
                  <p>하고 싶은 일을 그냥 적어 주세요.</p>
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
                          필요한 일은 프로젝트를 골라 시작해 주세요.
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
                <div key={turnIndex} className={styles.turn}>
                  <div className={styles.userMessage}>
                    <span>{turn.user}</span>
                  </div>

                  {live && (
                    <>
                      {(live.running || live.steps.length > 0) && (
                        <ProgressCard
                          steps={live.steps}
                          queries={live.queries}
                          evidenceCount={live.evidenceCount}
                          running={live.running}
                          title={
                            live.running
                              ? live.toolName
                                ? `${live.toolName} 실행 중`
                                : '생각하는 중'
                              : live.toolName
                                ? `${live.toolName} 완료`
                                : '정리 완료'
                          }
                        />
                      )}

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
                          busy={live.running}
                        />
                      )}

                      {live.confirm && live.tasks.length === 0 && (
                        <ConfirmCard
                          tasks={[]}
                          warnings={[
                            `${live.confirm.toolName} 실행을 승인하시겠습니까? ${live.confirm.count}건이 대상입니다.`,
                          ]}
                          selected={isLast ? selected : []}
                          onSelectedChange={isLast ? setSelected : () => undefined}
                          onApprove={isLast ? approve : undefined}
                          busy={live.running}
                        />
                      )}

                      {abandoned && (
                        <p className={styles.warnLine}>
                          <Icon name="triangle-alert" size={14} color="var(--color-warning-text)" />
                          승인하지 않고 넘어갔습니다 — 이 요청은 실행되지 않았습니다.
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
                          끝까지 마치지 못했습니다 ({live.stoppedReason}) — 위 결과는 여기까지 확인한 것입니다.
                        </p>
                      )}

                      {live.error && (
                        <ErrorCard
                          detail={live.error.detail}
                          answered={Boolean(live.answer)}
                          errorCode={live.error.errorCode}
                          onOpenSettings={() => navigate(PATHS.settingsMcp)}
                        />
                      )}
                    </>
                  )}
                </div>
              );
            })}
          </div>

          <div className={styles.inputBar}>
            {/* 승인 대기 중에도 **말할 수 있다**(6차 단계 1-5 · 확정 ③).
                체크박스로만 소통하게 두면 "3번은 빼고 다시 뽑아줘"를 할 방법이
                없어 폼 위저드가 된다. 전용 「다시 정리해줘」 버튼을 만들지 않고
                대화로 푸는 것이 이 제품의 성격에도 맞다.
                서버는 pending 을 무시하고 새 턴을 시작한다(실측 — 결과 블록). */}
            <input
              className={styles.input}
              value={utterance}
              onChange={(event) => setUtterance(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.nativeEvent.isComposing) send();
              }}
              disabled={streaming || !agentId}
              placeholder={
                waitingConfirm
                  ? '위에서 선택해 승인하거나, 고쳐서 다시 요청해 보세요'
                  : '무엇을 도와드릴까요?'
              }
            />
            {streaming ? (
              <Button
                variant="outline"
                iconLeft={<Icon name="x" size={14} />}
                onClick={() => abortRef.current?.abort()}
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

        {/*
          2026-08-15 추가 — 장기 메모리(`/memories/AGENTS.md`)에 실제로 어떤
          순서로 읽고 쓰는지 보고 싶다는 요청. 에이전트가 있으면(에이전트가
          없으면 이 대화 자체가 죽어 있어 패널도 의미 없다) 늘 보이는 고정
          패널이다 — 접었다 펼치는 상태를 따로 안 두는 이유는, 지금은 팀에
          공유할 데모용으로 "실제로 이렇게 돈다"를 보여주는 게 목적이라
          숨기면 그 목적에 안 맞는다.
        */}
        {agents.length > 0 && (
          <aside className={styles.memoryPanel}>
            <span className={styles.memoryPanelTitle}>
              <Icon name="database" size={13} color="var(--color-muted)" />
              장기 메모리 기록
            </span>
            {memoryOps.length === 0 ? (
              <p className={styles.memoryEmpty}>
                아직 이 대화에서 장기 메모리를 읽거나 쓴 적이 없습니다.
              </p>
            ) : (
              <ol className={styles.memoryOpList}>
                {memoryOps.map(({ call, path }, index) => (
                  <li key={`${call.toolCallId ?? 'x'}-${index}`} className={styles.memoryOp}>
                    <span className={styles.memoryOpIndex}>{index + 1}</span>
                    <span className={styles.memoryOpBody}>
                      <span className={styles.memoryOpLabel}>
                        {MEMORY_TOOL_LABEL[call.toolRef] ?? call.toolRef}
                      </span>
                      <span className={styles.memoryOpPath} title={path}>
                        {path.slice(MEMORY_PATH_PREFIX.length) || path}
                      </span>
                    </span>
                    <span
                      className={[
                        styles.memoryOpStatus,
                        call.status === 'FAILED' ? styles.memoryOpStatusFailed : '',
                        call.status === 'RUNNING' ? styles.memoryOpStatusRunning : '',
                      ]
                        .filter(Boolean)
                        .join(' ')}
                    >
                      {MEMORY_STATUS_LABEL[call.status]}
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </aside>
        )}
      </div>

      {/* 되돌릴 수 없는 삭제라 한 번 묻는다. 서버가 대화와 함께 메시지도
          지운다 — 실행 기록(agent_run·tool_call)은 남지만 대화는 복구할 수 없다. */}
      <Modal
        open={Boolean(pendingDelete)}
        onClose={() => setPendingDelete(null)}
        title="이 대화를 지울까요?"
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
              지우기
            </Button>
          </>
        }
      >
        <p className={styles.deleteBody}>
          <strong>{pendingDelete?.title ?? '제목 없는 대화'}</strong>
          <span>주고받은 내용이 함께 지워집니다. 되돌릴 수 없습니다.</span>
        </p>
      </Modal>
    </AppShell>
  );
}
