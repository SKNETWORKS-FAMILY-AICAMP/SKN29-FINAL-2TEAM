# 03. 도구와 MCP 연결

## 한 줄 정리

Deep Agents에 Tool을 직접 고정하지 않고, Agent 버전의 `tool_ref`를 실행 시점에
내장 Tool 또는 팀 MCP Tool로 변환한다.

## Deep Agents 기본 설계

개발자가 Python 함수나 LangChain Tool을 직접 넘긴다.

```python
create_deep_agent(
    tools=[document_search, task_register],
)
```

Deep Agents는 Tool을 실행하지만 팀·계정·프로젝트 격리, MCP 인증정보, side effect,
우리 DB 실행 로그는 알지 못한다.

## 우리 프로덕트 설계

```text
agent_versions.tool_refs
  → ToolLoader
  ├─ 내장 Tool adapter
  └─ 팀 MCP Tool adapter
  → RuntimeTool
  → LangChain StructuredTool
  → Deep Agents
```

`RuntimeTool`은 다음 정보를 가진다.

- 내부 식별자 `ref`
- 모델용 이름과 설명
- JSON input schema
- 실제 handler
- `side_effect`
- 서버가 주입할 context 목록

`team_id`, `account_id`, `session_id`, `project_id`, `run_id`는 모델이 결정하지
않고 인증된 `RuntimeContext` 값으로 덮어쓴다.

MCP token과 endpoint는 Tool 객체에 저장하지 않고 호출 직전에 DB에서 다시 읽는다.

내부 `mcp:MT001`은 모델에게 `mcp__MT001`로 전달하고 로그에 저장할 때 원래 값으로
복원한다.

모든 MCP Tool은 읽기·쓰기를 알 수 없으므로 현재 `side_effect=True`로 처리한다.
따라서 권한 검사, HITL 승인, timeout, 실행 추적 대상이다.

주요 코드:

- `services/agent_runtime/tools/loader.py`
- `services/agent_runtime/tools/adapters.py`
- `services/mcp/client.py`
- `services/mcp/security.py`

## 이렇게 설계한 이유

- 사용자가 Agent마다 필요한 Tool만 선택해야 한다.
- 사용자가 연결한 MCP를 코드 수정 없이 사용할 수 있어야 한다.
- 모델이 다른 팀 ID나 계정 ID를 만들어 테넌트 경계를 넘으면 안 된다.
- MCP 자격증명이 LLM 상태와 tracing에 들어가면 안 된다.
- MCP Tool의 read/write 여부를 신뢰성 있게 알 수 없으므로 모르는 것은 승인 대상으로
  처리해야 한다.

## 좋은 부분

- Agent Version에는 객체가 아니라 안정적인 `tool_ref`만 저장한다.
- 팀별 MCP Tool을 분리한다.
- 서버가 RuntimeContext를 강제해 테넌트 경계를 보호한다.
- token 갱신과 연결 해제가 다음 호출부터 반영된다.
- 모든 MCP를 기본 승인 대상으로 처리해 알 수 없는 외부 변경을 줄인다.
- MCP 응답은 최대 2MB까지만 읽고, HTTPS와 공인 IP만 허용한다.
- localhost, 사설 IP, link-local, metadata 주소를 차단한다.

## 문제점

### 모든 MCP가 side effect

읽기 전용 MCP도 매번 승인해야 한다. 또한 general-purpose는 읽기 Tool만 받기 때문에
현재 MCP Tool을 하나도 사용할 수 없다.

### Tool 이름 변환

`:`과 `__`를 단순 치환하므로 원래 이름에 `__`가 들어가면 충돌할 수 있다. 문자열
역변환 대신 실행 시 만든 이름 mapping을 쓰는 편이 안전하다.

### MCP schema와 description

전체 HTTP 응답은 2MB로 제한하지만 Tool description 길이, schema 크기·깊이,
Tool 개수에 별도 제한이 없다. 매우 큰 schema나 악성 description이 모델 입력을
오염시킬 수 있다.

### MCP 결과

2MB는 네트워크 보호에는 유효하지만 LLM context에는 너무 크다. 큰 결과는 저장소에
보관하고 모델에는 요약과 참조만 전달하는 방식이 필요하다.

### timeout 불일치

Agent Runtime의 MCP timeout은 기본 480초지만 실제 HTTP client는 연결 10초,
읽기 30초 timeout을 사용한다. 대부분은 30초가 먼저 적용되므로 장시간 MCP를
지원한다는 의미가 아니다.

### timeout 이후 상태

timeout이 나도 외부 MCP 서버가 작업을 완료했을 수 있다. 실패가 아니라 실행 여부를
알 수 없는 상태이며, 재시도하면 중복 side effect가 생길 수 있다.

## 현재 판단

ToolLoader와 RuntimeContext 주입 구조는 멀티테넌트 Agent Platform에 적합하다.
다만 임의 MCP를 공개적으로 연결하게 하려면 MCP를 신뢰하지 않는 보안 경계를 더
강하게 만들어야 한다.

## 즉시 수정이 필요한 치명적 문제

### 1. HTTP redirect SSRF 우회

등록 URL은 검사하지만 `requests.post()`가 redirect를 따라가면 공개 MCP URL이 내부
주소로 redirect할 수 있다.

```text
https://attacker.example/mcp
  → 302 redirect
  → 내부 metadata 또는 사내 서비스
```

MCP 요청에는 `allow_redirects=False`를 적용하고 3xx 응답을 거부해야 한다.

### 2. DNS 검사와 실제 연결의 분리

`security.recheck()`의 DNS 조회와 `requests.post()`의 실제 DNS 조회가 별개다.
검사할 때 공인 IP, 연결할 때 사설 IP를 반환하는 DNS rebinding 가능성이 남는다.

애플리케이션 검사 외에도 운영 환경에서 MCP outbound 트래픽의 내부 CIDR·metadata
접근을 네트워크 정책으로 차단해야 한다.

### 공개 MCP 전에 같이 처리할 높은 위험

- Tool description과 Tool 결과를 신뢰할 수 없는 데이터로 취급하는 prompt-injection 방어
- description·schema·Tool 개수 제한
- LLM에 전달하는 MCP 결과 크기 제한과 대용량 결과 offloading
- 30초 HTTP timeout과 480초 Runtime timeout의 정책 통일

