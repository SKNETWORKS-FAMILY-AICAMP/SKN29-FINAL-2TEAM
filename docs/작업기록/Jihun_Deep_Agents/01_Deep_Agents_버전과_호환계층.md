# 01. Deep Agents 버전과 호환 계층

## 한 줄 정리

Deep Agents를 코드 곳곳에서 직접 호출하지 않고, 검증한 `0.7.5` 버전만 별도
호환 계층을 거쳐 사용한다.

## Deep Agents 기본 설계

일반적으로 애플리케이션이 `create_deep_agent()`를 직접 호출한다.

```text
애플리케이션 → create_deep_agent()
```

라이브러리 버전이 바뀌면 함수 파라미터, 기본 Middleware 순서, 메모리·서브에이전트
조립 방식도 달라질 수 있다.

## 우리 프로덕트 설계

```text
AgentRuntimeFactory
  → compat/deepagents_v075.py
  → create_deep_agent()
```

- `deepagents==0.7.5`로 고정한다.
- 설치된 버전이 정확히 0.7.5가 아니면 실행을 막는다.
- Root와 Child 생성을 `create_root_graph()`와 `create_child_graph()`로 나눈다.
- HarnessProfile, MemoryMiddleware, FilesystemMiddleware 설정을 호환 계층에서 처리한다.

주요 코드:

- `requirements/base.txt`
- `services/agent_runtime/compat/deepagents_v075.py`
- `services/agent_runtime/factory.py`

## 이렇게 설계한 이유

우리 코드는 Deep Agents 기본 기능만 쓰지 않고 다음 내부 조립 방식에도 의존한다.

- 같은 이름의 Middleware로 자동 생성 Middleware 교체
- HarnessProfile로 `task` 설명 변경
- `CompiledSubAgent` 연결
- Memory와 Filesystem의 backend 공유
- HITL interrupt와 checkpoint 재개

검증하지 않은 버전으로 자동 업그레이드되면 에러 없이 정책만 빠지는 문제가 생길 수
있어 정확한 버전을 고정했다.

## 좋은 부분

- Deep Agents 호출 방식을 한곳에서 관리한다.
- 검증하지 않은 업그레이드를 즉시 발견한다.
- Root와 Child의 다른 설정이 명확하다.
- 테스트에서 Deep Agents에 전달한 값을 확인하기 쉽다.

## 문제점

- 작은 patch 업데이트도 바로 적용할 수 없다.
- 호환 계층이 Deep Agents 내부 Middleware 조립 규칙에 강하게 의존한다.
- 실제 버전 영향 범위가 호환 파일 하나로 완전히 격리되지는 않았다.
- 업그레이드할 때 `events`, `stream_adapter`, `memory`, `subagents`도 같이 확인해야 한다.
- HarnessProfile은 provider별 전역 설정이라 팀마다 서로 다른 profile이 필요해지면 제약이 된다.

## 현재 판단

현재 구조에는 적합하다. Deep Agents 내부 동작에 깊게 의존하므로 버전 고정이 필요하다.

## 즉시 수정이 필요한 치명적 문제

현재 확인된 치명적 문제는 없다.

다만 버전을 올릴 때 호환 파일만 수정하고 끝내면 안 된다. 업그레이드 전에 이벤트,
스트리밍, 메모리, HITL, 서브에이전트 실물 테스트를 반드시 함께 실행해야 한다.

