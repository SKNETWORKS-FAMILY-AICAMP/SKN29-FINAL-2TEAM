# halil 에이전트 작업 과정 UI 개선 구현 가이드

> 대상: Chat / Agent Runtime 담당자<br>
> 기준 브랜치: `main`<br>
> 기준일: 2026-08-25<br>
> 목표 일정: 2026-08-27(목)까지 P0 적용<br>
> Repository: https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN29-FINAL-2TEAM/

---

## 1. 결론부터

목요일까지는 **P0 범위만 적용하는 것이 가장 현실적**입니다.

이번 개선의 핵심은 OpenAI `reasoning.summary`를 한국어로 다시 번역하는 것이 아니라:

```text
한국어 User-visible Preamble
        ↓
agent_update Event
        ↓
기존 Tool Execution Timeline
        ↓
최종 답변
```

구조로 바꾸는 것입니다.

### 변경하지 않는 핵심 영역

P0에서는 아래를 변경하지 않습니다.

```text
ModelFactory의 reasoning.summary="auto"
DB Schema / Migration
기존 tool_call_id 매칭 방식
기존 HITL 승인 계약
기존 Subagent 실행 구조
```

즉 이번 작업은 **새 이벤트를 추가하고 UI 노출 정책을 바꾸는 최소 변경**으로 제한합니다.

### 이번 마감에서 권장하는 변경

- 한국어 Preamble 규칙 추가
- `agent_update` 이벤트 추가
- Tool Call과 같이 생성된 Assistant `content`를 버리지 않고 사용자용 업데이트로 전달
- Frontend Timeline에서 `agent_update` 렌더링
- UI 명칭 `생각 과정` → `작업 과정`
- 영어 Reasoning Summary는 기본 사용자 화면에서 숨김
- 기존 `tool_started / tool_progress / tool_completed / subagent / HITL` 구조는 최대한 유지
- 별도 번역용 LLM 호출은 추가하지 않음
- P0에서는 `reasoning.summary="auto"`도 그대로 유지

### 예상 난이도

> **중하 ~ 중간, 체감 약 5/10**

현재 프로젝트에는 이미 Event Stream, Timeline, Tool Lifecycle, Human-readable Tool Name, Subagent, HITL, 대화 저장/복원이 구현되어 있기 때문에 **새 에이전트 실행 구조를 만드는 작업은 아닙니다.**

핵심 구현은 **반나절~1일**, 실모델/회귀 테스트를 포함하면 **1~1.5일 정도**가 현실적인 범위입니다.

---

# 2. 현재 문제

현재 화면에서는 대략 다음과 같은 형태가 노출됩니다.

```text
생각 과정 2단계

**Assessing project tasks**

I need to inspect projects and tasks ...

✓ 프로젝트 조회 완료

{"projects":[...]}
```

여기에는 세 가지 문제가 있습니다.

### 2.1 영어 Reasoning Summary 직접 노출

현재 OpenAI Responses API에서 Reasoning Summary를 요청하고, 이를 실시간 `reasoning` 이벤트로 변환해 화면에 그대로 표시합니다.

따라서 OpenAI가 영어 Summary를 반환하면 그대로 영어가 보입니다.

### 2.2 사용자용 작업 과정과 Reasoning/Debug 정보가 섞임

일반 사용자가 알고 싶은 것은:

```text
무엇을 하려고 하는가?
→ 무엇을 실행했는가?
→ 무엇을 확인했는가?
→ 다음에는 무엇을 하는가?
```

입니다.

모델 내부 추론을 요약한 텍스트 전체를 읽는 것이 핵심 목적은 아닙니다.

### 2.3 Tool Raw Output까지 사용자 UI에 노출 가능

Tool Result의 JSON은 디버깅에는 유용하지만 제품 UI에서는 정보량이 과합니다.

예:

```json
{"projects":[{"proj_id":"PJ001", ...}]}
```

보다는:

```text
✓ 프로젝트 조회
  프로젝트 정보를 확인했습니다.
```

가 기본 UI에 더 적합합니다.

---

# 3. 현재 코드 흐름 재확인

현재 `main` 기준으로 관련 흐름은 다음과 같습니다.

```text
OpenAI / Anthropic / OpenAI-compatible Model
                ↓
        Deep Agent / LangGraph
                ↓
     services/agent_runtime/events.py
                ↓
          EventMapper
                ↓
     services/agent_runtime/executor.py
                ↓
        apps/chat/api_views.py
                ↓
             NDJSON
                ↓
       frontend/src/api/chat.ts
                ↓
      frontend liveChat.reduce()
                ↓
             timeline
                ↓
         ChatCards / ChatPage
```

이번 변경은 이 구조 자체를 바꾸지 않고 **Event 하나를 추가하고 사용자 표시 레이어를 정리하는 방향**입니다.

---

# 4. 현재 구현에서 이미 갖춰진 것

## 4.1 OpenAI Responses API + Reasoning Summary

`services/agent_runtime/models/factory.py`

현재 OpenAI 모델 생성 시:

```python
kwargs = {
    "model": resolved.model_id,
    "openai_api_key": resolved.api_key,
    "use_responses_api": True,
}

if resolved.reasoning_effort:
    kwargs["reasoning"] = {
        "effort": resolved.reasoning_effort,
        "summary": "auto",
    }
```

형태로 Reasoning Summary를 명시적으로 요청합니다.

### P0에서는 이 부분을 건드리지 않는 것을 권장

이번 변경의 목적은 **Reasoning 자체의 생성 정책을 바꾸는 것보다 사용자 UI를 분리하는 것**입니다.

따라서 목요일까지는:

```text
reasoning.summary="auto"
```

를 유지합니다.

Reasoning Summary 비활성화는 P1 이후 비용/필요성 검토 후 별도로 판단하는 편이 안전합니다.

---

## 4.2 Reasoning 실시간 Event

`services/agent_runtime/events.py`

현재 `stream_mode="messages"`는 Reasoning Delta를 처리합니다.

```text
OpenAI Reasoning Summary Delta
        ↓
_classify_reasoning_delta()
        ↓
EVENT_REASONING
        ↓
Frontend
```

즉 현재 영어 Reasoning은 이미 독립 Event입니다.

이 점을 활용하면 **기존 Reasoning Event를 삭제하지 않고도 기본 사용자 화면에서만 감출 수 있습니다.**

---

## 4.3 Tool Lifecycle Event

이미 다음 Event가 있습니다.

```text
tool_started
tool_progress
tool_completed
```

그리고 Tool마다 사람이 읽기 좋은 `tool_name`도 전달됩니다.

예:

```text
task_register
```

대신:

```text
업무 등록
```

처럼 표시하는 기반이 이미 있습니다.

---

## 4.4 Timeline

`frontend/src/pages/ChatPage/liveChat.ts`

현재 Timeline에는 다음이 실제 Event 발생 순서대로 쌓입니다.

```text
reasoning
tool
reasoning
tool
subagent
skill
...
```

따라서 Timeline 구조를 다시 만들 필요가 없습니다.

이번에는:

```text
update
```

라는 User-facing 항목을 하나 추가하는 방식이 가장 안전합니다.

---

# 5. 가장 중요한 현재 코드 포인트

## Prompt만 추가하면 안 됨

예를 들어 모델에게 다음과 같이 지시한다고 가정합니다.

```text
Tool을 호출하기 전에
"먼저 현재 프로젝트 현황을 확인하겠습니다."
처럼 사용자에게 짧게 안내하라.
```

모델이 다음처럼 반환할 수 있습니다.

```text
content:
"먼저 현재 프로젝트 현황을 확인하겠습니다."

tool_calls:
[get_project_list(...)]
```

그런데 현재 `services/agent_runtime/events.py`의 Parent Model 분기는 개념적으로 다음과 같습니다.

```python
content = message.text

if tool_calls:
    events.extend(
        self._classify_parent_tool_calls(...)
    )
    return events

if content:
    # 최종 답변 처리
```

즉 **Tool Call이 있으면 같은 AIMessage에 들어 있는 `content`가 현재 버려집니다.**

따라서 이번 개선은:

```text
Prompt 수정만
```

으로 끝나지 않고:

```text
Prompt
+
agent_update Event
+
Frontend Timeline 렌더링
```

까지 함께 가야 합니다.

---

# 6. 목표 구조

## 사용자 화면

```text
작업 과정

✓ 프로젝트 현황 확인
  먼저 현재 진행 중인 프로젝트를 확인하겠습니다.

✓ 프로젝트 조회 완료

✓ 업무 현황 확인
  이제 미완료 업무와 진행 상태를 확인하겠습니다.

✓ 업무 조회 완료
```

최종 답변은 기존처럼 별도로 표시합니다.

---

## 내부 구조

```text
Internal Reasoning
    └─ 기본 사용자 화면에서는 숨김
            ↓

User-visible Preamble
    └─ EVENT_AGENT_UPDATE
            ↓

Tool Call
    └─ existing tool_started
            ↓

Tool Progress
    └─ existing tool_progress
            ↓

Tool Result
    └─ existing tool_completed
            ↓

Next Preamble
            ↓

Final Answer
    └─ existing result
```

### 중요한 원칙

> **Preamble은 설명이고, Tool Event가 실제 실행의 Source of Truth입니다.**

모델이:

```text
프로젝트를 확인하겠습니다.
```

라고 말했다고 해서 실제 조회가 완료된 것은 아닙니다.

완료 여부는 반드시:

```text
tool_completed.status
```

를 기준으로 표시해야 합니다.

---


# 6-A. 개발 시작 전 30분 확인 절차

바로 코드부터 수정하기보다 **실모델 Tool Call 1회로 현재 SDK가 Preamble을 어떤 형태로 넘기는지 먼저 확인**하는 것을 권장합니다.

이 확인이 이번 작업에서 가장 중요한 Spike입니다.

## 확인용 요청

가능하면 Tool 하나만 필요한 단순한 요청을 사용합니다.

예:

```text
현재 진행 중인 프로젝트를 확인해줘.
```

## 임시 확인 값

`services/agent_runtime/events.py`의 Parent Model 분기 직전 또는 개발용 테스트 코드에서 다음만 확인합니다.

```python
print("text:", message.text)
print("content:", message.content)
print("tool_calls:", message.tool_calls)
print("response_metadata:", message.response_metadata)
print("additional_kwargs:", message.additional_kwargs)
```

## 판단표

| 실측 결과 | P0 구현 |
|---|---|
| `text`가 있고 `tool_calls`도 있음 | 본 문서의 `agent_update` 구현 그대로 진행 |
| `phase=commentary` 같은 신호가 별도로 보임 | 보강 조건으로 활용 가능 |
| Tool Call은 있는데 사용자용 text가 없음 | Prompt 적용 후 재확인, 그래도 없으면 Tool Progress만 fallback |
| 별도 중간 Message가 final result처럼 분류됨 | `phase`/metadata 실측 후 `agent_update` 분기 추가 |
| Provider마다 형태가 다름 | P0는 OpenAI 경로 우선, 나머지는 Tool Lifecycle fallback |

이 단계에서 **Raw Reasoning을 한국어로 바꾸는 실험은 하지 않습니다.**

확인이 끝나면 임시 `print`/debug log는 제거합니다.

---

# 7. P0 구현 순서

아래 순서대로 진행하면 됩니다.

---

## Step 1. Runtime Prompt 수정

### 파일

```text
services/agent_runtime/prompts.py
```

현재 `[답변]`의:

```text
- 불필요한 계획이나 진행 예고를 먼저 나열하지 않는다.
...
- 생각 과정도 화면에 그대로 보인다. 사용자가 한국어로 물으면 생각 과정과
  답변을 모두 한국어로 쓴다.
```

부분을 User-facing Progress 개념으로 정리합니다.

### 권장 문구

```text
[작업 진행 표시]
- 여러 단계의 작업이 필요하거나 도구를 호출해야 하는 경우,
  도구 호출 전에 지금 무엇을 확인하거나 수행하려는지 사용자에게 짧게 알려준다.
- 진행 안내는 사용자가 읽는 메시지다. 사용자가 한국어로 요청하면 자연스러운
  한국어로 작성한다.
- 한 번의 안내는 한 문장, 필요한 경우 최대 두 문장을 넘기지 않는다.
- 내부 Chain-of-Thought나 숨은 추론을 설명하지 않는다.
- "분석하겠습니다"처럼 추상적인 문구보다 실제 다음 행동을 설명한다.
  예: "먼저 현재 진행 중인 프로젝트와 업무 현황을 확인하겠습니다."
- 간단한 질문처럼 도구 호출이나 여러 단계 작업이 필요하지 않은 경우에는
  진행 안내 없이 바로 답한다.

[답변]
- 사용자의 질문에 직접 답한다.
- 최종 답변에서 이미 수행한 작업 계획을 불필요하게 다시 나열하지 않는다.
```

### 포인트

기존:

```text
불필요한 계획이나 진행 예고를 먼저 나열하지 않는다.
```

와 충돌하지 않도록 **Tool Preamble은 예외**라는 의미를 명확히 합니다.

---

# 8. Backend Event 추가

## Step 2. Event Constant 추가

### 파일

```text
services/agent_runtime/events.py
```

현재:

```python
EVENT_REASONING = "reasoning"
```

근처에:

```python
EVENT_AGENT_UPDATE = "agent_update"
```

를 추가합니다.

`__all__`에도 함께 추가합니다.

예:

```python
__all__ = [
    "EVENT_AGENT_STARTED",
    "EVENT_AGENT_UPDATE",
    ...
]
```

---

# 9. Parent Model의 Preamble 살리기

## Step 3. Tool Call이 있을 때 `content`를 Event로 전달

### 파일

```text
services/agent_runtime/events.py
```

Parent Model 처리부의 기존 구조:

```python
if ns_prefix is None:
    if node_name == "model":
        self._reasoning_cursor[ns_prefix] = None
        self._count_model_call(run_id, message)

        events: list[dict[str, Any]] = []

        if tool_calls:
            events.extend(
                self._classify_parent_tool_calls(...)
            )
            return events

        if content:
            events.append(
                {
                    "type": EVENT_RESULT,
                    ...
                }
            )
```

을 다음 개념으로 변경합니다.

```python
if tool_calls:
    if content:
        events.append(
            {
                "type": EVENT_AGENT_UPDATE,
                "text": content,
                "run_id": run_id,
                "agent_id": agent_id,
                "agent_version_id": agent_version_id,
                "complete": False,
            }
        )

    events.extend(
        self._classify_parent_tool_calls(
            tool_calls=tool_calls,
            run_id=run_id,
            agent_id=agent_id,
            agent_version_id=agent_version_id,
            definition=definition,
            root_resolved_model=root_resolved_model,
            child_resolved_models=child_resolved_models,
        )
    )
    return events
```

### 예상 Event 순서

한 Model Call에서:

```text
"먼저 프로젝트를 확인하겠습니다."
+
get_project_list()
```

가 나오면:

```json
{"type":"agent_update","text":"먼저 프로젝트를 확인하겠습니다."}
{"type":"tool_started","tool_name":"프로젝트 조회", ...}
```

순서가 됩니다.

---

# 10. Child/Subagent 처리

## P0에서는 Root만 적용

현재 프로젝트는 Child 자신의 Reasoning과 Tool 진행을 최상위 화면에 과도하게 섞지 않는 방향으로 이미 설계되어 있습니다.

따라서 이번 마감에서는:

```text
Root Preamble → 표시
Child Preamble → 표시하지 않음
```

으로 가는 것을 추천합니다.

사용자에게는:

```text
✓ 자료 조사를 다른 에이전트에게 위임
✓ 위임 완료
```

정도만 보여주면 됩니다.

Child 내부 Preamble까지 전부 올리기 시작하면 Timeline이 급격히 길어집니다.

---

# 11. Chat API Relay / 저장 구조

현재:

```text
apps/chat/api_views.py
```

의 relay 흐름은 비종료 Event를 그대로 브라우저로 전달하고, 최종 `result / error / awaiting_confirmation` 저장 시 그동안 쌓인 Event 배열도 같이 저장하는 구조입니다.

따라서 `agent_update`는 기존 흐름에 **additive Event**로 들어갈 수 있습니다.

### 예상

```text
DB Schema 변경 없음
Migration 없음
```

으로 처리 가능할 가능성이 높습니다.

다만 아래는 반드시 QA합니다.

```text
대화 실행
→ agent_update 발생
→ 완료
→ 새로고침
→ 저장된 events에서 agent_update가 다시 렌더링되는가?
```

---

# 12. Frontend Type 추가

## Step 4. ChatEvent 추가

### 파일

```text
frontend/src/api/chat.ts
```

추가:

```ts
| {
    type: 'agent_update';
    text: string;
    run_id?: string | null;
    agent_id?: string | null;
    agent_version_id?: string | null;
    complete?: false;
  }
```

---

# 13. Timeline Type 추가

## Step 5. TimelineEntry 추가

### 파일

```text
frontend/src/pages/ChatPage/cardTypes.ts
```

현재:

```ts
export type TimelineEntry =
  | { kind: 'reasoning'; text: string }
  | ...
```

에:

```ts
| { kind: 'update'; text: string }
```

추가.

### 이유

다음 둘은 의미가 다릅니다.

```text
reasoning
= OpenAI Reasoning Summary / Debug 성격

update
= 사용자를 위해 의도적으로 생성한 작업 진행 안내
```

따라서 타입 단계에서 분리하는 것이 좋습니다.

---

# 14. Reducer 처리

## Step 6. `agent_update` → Timeline

### 파일

```text
frontend/src/pages/ChatPage/liveChat.ts
```

추가:

```ts
case 'agent_update':
  return {
    ...state,
    timeline: [
      ...state.timeline,
      {
        kind: 'update',
        text: event.text,
      },
    ],
  };
```

### P0에서는 복잡한 중복 제거 불필요

동일 Update가 반복되는 현상이 실제로 확인되면 P1에서:

```text
직전 update와 동일하면 skip
```

정도를 추가하면 됩니다.

처음부터 dedupe 로직까지 넣지 않는 것을 권장합니다.

---

# 15. 화면 렌더링

## Step 7. `작업 과정`으로 표시

### 파일

```text
frontend/src/pages/ChatPage/cards/ChatCards.tsx
```

현재:

```text
생각 과정 {entries.length}단계
```

를 기본 사용자 UI에서는:

```text
작업 과정
```

으로 변경하는 것을 추천합니다.

### 이유

앞으로 이 영역에는:

```text
agent_update
tool
subagent
skill
```

이 같이 표시됩니다.

즉 더 이상 정확한 의미가 `생각 과정`이 아닙니다.

---

## Step 8. `update` 렌더링

예:

```tsx
if (entry.kind === 'update') {
  return (
    <li key={index} className={styles.reasoningStep}>
      <span>{entry.text}</span>
    </li>
  );
}
```

스타일은 기존 reasoning text 스타일을 재사용해도 됩니다.

이번 마감에서는 UI 구조를 크게 갈아엎지 않는 것이 좋습니다.

---

# 16. 영어 Reasoning 기본 숨김

## Step 9. Reasoning은 기본 사용자 Timeline에서 제외

P0에서는 `reasoning` Event 자체를 Backend에서 제거하지 않습니다.

대신 일반 사용자에게 보여주는 Entries에서:

```ts
entry.kind !== 'reasoning'
```

만 그리도록 할 수 있습니다.

예:

```ts
const visibleEntries = entries.filter(
  (entry) => entry.kind !== 'reasoning'
);
```

그리고:

```tsx
visibleEntries.map(...)
```

으로 렌더링합니다.

### 이유

- Backend/Model 동작을 한 번에 많이 바꾸지 않음
- 기존 Reasoning Summary를 필요하면 Debug용으로 재사용 가능
- Rollback 쉬움
- 목요일 일정에 적합

---


# 16-A. ChatPage의 표시 조건도 함께 수정

영어 `reasoning`을 렌더링에서만 숨기고 기존:

```ts
const showReasoning = live.timeline.length > 0;
```

같은 조건을 그대로 두면, Timeline에 Reasoning만 있는 턴에서 **내용이 비어 있는 작업 과정 영역**이 생길 수 있습니다.

따라서 `ChatPage.tsx`에서 먼저 사용자용 Timeline을 계산한 뒤 표시 여부도 그 값으로 판단하는 편이 안전합니다.

예:

```ts
const visibleTimeline = live.timeline.filter(
  (entry) => entry.kind !== 'reasoning'
);

const showTrace = visibleTimeline.length > 0;
```

그리고:

```tsx
{showTrace && (
  <ReasoningTrace
    bare
    entries={visibleTimeline}
    defaultOpen={false}
    running={live.running}
  />
)}
```

처럼 전달합니다.

P0에서는 컴포넌트 이름 `ReasoningTrace` 자체를 즉시 바꾸지 않아도 됩니다.<br>
**화면 의미만 `작업 과정`으로 바꾸고 코드 레벨 rename은 P1로 미루는 것이 회귀 위험이 낮습니다.**

또한 `entries.length`를 그대로 `"N단계"`로 표시하면 `agent_update`, Tool, Skill, Subagent가 모두 각각 한 항목으로 계산되어 사용자가 실제 업무 단계 수로 오해할 수 있습니다.

따라서 P0에서는:

```text
생각 과정 4단계
```

대신 단순히:

```text
작업 과정
```

으로 표시하는 것을 권장합니다.

---

# 17. Raw Tool Output 처리

현재 Tool Output은 클릭 시 펼칠 수 있습니다.

P0에서는 최소한 **기본 사용자 작업 과정에서는 Raw JSON이 바로 노출되지 않도록** 합니다.

### 가장 안전한 P0

```text
Tool 이름 + RUNNING / 완료 / 실패
```

까지만 표시.

예:

```text
✓ 프로젝트 조회 완료
```

### P1 이후

Tool별 Result Mapper를 만들어:

```text
프로젝트 조회 완료
→ 진행 중인 프로젝트 3개를 확인했습니다.
```

처럼 개선합니다.

---

# 18. Tool Result Mapper는 이번에 어디까지 할까

목요일까지 다른 작업도 병행하는 것을 고려하면 **모든 Tool을 한 번에 처리하지 않는 것을 추천**합니다.

### 이번에 가능하면 처리할 것

최종 데모에서 자주 사용하는 핵심 Tool 2~4개 정도만 선택.

예:

```text
프로젝트 조회
업무 조회
문서 검색
Jira 조회
```

단, P0 완료에 꼭 필요한 항목은 아닙니다.

---

# 19. 구현 전에 반드시 한 번 확인할 것

## Preamble이 실제 LangChain AIMessage에서 어떤 형태로 오는지 확인

이 부분은 구현 리스크를 크게 줄여줍니다.

실모델 Tool Call 1회에서 임시로 다음 값을 확인합니다.

```python
print(message.content)
print(message.text)
print(message.tool_calls)
print(message.response_metadata)
print(message.additional_kwargs)
```

### Case A — 기대하는 형태

```text
message.text:
"먼저 프로젝트를 확인하겠습니다."

message.tool_calls:
[get_project_list(...)]
```

이면 위 P0 구현 그대로 진행하면 됩니다.

---

### Case B — 별도 Commentary Message로 옴

OpenAI 공식 Reasoning 가이드는 현재 **GPT-5.5 / GPT-5.4의 장시간·Tool-heavy Responses API 흐름**에서 Assistant Message의 `phase`를 사용해 중간 업데이트와 최종 답을 구분하는 방식을 안내합니다.

```text
phase: "commentary"
→ Tool 호출 전 Preamble 같은 중간 사용자 메시지

phase: "final_answer"
→ 완료된 최종 답변
```

다만 현재 프로젝트에서 사용하는 모델과 설치된 `langchain-openai` 조합이 이 값을 `AIMessage.response_metadata`, `additional_kwargs` 또는 content block에 실제로 보존하는지는 별도 문제입니다.

따라서 실측 결과 `phase`가 내려오는 경우에만:

```text
commentary → agent_update
final_answer → result
```

로 활용합니다.

### 주의

**GPT-5.6에도 같은 방식으로 내려올 것이라고 가정해서 구현하지 않습니다.**<br>
이번 P0의 1차 기준은 현재 코드에서 확실히 관찰 가능한 `message.text + tool_calls` 조합이고, `phase`는 실측 후 사용할 수 있는 보강 신호로 취급합니다.

---

### Case C — Preamble Content가 아예 안 나옴

이 경우에도 실행을 실패시키면 안 됩니다.

Fallback:

```text
agent_update 없음
↓
기존 tool_started / tool_progress / tool_completed만 표시
```

로 정상 작동해야 합니다.

즉 Preamble은 **Best-effort UX**이고 Tool Lifecycle이 정본입니다.

---

# 20. 이번 주에는 일반 Output Text Token Streaming까지 확장하지 않기

현재 `stream_mode="messages"`는 Reasoning Delta를 처리하는 데 사용됩니다.

Preamble을 ChatGPT처럼 글자 단위로 실시간 표시하려면 일반 Output Text Delta도 별도로 처리해야 할 가능성이 있습니다.

하지만 목요일까지는:

```text
AIMessage 완료
→ agent_update
→ tool_started
```

정도면 충분합니다.

### 이번에 제외하는 이유

- Event 분류 복잡도 증가
- Chunk 병합 처리 필요
- Provider별 차이 고려 필요
- 기존 Reasoning Delta와 섞일 위험
- 체감 UX 개선 대비 일정 리스크가 큼

---

# 21. Provider별 고려

현재 ModelFactory는 다음을 지원합니다.

```text
OpenAI
Anthropic
OpenAI-compatible
```

Reasoning Summary는 Provider마다 지원 방식이 다릅니다.

하지만 이번 구조는:

```text
User-visible Assistant Content
+
App Tool Lifecycle Event
```

를 중심으로 하기 때문에 Reasoning Summary에 덜 종속됩니다.

### 장점

OpenAI에서 Reasoning Summary가 영어로 나오더라도 기본 UI 영향 없음.

Anthropic이나 OpenAI-compatible 모델에서 Reasoning Summary 구조가 달라도:

```text
Tool 실행 상태
```

는 그대로 표시 가능.

즉 현재 프로젝트의 **멀티 Provider 방향에도 더 적합한 구조**입니다.

---

# 22. HITL 주의사항

외부 변경 Tool에서는 기존 HITL 정책을 절대 깨면 안 됩니다.

잘못된 Preamble:

```text
Jira에 이슈를 등록했습니다.
```

아직 승인 전이라면 거짓입니다.

권장:

```text
Jira에 등록할 내용을 준비했습니다.
승인 후 등록이 진행됩니다.
```

또는 Preamble 단계에서는:

```text
Jira 등록에 필요한 내용을 확인하겠습니다.
```

정도로만 표현합니다.

### Source of Truth

```text
awaiting_confirmation
→ 아직 실행 전

tool_completed.status == OK
→ 실제 실행 완료
```

---

# 23. Parallel Tool Call 주의사항

현재 Timeline은 `tool_call_id`로 Tool Started / Completed를 매칭하고 있습니다.

이 구조는 그대로 유지합니다.

새 `agent_update`에는 Tool ID를 억지로 연결하지 않아도 됩니다.

예:

```text
agent_update
"프로젝트와 Jira 현황을 함께 확인하겠습니다."

tool_started A
tool_started B

tool_completed B
tool_completed A
```

처럼 실제 완료 순서가 달라도 기존 Tool ID 매칭이 처리합니다.

---

# 24. Subagent 주의사항

P0 기준:

```text
Root update
→ 표시

subagent_started
→ 표시

Child reasoning
→ 숨김

Child tool
→ 기존 정책대로 최상위 사용자 Timeline에서는 숨김

subagent_completed
→ 표시
```

로 유지합니다.

이번에 Child까지 펼치기 시작하면 화면과 테스트 범위가 크게 늘어납니다.

---

# 25. 저장된 대화 복원

현재 Agent Message에는 실행 Event가 함께 저장되고, 새로고침 시 다시 `reduce()`에 태워 Timeline을 복원합니다.

`agent_update`도 Event 배열에 저장되면 동일하게 복원될 수 있어야 합니다.

반드시 확인:

```text
1. Tool 사용 대화 실행
2. Preamble 표시 확인
3. 실행 완료
4. 페이지 새로고침
5. 같은 대화 다시 열기
6. "작업 과정"이 동일하게 복원되는지 확인
```

---

# 26. Event Contract 예시

## 26.1 Agent Update

```json
{
  "type": "agent_update",
  "text": "먼저 현재 진행 중인 프로젝트를 확인하겠습니다.",
  "run_id": "RUN-...",
  "agent_id": "AGENT-...",
  "agent_version_id": "VER-...",
  "complete": false
}
```

---

## 26.2 Tool Started

기존 계약 사용:

```json
{
  "type": "tool_started",
  "tool_ref": "project_list",
  "tool_name": "프로젝트 조회",
  "tool_call_id": "call_..."
}
```

`RUNNING`은 현재 Frontend Timeline이 `tool_started`를 받았을 때 화면 상태로 부여하며, Backend `tool_started` 계약 자체에 별도 `status: "RUNNING"` 필드를 추가할 필요는 없습니다.

```text
tool_started 수신
→ Frontend Timeline entry 생성
→ status = RUNNING

tool_completed 수신
→ 같은 tool_call_id entry 갱신
→ status = OK / FAILED
```

---

## 26.3 Tool Completed

기존 계약 사용:

```json
{
  "type": "tool_completed",
  "tool_ref": "project_list",
  "tool_call_id": "call_...",
  "status": "OK",
  "output": "..."
}
```

---

## 26.4 Final Result

기존 계약 사용:

```json
{
  "type": "result",
  "text": "...",
  "complete": true
}
```

---

# 27. 기대 Event 순서

## 단일 Tool

```text
agent_update
tool_started
tool_completed
result
```

---

## 연속 Tool

```text
agent_update
tool_started
tool_completed

agent_update
tool_started
tool_completed

result
```

---

## HITL

```text
agent_update
tool_started 또는 승인 대상 감지
awaiting_confirmation

[사용자 승인]

tool_completed
result
```

실제 현재 Engine의 승인 Event 순서에 맞춰 QA합니다.

---

# 28. UI 예시

사용자:

```text
나 지금 뭐 해야 돼?
```

### 개선 후

```text
작업 과정

✓ 프로젝트 현황 확인
  먼저 현재 진행 중인 프로젝트와 업무 현황을 확인하겠습니다.

✓ 프로젝트 조회 완료

✓ 업무 현황 확인
  이제 미완료 업무와 진행 상태를 확인하겠습니다.

✓ 업무 조회 완료
```

최종:

```text
현재 기준으로는 진행 중인 프로젝트의 미완료 업무부터 확인하는 것이 좋습니다.

- ...
```

기본 화면에는 다음이 나오지 않습니다.

```text
Assessing project tasks
I need to inspect...
raw tool JSON
internal tool_ref
run_id
tool_call_id
```

---

# 29. 테스트 시나리오

| 시나리오 | 확인 내용 | 기대 결과 |
|---|---|---|
| 단순 질문, Tool 없음 | Preamble 남발 여부 | 작업 과정 없이 바로 답변 |
| Read Tool 1개 | Preamble + Tool | `agent_update → tool_started → tool_completed → result` |
| Tool 2개 순차 실행 | 순서 | 각 Tool 전에 Update가 자연스럽게 표시 |
| Tool 병렬 실행 | 매칭 | 기존 `tool_call_id` 기준 상태가 정확히 업데이트 |
| Tool 실패 | 실패 표시 | 성공처럼 보이지 않고 FAILED 표시 |
| HITL Write Tool | 승인 전 완료 표현 여부 | 승인 전 “등록 완료” 금지 |
| Subagent | Root/Child 분리 | Child 내부 Reasoning이 최상위에 섞이지 않음 |
| 새로고침 | Event persistence | 작업 과정 동일하게 복원 |
| 한국어 질문 | 언어 | Preamble 한국어 |
| 영어 질문 | 언어 | 가능하면 영어 Preamble |
| Preamble 미생성 | Fallback | Tool Progress만으로 정상 작동 |
| OpenAI-compatible 모델 | Provider 차이 | Reasoning 형식과 무관하게 Tool Progress 정상 |
| 기존 과거 대화 | 하위 호환 | `agent_update`가 없어도 정상 렌더링 |

---

# 30. 개발 중 권장 확인 로그

개발 환경에서 Tool 1개짜리 요청을 보내고 최소한 아래를 확인합니다.

```text
[Model]
message.text
message.tool_calls
message.content
message.response_metadata
message.additional_kwargs

[Mapped Events]
agent_update
tool_started
tool_completed
result

[Frontend]
timeline
```

목적은 **Preamble이 실제 어느 필드로 내려오는지 실측하는 것**입니다.

확인 후 임시 Debug Log는 제거합니다.

---

# 31. 구현 난이도 / 일정

| 구분 | 작업 | 난이도 | 예상 소요 | 목요일까지 |
|---|---|---:|---:|---|
| P0-A | Runtime Prompt Preamble 규칙 | 하 | 1~2시간 | 필수 |
| P0-B | `EVENT_AGENT_UPDATE` 추가 | 하 | 1시간 내외 | 필수 |
| P0-C | Tool Call + Content 분기 수정 | 중 | 2~4시간 | 필수 |
| P0-D | Frontend Type / Reducer | 중하 | 2~3시간 | 필수 |
| P0-E | `작업 과정` UI + reasoning 기본 숨김 | 중하 | 2~3시간 | 필수 |
| P0-F | 실모델 동작 확인 | 중 | 1~2시간 | 필수 |
| P0-G | HITL/Subagent/복원 회귀 테스트 | 중 | 2~4시간 | 필수 |
| P1-A | Raw Tool Output 별도 Debug UI | 중하 | 2~4시간 | 여유 시 |
| P1-B | 핵심 Tool Result Mapper | 중 | 반나절 | 일부만 |
| P1-C | Reasoning Debug Trace 완전 분리 | 중 | 반나절 | 이후 가능 |
| P2-A | Preamble Token Streaming | 중상 | 0.5~1.5일 | 제외 |
| P2-B | 전체 Tool Result Mapper | 중상 | 1일+ | 제외 |
| P2-C | Reasoning 번역 / 다국어 Fallback | 중 | 0.5~1일+ | 제외 |

---

# 32. 이번 마감 Scope

## MUST

- [ ] Runtime Prompt에 User-visible Preamble 규칙 추가
- [ ] `EVENT_AGENT_UPDATE` 추가
- [ ] Tool Call과 함께 온 Assistant `content`를 `agent_update`로 전달
- [ ] Frontend `ChatEvent` 추가
- [ ] Timeline `update` 타입 추가
- [ ] Reducer 처리
- [ ] 기본 UI `생각 과정` → `작업 과정`
- [ ] 영어 `reasoning` 기본 사용자 화면에서 숨김
- [ ] 기존 Tool Lifecycle 유지
- [ ] 실모델 1~2개 Tool 시나리오 확인
- [ ] HITL / Subagent / 새로고침 복원 회귀 확인

---

## SHOULD

시간이 남으면:

- [ ] Raw Tool JSON을 일반 사용자 UI에서 완전히 제거
- [ ] 데모 핵심 Tool 2~4개 Result Mapper
- [ ] 사용자 친화적인 FAILED 문구 정리
- [ ] Debug 상세 로그 진입점

---

## LATER

이번 목요일 이후:

- [ ] Preamble Token Streaming
- [ ] Reasoning 전용 Developer Trace
- [ ] 모든 Tool Result Mapper
- [ ] Reasoning Summary 사용 여부/비용 재검토
- [ ] `ReasoningTrace` → `ExecutionTrace` 코드 레벨 리팩터링
- [ ] Provider별 Preamble 품질 최적화
- [ ] 다국어 Progress 정책

---

# 33. 이번 P0에서 건드리지 않는 것

### 33.1 `reasoning.summary="auto"`

이번에는 유지.

Reasoning을 기본 UI에서 숨기는 것과 모델의 Reasoning 생성 정책 변경을 한 번에 묶지 않습니다.

---

### 33.2 Reasoning 번역용 LLM

추가하지 않음.

이유:

- 추가 Token
- 추가 API Round-trip
- Latency
- 실패 지점 증가
- Streaming 번역 품질 문제
- Tool 실행보다 Reasoning 텍스트에 UX가 종속됨

---

### 33.3 Preamble Token Streaming

이번에는 하지 않음.

---

### 33.4 모든 Tool Result 문장화

이번에는 필수가 아님.

---

### 33.5 대규모 컴포넌트 리팩터링

화면 문구를 `작업 과정`으로 바꾸는 것은 P0.

파일/컴포넌트 명 `ReasoningTrace`를 `ExecutionTrace`로 전부 리네임하는 것은 P1 이후.

---

# 34. Definition of Done

다음 조건을 만족하면 P0 완료로 봅니다.

- [ ] 한국어 사용자의 일반 Chat 화면에 영어 Reasoning Summary가 기본 노출되지 않는다.
- [ ] 별도 Reasoning 번역 API 호출이 없다.
- [ ] Tool 실행 전에 자연스러운 한국어 작업 안내가 표시될 수 있다.
- [ ] Preamble이 없어도 실행이 정상적으로 진행된다.
- [ ] Tool 실제 상태와 화면 상태가 일치한다.
- [ ] 승인 전 외부 변경을 완료된 것처럼 표현하지 않는다.
- [ ] Tool 실패를 성공으로 표시하지 않는다.
- [ ] 병렬 Tool의 Started/Completed 매칭이 깨지지 않는다.
- [ ] Subagent 내부 로그가 Root 일반 화면에 과도하게 섞이지 않는다.
- [ ] 새로고침 후 작업 과정이 복원된다.
- [ ] 기존 `agent_update`가 없는 과거 대화도 정상 렌더링된다.
- [ ] 단순 질문에서는 불필요한 작업 과정 카드가 생기지 않는다.
- [ ] 최종 답변 품질에 회귀가 없다.

---

# 35. Rollback / 하위 호환

이번 변경은 가능한 한 **additive**하게 진행합니다.

```text
기존 Event
+
agent_update 하나 추가
```

형태입니다.

### 장점

문제가 생기면:

```text
Prompt의 Preamble 규칙 제거
+
Frontend에서 agent_update 무시
```

만으로 쉽게 원복할 수 있습니다.

DB Schema를 바꾸지 않는 방향이므로 Rollback 부담도 작습니다.

또 과거 저장된 대화에는 `agent_update`가 없어도 기존 Event로 그대로 렌더링됩니다.

---

# 36. 구현 체크리스트 — 담당자가 바로 시작할 때

### Backend

1. `services/agent_runtime/prompts.py` 열기
2. `[작업 진행 표시]` 규칙 추가
3. `services/agent_runtime/events.py`에서 `EVENT_AGENT_UPDATE` 추가
4. `__all__` 추가
5. Parent Model + Tool Call 분기에서 `content`를 `agent_update`로 emit
6. Child는 건드리지 않기
7. Tool 1개 요청으로 `message.text / content / tool_calls / response_metadata` 실측
8. Event 순서 확인

### Frontend

9. `frontend/src/api/chat.ts`에 `agent_update` 추가
10. `cardTypes.ts`에 `kind: 'update'` 추가
11. `liveChat.ts` reducer 추가
12. `ChatCards.tsx`에서 update 렌더링
13. 화면 제목 `생각 과정` → `작업 과정`
14. 일반 사용자 view에서 `reasoning` 숨김
15. Raw Tool Output 기본 노출 여부 정리

### QA

16. 단일 Tool
17. 연속 Tool
18. Tool 실패
19. HITL
20. Subagent
21. 병렬 Tool
22. 새로고침
23. 과거 대화
24. Preamble 미생성
25. 한국어/영어 질문

---

# 37. 관련 Repository 파일

## Project

- Main Repository<br>
  https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN29-FINAL-2TEAM/

- `services/agent_runtime/prompts.py`<br>
  https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN29-FINAL-2TEAM/blob/main/services/agent_runtime/prompts.py

- `services/agent_runtime/models/factory.py`<br>
  https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN29-FINAL-2TEAM/blob/main/services/agent_runtime/models/factory.py

- `services/agent_runtime/events.py`<br>
  https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN29-FINAL-2TEAM/blob/main/services/agent_runtime/events.py

- `services/agent_runtime/executor.py`<br>
  https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN29-FINAL-2TEAM/blob/main/services/agent_runtime/executor.py

- `apps/chat/api_views.py`<br>
  https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN29-FINAL-2TEAM/blob/main/apps/chat/api_views.py

- `frontend/src/api/chat.ts`<br>
  https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN29-FINAL-2TEAM/blob/main/frontend/src/api/chat.ts

- `frontend/src/pages/ChatPage/liveChat.ts`<br>
  https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN29-FINAL-2TEAM/blob/main/frontend/src/pages/ChatPage/liveChat.ts

- `frontend/src/pages/ChatPage/cardTypes.ts`<br>
  https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN29-FINAL-2TEAM/blob/main/frontend/src/pages/ChatPage/cardTypes.ts

- `frontend/src/pages/ChatPage/cards/ChatCards.tsx`<br>
  https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN29-FINAL-2TEAM/blob/main/frontend/src/pages/ChatPage/cards/ChatCards.tsx

- `frontend/src/pages/ChatPage/ChatPage.tsx`<br>
  https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN29-FINAL-2TEAM/blob/main/frontend/src/pages/ChatPage/ChatPage.tsx

---

# 38. 관련 Git Commit

## Reasoning UI 추가

`d90bf7840aeffd60517c8c5b158fd2b625bdf476`

- OpenAI Responses API Reasoning Summary 요청
- Reasoning 접이식 UI 추가

https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN29-FINAL-2TEAM/commit/d90bf7840aeffd60517c8c5b158fd2b625bdf476

---

## 영어 Reasoning 자동 노출 완화 + Tool Name 개선

`68626a8d5a5fd13eeedad8e1d87bad0b6d3f1eea`

- 실행 중 영어 Reasoning 자동 펼침 제거
- `tool_ref` 대신 사람이 읽는 `tool_name` 사용

https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN29-FINAL-2TEAM/commit/68626a8d5a5fd13eeedad8e1d87bad0b6d3f1eea

---

## Timeline Tool Name 개선

`7f95ea59d417a1af822ec279b4095801a95df233`

- Timeline에서도 내부 Tool Ref 대신 Human-readable Name 사용

https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN29-FINAL-2TEAM/commit/7f95ea59d417a1af822ec279b4095801a95df233

---

# 39. OpenAI 참고자료

## Reasoning Guide

OpenAI Reasoning 모델 및 Reasoning Summary 관련 공식 가이드.

https://developers.openai.com/api/docs/guides/reasoning

핵심 참고사항:

- Raw internal reasoning / Chain-of-Thought를 그대로 API로 제공하는 구조가 아님
- Reasoning Summary를 별도로 요청할 수 있음
- Reasoning Summary 언어를 `ko`로 강제하는 전용 공개 파라미터는 현재 문서상 확인되지 않음

---

## OpenAI Model Guidance — Preamble 참고

OpenAI의 GPT-5.2 Model Guidance에는 **Tool 호출 전에 짧은 user-visible explanation을 생성하는 Preamble 패턴**이 명시되어 있습니다.

https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.2

이번 구현의:

```text
User-visible Preamble
→ Tool Call
```

UX를 설계할 때 참고합니다.

단, 이것을 현재 프로젝트의 모든 모델/Provider가 동일한 응답 구조로 반환한다는 보장으로 해석하지 않습니다. 실제 `AIMessage` 형태는 구현 전에 프로젝트 환경에서 한 번 확인합니다.

---

## OpenAI API Reference

Responses API 및 Streaming Event 계약 확인.

https://developers.openai.com/api/reference

---

## Learning to reason with LLMs

Reasoning Model의 Raw Chain-of-Thought 비노출 배경 참고.

https://openai.com/index/learning-to-reason-with-llms/

---

# 40. 최종 판단

이번 작업은 **Reasoning 번역 기능 추가가 아니라 사용자용 Agent Execution UX 분리 작업**으로 정의하는 것이 가장 적절합니다.

목요일까지는:

```text
한국어 Preamble
+
agent_update
+
기존 Tool Timeline
+
작업 과정 UI
+
영어 Reasoning 기본 숨김
```

까지만 안정적으로 완료하는 것을 권장합니다.

현재 코드 구조를 기준으로 볼 때 대규모 재설계가 필요한 작업은 아니며, **기존 Event Stream을 최대한 유지하면서 사용자에게 노출되는 레이어만 명확히 분리하는 방식**이 가장 리스크가 낮습니다.

특히 구현 전에 **Tool Call이 있는 실제 AIMessage에서 Preamble이 어느 필드로 내려오는지 한 번 실측**한 뒤 작업을 시작하면 불필요한 시행착오를 크게 줄일 수 있습니다.
