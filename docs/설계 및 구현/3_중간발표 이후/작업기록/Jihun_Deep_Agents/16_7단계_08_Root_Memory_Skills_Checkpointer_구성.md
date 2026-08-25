# 16. 7단계 세부 08 — Root Memory·Skills·Checkpointer 구성

## 핵심 구분

| 기능 | 저장하는 것 | 유지 범위 |
|---|---|---|
| Memory | 사용자의 장기 선호와 기억 | 다른 대화에서도 유지 |
| Skills | 개인·팀 스킬 문서 | 다른 대화에서도 유지 |
| Checkpointer | 현재 대화의 Graph 상태 | 같은 채팅 세션에서 유지 |

```text
Memory
→ 사용자를 장기적으로 기억

Skills
→ 재사용할 작업 지침 제공

Checkpointer
→ 현재 실행 위치와 상태 기억
```

세 기능은 Root에만 직접 연결한다.

## 이 단계에서 하는 일

1. MemoryProvider가 있는지 확인한다.
2. 개인 Memory 경로를 준비한다.
3. Memory와 Skills가 공유할 Backend를 만든다.
4. 장기 저장용 PostgresStore를 준비한다.
5. Memory와 Skills 시스템 지침을 준비한다.
6. 개인·팀 Skills 경로를 Backend에 연결한다.
7. Memory 쓰기 방어와 잠금 미들웨어를 추가한다.
8. Checkpointer를 준비한다.
9. Root Graph에 전달할 `root_kwargs`와 `root_middleware`를 완성한다.

## 전체 동작 흐름

```text
Root 기본 설정 준비 완료
    ↓
MemoryProvider 확인
    ↓
├─ 없음
│  → Memory·Skills 장기 저장 구성 생략
│
└─ 있음
   ↓
Memory 경로 준비
   ↓
Skills 개인·팀 경로 준비
   ↓
하나의 CompositeBackend에 경로 결합
   ↓
PostgresStore 연결
   ↓
Memory·Skills 시스템 지침 준비
   ↓
Memory 쓰기 방어·잠금 추가
    ↓
CheckpointerProvider 확인
    ↓
├─ 없음
│  → Checkpointer 생략
│
└─ 있음
   → PostgresSaver 연결
    ↓
Root 전용 설정 완성
```

## Memory 구성

현재 장기 Memory는 `/memories/users/preferences.md` 같은 사용자 개인 선호를
저장한다.

```text
Memory
├─ memory paths
├─ CompositeBackend
├─ PostgresStore
├─ Memory system prompt
├─ MemoryWriteGuardMiddleware
└─ MemoryWriteLockMiddleware
```

```text
/memories/users/**
    ↓
StoreBackend
    ↓
PostgresStore
```

Memory namespace는 `team_id + agent_id + account_id`로 격리한다. 같은 파일 경로를
사용해도 다른 사용자나 다른 에이전트는 서로 다른 저장 공간을 본다.

## Skills 구성

```text
개인 Skill
→ account_id 기준 격리

팀 Skill
→ team_id 기준 공유
```

Memory의 `CompositeBackend`에 Skills 경로를 병합한다.

```text
CompositeBackend
├─ /memories/users/**  → 개인 Memory
├─ /skills/personal/** → 개인 Skill
└─ /skills/team/**     → 팀 Skill
```

MemoryProvider와 SkillsProvider가 모두 있을 때만 Skills를 연결한다. GP에는 같은
Skill source를 명시적으로 전달하고 Child에는 기본적으로 연결하지 않는다.

## Memory 쓰기 방어

`MemoryWriteGuardMiddleware`는 개인 Memory 쓰기 전에 Credential, 개인정보와
권한·보안 설정 서술을 검사해 거부한다.

`MemoryWriteLockMiddleware`는 같은 namespace와 파일 경로의 동시 쓰기를 Postgres
advisory lock으로 직렬화한다.

```text
기존 custom_middleware
→ MemoryWriteGuardMiddleware
→ MemoryWriteLockMiddleware
```

Guard에서 먼저 거부한 내용은 DB 잠금을 잡지 않는다.

## Checkpointer 구성

Checkpointer는 다음 Graph 상태를 PostgresSaver에 저장한다.

```text
대화 메시지 상태
모델·도구 루프 진행 상태
TODO 상태
HITL interrupt 상태
승인 후 재개할 위치
```

실행 시 `session_id`를 LangGraph `thread_id`로 사용해 같은 채팅의 상태를 이어간다.

```text
HITL interrupt
    ↓
Checkpointer에 상태 저장
    ↓
사용자 승인
    ↓
같은 session_id로 resume
    ↓
저장된 위치부터 재개
```

Checkpointer가 없으면 재개할 수 없으므로 HITL도 구성하지 않는다.

## Memory와 Checkpointer의 차이

```text
Memory
→ 사용자가 누구이며 무엇을 선호하는가
→ 다른 채팅에서도 사용

Checkpointer
→ 이 채팅이 어디까지 진행됐는가
→ 같은 채팅에서 사용
```

## Root와 Child 차이

```text
Root
→ Memory·Skills·Store·Checkpointer 직접 연결

Child
→ 별도 Memory·Skills·Store·Checkpointer 없음
```

Child의 실행 상태는 상위 Root Graph를 통해 관리한다.

## 이 단계의 결과

```text
root_kwargs
├─ memory
├─ backend
├─ store
├─ memory_system_prompt
├─ skills
├─ skills_system_prompt
└─ checkpointer
```

```text
root_middleware
├─ 기존 custom_middleware
├─ MemoryWriteGuardMiddleware
└─ MemoryWriteLockMiddleware
```

## 각 동작을 확인할 파일

| 동작 | 확인할 파일 |
|---|---|
| Root 전용 구성 전체 | `services/agent_runtime/factory.py` |
| Memory Provider | `services/agent_runtime/memory/provider.py` |
| Memory Backend | `services/agent_runtime/memory/backend.py` |
| Memory Store | `services/agent_runtime/memory/store.py` |
| Memory 쓰기 방어 | `services/agent_runtime/memory/write_guard.py` |
| Memory 쓰기 잠금 | `services/agent_runtime/memory/write_lock.py` |
| Skills Provider | `services/agent_runtime/skills/provider.py` |
| Skills Backend | `services/agent_runtime/skills/backend.py` |
| Checkpointer Provider | `services/agent_runtime/checkpoint/provider.py` |
| Postgres Checkpointer | `services/agent_runtime/checkpoint/checkpointer.py` |
