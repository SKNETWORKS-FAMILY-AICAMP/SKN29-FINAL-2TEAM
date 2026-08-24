# 14. 7단계 세부 06 — Child Graph 조립

## 이 단계에서 하는 일

1. Root 정의에 포함된 Child 목록을 순회한다.
2. Child 정의를 독립적인 `AgentDefinition`으로 변환한다.
3. Child가 다른 Child를 갖지 못하도록 설정한다.
4. Child의 모델·도구·HITL·미들웨어를 준비한다.
5. Deep Agents를 호출해 Child Graph를 만든다.
6. Child Graph에 위임용 `alias`와 설명을 연결한다.
7. 완성된 Child들을 Root Graph에 전달할 목록으로 모은다.

## 전체 동작 흐름

```text
Root의 SubagentDefinition 목록
    ↓
Child 하나 선택
    ↓
Child용 AgentDefinition 생성
    ↓
AgentRuntimeFactory.build(allow_subagents=False)
    ↓
Child 모델·도구 준비
    ↓
Child HITL·미들웨어 준비
    ↓
Child 시스템 프롬프트 조립
    ↓
create_child_graph()
    ↓
Deep Agents create_deep_agent()
    ↓
Compiled Child Graph
    ↓
alias와 위임 설명 연결
    ↓
CompiledSubAgent
    ↓
다음 Child 반복
    ↓
compiled_children 완성
```

## Child 정의 변환

```text
SubagentDefinition
├─ 실행 설정
├─ alias
└─ delegation_description
```

Graph 생성 전 일반 `AgentDefinition`으로 변환하며 다음 값을 비운다.

```text
subagents = ()
```

Child가 다시 다른 Child에게 위임하지 못하게 하는 설정이다.

## 재귀적인 Factory 호출

```text
Root build
    ↓
Child마다 build 재호출
    ↓
allow_subagents=False
```

Child도 모델 설정 해석, 모델 객체 생성, 도구 로딩, StructuredTool 변환, HITL,
커스텀 미들웨어와 프롬프트 조립을 거친다. `allow_subagents=False`이므로 Root가
아닌 Child Graph 생성 경로로 빠진다.

## Child Graph 입력

```text
create_child_graph
├─ model
├─ system_prompt
├─ tools
├─ middleware
├─ fs_excluded_tools
└─ interrupt_on
```

## Child에 직접 연결되지 않는 기능

```text
장기 MemoryProvider 없음
SkillsProvider 없음
Store 없음
별도 Checkpointer 없음
Memory Write Guard 없음
Memory Write Lock 없음
사용자 정의 Child 목록 없음
```

Child는 상위 Root Graph 실행 컨텍스트 안에서 실행되므로 별도 Checkpointer를
만들지 않는다. Filesystem은 장기 Memory Backend가 아니라 Deep Agents 기본
`StateBackend` 범위로 사용한다.

## Child HITL

Child 도구 중 `side_effect=True`인 도구가 있으면 Child Graph에도
`interrupt_on`을 전달한다.

```text
Child 모델이 쓰기 도구 선택
    ↓
Child Graph에서 HITL interrupt
    ↓
Root 실행 전체가 승인 대기
```

## Child 기본 미들웨어 조립

```text
Child custom_middleware
    ↓
create_child_graph()
    ↓
Filesystem 설정 추가
    ↓
create_deep_agent()
    ↓
Deep Agents 기본 미들웨어와 결합
    ↓
Compiled Child Graph
```

Child는 `subagents=[]`로 생성되므로 재위임용 SubAgent 기능은 구성하지 않는다.

## `CompiledSubAgent`

```text
CompiledSubAgent
├─ name         ← alias
├─ description  ← delegation_description
└─ runnable     ← Child Graph
```

Root는 `name`과 `description`을 보고 위임 대상을 고르고 `runnable`을 실행한다.

## Child별 실제 모델 설정

```text
child_resolved_models
{
    alias: ResolvedModelConfig
}
```

이 값은 Child가 실제 실행될 때 `subagent_started` 이벤트에 실제 provider와
endpoint hash를 넣는 데 사용한다.

## 모든 Child는 미리 조립된다

```text
Root Graph 조립 시점
    ↓
모든 Child Graph 미리 조립
    ↓
Root Graph에 연결
```

실제 위임 여부와 관계없이 연결된 Child의 정의·모델·도구·미들웨어 조립은 이
시점에 완료된다. 모델 API와 도구 handler는 아직 호출하지 않는다.

## 이 단계의 결과

```text
compiled_children
→ Root Graph에 연결할 CompiledSubAgent 목록

child_resolved_models
→ Child alias별 실제 모델 설정
```

## 각 동작을 확인할 파일

| 동작 | 확인할 파일 |
|---|---|
| Child 목록 순회와 재귀 Factory 호출 | `services/agent_runtime/factory.py` |
| `SubagentDefinition` 변환 | `services/agent_runtime/subagents/builder.py` |
| Child Graph 생성 | `services/agent_runtime/compat/deepagents_v075.py` |
| Child 실행 정의 | `services/agent_runtime/definitions.py` |
| Child 프롬프트 조립 | `services/agent_runtime/prompts.py` |
| Child 조립 테스트 | `tests/test_subagents_builder.py`, `tests/test_factory.py` |
