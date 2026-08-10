import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppShell, Button, Icon } from '../../components';
import { PATHS } from '../../routes';
import { ConfirmCard, DocPickCard, ErrorCard, ProgressCard, ResultCard } from './cards/ChatCards';
import {
  CHAT_STATE_LABELS,
  DEMO_UTTERANCE,
  MOCK_SESSIONS,
  STARTER_AGENTS,
} from './mockChat';
import type { ChatState } from './mockChat';
import styles from './ChatPage.module.css';

/**
 * Chat 홈. 카드 6종과 상태 전환을 mock으로 먼저 세운다 — 실연동(NDJSON
 * 스트림·확인 게이트 API)은 백엔드 단계 3 이후다.
 *
 * 상태는 DEV 전환기로 골라 본다. 스토리북을 따로 두지 않고 화면 안에서
 * 전부 확인할 수 있게 한 것이고, 개발 빌드에서만 보인다.
 */
export default function ChatPage() {
  const navigate = useNavigate();
  const [state, setState] = useState<ChatState>('empty');

  const isEmpty = state === 'empty' || state === 'empty-onboarding';
  const streaming = state === 'streaming';
  const waitingConfirm = state === 'confirm';

  return (
    <AppShell variant="flush">
      <div className={styles.chat}>
        <aside className={styles.sessions}>
          <span className={styles.sessionsTitle}>대화 목록</span>
          {isEmpty ? (
            <p className={styles.sessionsEmpty}>아직 대화가 없습니다</p>
          ) : (
            MOCK_SESSIONS.map((session, index) => (
              <button
                key={session.id}
                type="button"
                className={[styles.session, index === 0 ? styles.sessionActive : ''].filter(Boolean).join(' ')}
              >
                {session.title}
              </button>
            ))
          )}
        </aside>

        <div className={styles.main}>
          <header className={styles.agentBar}>
            <button type="button" className={styles.agentPicker}>
              <Icon name="sparkles" size={15} color="var(--color-primary)" />
              업무 추출 에이전트
              <Icon name="chevron-down" size={14} color="var(--color-placeholder)" />
            </button>
            <span className={styles.agentDesc}>기준 문서에서 업무 후보를 찾고 근거와 함께 정리합니다</span>

            {import.meta.env.DEV && (
              <select
                className={styles.stateSwitch}
                value={state}
                onChange={(event) => setState(event.target.value as ChatState)}
                aria-label="mock 상태 전환 (개발용)"
              >
                {CHAT_STATE_LABELS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            )}
          </header>

          <div className={styles.stream}>
            {isEmpty && (
              <div className={styles.empty}>
                <div className={styles.emptyIntro}>
                  <h2>무엇을 도와드릴까요?</h2>
                  <p>아래 에이전트를 고르거나, 하고 싶은 일을 그냥 적어 주세요.</p>
                </div>

                <div className={styles.starters}>
                  {STARTER_AGENTS.map((agent) => (
                    <button key={agent.name} type="button" className={styles.starter}>
                      <span className={styles.starterIcon}>
                        <Icon name="sparkles" size={20} color="var(--color-primary)" />
                      </span>
                      <strong>{agent.name}</strong>
                      <span className={styles.starterDesc}>{agent.desc}</span>
                      <span className={styles.starterExample}>“{agent.example}”</span>
                    </button>
                  ))}
                </div>

                {state === 'empty-onboarding' && (
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

            {!isEmpty && (
              <>
                <div className={styles.userMessage}>
                  <span>{state === 'success' || state === 'partial' ? '확인했어. 선택한 20건 등록해줘.' : DEMO_UTTERANCE}</span>
                </div>

                {state === 'doc-pick' && (
                  <>
                    <div className={styles.agentMessage}>
                      어떤 문서를 기준으로 삼을까요? 이 프로젝트에서 기준이 될 만한 문서를 찾았습니다. 하나만 골라 주세요.
                    </div>
                    <DocPickCard />
                  </>
                )}

                {streaming && (
                  <>
                    <div className={styles.agentMessage}>
                      기준 문서 「2026 상반기 통합포털 개편 기획서」를 기준으로 업무를 정리하겠습니다. 근거를 찾은 뒤
                      확인을 요청드릴게요.
                    </div>
                    <ProgressCard />
                  </>
                )}

                {waitingConfirm && (
                  <>
                    <div className={styles.agentMessage}>
                      업무 20건을 찾았습니다. 근거를 함께 확인하시고, Jira에 등록할 업무를 골라 주세요.
                    </div>
                    <ConfirmCard />
                  </>
                )}

                {(state === 'success' || state === 'partial') && (
                  <>
                    <div className={styles.agentMessage}>
                      {state === 'partial'
                        ? 'Jira에 등록했습니다. 3건은 실패해서 사유와 함께 남겨 두었습니다.'
                        : 'Jira에 20건 모두 등록했습니다. 업무별 근거는 위 확인 카드에 그대로 남아 있습니다.'}
                    </div>
                    <ResultCard partial={state === 'partial'} />
                  </>
                )}

                {state === 'error' && (
                  <>
                    {/* 스트림이 끊겨도 앞 단계 결과물은 남긴다(E2E §2-3). */}
                    <div className={styles.keptResult}>
                      <Icon name="check-circle" size={15} color="var(--color-success)" />
                      정리된 업무 20건 · 근거 24개 문단 — 이 결과는 남아 있습니다
                    </div>
                    <ErrorCard />
                  </>
                )}
              </>
            )}
          </div>

          <div className={styles.inputBar}>
            <div className={[styles.input, waitingConfirm ? styles.inputDisabled : ''].filter(Boolean).join(' ')}>
              {waitingConfirm ? '위 목록에서 등록할 업무를 선택해 주세요' : '무엇을 도와드릴까요?'}
            </div>
            {streaming ? (
              <Button variant="outline" iconLeft={<Icon name="x" size={14} />}>
                중단
              </Button>
            ) : (
              <Button aria-label="보내기" disabled={waitingConfirm}>
                <Icon name="arrow-right" size={16} />
              </Button>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
