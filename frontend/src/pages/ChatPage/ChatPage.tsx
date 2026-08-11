import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppShell, Button, Icon } from '../../components';
import { PATHS } from '../../routes';
import { loadSessionToken } from '../../utils/session';
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
import { listAgents } from '../../api/agents';
import type { Agent } from '../../api/agents';
import { useProjectContext } from '../../utils/projectContext';
import { ConfirmCard, ErrorCard, ProgressCard, ResultCard } from './cards/ChatCards';
import { emptyLive, reduce, toCards, traceLine } from './liveChat';
import type { LiveChat } from './liveChat';
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
export default function ChatPage() {
  const navigate = useNavigate();
  const token = loadSessionToken();
  const project = useProjectContext();

  const [agents, setAgents] = useState<Agent[]>([]);
  const [agentId, setAgentId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [utterance, setUtterance] = useState('');
  const [turns, setTurns] = useState<Turn[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [fatal, setFatal] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const streamRef = useRef<HTMLDivElement | null>(null);
  /** 사용자가 위로 올려 읽는 중이면 따라가지 않는다. */
  const stickToBottom = useRef(true);

  useEffect(() => {
    if (!token) return;
    listAgents(token)
      .then((rows) => {
        setAgents(rows);
        // 에이전트는 사람이 고른다(확정 ①). 기본값은 첫 항목이고, 목록은
        // is_prebuilt 가 앞에 오도록 서버가 정렬해 준다.
        setAgentId((prev) => prev ?? rows[0]?.agent_id ?? null);
      })
      .catch(() => setFatal('에이전트 목록을 불러오지 못했습니다.'));
    listSessions(token).then(setSessions).catch(() => undefined);
  }, [token]);

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
      }
    },
    [token],
  );

  function startNew() {
    abortRef.current?.abort();
    setSessionId(null);
    setTurns([]);
    setSelected([]);
    setFatal(null);
    stickToBottom.current = true;
  }

  async function remove(id: string) {
    if (!token) return;
    try {
      await deleteSession(token, id);
      setSessions((prev) => prev.filter((session) => session.session_id !== id));
      if (id === sessionId) startNew();
    } catch (error) {
      setFatal(error instanceof ApiError ? error.message : '대화를 지우지 못했습니다.');
    }
  }

  async function send() {
    if (!token || !utterance.trim() || !agentId) return;
    const text = utterance.trim();
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
        // 상단바에서 고른 프로젝트가 이 대화의 문맥이 된다. 「전체(팀)」이면
        // null 이고, 그때 업무 추출은 "프로젝트를 먼저 고르세요"로 끝난다 —
        // 기준 문서를 모델이 고르게 하지 않기로 한 결정의 연장이다.
        const created = await createSession(token, {
          agent_id: agentId,
          proj_id: project?.proj_id ?? null,
          title: text.slice(0, 60),
        });
        id = created.session_id;
        setSessionId(id);
        setSessions((prev) => [created, ...prev]);
      }
    } catch (error) {
      setFatal(error instanceof ApiError ? error.message : '대화를 열지 못했습니다.');
      return;
    }

    await run(
      (onEvent, signal) => streamMessage(token, id as string, text, onEvent, signal),
      emptyLive(),
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
      }, controller.signal);
    } catch (error) {
      if (controller.signal.aborted) return;
      setFatal(error instanceof ApiError ? error.message : '요청을 보내지 못했습니다.');
    } finally {
      updateLastLive((prev) => (prev ? { ...prev, running: false } : prev));
    }
  }

  const agent = agents.find((item) => item.agent_id === agentId) ?? null;
  const isEmpty = turns.length === 0;
  const lastLive = turns[turns.length - 1]?.live ?? null;
  const streaming = Boolean(lastLive?.running);
  const waitingConfirm = Boolean(lastLive?.confirm);

  return (
    <AppShell variant="flush">
      <div className={styles.chat}>
        <aside className={styles.sessions}>
          <span className={styles.sessionsTitle}>대화 목록</span>
          {sessions.length === 0 ? (
            <p className={styles.sessionsEmpty}>아직 대화가 없습니다</p>
          ) : (
            sessions.map((session) => (
              <span key={session.session_id} className={styles.sessionRow}>
                <button
                  type="button"
                  onClick={() => openSession(session.session_id)}
                  className={[styles.session, session.session_id === sessionId ? styles.sessionActive : '']
                    .filter(Boolean)
                    .join(' ')}
                >
                  {session.title ?? '제목 없는 대화'}
                </button>
                <button
                  type="button"
                  className={styles.sessionDelete}
                  aria-label={`${session.title ?? '대화'} 삭제`}
                  onClick={() => remove(session.session_id)}
                >
                  <Icon name="x" size={13} color="var(--color-placeholder)" />
                </button>
              </span>
            ))
          )}
        </aside>

        <div className={styles.main}>
          <header className={styles.agentBar}>
            <select
              className={styles.agentPicker}
              value={agentId ?? ''}
              onChange={(event) => setAgentId(event.target.value)}
              // 대화가 시작된 뒤에는 바꾸지 않는다 — 갈면 앞선 턴이 다른
              // 스캐폴드로 만들어진 것이 되어 이어지는 답의 근거가 흔들린다.
              disabled={Boolean(sessionId)}
              aria-label="에이전트 선택"
            >
              {agents.map((item) => (
                <option key={item.agent_id} value={item.agent_id}>
                  {item.name}
                  {item.is_prebuilt ? ' (기본 제공)' : ''}
                </option>
              ))}
            </select>
            <span className={styles.agentDesc}>{agent?.description ?? ''}</span>
            <Button size="sm" variant="outline" onClick={startNew}>
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

            {isEmpty && (
              <div className={styles.empty}>
                <div className={styles.emptyIntro}>
                  <h2>무엇을 도와드릴까요?</h2>
                  <p>아래 에이전트를 고르거나, 하고 싶은 일을 그냥 적어 주세요.</p>
                  {/* 문맥을 먼저 말한다 — 업무 추출은 이 프로젝트의 기준 문서로 돈다. */}
                  <p className={styles.projectContext}>
                    <Icon name="folder" size={14} color="var(--color-muted)" />
                    {project ? (
                      <span>
                        <strong>{project.name}</strong> 문맥으로 시작합니다.
                      </span>
                    ) : (
                      <span>
                        <strong>전체(팀)</strong> 문맥입니다 — 업무 추출처럼 기준 문서가 필요한 일은
                        상단바에서 프로젝트를 먼저 골라 주세요.
                      </span>
                    )}
                  </p>
                </div>

                <div className={styles.starters}>
                  {agents.map((item) => (
                    <button
                      key={item.agent_id}
                      type="button"
                      className={styles.starter}
                      onClick={() => setAgentId(item.agent_id)}
                    >
                      <span className={styles.starterIcon}>
                        <Icon name="sparkles" size={20} color="var(--color-primary)" />
                      </span>
                      <strong>{item.name}</strong>
                      <span className={styles.starterDesc}>{item.description}</span>
                    </button>
                  ))}
                </div>

                {agents.length === 0 && (
                  <p className={styles.onboardingBanner}>
                    <Icon name="info" size={15} color="var(--color-info)" />
                    쓸 수 있는 에이전트가 없습니다. 에이전트를 먼저 만들어 주세요.
                    <button type="button" onClick={() => navigate(PATHS.agents)}>
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
                          title={live.toolName ? `${live.toolName} 실행 중` : '생각하는 중'}
                          loop={{ step: live.loopStep, total: live.loopTotal }}
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

                      {live.answer && <div className={styles.agentMessage}>{live.answer}</div>}

                      {live.stoppedReason && (
                        <p className={styles.warnLine}>
                          <Icon name="triangle-alert" size={14} color="var(--color-warning-text)" />
                          끝까지 마치지 못했습니다 ({live.stoppedReason}) — 위 결과는 여기까지 확인한 것입니다.
                        </p>
                      )}

                      {live.error && (
                        <ErrorCard
                          detail={live.error.detail}
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
      </div>
    </AppShell>
  );
}
