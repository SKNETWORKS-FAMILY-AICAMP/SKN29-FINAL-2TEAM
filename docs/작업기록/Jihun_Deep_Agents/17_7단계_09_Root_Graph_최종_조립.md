# 7단계 세부 09 — Root Graph 최종 조립

## 이 단계에서 하는 일

지금까지 준비한 구성요소를 `create_deep_agent()`에 전달해 실행 가능한 최상위 Runtime Graph를 만든다.

이 시점에는 Graph만 완성하며, 모델 호출이나 도구 실행은 아직 시작하지 않는다.

## 전체 동작

```text
Root 모델·프롬프트·도구
GP·Child 서브에이전트
미들웨어·Memory·Skills
Checkpointer·HITL·파일시스템 정책
        ↓
create_root_graph()
        ↓
Deep Agents 입력과 미들웨어 정리
        ↓
create_deep_agent()
        ↓
실행 가능한 Root Graph 완성
```

## 조립되는 정보

### Root의 기본 구성

- `model`: 해석을 마친 Root 모델
- `system_prompt`: 공통 Runtime 지침과 Agent 프롬프트를 결합한 최종 프롬프트
- `tools`: 실행 어댑터가 연결된 Root 도구
- `subagents`: `[gp_spec, *compiled_children]`
- `middleware`: 앞 단계에서 조립한 Root 미들웨어

### 상태와 실행 정책

- Memory와 Skills
- Backend와 Store
- Checkpointer
- HITL의 `interrupt_on`
- 사용할 수 없는 파일시스템 도구 목록

## 호환 계층의 역할

`factory.py`는 Deep Agents를 바로 호출하지 않고 `create_root_graph()`를 거친다.

이 함수는 우리 Runtime 설정을 Deep Agents 인자로 옮기고, 직접 구성한 Memory·Skills·Filesystem 미들웨어가 있으면 Deep Agents가 자동으로 만든 같은 종류의 미들웨어를 이름 기준으로 교체한다. 그 뒤 `create_deep_agent()`를 호출한다.

Deep Agents는 여기에 도구 호출 보정, 대화 요약, 서브에이전트 호출, HITL 같은 기본 동작을 결합해 최종 Graph를 만든다.

## 반환값

`factory.build()`는 다음 값을 반환한다.

```text
runtime
resolved_model
child_resolved_models
```

- `runtime`: 실행 가능한 Root Graph
- `resolved_model`: 실제 선택된 Root 모델 정보
- `child_resolved_models`: Child별 실제 선택 모델 정보

## 단계 종료 상태

Graph 구조와 모든 실행 부품은 준비됐지만 다음 동작은 아직 발생하지 않았다.

- LLM 호출
- Tool 실행
- Child Agent 실행
- 응답 스트리밍

실제 Graph 실행은 이후 `runtime.stream()`에서 시작된다.

## 봐야 할 파일

| 확인할 내용 | 파일 |
|---|---|
| Root Graph에 최종 인자 전달 | `services/agent_runtime/factory.py` |
| Deep Agents 인자 변환과 최종 생성 | `services/agent_runtime/compat/deepagents_v075.py` |
| Root 시스템 프롬프트 조립 | `services/agent_runtime/prompts.py` |
| Root 미들웨어 구성 | `services/agent_runtime/middleware/factory.py` |
| Graph 조립 후 반환값 사용 | `services/agent_runtime/executor.py` |
