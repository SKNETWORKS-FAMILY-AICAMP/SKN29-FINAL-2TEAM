# 0. 전체 Agent 실행 흐름

Claw Code의 전체적인 동작은 다음과 같이 이해할 수 있다.

```text
사용자 요청
   ↓
이번 작업을 수행할 Agent 준비
   ↓
┌─────────────────────────────┐
│        Agent Runtime        │
│                             │
│  대화 내용                    │
│  시스템 지침                  │
│  사용할 Tool                 │
│  권한 설정                    │
│  현재 Session 상태            │
└──────────────┬──────────────┘
               ↓
              LLM
               ↓
        "무엇을 해야 하지?"
               ↓
       ┌───────┴────────┐
       │                │
    답변이면          Tool이 필요하면
       │                │
       ↓                ↓
    최종 답변       Tool 실행
                        ↓
                    결과 반환
                        ↓
                       LLM
                        ↓
                 다시 판단
                        ↓
                  필요하면 반복
```

핵심은 **Runtime이 Agent 실행을 관리하고, LLM은 주어진 Context를 보고 다음 행동을 결정하며, Tool이 필요하면 Tool을 실행한 결과를 다시 LLM에게 전달하는 구조**라는 것이다.

---

# 1. Architecture

### 질문

> 전체적으로 어떤 컴포넌트가 있는가? 폴더/모듈 구조는 어떻게 나뉘어 있는가? 진입점(entry point)은 어디인가?

Claw Code는 기능을 Rust `crate` 단위로 나눠 관리한다.

| crate              | 하는 일                                                      |
| ------------------ | --------------------------------------------------------- |
| `api`              | AI 모델과 통신                                                 |
| `runtime`          | 대화 루프, Session, Tool 실행, MCP, Permission 등 핵심 Agent 실행 로직 |
| `tools`            | Agent가 사용할 각종 Tool                                        |
| `claw-rag-service` | 코드베이스 검색                                                  |
| `plugins`          | Plugin 관리                                                 |
| `telemetry`        | 사용량·로그 등 관측 기능                                            |
| `rusty-claude-cli` | 실제 CLI 프로그램. 위 crate들을 가져와 전체 프로그램으로 조립                   |

즉 하나의 프로그램 안에 모든 기능을 넣기보다,

```text
CLI
 ↓
Runtime
 ├── API / Model
 ├── Tools
 ├── MCP
 ├── Permission
 └── Session
```

처럼 역할을 나누어 놓은 구조다.

**핵심:** `runtime`이 Agent 실행의 중심이고, `rusty-claude-cli`가 각 기능을 실제 프로그램으로 조립하는 진입점 역할을 한다.

---

# 2. Agent Runtime

### 질문

> Agent 실행을 누가 관리하는가? 실행 단위는 무엇이고 여러 실행은 어떻게 관리하는가?

Claw Code에서 **Runtime은 Agent가 LLM과 대화하고 Tool을 실행하는 전체 실행 환경을 관리하는 역할**을 한다.

터미널에서 Claw Code를 실행하면 하나의 실행 환경 안에 다음 정보가 함께 관리된다.

* 현재 Session
* 사용 중인 LLM
* System Prompt
* Tool Executor
* Permission Policy
* 현재 실행에 필요한 설정

즉 Runtime은 단순히 "LLM을 한 번 호출하는 객체"가 아니라,

> **하나의 Agent가 작업을 수행하기 위해 필요한 실행 환경 전체를 관리하는 객체**

라고 이해하면 된다.

여러 실행은 서로 다른 Session과 작업 폴더를 기준으로 분리되어 관리된다.

---

# 3. Agent Loop

### 질문

> LLM → Tool → Result → LLM이 어떻게 반복되는가? 종료 조건은 무엇인가?

기본적인 흐름은 다음과 같다.

```text
사용자 입력
    ↓
대화 기록에 저장
    ↓
대화 기록 + System Prompt
    ↓
LLM 호출
    ↓
Tool 호출이 있는가?
    │
 ┌──┴───┐
 No     Yes
 │       │
 ↓       ↓
최종    Permission 확인
답변     ↓
         Tool 실행
            ↓
         실행 결과를
         대화 기록에 추가
            ↓
           LLM
            ↓
         다시 판단
```

즉 LLM이 한 번 답하고 끝나는 것이 아니라,

> **LLM이 다음 행동을 결정 → Tool 실행 → 결과를 Context에 추가 → 다시 LLM 호출**

을 반복한다.

Tool 호출이 없는 LLM 응답이 나오면 해당 응답을 최종 답변으로 처리한다.

Claw Code에는 최대 반복 횟수를 제한하는 기능이 준비되어 있지만, 현재 CLI 실행 경로에서는 이 제한을 사용하지 않아 **Tool 호출이 끝날 때까지 반복되는 구조**다.

### 권한(Permission) 확인은 정확히 어떻게 되는가
 
도구를 실행해도 되는지는 딱 하나의 값으로 정해지는 게 아니라, "지금 전체적으로 어느 정도 권한 모드로 실행 중인가"와 "이 도구는 원래 얼마만큼의 권한이 필요한가"를 비교하고, 여기에 사용자가 설정한 추가 규칙(무조건 허용/무조건 거부/꼭 물어보기 목록)까지 같이 확인해서 최종적으로 허용(Allow) 또는 거부(Deny) 둘 중 하나로 결론 내요.
 
| 값 | 의미 |
|---|---|
| `ReadOnly` | 읽기만 가능 |
| `WorkspaceWrite` | 지금 작업 폴더 안에서는 쓰기(파일 수정 등)도 가능 |
| `DangerFullAccess` | 셸 명령 실행처럼 위험할 수 있는 것까지 허용 |
| `Prompt` | 애매한 상황이면 항상 사용자에게 먼저 물어보는 모드 |
| `Allow` | 규칙에서 허용된 건 묻지 않고 바로 통과시키는 모드 |

---

# 4. Context

### 질문

> LLM에 어떤 정보를 넣는가? Context가 커지면 어떻게 처리하는가?

LLM에 전달되는 핵심 정보는 크게 두 가지다.

### ① System Prompt

AI가 따라야 하는 규칙과 현재 환경 정보를 담는다.

예:

* Agent가 따라야 할 지침
* 사용 가능한 환경 정보
* 프로젝트 지시사항
* Tool 사용 관련 정보

### ② 대화 기록

지금까지 발생한 내용을 시간순으로 가지고 있다.

```text
사용자 요청
→ LLM 응답
→ Tool 호출
→ Tool 결과
→ LLM 응답
→ ...
```

매 반복마다 이 정보를 모아 LLM에 다시 전달한다.

### Context가 너무 커지면?

대화 기록이 일정 크기를 넘으면 **Compaction**이 발생한다.

Claw Code에서는 대화 기록 중 최근 4개 메시지는 원문으로 유지하고, 그보다 오래된 메시지는 하나의 요약 정보로 압축한다.

요약에는 다음과 같은 정보가 포함될 수 있다.

* 최근 사용자 요청
* 사용한 Tool
* 주요 파일
* 이전 작업의 핵심 내용

즉 모든 과거 대화를 그대로 계속 전달하는 것이 아니라,

```text
오래된 대화
    ↓
요약
    ↓
최근 대화 + 요약
    ↓
LLM
```

형태로 Context 크기를 관리한다.

---

# 5. Codebase 탐색 (Retrieval)

### 질문

> 프로젝트 전체를 어떻게 탐색하는가? 필요한 코드만 Context에 가져오는가?

Claw Code는 프로젝트 전체 코드를 처음부터 LLM Context에 넣지 않는다.

LLM이 필요할 때 검색 Tool을 호출해 필요한 코드만 찾아본다.

| Tool         | 역할                |
| ------------ | ----------------- |
| `GlobSearch` | 파일 이름·경로 검색       |
| `GrepSearch` | 파일 내용에서 문자열·패턴 검색 |
| `ReadFile`   | 찾은 파일의 실제 내용 읽기   |
| `ToolSearch` | 필요한 Tool 자체 검색    |

흐름은 다음과 같다.

```text
사용자 요청
    ↓
LLM
    ↓
"관련 코드를 찾아야겠다"
    ↓
GlobSearch / GrepSearch
    ↓
관련 파일 발견
    ↓
ReadFile
    ↓
파일 내용
    ↓
Context
    ↓
LLM
```

중요한 점은 **코드 검색의 검색어 자체도 LLM이 결정한다는 것**이다.

예를 들어 사용자가 "권한 처리가 어디에 있어?"라고 하면 LLM이 `permission`, `required_permission` 등의 검색어를 만들어 검색 Tool에 전달한다.

따라서 기본적인 코드 탐색은 "임베딩 유사도 Top-K 검색"보다는 **LLM이 검색 Tool을 선택하고 검색어를 만들어 반복적으로 탐색하는 방식**에 가깝다.

---

# 6. State

### 질문

> 실행 중인 Agent 상태는 어디에서 관리하는가?

Claw Code에서는 하나의 객체에 모든 상태를 넣기보다 목적에 따라 나눠 관리한다.

| 상태                    | 의미                                                           |
| --------------------- | ------------------------------------------------------------ |
| `Session`             | 지금까지의 대화와 세션 정보                                              |
| `ConversationRuntime` | LLM, Tool Executor, Permission, Prompt 등 Agent 실행에 필요한 전체 환경 |
| `PermissionContext`   | 특정 Tool 실행 시 필요한 권한 판단 정보                                    |
| `Worker`              | 하위 작업자의 현재 상태                                                |

쉽게 구분하면:

```text
Session
→ "무슨 대화를 했는가?"

ConversationRuntime
→ "이 Agent를 어떻게 실행하고 있는가?"

PermissionContext
→ "지금 이 Tool을 실행해도 되는가?"

Worker
→ "하위 작업이 지금 어디까지 진행됐는가?"
```

---

# 7. Memory

### 질문

> 장기/단기 기억을 어떻게 관리하는가? 세션이 끝나도 남는 정보가 있는가?

Claw Code에서 세션이 끝난 뒤에도 남을 수 있는 정보는 크게 세 종류로 볼 수 있다.

### ① Session 파일

현재 대화 내용을 디스크에 저장한다.

따라서 이후 `--resume` 등을 이용해 이전 대화를 다시 이어갈 수 있다.

```text
대화
 ↓
Session 파일 저장
 ↓
프로그램 종료
 ↓
다시 실행
 ↓
Session 복원
```

### ② 프로젝트 지시 파일

예:

```text
CLAUDE.md
AGENTS.md
```

사람이 프로젝트에 대한 규칙이나 지식을 직접 작성해두는 파일이다.

새로운 대화를 시작해도 프로젝트 지침으로 다시 읽어들일 수 있다.

### ③ 설정 파일

예:

```text
.claw.json
settings.json
```

모델, 기능, 실행 옵션 등의 구조화된 설정을 저장한다.

즉 Claw Code의 Memory는 하나의 Vector DB에 모든 것을 저장하는 형태라기보다,

> **대화(Session) / 사람이 작성한 프로젝트 지침 / 시스템 설정을 서로 다른 방식으로 영속화**

하는 구조에 가깝다.

---

# 8. Tool Calling

### 질문

> Tool을 어떻게 등록하고 실행하는가? 승인이 필요한 Tool은 어떻게 구분하는가?

먼저 두 가지 개념을 구분해야 한다.

### Tool Spec

> **하나의 Tool이 무엇을 하고 어떤 입력을 받는지 정의한 설명서**

예:

```text
Tool 이름
Tool 설명
입력값 형식
필요 권한
```

### Tool Registry

> **Agent가 사용할 수 있는 Tool들을 등록하고 관리하는 목록**

전체 흐름은 다음과 같다.

```text
① Tool Spec 정의
        ↓
② Tool Registry에 등록
        ↓
③ LLM에게 사용 가능한 Tool 정보 전달
        ↓
④ LLM이 Tool Call 생성
        ↓
⑤ Permission 검사
        ↓
⑥ 실제 Tool 실행
        ↓
⑦ 실행 결과를 LLM에 전달
```

Tool마다 단순히 `승인 필요 = true/false`를 가지고 있는 것이 아니다.

Tool이 요구하는 권한과 현재 Permission Mode, 추가 규칙을 종합해 실행 여부를 결정한다.

예:

```text
ReadFile
→ 읽기 권한 필요

WriteFile
→ 작업 폴더 쓰기 권한 필요

Bash
→ 더 높은 권한이 필요할 수 있음
```

즉,

> **Tool 등록 → LLM에게 노출 → Tool Call → Permission 확인 → 실행**

의 구조다.

---

# 9. 실행 환경 (Sandbox)

### 질문

> 파일/명령 실행 환경은 어디인가? 작업 디렉토리와 Shell 접근 범위는 어떻게 제한하는가?

여기서는 **Permission과 Sandbox를 구분해야 한다.**

```text
Permission
→ "이 Tool을 실행해도 되는가?"

Sandbox
→ "실행한다면 어디까지 접근할 수 있는가?"
```

명령 실행에는 두 단계의 방어가 있다.

### ① 실행 전 검사

실제 명령을 실행하기 전에 명령어 문자열을 분석한다.

예:

* 경로 탈출 시도
* 파괴적인 명령
* 위험한 패턴

등을 검사한다.

### ② 실제 실행 환경 격리

Linux 환경에서는 `unshare` 등을 사용해 실행 환경을 분리한다.

이를 통해 프로세스의 네트워크·파일시스템 접근 범위를 제한할 수 있다.

즉:

```text
AI가 명령 실행
    ↓
위험 명령인지 검사
    ↓
실행 환경의 접근 범위 제한
    ↓
실제 명령 실행
```

이라는 **이중 방어 구조**로 이해할 수 있다.

---

# 10. MCP

### 질문

> MCP를 어떻게 연결하는가? 서버 설정과 Tool 이름 충돌은 어떻게 처리하는가?

Claw Code는 **MCP Client와 MCP Server 역할을 모두 지원한다.**

### MCP Client

외부 MCP Server에 연결해 그 Server가 제공하는 Tool을 가져온다.

연결 방식도 여러 가지를 지원한다.

* Stdio
* SSE/HTTP
* WebSocket
* SDK
* Managed Proxy

기본적인 흐름은:

```text
MCP Server
    ↓
"내가 제공하는 Tool은 이것들이다"
    ↓
MCP Client
    ↓
McpToolRegistry
    ↓
Claw Code의 Tool 실행 경로
```

가 된다.

MCP Server에서 가져온 Tool도 Claw Code 안에서는 Agent가 사용할 수 있는 Tool로 연결된다.

### Tool 이름 충돌

여러 MCP Server에서 같은 Tool 이름을 제공할 수 있기 때문에 서버 이름을 포함한 이름으로 관리한다.

```text
mcp__서버이름__tool이름
```

예:

```text
mcp__github__search_pr
mcp__slack__search_pr
```

처럼 구분한다.

따라서 MCP Tool도 등록된 이후에는 Agent 입장에서 일반 Tool과 비슷한 방식으로 호출할 수 있다.

---

# 11. Model

### 질문

> LLM을 어떤 인터페이스로 연결하는가? 몇 개 Provider를 지원하는가?

Claw Code는 **`ApiClient`라는 공통 인터페이스를 통해 LLM Provider를 추상화**한다.

현재 Provider 분기는 크게 다음 세 가지다.

```text
Anthropic
Xai
OpenAi
```

여기서 `OpenAi`는 OpenAI만 의미하는 것이 아니라 OpenAI-compatible API를 사용하는 서비스까지 포함한다.

예:

* OpenAI
* Ollama
* DashScope
* 기타 OpenAI-compatible endpoint

전체 흐름은 다음과 같다.

```text
사용자가 모델 지정
예: opus / grok / llama3.2
        ↓
resolve_model_alias()
        ↓
실제 모델 ID 결정
        ↓
detect_provider_kind()
        ↓
Anthropic / Xai / OpenAi 결정
        ↓
Provider Client 생성
        ↓
AnthropicRuntimeClient
        ↓
ApiClient 인터페이스
        ↓
ConversationRuntime
```

중요한 점은 `ConversationRuntime`이 실제로 어떤 Provider를 사용하는지 직접 알 필요가 없다는 것이다.

```text
ConversationRuntime
        ↓
    ApiClient
        ↓
실제 Provider
```

로 분리되어 있기 때문이다.

따라서 **Agent Loop와 Model Provider가 분리된 구조**라는 점이 우리 Harness에서 참고할 만한 부분이다.

---

# 12. Sub-agent

### 질문

> 다른 Agent를 호출할 수 있는가? 어떤 기준으로 위임하고 결과는 어떻게 돌아오는가?

Claw Code에서는 Main Agent가 여러 개의 **Task/Worker Tool을 조합해 작업을 위임**한다.

단순히:

```text
Agent Tool 호출
→ Sub-agent 실행
→ 결과 반환
```

으로 끝나는 구조가 아니다.

여러 Tool을 이용해 Worker의 상태를 단계적으로 관리한다.

```text
Main Agent
    ↓
"이 작업을 위임하자"
    ↓
WorkerCreate
    ↓
WorkerObserve / WorkerResolveTrust
    ↓
WorkerSendPrompt
    ↓
Worker 작업
    ↓
WorkerObserveCompletion
    ↓
TaskOutput / WorkerGet
    ↓
Main Agent가 결과 조회
```

### 중요한 특징 ① 여러 Tool을 조합한다

Task/Worker 관련 기능이 여러 개의 Tool로 나뉘어 있다.

예:

```text
TaskCreate
TaskGet
TaskList
TaskStop
TaskUpdate
TaskOutput

WorkerCreate
WorkerObserve
WorkerResolveTrust
WorkerAwaitReady
WorkerSendPrompt
WorkerRestart
WorkerTerminate
WorkerObserveCompletion
```

즉 Sub-agent를 하나의 Tool로 처리하기보다 **작업의 생명주기를 여러 Tool로 관리하는 구조**다.

### 중요한 특징 ② 전체 Context를 복사하지 않는다

Worker에게 전달되는 정보는 작업에 필요한 정보 중심이다.

예:

```text
objective
scope
repo
branch_policy
acceptance_tests
commit_policy
reporting_contract
escalation_policy
```

또는:

```text
prompt
task_receipt
```

등이다.

반면 Main Agent의 전체 `Session.messages`를 그대로 전달하는 필드는 없다.

따라서:

> **Sub-agent는 Main Agent의 전체 대화를 그대로 물려받는 것이 아니라, 작업 목표와 필요한 메타데이터를 전달받아 새로운 작업으로 시작하는 구조에 가깝다.**

### 중요한 특징 ③ 결과가 자동으로 돌아오지 않는다

일반 Tool Calling은:

```text
LLM
 ↓
Tool
 ↓
결과
 ↓
LLM
```

이지만 Worker는:

```text
Worker 생성
 ↓
작업 진행
 ↓
완료 여부 조회
 ↓
결과 조회
 ↓
Main Agent
```

와 같이 **상태 조회와 결과 조회가 별도로 이루어지는 구조**다.

즉 Sub-agent는 단순 Tool보다 **장시간 실행되는 작업 단위**에 가깝게 설계되어 있다.

---

# 13. Error / Retry

### 질문

> Tool·LLM 실패를 어떻게 처리하는가? 재시도 정책과 반복 실패 시 처리는?

실패 종류에 따라 처리 방식이 다르다.

| 실패                         | 처리                      |
| -------------------------- | ----------------------- |
| LLM API                    | 자동 재시도, 최대 8회, 지수 백오프   |
| 일반 Tool                    | 자동 재시도하지 않고 오류를 LLM에 전달 |
| Worker/MCP/Plugin 등 구조적 장애 | 상황별 복구 절차 수행            |

예를 들어:

| 상황               | 자동 복구                      |
| ---------------- | -------------------------- |
| Trust Prompt 문제  | 자동 수락 시도                   |
| Prompt 전달 실패     | 프롬프트 재전달                   |
| 오래된 Branch       | Rebase + Clean Build       |
| Build 실패         | Clean Build                |
| MCP Handshake 실패 | 일정 시간 동안 재시도               |
| Plugin 시작 실패     | Plugin 재시작 + Handshake 재시도 |
| Provider 장애      | Worker 재시작                 |

복구가 실패하면 상황에 따라:

* 사용자에게 알림
* 실행 중단
* 로그만 남기고 계속 진행

등으로 처리한다.

핵심은 **모든 오류를 동일하게 재시도하지 않고 오류 종류에 따라 복구 전략을 다르게 적용한다는 것**이다.

---

# 14. Checkpoint

### 질문

> 중간 실행 상태를 저장하고 재개할 수 있는가? 저장 시점과 단위는 무엇인가?

Claw Code는 실행 중간 상태를 저장하고 이후 다시 이어서 실행할 수 있다.

특히 중요한 점은 **턴이 끝날 때만 저장하는 것이 아니라 메시지가 추가될 때마다 저장한다는 것**이다.

```text
사용자 메시지 추가
    ↓
저장

LLM 응답 추가
    ↓
저장

Tool 결과 추가
    ↓
저장
```

저장 형식은 JSONL이며 메시지 하나가 하나의 줄을 차지한다.

| 항목    | 내용                         |
| ----- | -------------------------- |
| 저장 시점 | 메시지 1개가 추가될 때마다            |
| 저장 단위 | Session 파일                 |
| 형식    | JSONL                      |
| 파일 크기 | 256KB 초과 시 Rotation        |
| 이전 파일 | 최대 3개 보관                   |
| 재개    | 최신 세션 / Session ID / 파일 경로 |
| 세션 분리 | 작업 폴더 fingerprint 기준       |
| Fork  | 새 Session ID를 만들어 분기       |

따라서 Agent가 중간에 종료되더라도 **마지막까지 저장된 Session을 기반으로 작업을 다시 이어갈 수 있다.**

---

# 15. 우리 Harness에 적용할 것 / 적용하지 않을 것과 이유

Claw Code의 모든 구조를 그대로 가져오는 것이 아니라, 우리 Harness의 규모와 목적에 필요한 부분만 적용한다.

## 적용할 것

### ① Runtime과 Model Interface 분리

```text
Agent Runtime
      ↓
Model Interface
      ↓
Claude / GPT / Gemini 등
```

**이유:**
Agent Loop를 특정 LLM Provider에 종속시키지 않기 위해서다.

---

### ② Agent Loop 구조

```text
LLM
 ↓
Tool Call
 ↓
Permission
 ↓
Tool 실행
 ↓
Result
 ↓
LLM
```

**이유:**
우리 Harness의 기본 Agent 실행 구조로 가장 직접적으로 활용할 수 있다.

---

### ③ Tool Spec + Tool Registry

```text
Tool Spec
 ↓
Tool Registry
 ↓
LLM에 Tool 목록 제공
 ↓
Tool Call
```

**이유:**
Tool이 늘어나더라도 Agent Runtime과 개별 Tool을 분리해서 관리할 수 있다.

---

### ④ Permission과 Tool 실행 분리

```text
Tool Call
 ↓
Permission
 ↓
Tool Executor
```

**이유:**
AI가 Tool을 호출할 수 있는 것과 실제 실행할 수 있는 것을 분리하면 안전성과 관리성이 높아진다.

---

### ⑤ 필요한 코드만 가져오는 Code Retrieval

```text
검색
 ↓
관련 파일
 ↓
Read
 ↓
Context
```

**이유:**
전체 Repository를 Context에 넣지 않고 필요한 코드만 가져오므로 Context 비용을 줄일 수 있다.

---

### ⑥ Session 기반 Checkpoint

**이유:**
Agent 작업이 길어질 경우 중간에 종료되어도 작업을 이어갈 수 있어야 한다.

다만 Claw Code처럼 메시지마다 파일에 저장하는 방식은 우리 MVP에서는 필요성을 검토한 뒤 적용한다.

---

### ⑦ 장시간 작업을 위한 Task 상태 관리

Claw Code의 Worker 구조에서 참고할 부분이다.

```text
Created
 ↓
Running
 ↓
Completed / Failed
```

**이유:**
우리 프로젝트에서도 Agent가 여러 작업을 수행하게 되면 단순한 동기 Tool 호출만으로는 관리하기 어렵다.

---

## 적용하지 않을 것

### ① Claw Code의 복잡한 Worker 상태 머신 전체

```text
WorkerCreate
→ Observe
→ ResolveTrust
→ SendPrompt
→ AwaitReady
→ ObserveCompletion
→ Output
```

**이유:**
우리 MVP에서는 Agent 작업이 Claw Code만큼 복잡하거나 장시간 실행되는 구조가 아니므로 초기부터 동일한 상태 머신을 구현하면 복잡도만 증가한다.

필요해질 경우 Task 상태 관리부터 단계적으로 확장한다.

---

### ② Claw Code의 모든 Provider 호환 구조

OpenAI-compatible API까지 포함한 복잡한 Provider 처리 구조를 그대로 가져오지는 않는다.

**이유:**
우리 서비스에서 실제 사용할 Model Provider부터 추상화하고, 필요한 시점에 Provider를 추가하는 것이 적절하다.

---

### ③ 복잡한 Sandbox 구현 전체

Claw Code의 `unshare` 기반 격리와 다양한 Shell 보안 정책을 그대로 구현하지 않는다.

**이유:**
우리 Harness의 실행 환경과 보안 요구사항이 다르기 때문이다. MVP에서는 실행 가능한 Tool의 범위를 제한하고, 필요한 경우 별도 Sandbox를 도입한다.

---

### ④ Claw Code의 모든 Memory 구조

CLAUDE.md, AGENTS.md 등 Claw Code의 프로젝트 지시 체계를 그대로 복제하지 않는다.

**이유:**
우리 Harness에서는 프로젝트 문서와 RAG를 이미 별도의 Context 공급원으로 관리할 수 있기 때문이다.

---

## 최종적으로 가져갈 구조

우리 Harness에서는 Claw Code의 구조를 참고하되 다음 정도로 단순화한다.

```text
                    User Request
                         ↓
                 ┌──────────────┐
                 │ Agent Runtime│
                 │              │
                 │ Context      │
                 │ Session      │
                 │ Permission   │
                 └──────┬───────┘
                        ↓
                  Model Interface
                        ↓
                 Claude / GPT ...
                        ↓
                  Tool Call 판단
                        ↓
                 ┌──────┴──────┐
                 │             │
              Final         Tool Call
                 │             │
                 │        Permission
                 │             ↓
                 │        Tool Registry
                 │             ↓
                 │        Tool Executor
                 │             ↓
                 │          Result
                 │             │
                 └─────────────┘
                        ↓
                       LLM
```

**핵심적으로 가져갈 것은 `Runtime / Context / Model Interface / Tool Registry / Permission / Session`의 분리이고, Claw Code의 복잡한 Worker 상태 머신이나 전체 Sandbox 구조는 우리 서비스의 필요성이 확인된 뒤 단계적으로 적용한다.**
