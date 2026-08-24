# 8단계 — 스트림 입력과 LangGraph 실행 설정 구성

## 이 단계에서 하는 일

완성된 Root Graph를 어떤 대화 상태로, 어떤 스트림 방식으로 실행할지 설정한다. 이 단계의 마지막에 `runtime.stream()`이 호출되면서 실제 Deep Agents 실행이 시작된다.

## 전체 동작

```text
사용자 입력·세션 ID·이전 대화
추적 콜백·동시 실행 제한
        ↓
DeepAgentStreamAdapter.stream()
        ↓
입력 상태와 LangGraph config 구성
        ↓
스트림 구독 방식 구성
        ↓
runtime.stream()
```

## 추적 설정

설정된 경우 Langfuse와 LangSmith 콜백을 생성한다. 콜백이 있으면 세션, 계정, 팀, Agent 식별 정보를 추적 메타데이터로 전달한다.

외부 추적 서비스로 보내는 입력과 출력의 사본에는 이메일, credential, 주민등록번호, 카드번호, 전화번호 등의 마스킹을 적용한다. 실제 Agent 입력과 사용자 응답은 변경하지 않는다.

콜백 생성이나 추적 기록이 실패해도 Agent 실행은 계속한다.

## 입력 메시지 구성

### 세션이 있는 경우

이번 사용자 메시지만 `input_state`에 넣는다. 이전 대화는 같은 `thread_id`의 Checkpointer 상태에 이미 들어 있기 때문이다.

```text
Checkpointer의 이전 상태 + 이번 사용자 메시지
```

### 세션이 없는 경우

Checkpointer에서 이전 상태를 찾을 수 없으므로 조회해 둔 이전 대화와 이번 메시지를 함께 넣는다.

```text
conversation_messages + 이번 사용자 메시지
```

## LangGraph 실행 설정

우리 프로젝트의 `session_id`를 LangGraph의 `configurable.thread_id`로 사용한다. Runtime 정책의 `max_concurrency`도 전달해 동시 Tool Call 수를 제한하고, 초과한 호출은 버리지 않고 대기시킨다.

## 스트림 구독

```python
stream_mode = ["updates", "custom", "messages"]
subgraphs = True
```

| 설정 | 받는 정보 |
|---|---|
| `updates` | Graph 노드가 끝난 뒤 변경된 상태 |
| `custom` | 도구가 직접 보내는 진행 이벤트 |
| `messages` | 모델이 생성하는 토큰과 reasoning 조각 |
| `subgraphs=True` | Root뿐 아니라 GP·Child 내부 이벤트와 namespace |

## 최종 실행 형태

```text
input_state
└─ messages

stream_kwargs
├─ stream_mode: updates, custom, messages
├─ subgraphs: true
└─ config
   ├─ configurable.thread_id
   ├─ max_concurrency
   ├─ callbacks
   └─ metadata
```

준비된 값을 `runtime.stream(input_state, **stream_kwargs)`에 전달하면서 실제 Runtime 실행이 시작된다.

## 단계 종료 상태

- 사용자 입력 상태 구성 완료
- Checkpointer thread 연결 완료
- 추적 콜백 연결 완료
- 동시 실행 제한 적용 완료
- Root·Child 스트림 구독 설정 완료
- `runtime.stream()` 실행 시작

## 봐야 할 파일

| 확인할 내용 | 파일 |
|---|---|
| 실행 설정을 Stream Adapter에 전달 | `services/agent_runtime/executor.py` |
| 입력 상태, config와 스트림 모드 구성 | `services/agent_runtime/stream_adapter.py` |
| Langfuse·LangSmith 콜백 | `services/agent_runtime/tracing/callbacks.py` |
| 외부 반출 데이터 마스킹 | `services/agent_runtime/sensitive_text.py` |
| 동시 실행 정책 | `services/agent_runtime/runtime_policy.py` |
| 도구의 custom 진행 이벤트 | `services/agent_runtime/tools/adapters.py` |
| messages·namespace 해석 기반 | `services/agent_runtime/events.py` |
