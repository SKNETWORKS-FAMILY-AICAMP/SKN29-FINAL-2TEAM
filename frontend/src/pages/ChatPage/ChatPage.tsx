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
import type { ChatSession } from '../../api/chat';
import { listAgents } from '../../api/agents';
import type { Agent } from '../../api/agents';
import { useProjectContext } from '../../utils/projectContext';
import { ConfirmCard, ErrorCard, ProgressCard, ResultCard } from './cards/ChatCards';
import { emptyLive, reduce, toCards } from './liveChat';
import type { LiveChat } from './liveChat';
import styles from './ChatPage.module.css';

/**
 * Chat 홈. **서버와만 말한다** — mock 은 없다(개발지시_3차 단계 1).
 *
 * 이벤트를 카드 상태로 접는 규칙은 `liveChat.ts` 에 있다. 핵심은 `stage` 가 두
 * 층에서 온다는 것 — `tool_ref` 가 있으면 그 도구의 진행, 없으면 Loop 회전이다.
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
  const [sent, setSent] = useState<string | null>(null);
  const [live, setLive] = useState<LiveChat | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [fatal, setFatal] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

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

  const openSession = useCallback(
    async (id: string) => {
      if (!token) return;
      abortRef.current?.abort();
      setSessionId(id);
      setFatal(null);
      try {
        const detail = await getSession(token, id);
        setAgentId(detail.agent_id);
        // 새로고침 재현 — 저장된 마지막 에이전트 답을 이벤트로 다시 접는다.
        const last = [...detail.messages].reverse().find((message) => message.role === 'agent');
        const lastUser = [...detail.messages].reverse().find((message) => message.role === 'user');
        setSent(lastUser?.content.text ?? null);
        const restored = last?.content.events
          ? last.content.events.reduce(reduce, { ...emptyLive(), running: false })
          : null;
        setLive(restored);
        setSelected(restored ? restored.tasks.map((_, index) => index) : []);
      } catch (error) {
        setFatal(error instanceof ApiError ? error.message : '대화를 불러오지 못했습니다.');
      }
    },
    [token],
  );

  function startNew() {
    abortRef.current?.abort();
    setSessionId(null);
    setSent(null);
    setLive(null);
    setSelected([]);
    setFatal(null);
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
    setSent(text);
    setFatal(null);

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

    await run((onEvent, signal) => streamMessage(token, id as string, text, onEvent, signal));
  }

  async function approve() {
    if (!token || !sessionId) return;
    // **인덱스만 보낸다.** 실행할 인자는 서버가 저장해 둔 것을 쓴다 — 화면이
    // 인자를 보내면 승인 게이트가 아무것도 막지 못한다.
    const indices = selected;
    await run((onEvent, signal) => confirmMessage(token, sessionId, indices, onEvent, signal));
  }

  async function run(
    start: (onEvent: Parameters<typeof streamMessage>[3], signal: AbortSignal) => Promise<void>,
  ) {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    let state = emptyLive();
    setLive(state);
    try {
      await start((event) => {
        state = reduce(state, event);
        setLive({ ...state });
        if (event.type === 'task_extraction_result') {
          setSelected(toCards(event.result).map((_, index) => index));
        }
      }, controller.signal);
    } catch (error) {
      if (controller.signal.aborted) return;
      setFatal(error instanceof ApiError ? error.message : '요청을 보내지 못했습니다.');
    } finally {
      setLive((prev) => (prev ? { ...prev, running: false } : prev));
    }
  }

  const agent = agents.find((item) => item.agent_id === agentId) ?? null;
  const isEmpty = !sent && live === null;
  const streaming = Boolean(live?.running);
  const waitingConfirm = Boolean(live?.confirm);

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

          <div className={styles.stream}>
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

            {sent && <div className={styles.userMessage}><span>{sent}</span></div>}

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
                    trace={
                      live.extraction
                        ? `검색 ${live.extraction.trace.join(' · ')} · ${live.extraction.model}(${live.extraction.reasoning_effort})`
                        : undefined
                    }
                    selected={selected}
                    onSelectedChange={setSelected}
                    onApprove={live.confirm ? approve : undefined}
                    busy={live.running}
                  />
                )}

                {live.confirm && live.tasks.length === 0 && (
                  <ConfirmCard
                    tasks={[]}
                    warnings={[
                      `${live.confirm.toolName} 실행을 승인하시겠습니까? ${live.confirm.count}건이 대상입니다.`,
                    ]}
                    selected={selected}
                    onSelectedChange={setSelected}
                    onApprove={approve}
                    busy={live.running}
                  />
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

          <div className={styles.inputBar}>
            <input
              className={[styles.input, waitingConfirm ? styles.inputDisabled : ''].filter(Boolean).join(' ')}
              value={utterance}
              onChange={(event) => setUtterance(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.nativeEvent.isComposing) send();
              }}
              disabled={waitingConfirm || streaming || !agentId}
              placeholder={
                waitingConfirm ? '위 목록에서 등록할 업무를 선택해 주세요' : '무엇을 도와드릴까요?'
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
              <Button aria-label="보내기" onClick={send} disabled={waitingConfirm || !utterance.trim()}>
                <Icon name="arrow-right" size={16} />
              </Button>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
