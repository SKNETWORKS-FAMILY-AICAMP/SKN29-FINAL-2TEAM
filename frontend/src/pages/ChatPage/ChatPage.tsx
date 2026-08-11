import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppShell, Button, Icon } from '../../components';
import { PATHS } from '../../routes';
import { loadSessionToken } from '../../utils/session';
import {
  ApiError,
  confirmMessage,
  createSession,
  getSession,
  listSessions,
  streamMessage,
} from '../../api/chat';
import type { ChatSession } from '../../api/chat';
import { MOCK_AGENTS } from '../../data/mockAgents';
import { ConfirmCard, DocPickCard, ErrorCard, ProgressCard, ResultCard } from './cards/ChatCards';
import { emptyLive, reduce, toCards } from './liveChat';
import type { LiveChat } from './liveChat';
import { CHAT_STATE_LABELS, DEMO_UTTERANCE, STARTER_AGENTS } from './mockChat';
import type { ChatState } from './mockChat';
import styles from './ChatPage.module.css';

/**
 * Chat 홈. **서버와 실제로 말한다** — NDJSON 스트림과 확인 게이트.
 *
 * 이벤트를 카드 상태로 접는 규칙은 `liveChat.ts` 에 있다. 핵심은 `stage` 가 두
 * 층에서 온다는 것 — `tool_ref` 가 있으면 그 도구의 진행, 없으면 Loop 회전이다.
 *
 * DEV 상태 전환기는 그대로 둔다. 카드 8종을 서버 없이 확인할 수 있어야 Figma 와
 * 나란히 놓고 볼 수 있고, 실연동 경로와 **같은 컴포넌트**를 쓰므로 전환기에서
 * 본 모양이 실제와 어긋나지 않는다.
 */
export default function ChatPage() {
  const navigate = useNavigate();
  const token = loadSessionToken();

  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [utterance, setUtterance] = useState('');
  const [sent, setSent] = useState<string | null>(null);
  const [live, setLive] = useState<LiveChat | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [fatal, setFatal] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  /** mock 전환기. 서버를 안 부르는 경로라 실연동 상태와 완전히 갈라 둔다. */
  const [mockState, setMockState] = useState<ChatState | 'live'>('live');
  const mocking = mockState !== 'live';

  // 에이전트는 사람이 고른다(확정 ①). 선택기 UI 는 아직 mock 목록을 쓰고,
  // 실제 목록은 agent API 가 붙을 때 갈아 끼운다 — 대화를 열 때 이 id 를 보낸다.
  const agent = MOCK_AGENTS[0];
  const agentId = agent.id;

  useEffect(() => {
    if (!token) return;
    listSessions(token).then(setSessions).catch(() => undefined);
  }, [token]);

  // 브라우저를 닫거나 화면을 떠나면 스트림을 끊는다. 서버는 그 run 을 FAILED 로
  // 닫으므로 RUNNING 으로 남지 않는다.
  useEffect(() => () => abortRef.current?.abort(), []);

  const openSession = useCallback(
    async (id: string) => {
      if (!token) return;
      setSessionId(id);
      setFatal(null);
      try {
        const detail = await getSession(token, id);
        // 새로고침 재현 — 저장된 마지막 에이전트 답을 이벤트로 다시 접는다.
        const last = [...detail.messages].reverse().find((message) => message.role === 'agent');
        const lastUser = [...detail.messages].reverse().find((message) => message.role === 'user');
        setSent(lastUser?.content.text ?? null);
        setLive(
          last?.content.events
            ? last.content.events.reduce(reduce, { ...emptyLive(), running: false })
            : null,
        );
      } catch (error) {
        setFatal(error instanceof ApiError ? error.message : '대화를 불러오지 못했습니다.');
      }
    },
    [token],
  );

  async function send() {
    if (!token || !utterance.trim()) return;
    const text = utterance.trim();
    setUtterance('');
    setSent(text);
    setFatal(null);

    let id = sessionId;
    try {
      if (!id) {
        // 첫 발화가 대화를 만든다. 에이전트는 사람이 고른 것을 쓴다(확정 ①).
        const created = await createSession(token, { agent_id: agentId, title: text.slice(0, 60) });
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
        // 새 객체로 넣어야 React 가 갱신을 알아챈다.
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

  const isEmpty = !mocking && !sent && live === null;
  const streaming = mocking ? mockState === 'streaming' : Boolean(live?.running);
  const waitingConfirm = mocking ? mockState === 'confirm' : Boolean(live?.confirm);

  return (
    <AppShell variant="flush">
      <div className={styles.chat}>
        <aside className={styles.sessions}>
          <span className={styles.sessionsTitle}>대화 목록</span>
          {sessions.length === 0 ? (
            <p className={styles.sessionsEmpty}>아직 대화가 없습니다</p>
          ) : (
            sessions.map((session) => (
              <button
                key={session.session_id}
                type="button"
                onClick={() => openSession(session.session_id)}
                className={[styles.session, session.session_id === sessionId ? styles.sessionActive : '']
                  .filter(Boolean)
                  .join(' ')}
              >
                {session.title ?? '제목 없는 대화'}
              </button>
            ))
          )}
        </aside>

        <div className={styles.main}>
          <header className={styles.agentBar}>
            <button type="button" className={styles.agentPicker}>
              <Icon name="sparkles" size={15} color="var(--color-primary)" />
              {agent.name}
              <Icon name="chevron-down" size={14} color="var(--color-placeholder)" />
            </button>
            <span className={styles.agentDesc}>{agent.description}</span>

            {import.meta.env.DEV && (
              <select
                className={styles.stateSwitch}
                value={mockState}
                onChange={(event) => setMockState(event.target.value as ChatState | 'live')}
                aria-label="mock 상태 전환 (개발용)"
              >
                <option value="live">실연동</option>
                {CHAT_STATE_LABELS.map((option) => (
                  <option key={option.value} value={option.value}>
                    mock · {option.label}
                  </option>
                ))}
              </select>
            )}
          </header>

          <div className={styles.stream}>
            {fatal && <p className={styles.fatal}>{fatal}</p>}

            {(mocking ? mockState === 'empty' || mockState === 'empty-onboarding' : isEmpty) && (
              <div className={styles.empty}>
                <div className={styles.emptyIntro}>
                  <h2>무엇을 도와드릴까요?</h2>
                  <p>아래 에이전트를 고르거나, 하고 싶은 일을 그냥 적어 주세요.</p>
                </div>

                <div className={styles.starters}>
                  {STARTER_AGENTS.map((starter) => (
                    <button
                      key={starter.name}
                      type="button"
                      className={styles.starter}
                      onClick={() => setUtterance(starter.example)}
                    >
                      <span className={styles.starterIcon}>
                        <Icon name="sparkles" size={20} color="var(--color-primary)" />
                      </span>
                      <strong>{starter.name}</strong>
                      <span className={styles.starterDesc}>{starter.desc}</span>
                      <span className={styles.starterExample}>“{starter.example}”</span>
                    </button>
                  ))}
                </div>

                {mockState === 'empty-onboarding' && (
                  <p className={styles.onboardingBanner}>
                    <Icon name="info" size={15} color="var(--color-info)" />
                    Drive 연결 후 문서 기반 요청이 가능합니다
                    <button type="button" onClick={() => navigate(PATHS.settingsConnectors)}>
                      설정으로 이동 →
                    </button>
                  </p>
                )}
              </div>
            )}

            {/* ── 실연동 ── */}
            {!mocking && sent && <div className={styles.userMessage}><span>{sent}</span></div>}

            {!mocking && live && (
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

                {live.confirm && !live.tasks.length && (
                  <ConfirmCard
                    tasks={[]}
                    warnings={[`${live.confirm.toolName} 실행을 승인하시겠습니까? ${live.confirm.count}건이 대상입니다.`]}
                    selected={selected}
                    onSelectedChange={setSelected}
                    onApprove={approve}
                    busy={live.running}
                  />
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

            {/* ── mock 전환기 ── */}
            {mocking && mockState !== 'empty' && mockState !== 'empty-onboarding' && (
              <>
                <div className={styles.userMessage}>
                  <span>
                    {mockState === 'success' || mockState === 'partial'
                      ? '확인했어. 선택한 20건 등록해줘.'
                      : DEMO_UTTERANCE}
                  </span>
                </div>

                {mockState === 'doc-pick' && (
                  <>
                    <div className={styles.agentMessage}>
                      어떤 문서를 기준으로 삼을까요? 이 프로젝트에서 기준이 될 만한 문서를 찾았습니다. 하나만 골라 주세요.
                    </div>
                    <DocPickCard />
                  </>
                )}

                {mockState === 'streaming' && (
                  <>
                    <div className={styles.agentMessage}>
                      기준 문서 「2026 상반기 통합포털 개편 기획서」를 기준으로 업무를 정리하겠습니다. 근거를 찾은 뒤
                      확인을 요청드릴게요.
                    </div>
                    <ProgressCard />
                  </>
                )}

                {mockState === 'confirm' && (
                  <>
                    <div className={styles.agentMessage}>
                      업무 20건을 찾았습니다. 근거를 함께 확인하시고, Jira에 등록할 업무를 골라 주세요.
                    </div>
                    <ConfirmCard />
                  </>
                )}

                {(mockState === 'success' || mockState === 'partial') && (
                  <>
                    <div className={styles.agentMessage}>
                      {mockState === 'partial'
                        ? 'Jira에 등록했습니다. 3건은 실패해서 사유와 함께 남겨 두었습니다.'
                        : 'Jira에 20건 모두 등록했습니다. 업무별 근거는 위 확인 카드에 그대로 남아 있습니다.'}
                    </div>
                    <ResultCard partial={mockState === 'partial'} />
                  </>
                )}

                {mockState === 'error' && (
                  <>
                    {/* 스트림이 끊겨도 앞 단계 결과물은 남긴다(E2E §2-3). */}
                    <div className={styles.keptResult}>
                      <Icon name="check-circle" size={15} color="var(--color-success)" />
                      정리된 업무 20건 · 근거 24개 문단 — 이 결과는 남아 있습니다
                    </div>
                    <ErrorCard errorCode="401" />
                  </>
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
              disabled={waitingConfirm || streaming || mocking}
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
              <Button
                aria-label="보내기"
                onClick={send}
                disabled={waitingConfirm || mocking || !utterance.trim()}
              >
                <Icon name="arrow-right" size={16} />
              </Button>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
