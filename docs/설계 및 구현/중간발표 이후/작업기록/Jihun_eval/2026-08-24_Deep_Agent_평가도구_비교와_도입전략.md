# Deep Agent 평가 도구 비교와 단계적 도입 전략

- 작성일: 2026-08-24
- 작성 목적: Deep Agent의 성능 평가·검증을 위한 도구별 역할을 구분하고, 현재 프로젝트에 적용할 평가 및 관측성 구성을 결정한다.
- 비교 대상: Langfuse, LangSmith, OpenTelemetry, Ragas, DeepEval

### 문서 적용 상태

| 항목 | 상태 |
|---|---|
| 중앙 관측 플랫폼 결정 | Langfuse 사용 |
| LangSmith 결정 | 신규 평가 체계에서는 미사용 |
| 현재 코드 | Langfuse Python SDK v4 단일 callback 사용 |
| P0 HITL 정합성 | 수정·수동 QA·회귀 테스트 완료 |
| Langfuse/LangSmith | Langfuse v4 전환 완료, LangSmith 연결·자동 tracing 제거 완료 |
| 다음 작업 | 평가 PoC dataset과 기준선 수집 |
| 평가 도구 | DeepEval·Ragas는 도입 설계 단계이며 아직 평가 pipeline이 완성되지 않음 |

이 문서의 “결정”과 “현재 구현”을 구분한다. 2026-08-24 후속 구현으로
LangSmith callback과 환경변수 제거까지 완료했다.

평가 착수의 최우선 선행조건은 HITL 승인 도구의 DB 기록 정합성 수정이다. 현재 승인 대기 interrupt를 일반적인 스트림 조기 종료로 처리하여 실제 성공한 도구가 `FAILED / STREAM_CLOSED`로 남을 수 있으므로, 이 결함을 고치기 전의 Tool 성공률·HITL 승인 후 성공률은 평가 기준선으로 사용하지 않는다.

## 1. 배경

현재 프로젝트는 LangGraph/Deep Agents 기반으로 동작하며 다음과 같은 복합 실행 구조를 가진다.

- 루트 에이전트와 서브에이전트 위임
- LLM 및 여러 도구 호출
- RAG 기반 문서 검색
- 메모리 및 체크포인트
- HITL 승인·거부·재개
- 병렬 실행, timeout, 실패 복구
- 사용자·팀·테넌트별 권한과 데이터 격리

Langfuse v4 단일 실행 추적 연동까지 완료된 상태다. 비교 검토 결과 신규 평가 체계에서는 LangSmith를 사용하지 않고 Langfuse를 초기 중앙 관측·평가 플랫폼으로 사용하기로 결정했다. 앞으로는 단순히 실행 내역을 보는 것을 넘어, Agent가 목표를 달성했는지, 올바른 도구를 안전하고 효율적으로 사용했는지, 모델이나 프롬프트 변경으로 성능이 저하되지 않았는지를 검증해야 한다.

현재 프로젝트의 `requirements/base.txt`는 `langfuse>=4.7,<5.0`이며 실제 web
컨테이너는 `4.14.4`를 사용한다. P0 HITL 기록 정합성을 먼저 수정한 뒤 v4
callback 생성, 마스킹, Cloud observation 쓰기·조회까지 검증했다.

이 과정에서 중요한 점은 다섯 대상이 모두 같은 종류의 제품이 아니라는 것이다.

| 분류 | 대상 | 핵심 역할 |
|---|---|---|
| 관측·실험 플랫폼 | Langfuse, LangSmith | 실행 데이터를 저장하고 탐색하며 데이터셋·실험·평가 결과를 관리 |
| 계측 표준 | OpenTelemetry | trace, metric, log를 표준 형식으로 생성·수집·전송 |
| 평가 프레임워크 | Ragas, DeepEval | Agent 또는 RAG의 품질 점수를 계산하고 회귀 테스트 수행 |

따라서 하나만 골라 나머지를 모두 대체하는 문제가 아니라, 각 계층에서 필요한 도구를 조합하는 문제로 봐야 한다.

## 2. 한눈에 보는 비교

| 구분 | Langfuse | LangSmith | OpenTelemetry | Ragas | DeepEval |
|---|---|---|---|---|---|
| 정체 | LLM 관측·평가 플랫폼 | LangChain 계열 관측·평가 플랫폼 | 범용 텔레메트리 표준 | RAG/LLM 평가 라이브러리 | LLM/Agent 테스트 프레임워크 |
| 핵심 목적 | 운영 추적, 데이터셋, 실험, 평가 결과 관리 | LangGraph 실행 분석, 데이터셋, 실험 | telemetry의 표준 수집·전송 | 검색 및 답변 품질 측정 | Agent 품질 및 회귀 테스트 |
| 실행 추적 | 강함 | 강함 | 데이터를 만들고 전달하지만 UI는 없음 | 제한적 | 평가용 trace 지원 |
| RAG 평가 | 평가기 구성 필요 | 평가기 구성 필요 | 직접 평가 불가 | 매우 강함 | 강함 |
| Agent 평가 | 점수 저장·온라인 평가 중심 | LangGraph 실행 분석에 유리 | 직접 평가 불가 | 일부 Agent 지표 | end-to-end/component 평가에 강함 |
| CI/CD | 가능 | 가능 | 직접 지원하지 않음 | 가능 | 매우 적합 |
| 프로덕션 관측 | 강함 | 강함 | 별도 백엔드 필요 | 주목적 아님 | 가능하나 평가 중심 |
| 셀프호스팅 | 오픈소스 선택지가 강점 | Enterprise 중심 | 완전한 오픈 표준 | 오픈소스 | 오픈소스 코어 |
| 벤더 종속성 | 비교적 낮음 | 상대적으로 높음 | 가장 낮음 | 낮음 | 낮음~중간 |
| 프로젝트 적합도 | 높음 | 높지만 Langfuse와 중복 | 중장기적으로 높음 | RAG 구간에 높음 | 전체 Agent 평가에 매우 높음 |

## 3. Langfuse

### 3.1 역할

Langfuse는 Deep Agent의 실행 trace를 저장하고 개발자와 운영자가 분석할 수 있도록 하는 LLM 관측·평가 플랫폼이다.

프로젝트에서 다음 정보를 확인하는 데 사용할 수 있다.

- 사용자 요청이 어떤 에이전트와 서브에이전트를 거쳤는지
- LLM 호출 횟수, 모델, token 및 비용
- 호출된 도구와 수집이 허용된 인자·결과 요약, 오류
- RAG 검색 문서와 최종 답변의 관계
- 각 단계와 전체 실행의 지연시간
- 프롬프트·모델·Agent 버전별 결과 비교
- 사용자 피드백과 자동 평가 점수
- 운영 중 발생한 실패 사례

또한 dataset, experiment, LLM-as-a-Judge, code evaluator, annotation, custom score 등을 제공한다. Ragas나 DeepEval로 외부에서 계산한 점수도 trace, observation, session, dataset run에 연결할 수 있다.

### 3.2 장점

- 오픈소스이며 셀프호스팅 선택지가 좋다.
- 특정 Agent 프레임워크에 비교적 덜 종속된다.
- LangChain callback과 OpenTelemetry를 모두 사용할 수 있다.
- trace, prompt, dataset, experiment, score를 한곳에서 관리할 수 있다.
- Ragas·DeepEval 결과를 중앙 대시보드로 모으기 좋다.
- Python과 JavaScript/TypeScript 서비스의 관측을 통합하기 쉽다.
- 현재 프로젝트에 이미 연결되어 있어 초기 도입 비용이 낮다.

### 3.3 단점

- trace를 수집하는 것만으로 품질 평가가 자동 완성되지는 않는다.
- 계획·도구 선택·목표 달성 여부를 판단할 평가 기준은 별도로 설계해야 한다.
- 모든 trace를 장기 보존하고 LLM Judge까지 수행하면 저장 및 모델 비용이 증가한다.
- 셀프호스팅 시 데이터베이스와 플랫폼 운영 부담이 생긴다.
- LangGraph 고유 node/thread 분석은 LangSmith가 더 자연스러울 수 있다.

### 3.4 프로젝트 내 권장 역할

Langfuse를 운영 trace와 평가 결과의 중앙 플랫폼으로 사용한다.

- 전체 Deep Agent 실행 trace 저장
- 모델, 프롬프트, agent version, runtime profile version 기록
- Ragas·DeepEval 및 자체 evaluator 점수 저장
- 사용자 피드백 수집
- 실패 trace를 평가 dataset으로 승격
- 릴리스 전후 experiment 비교

### 3.5 v4 마이그레이션 결과와 후속 검증 원칙

현재 연동은 Python SDK v4의 `Langfuse(..., mask=...)`와 LangChain callback을
사용한다. SDK 전환 시 callback 생성, v4 Cloud observation 쓰기·조회와
마스킹은 확인했다. 다음 항목은 실제 평가 pipeline과 공통 OpenTelemetry
계측을 추가하면서 계속 검증한다.

- 기존 마스킹 함수가 observation input/output과 tool payload에 동일하게 적용되는가
- session, user, team, agent metadata가 모든 필요한 observation에 전파되는가
- LangChain/LangGraph, DB, HTTP, 프로젝트 custom span 중 필요한 span이 기본 filter에서 누락되지 않는가
- trace, observation, score 조회 및 평가 결과 연결 코드가 v4 API에서 동작하는가
- Collector에서 Langfuse v4 OTLP endpoint로 보낼 때 `x-langfuse-ingestion-version: 4` 헤더가 적용되는가
- 비동기 export 종료 시 flush와 유실 처리 정책이 동작하는가

v3 trace를 별도 파일로 보관한 뒤 동일 시나리오를 재생하는 절차는 전환 전에
완료하지 못했다. 기존 Cloud trace를 참고 자료로 남기되, 이후 비교의 정식
기준선은 v4 고정 시나리오에서 새로 수집한다.

## 4. LangSmith

### 4.1 역할

LangSmith는 LangChain/LangGraph 생태계에 특화된 관측·평가 플랫폼이다. 현재 프로젝트처럼 Deep Agents와 LangGraph를 사용하는 경우 다음 분석에 편리하다.

- LangGraph node별 실행
- parent/child run 구조
- 서브에이전트 및 서브그래프
- tool, chain, LLM 호출 구분
- thread와 실행 이력
- dataset 기반 모델·프롬프트 실험

### 4.2 장점

- LangChain/LangGraph 실행 구조가 자연스럽게 표현된다.
- callback 연결로 풍부한 trace를 수집하기 쉽다.
- dataset, evaluator, experiment 비교가 잘 통합되어 있다.
- LangGraph 개발 및 디버깅 경험이 좋다.
- trace의 실패 사례를 dataset으로 만드는 흐름이 편리하다.

### 4.3 단점

- Langfuse와 기능 중복이 크다.
- 둘을 동시에 장기간 운영하면 trace 이중 전송, 저장 비용 증가, 마스킹 검증 중복, dataset과 점수 분산 문제가 발생한다.
- 팀이 어느 대시보드를 기준으로 판단할지 불명확해질 수 있다.
- LangChain 생태계 의존성이 상대적으로 높다.
- 셀프호스팅은 일반적인 오픈소스 선택이라기보다 Enterprise 중심이다.
- LangSmith를 사용해도 평가 dataset과 evaluator 품질은 팀이 직접 책임져야 한다.

### 4.4 프로젝트 내 결정

LangSmith는 비교 검토 결과 Langfuse와 역할 중복이 크고, trace·dataset·평가 점수의 이중 관리 및 민감정보 마스킹 검증 부담이 증가하므로 신규 평가 체계에서는 사용하지 않는다.

이 결정은 `docs/설계 및 구현/중간발표 이후/작업기록/LangSmith_LangFuse/2026-08-19_01_작업계획.md`의 기존 병행 운영 결정을 변경한다. 기존 계획은 LangSmith를 LangGraph run·node·tool 흐름 재현과 디버깅에, Langfuse를 장기 trace·Dataset·Experiment·비용·데이터 소유권 관리에 사용하여 관심사를 나누려는 선택이었다. 또한 양쪽 실 키와 공통 마스킹 함수의 동작까지 검증했다.

새 결정은 LangSmith의 LangGraph 전용 디버깅 이점을 부정하지 않는다. 다만 장기 운영 기준에서는 다음 비용이 그 편익보다 크다고 판단한다.

- 동일 실행의 이중 전송과 두 외부 플랫폼의 마스킹 회귀 검증
- trace·dataset·평가 점수와 팀의 기준 대시보드 분산
- LangChain/LangGraph 전용 데이터 모델에 대한 추가 종속
- OpenTelemetry와 프로젝트 내부 event·trace 모델을 별도로 구축하면서 생기는 중복 계측

이미 완료한 LangSmith 구현과 실 키 검증 비용은 매몰비용으로 보고, 프레임워크 중립적인 OpenTelemetry 계측, 데이터 소유권과 장기적인 자체 분석 가능성을 더 높은 우선순위로 둔다. LangSmith 제거로 줄어드는 LangGraph 디버깅 편의는 프로젝트 event 모델, DB trace와 OpenTelemetry parent-child span을 보강하여 대체한다.

- Langfuse를 초기 중앙 관측·평가 플랫폼으로 사용한다.
- 기존 LangSmith 설정과 callback은 제거했다.
- LangGraph 고유 구조의 디버깅이 필요해지더라도 우선 OpenTelemetry span과 프로젝트 이벤트 모델을 보강한다.
- 향후 요구사항이 바뀌면 특정 플랫폼 종속 연동보다 OpenTelemetry 호환 백엔드를 우선 검토한다.

현재 코드에서 `get_langsmith_callback()`과 `LANGSMITH_*`/`LANGCHAIN_*` 설정,
로컬 자동 tracing 환경변수를 제거했다. 전이 의존성인 `langsmith` 패키지는
남아 있지만 자동 tracing 판정은 `False`다. 완료 확인 결과는 다음과 같다.

- 실행기가 Langfuse callback만 구성하는 회귀 테스트가 통과한다.
- 실행 컨테이너의 LangSmith 관련 환경 변수는 0개다.
- Django `LANGCHAIN_*` 설정이 없고 `tracing_is_enabled()`는 `False`다.
- Langfuse v4 Cloud observation 쓰기·조회와 마스킹이 정상 동작한다.

## 5. OpenTelemetry

### 5.1 역할

OpenTelemetry는 평가 제품이나 대시보드가 아니라 trace, metric, log를 표준 형식으로 생성·수집·전송하는 벤더 중립 계측 표준이다.

```text
Deep Agent
   ↓ 계측
OpenTelemetry SDK
   ↓
OpenTelemetry Collector
   ├─ Langfuse
   ├─ 자체 관측·평가 플랫폼
   ├─ Grafana/Tempo
   └─ 기타 관측 백엔드
```

### 5.2 벤더 중립의 의미

벤더 중립은 특정 회사의 전용 SDK와 데이터 규격에만 종속되지 않는다는 의미다. Agent가 OpenTelemetry 표준으로 telemetry를 만들면, 이후 관측 백엔드를 Langfuse, 자체 플랫폼, Grafana, Jaeger, Datadog, Elastic 등으로 바꾸거나 동시에 전송하기가 쉬워진다.

반대로 플랫폼 전용 SDK에만 강하게 의존하면 플랫폼 변경 시 계측 코드를 수정해야 할 가능성이 커진다. 이를 벤더 락인이라고 한다.

다만 OpenTelemetry가 모든 종속성을 없애는 것은 아니다. Langfuse의 dataset, evaluator, prompt 관리, 전용 UI를 깊게 사용하면 그 기능에는 여전히 종속될 수 있다. OpenTelemetry가 주로 중립화하는 영역은 telemetry의 생성·수집·전송 계층이다.

### 5.3 할 수 있는 역할

- Agent, LLM, retriever, tool, DB, 외부 API의 trace 연결
- latency, error, token 등 metric 수집
- 로그에 trace ID를 넣어 상호 연결
- Collector에서 마스킹, 필터링, sampling, batch 처리
- 동일 telemetry를 여러 백엔드로 전송
- 관측 플랫폼 변경 시 애플리케이션 수정 범위 축소

### 5.4 장점

- 특정 관측 벤더에 종속되지 않는다.
- LLM뿐 아니라 Django API, PostgreSQL, Redis, 외부 API까지 end-to-end로 연결할 수 있다.
- Collector에서 중앙 마스킹과 sampling 정책을 적용할 수 있다.
- 여러 언어와 인프라에 공통으로 적용할 수 있다.
- 관측 플랫폼을 교체하거나 추가하기 쉽다.

### 5.5 단점

- 품질 점수를 직접 계산하지 않는다.
- UI와 저장소가 없다.
- 평가 dataset과 experiment 기능이 없다.
- OpenTelemetry GenAI semantic convention을 기준으로 삼되 아직 표준이 포괄하지 않는 프로젝트 고유 attribute는 팀에서 설계해야 한다.
- Collector와 저장 백엔드 운영이 필요할 수 있다.
- 민감정보 필터링을 잘못 구성하면 prompt나 도구 인자가 외부로 전송될 수 있다.

## 6. OpenTelemetry UI와 저장소를 직접 만들 경우

OpenTelemetry용 저장소와 UI를 자체 개발하면 기술적으로 Langfuse를 사용하지 않아도 된다. 그러나 이 경우 단순 로그 화면이 아니라 사실상 작은 LLM 관측 플랫폼을 직접 만드는 셈이다.

> **적용 상태: 장기 참고용·조건부 설계.** 현재 실행 범위는 Langfuse Cloud를 사용하면서 평가 체계와 공통 OpenTelemetry 계측을 구축하는 데까지다. 이 절은 자체 플랫폼 착수를 승인한 계획이 아니며, §10.5의 Go/No-Go 조건을 충족해 별도 결정을 내린 경우에만 실행한다.

```text
Deep Agent
   ↓ OpenTelemetry
OpenTelemetry Collector
   ↓
자체 저장소
   ↓
자체 UI 및 평가 시스템
```

직접 준비해야 하는 범위는 다음과 같다.

### 6.1 수집·저장 계층

- trace/span 저장 및 인덱싱
- 검색, 필터링, 집계
- trace ID 기반 호출 관계 연결
- 대용량 데이터 보존 및 삭제 정책
- 장애 시 재전송과 유실 처리
- metric과 log 저장소 연동

일반적으로 trace에는 Tempo, Jaeger 또는 ClickHouse, metric에는 Prometheus, log에는 Loki 또는 Elasticsearch, UI에는 Grafana나 자체 화면을 사용할 수 있다.

Langfuse는 이 구조에서 주로 LLM/Agent trace와 평가 결과를 소비하는 백엔드다. OpenTelemetry가 다루는 모든 시스템 metric과 일반 application log까지 Langfuse가 저장한다고 가정하지 않는다. 장기 목표 구조에서는 신호별 목적지를 구분한다.

```text
OpenTelemetry Collector
├─ LLM/Agent trace → Langfuse 및 자체 trace 저장소
├─ System metric   → Prometheus 등 metric 저장소
└─ Application log → Loki/Elasticsearch 등 log 저장소
```

자체 플랫폼은 공통 trace ID를 사용해 이 데이터를 연결한다.

### 6.2 LLM/Agent 전용 데이터 모델

범용 APM은 HTTP와 DB 호출을 잘 보여주지만 LLM/Agent 관측에는 다음 정보가 추가로 필요하다. OpenTelemetry GenAI semantic convention에 있는 항목은 표준을 사용하고, 없는 항목만 프로젝트에서 별도로 정의한다.

- prompt와 completion
- model과 inference parameter
- input/output token 및 비용
- tool name, arguments, result
- retrieval query와 검색 문서
- 루트·서브에이전트 관계
- agent/prompt/runtime profile version
- HITL interrupt/resume
- session/user/tenant
- 평가 점수와 사용자 피드백

속성은 OpenTelemetry GenAI semantic convention을 우선하고, 프로젝트 전용 값에만 `skn.*` namespace를 사용한다. 표준 규격이 Development 상태일 수 있으므로 적용한 semantic convention 버전을 코드와 문서에 고정하고 업그레이드 시 호환성을 검증한다.

예시 attribute는 다음과 같다.

```text
gen_ai.operation.name
gen_ai.agent.name
gen_ai.request.model
gen_ai.usage.input_tokens
gen_ai.usage.output_tokens
gen_ai.tool.name
gen_ai.tool.call.arguments       # 민감 원문이므로 기본 비수집
gen_ai.tool.call.result          # 민감 원문이므로 기본 비수집
skn.agent.version
skn.agent.runtime_profile.version
skn.retrieval.document_ids
skn.hitl.state
skn.evaluation.task_success
skn.evaluation.faithfulness
```

루트·서브에이전트와 tool의 관계는 `agent.parent_id` 같은 별도 문자열 속성보다 OpenTelemetry trace context와 span parent-child 관계를 정본으로 사용한다. 업무상의 내부 run ID가 필요하면 별도 correlation attribute를 추가하되 trace 관계를 중복 구현하지 않는다.

### 6.3 원문 payload 수집 정책

prompt, completion, tool arguments, tool result와 retrieval chunk는 유용하지만 크고 민감하다. 정규식 마스킹만으로 모든 개인정보와 업무상 기밀을 식별할 수 없으므로 기본 수집은 allowlist와 요약값 중심으로 구성한다.

- 기본 기록: `tool.name`, 성공 여부, latency, result count·size, error type, schema validation 결과
- 조건부 기록: 허용된 argument 필드, document/chunk ID, payload hash, truncation 여부
- 기본 비수집: Jira 본문, 파일 원문, RAG chunk 원문, credential, 개인 식별 정보가 포함될 수 있는 전체 tool result
- 원문 capture: 개발 환경 또는 승인된 디버깅 세션에서만 opt-in하고 짧은 보존 기간 적용
- 크기 제한: span attribute와 event에 최대 길이·배열 개수 제한을 적용
- 실패 정책: 직렬화나 마스킹이 실패하면 원문을 보내지 않는 fail-closed 방식 사용

`user_id_hash`는 salt와 회전 정책을 포함해 정의하고, tenant와 account 식별자도 외부 백엔드에 꼭 필요한 수준만 전송한다. Collector 필터는 추가 방어선이며 애플리케이션의 allowlist·마스킹을 대체하지 않는다.

### 6.4 평가 및 운영 기능

- 평가 dataset 관리
- 동일 dataset 반복 실행
- 모델·프롬프트 A/B 비교
- Ragas·DeepEval 점수 저장과 통계
- LLM-as-a-Judge 실행
- 사람 평가 annotation UI
- 실패 trace의 dataset 전환
- CI/CD 품질 기준과 알림
- 사용자 권한, tenant 격리, 마스킹, 보존 기간 관리

따라서 현재 프로젝트의 목표가 관측 플랫폼 개발이 아니라 Deep Agent 품질 검증이라면, 초반부터 Langfuse 전체를 대체하는 자체 플랫폼을 만드는 것은 효율적이지 않다.

## 7. Ragas

### 7.1 역할

Ragas는 RAG 검색과 생성 답변의 품질을 정량화하는 데 강한 평가 라이브러리다. 현재는 Agent 및 tool use metric도 제공하지만 핵심 강점은 RAG 평가다.

주요 평가 예시는 다음과 같다.

- Context Precision: 검색 문서 중 실제로 유용한 문서의 비율
- Context Recall: 답변에 필요한 정보를 충분히 검색했는지
- Faithfulness: 답변이 검색 문서에 근거하는지
- Response Relevancy: 답변이 질문과 관련 있는지
- Factual Correctness: 기준 답변과 사실적으로 일치하는지
- Agent Goal Accuracy: Agent가 사용자 목표를 달성했는지
- Tool Call Accuracy: 올바른 도구와 인자를 선택했는지

### 7.2 장점

- RAG 지표가 풍부하고 빠르게 시작할 수 있다.
- 일부 지표는 정답 reference 없이 평가 가능하다.
- retriever 문제와 generator 문제를 분리해 분석할 수 있다.
- 평가 LLM 및 embedding을 교체할 수 있다.
- custom metric을 작성할 수 있다.
- 특정 관측 플랫폼에 독립적으로 실행할 수 있다.

### 7.3 단점

- 복잡한 Deep Agent 전체 동작 검증에는 부족할 수 있다.
- HITL, 권한, 메모리, 서브에이전트, 실패 복구는 별도 테스트가 필요하다.
- LLM Judge 기반 점수는 평가 모델과 prompt에 따라 달라질 수 있다.
- 한국어와 사내 도메인에 대해 인간 평가와의 상관관계를 검증해야 한다.
- 대량 평가 시 LLM 및 embedding 비용이 발생한다.

### 7.4 프로젝트 내 권장 역할

Ragas는 문서 및 RAG 기반 기능에만 선택적으로 적용한다.

- context precision
- context recall
- faithfulness
- answer relevancy
- 필요한 경우 factual correctness

Jira 등록, 업무량 계산, 파일 쓰기, MCP 승인, 서브에이전트 위임과 같은 워크플로우 검증은 Ragas보다 DeepEval 또는 deterministic assertion이 적합하다.

## 8. DeepEval

### 8.1 역할

DeepEval은 LLM 애플리케이션을 일반 소프트웨어 테스트처럼 평가하고 CI/CD에서 회귀를 차단하는 평가 프레임워크다. Agent 전체 trace와 개별 component를 모두 평가할 수 있다.

- 최종 목표 달성 여부
- 도구 선택과 인자 정확성
- 불필요한 반복 호출
- 서브에이전트 위임 적절성
- RAG 근거성
- 답변 완전성·유용성
- 환각, 편향, 유해성
- 모델 및 프롬프트 변경 후 품질 저하

### 8.2 장점

- pytest 및 기존 CI 파이프라인과 잘 어울린다.
- threshold 기반 pass/fail 판정이 쉽다.
- Agent의 end-to-end 및 component-level 평가에 적합하다.
- RAG, hallucination, relevancy, toxicity 등 다양한 metric을 제공한다.
- custom metric과 rubric을 만들 수 있다.
- golden dataset 기반 회귀 테스트에 강하다.
- red-team 및 취약 시나리오로 확장할 수 있다.

### 8.3 단점

- 좋은 golden dataset과 rubric을 직접 만들어야 한다.
- LLM Judge는 비결정적일 수 있다.
- 복잡한 프로젝트 trace를 DeepEval 형식으로 연결하는 adapter 작업이 필요할 수 있다.
- 모든 평가를 pull request마다 실행하면 느리고 비싸다.
- 관측 플랫폼 자체를 완전히 대체하지는 않는다.

### 8.4 프로젝트 내 권장 역할

Deep Agent 전체 회귀 테스트의 중심으로 사용한다. 다만 명확한 규칙은 LLM Judge보다 코드 기반 assertion을 우선한다.

deterministic test가 적합한 항목:

- 승인 전에 side-effect 도구가 실행되지 않았는가
- 허용되지 않은 파일 경로에 쓰지 않았는가
- tool timeout과 최대 step/concurrency가 지켜졌는가
- 존재하지 않는 subagent가 성공으로 처리되지 않았는가
- 동일한 side-effect가 중복 실행되지 않았는가
- HITL resume 후 중복 호출이 없는가
- tenant/user 간 memory가 섞이지 않았는가

DeepEval의 semantic metric이 적합한 항목:

- 최종 목표 달성도
- 계획의 적절성
- 도구 선택의 의미적 적절성
- 답변 완전성 및 유용성
- 문서 근거성

## 9. 프로젝트 권장 구성

현재 기준 최우선 권장안은 다음과 같다.

```text
관측·평가 결과 중앙 플랫폼
└─ Langfuse v4

전체 Agent 회귀 평가
└─ DeepEval + pytest

RAG 전용 평가
└─ Ragas

문서 처리·검색기 기준선
└─ pytest/custom evaluation

공통 계측·전송
└─ OpenTelemetry를 단계적으로 도입

LangSmith
└─ 신규 평가 체계에서 사용하지 않으며 기존 연동은 비활성화 또는 제거
```

도구별 책임은 다음과 같이 분리한다.

- Langfuse: 운영 trace, dataset, experiment, feedback, 평가 점수의 중앙 저장소
- DeepEval: Agent 목표 달성 및 semantic 품질의 자동 회귀 테스트
- pytest/custom assertion: 권한, 승인, timeout, 중복 실행 등 결정적 규칙 검증
- Ragas: 검색 문서와 생성 답변 사이의 품질 평가
- pytest/custom evaluation: 파싱·구조 보존, document/chunk Recall@k, 업무 추출 Precision/Recall 측정
- OpenTelemetry: Django부터 Agent, tool, DB까지 공통 계측 및 백엔드 중립성 확보
- LangSmith: Langfuse와의 역할 중복을 피하기 위해 사용하지 않음

## 10. 단계적 도입 전략

### 10.0 0단계: P0 HITL tool-call 기록 정합성 수정

현재 `trace_events()`는 스트림마다 `open_tool_calls`를 빈 상태로 만들고, HITL interrupt 때 `_suspend_run()`은 `agent_run`만 PENDING으로 남긴다. 승인 대기 tool call은 `finally`의 `_close_orphans()`가 `FAILED / STREAM_CLOSED`로 종료하며, 재개 스트림은 기존 DB 행과 짝을 찾지 못해 실제 성공 결과를 반영하지 못한다.

이 상태에서 Tool 성공률, HITL 승인 후 성공률, 실패 단계 분포를 측정하면 거짓 숫자가 기준선에 들어간다. 따라서 Langfuse v3 기준선 저장과 v4 마이그레이션보다 먼저 다음을 완료한다.

1. HITL interrupt 시 해당 run의 승인 대기 tool call을 orphan 실패 처리 대상에서 제외하고 `PENDING`으로 유지한다.
2. `tool_call` 행을 LangChain의 `tool_call_id`와 안정적으로 연결할 수단을 마련한다. `(run_id, langchain_tool_call_id)`를 직접 저장하거나 기존 idempotency 기록을 이용하는 방식 중 하나를 선택한다.
3. resume 시 동일 식별자로 기존 PENDING 행을 다시 열어 승인 후 실제 성공·실패 결과로 종료한다.
4. 거부는 실행 실패와 구분되는 상태·오류 코드 정책을 정하고, 실행되지 않은 도구를 성공이나 일반 실행 실패로 집계하지 않는다.
5. 동일 도구의 병렬 승인, 승인·거부, resume 성공·실패, 중복 resume를 포함한 deterministic 회귀 테스트를 추가한다.

완료 조건은 다음과 같다.

- interrupt 직후 승인 대기 tool call이 `FAILED / STREAM_CLOSED`로 기록되지 않는다.
- 승인 후 실제 성공한 tool call이 기존 DB 행에서 `OK`로 종료된다.
- 거부·실행 실패·실제 스트림 비정상 종료가 서로 구분된다.
- 병렬로 같은 tool을 호출해도 각 `tool_call_id`가 정확한 행과 연결된다.
- HITL 관련 운영 집계와 Langfuse trace가 같은 실행 결과를 나타낸다.

### 10.1 1단계: Langfuse v4 전환과 현행 기준선 고정

신규 Collector나 evaluator를 추가하기 전에 현재 v3 trace의 기준선을 저장하고 Python SDK v4 마이그레이션을 진행한다.

1. 대표 시나리오 5~10개의 v3 trace와 마스킹 결과를 기준선으로 보관한다.
2. v4 호환 branch에서 callback, metadata 전파, span filtering, score API를 수정한다.
3. 동일 시나리오로 trace 구조·token·비용·마스킹·유실 여부를 비교한다.
4. v4 전환 후 LangSmith callback과 자동 tracing 경로를 비활성화하거나 제거한다.
5. Langfuse만 활성화된 상태를 회귀 테스트로 고정한다.

이 단계가 끝나야 이후 문서의 “현재”는 Langfuse v4 단일 중앙 플랫폼을 의미한다.

### 10.2 2단계: 프로젝트 공통 OpenTelemetry 계측 도입

현재 구현과 목표 구조를 구분한다. 현재 코드는 Langfuse의 LangChain callback을 사용하며, Langfuse SDK가 내부적으로 OpenTelemetry provider와 전송을 구성한다. 아직 프로젝트가 직접 관리하는 공통 OpenTelemetry 계측 계층과 Collector를 구축한 상태는 아니다. 즉 현재는 “Langfuse SDK가 OTel을 내부 기반으로 사용”하는 상태이지, “프로젝트 공통 OTel + Collector” 구축이 완료된 상태가 아니다.

```text
현재
Deep Agent → Langfuse LangChain callback
                 └─ Langfuse SDK 내부 OpenTelemetry 처리 및 Langfuse 전송

목표
Deep Agent → 프로젝트 공통 OpenTelemetry 계측 → OpenTelemetry Collector
                                            ├─ Langfuse
                                            └─ 자체 관측·평가 플랫폼
```

Collector가 Langfuse v4로 export할 때 인증 헤더와 함께 `x-langfuse-ingestion-version: 4`를 설정하여 지연된 호환 수집 경로를 피한다. 하나의 전역 TracerProvider와 여러 span processor를 사용할지 Collector 중심으로 통합할지는 PoC에서 중복 span, orphan span, sampling 일관성을 비교해 결정한다.

이 단계에서는 Langfuse를 완성된 UI이자 요구사항 발견 도구로 사용한다. 실제 운영 과정에서 팀이 자주 확인하는 화면과 필터, 필요한 지표, 부족한 기능을 기록한다.

필수로 표준화할 metadata 예시는 다음과 같다.

- trace_id, session_id, user_id_hash, tenant_id
- agent_name, agent_version, subagent_name
- model, input/output token, cost
- tool_name, success, latency, result_count, result_size, error_type
- 검색 문서 ID와 retrieval score
- HITL 승인·거부·재개 상태
- 평가 점수와 오류 유형
- prompt 및 runtime profile version

민감한 원문과 tool arguments는 저장 전에 애플리케이션 계층에서 우선 마스킹한다. Collector의 필터링은 추가 방어선으로 사용하며, Collector 설정 하나에 개인정보 보호를 전적으로 의존하지 않는다.

원문 tool result는 공통 metadata에 넣지 않는다. §6.3의 allowlist, opt-in capture, 크기 제한과 fail-closed 정책을 적용한다.

### 10.3 3단계: 실제 UI 요구사항 수집

Langfuse를 사용하면서 다음을 확인한다.

- 실패 분석에 실제로 사용하는 필터
- 가장 자주 확인하는 span과 attribute
- 모델·프롬프트·Agent 버전 비교 방식
- Ragas·DeepEval 점수를 보는 단위
- 성공률, 비용, 지연 중 우선하는 지표
- 개발자와 운영자의 화면 요구 차이
- Langfuse에서 부족하거나 불편한 기능

### 10.4 선택적 고도화: 프로젝트 전용 요약 UI 추가

이 단계는 현재 필수 실행 범위가 아니다. Langfuse를 실제로 사용한 결과 프로젝트 고유의 운영 요약 요구가 명확하고 기존 `/ops/usage` 확장만으로 해결되지 않을 때 별도 승인을 받아 착수한다. 처음부터 Langfuse 전체를 복제하지 않고 운영 의사결정에 필요한 요약 화면부터 만든다. Langfuse 외부 trace를 직접 조회해야 할 필요가 확인된 경우에만 OTLP 수신, trace·평가 결과 저장, 검색·집계 API, 보존·삭제 정책을 추가한다.

- Agent 버전별 작업 성공률
- 업무 유형별 평균 비용 및 지연
- 도구별 성공률과 timeout 비율
- 서브에이전트 위임 성공률
- HITL 승인·거부 및 승인 후 성공률
- RAG faithfulness와 context recall
- 실패 유형 상위 목록
- 이전 버전 대비 품질 하락 경고

역할을 다음처럼 나눈다.

```text
자체 UI: 우리 Agent가 전체적으로 잘 작동하고 있는가?
Langfuse: 특정 실행이 내부적으로 왜 실패했는가?
```

### 10.5 장기 조건부 선택지: Langfuse 유지·축소·제거 판단

Langfuse 대체 플랫폼은 현재 로드맵의 확정 작업이 아니다. 기존에 Langfuse 셀프호스팅도 현재 팀 규모·트래픽에서는 Cloud보다 운영비가 크다고 판단했으므로, 그보다 범위가 큰 자체 플랫폼은 다음 Go 조건 중 하나 이상이 명확하고 전담 역량이 확보됐을 때만 별도 의사결정으로 착수한다.

- Langfuse 비용이 자체 구축·운영의 총비용보다 지속적으로 커짐
- 외부 반출·데이터 주권 정책 때문에 Langfuse Cloud 사용이 불가능해짐
- Langfuse와 기존 `/ops/usage`로 해결할 수 없는 핵심 도메인 요구가 반복적으로 확인됨
- 플랫폼을 개발·운영할 담당 인력과 장기 제품 운영 계획이 확보됨

Go 결정 후 자체 UI가 안정된 경우 다음 조건을 기준으로 Langfuse 유지 여부를 판단한다.

- 상세 trace 디버깅을 자체 UI가 충분히 대체하는가
- dataset/experiment/annotation 기능이 계속 필요한가
- 저장 및 운영 비용이 합리적인가
- 자체 플랫폼을 운영할 인력이 있는가
- 외부 반출과 보안 요구가 자체 구축을 요구하는가

판단이 주관적이지 않도록 최소한 다음 교체 기준을 정량적으로 검증한다. 실제 목표치는 부하 시험과 운영 환경을 바탕으로 확정한다.

- trace 수집 성공률과 허용 가능한 유실률
- 루트·서브에이전트·tool의 parent-child 연결 정확도
- Ragas·DeepEval 평가 점수 누락률
- trace 목록 및 상세 조회의 p95 응답시간
- token·비용 집계의 Langfuse 대비 허용 오차
- HITL interrupt/resume 연결 성공률
- tenant 간 데이터 노출 및 권한 회귀 테스트 통과율
- 민감정보 마스킹 회귀 테스트 통과율
- 데이터 보존·삭제와 장애 시 재전송 정책 검증
- 정해진 병행 운영 기간 동안 Langfuse와 자체 플랫폼의 결과 일치 여부

실제 사용 결과 Langfuse가 충분하다면 자체 UI를 더 확장하지 않는 것도 올바른 결론이다. 반대로 위 기준을 충족한 자체 플랫폼이 안정적으로 병행 운영된 이후에만 Langfuse를 제거한다.

## 11. 자체 UI를 고려할 때 지켜야 할 경계

나중에 Langfuse를 교체할 가능성을 열어두려면 다음 원칙을 유지한다.

- 애플리케이션 계측은 OpenTelemetry 중심으로 작성한다.
- 프로젝트 고유 attribute 규격을 별도 문서와 코드 상수로 관리한다.
- 평가 계산은 Ragas, DeepEval 및 자체 evaluator에서 수행한다.
- golden dataset, 평가 케이스, metric/rubric 버전은 Git 또는 프로젝트 DB를 정본으로 관리한다.
- Ragas·DeepEval 원시 결과와 평가 실행 metadata는 프로젝트 DB 또는 내부 object storage에 보관한다.
- Langfuse는 telemetry와 평가 결과를 소비하는 백엔드 중 하나로 취급한다.
- 내부 run ID와 Langfuse trace ID의 매핑을 유지한다.
- 마스킹과 tenant 격리 정책을 특정 UI에만 맡기지 않는다.

평가 데이터의 소유권은 다음과 같이 정의한다.

```text
프로젝트 Git/DB/object storage = 평가 dataset과 원시 결과의 정본
Langfuse                      = 초기 trace·평가 조회 및 실험 UI
자체 플랫폼                   = 이후 추가되는 내부 소비자이자 장기 대체 대상
```

최소 보존 항목은 평가 케이스와 기대 결과, metric/rubric 버전, Agent·prompt·model·runtime 버전, 평가 모델, 내부 run/trace ID, 원시 점수, 평가 시각 및 사용자 피드백이다. Langfuse의 dataset과 prompt 기능을 사용하더라도 프로젝트 외부에만 유일한 원본이 존재하지 않게 한다.

처음부터 Langfuse와 자체 저장소에 모든 데이터를 이중 영구 저장할 필요는 없다. 자체 UI 개발을 시작할 때 OpenTelemetry Collector에서 필요한 데이터만 복제하는 편이 효율적이다.

## 12. 평가 지표 설계

Deep Agent는 최종 답변만 평가해서는 안 된다. 문서 처리, 검색, 목표 달성, 과정, 효율, 안전성을 분리해 본다. 특히 Ragas의 LLM 기반 Context Precision/Recall만으로 검색기 자체의 결정적 성능을 대체하지 않는다. 문서 후보 선정과 chunk 검색은 정답 document/chunk ID를 기준으로 별도 측정한다.

| 평가 영역 | 추천 지표 | 평가 방법 |
|---|---|---|
| 문서 처리 | 파싱 성공률 | 등록 시도 대비 검색 가능한 문서 생성 비율 |
| 구조 보존 | Heading·표 구조 보존율 | golden document의 기대 구조와 파싱 결과 대조 |
| 문서 후보 검색 | Coarse Document Recall@k | 기대 document ID의 후보 포함 여부 |
| Chunk 검색 | Recall@k, Top-1 Accuracy | 기대 chunk ID와 retriever 결과 직접 대조 |
| 업무 추출 | Precision, Recall, missing-fields 정직성 | golden task와 추출 결과 대조 |
| 최종 성공 | Task Success Rate | DeepEval/custom rubric |
| 도구 선택 | Tool Selection Accuracy | deterministic + DeepEval |
| 인자 정확성 | Argument Accuracy | schema/business rule 검사 |
| 실행 효율 | 평균 step/tool/LLM 호출 수 | trace 집계 |
| 지연 | p50/p95 end-to-end latency | Langfuse/OpenTelemetry |
| 비용 | 성공 작업당 token 및 비용 | Langfuse 집계 |
| RAG 응답 문맥 | Context Precision/Recall | Ragas |
| 근거성 | Faithfulness | Ragas 또는 DeepEval |
| 안전성 | 승인·권한 위반율 | pytest deterministic test |
| 안정성 | timeout·실패·복구 성공률 | trace + 장애 주입 테스트 |
| 위임 품질 | subagent 선택 및 결과 활용 | custom evaluator |
| 실행 궤적 | Trajectory Correctness | 필수·금지·허용 Tool path, 순서 제약과 postcondition 검사 |
| 과정 품질 | Plan·Delegation·Recovery Quality | DeepEval custom metric 또는 Agent-as-a-Judge |
| 실패 위치 | Failure Stage Distribution | root/subagent/retriever/tool/HITL 단계별 trace 집계 |
| 메모리 | 저장·검색 정확성 및 격리 | deterministic test |
| 사용자 품질 | 만족도 및 수정 요청률 | Langfuse feedback |

대표 계산식은 다음과 같다.

```text
Task Success Rate
= 성공한 테스트 케이스 / 전체 테스트 케이스

Tool Precision
= 실제 호출 중 올바른 도구 호출 수 / 전체 실제 도구 호출 수

Tool Recall
= 올바르게 수행한 필수 도구 호출 수 / 전체 필수 도구 호출 수

Redundant Tool Call Rate
= 불필요하거나 중복된 도구 호출 수 / 전체 도구 호출 수

Cost per Successful Task
= 전체 평가 비용 / 성공한 케이스 수

Recovery Success Rate
= 장애 후 정상 완료한 수 / 복구 가능한 장애 주입 수
```

성공했더라도 도구를 과도하게 호출할 수 있으므로 성공률, 비용, 지연을 함께 비교해야 한다.

Trajectory 평가는 하나의 고정 경로와 문자열이 일치하는지를 검사하지 않는다. 업무 규칙상 필요한 승인 순서, 필수·금지 Tool, 재시도 상한과 postcondition은 deterministic assertion으로 평가하고, 여러 안전한 경로 중 계획·위임·근거 활용·실패 복구가 의미적으로 적절했는지는 Agent-as-a-Judge로 평가한다. 최종 결과가 성공하더라도 중간 단계의 잘못된 위임이나 불필요한 side effect가 있으면 과정 품질 실패로 별도 기록한다.

소규모 dataset의 평균만 보고 성능을 일반화하지 않는다. 모든 보고서에는 사례 수, 성공/실패 절대 건수, 실행 반복 수를 함께 표시한다. 가능한 비율 지표에는 신뢰구간을 병기하고, 3회 반복 사례는 평균뿐 아니라 최솟값과 실행 간 변동도 기록한다.

### 12.1 평가 실행 등급과 배포 gate

평가 비용과 외부 side effect를 통제하기 위해 실행 시점을 네 등급으로 분리한다.

| 등급 | 실행 시점 | 포함 항목 | 외부 서비스 | 기본 판정 |
|---|---|---|---|---|
| PR-fast | 모든 pull request | schema, 권한, HITL, timeout, 중복 실행, retriever deterministic test | mock/fake만 사용 | 하나라도 실패하면 차단 |
| Nightly-semantic | 매일 또는 주요 변경 후 | 핵심 개발 사례 10개, Ragas·DeepEval, 3회 반복 대상 | 읽기 전용 또는 sandbox | 기준선 대비 허용 하락폭 초과 시 경고·조사 |
| Release-candidate | 배포 후보 확정 시 | 개발 dataset 20개 전체, 비용·지연 포함 | sandbox tenant | 필수 안전 규칙 100%, semantic threshold 충족 |
| Final-holdout | 최종 승인 시 | 비공개 holdout 10개 포함 첫 전체 평가 | 통제된 sandbox | 개발셋과 holdout 모두 보고 후 승인 |

초기 threshold는 PoC 기준선을 얻은 후 metric별로 확정한다. 안전·권한·승인·tenant 격리처럼 위반을 허용할 수 없는 규칙은 평균 점수와 무관하게 100% 통과해야 한다. LLM Judge 기반 metric은 단일 실행의 작은 하락만으로 배포를 막지 않고, 반복 실행 결과·사례별 실패·사람 검토를 함께 본다.

### 12.2 Side-effect 평가 격리

Jira 등록, 파일 쓰기, MCP 호출과 같은 평가가 실제 운영 데이터에 영향을 주지 않도록 다음을 강제한다.

- PR에서는 fake adapter 또는 in-memory stub을 사용한다.
- Nightly와 release 평가는 전용 sandbox tenant·프로젝트·디렉터리만 사용한다.
- 생성 요청에는 idempotency key를 부여하고 성공한 항목을 재시도하지 않는다.
- 허용된 경로와 tenant를 코드 assertion으로 검사한다.
- 평가 실행 종료 후 생성 데이터를 식별할 run ID와 정리 정책을 둔다.
- 실제 운영 connector를 사용해야 하는 검증은 별도 승인과 dry-run을 거친다.

## 13. 평가 dataset 제안

초기부터 50~100개를 구축하면 평가 비용과 실행시간뿐 아니라 실패 원인 분석 부담이 커진다. 평가 pipeline과 rubric을 만드는 PoC는 대표 사례 10개로 시작하고, 개발·기준선 dataset 20개와 별도의 비공개 holdout 10개를 합친 총 30개를 첫 평가 기준으로 사용한다.

### 13.1 개발 dataset과 holdout 분리

| 유형 | 개발·기준선 | Holdout | 합계 | 주요 검증 |
|---|---:|---:|---:|---|
| 기본 Agent·no-tool | 4개 | 1개 | 5개 | 요청 이해, 목표 달성, 불필요한 Tool 호출 방지 |
| RAG 문서 질의 | 4개 | 3개 | 7개 | 검색 정확성, faithfulness, relevancy |
| Tool 선택·인자 | 3개 | 1개 | 4개 | 도구 선택, 인자 정확성 |
| 서브에이전트·trajectory | 2개 | 1개 | 3개 | 위임 대상, 결과 활용, 전체 실행 경로 |
| HITL 승인·거부 | 2개 | 1개 | 3개 | 승인 전 실행 방지, 승인·거부 후 상태 |
| 실패·부분 성공·복구 | 2개 | 1개 | 3개 | timeout, 재시도, PARTIAL_RESULT |
| 권한·데이터 격리 | 2개 | 1개 | 3개 | 금지 도구와 tenant/user 격리 |
| 모호하거나 실행 불가능한 요청 | 1개 | 1개 | 2개 | 무리한 실행과 환각 방지 |
| 합계 | **20개** | **10개** | **30개** | |

개발 dataset은 평가 코드와 rubric 개발, 모델·프롬프트 개선, 실패 원인 분석에 반복 사용한다. Holdout은 개발 중 결과를 보며 튜닝하지 않고 최종 후보가 정해진 후 실행하여 dataset 과적합 여부를 확인한다. Holdout 결과를 분석하여 수정에 사용한 사례는 다음 평가 주기부터 개발 dataset으로 승격하고 새로운 holdout으로 교체한다.

20개는 평가 체계를 시작하기에는 충분하지만 최종 성능을 일반화하기에는 부족하다. 특히 RAG 4개는 한 건이 평균의 25%, HITL 2개는 한 건이 50%를 바꾸므로 개발 dataset 점수만으로 제품 전체 성능을 단정하지 않는다. 첫 보고 수치는 holdout을 포함한 30개 결과와 사례 수를 함께 표시한다.

### 13.2 기존 평가 설계에서 가져오는 구성 원칙

본 문서의 20개 개발 dataset과 10개 holdout 구성을 현재 실행 기준으로 사용한다. `docs/설계 및 구현/중간발표 이후/설계/4_평가_설계.md`의 기존 G-DOC/G-QUERY/G-TASK/G-PROMPT 규모와 담당 계획은 본 작업의 정본으로 사용하지 않되, 다음 평가 원칙은 흡수한다.

- **어려운 RAG corpus:** 주제가 완전히 다른 문서 대신 서로 혼동하기 쉬운 정보시스템 구축·RFP 계열 문서 4~5건을 fixture로 사용한다. 문서 fixture 수는 위 30개 평가 사례 수에 포함하지 않는다.
- **두 단계 정답 라벨:** 기대 문서 ID와 기대 chunk ID를 함께 기록하여 문서 후보 선정 실패, chunk 검색 실패, 생성 실패를 구분한다.
- **질문 스타일 혼합:** 문서 어휘 기반 질문과 실제 사용자의 자연어 질문을 섞는다.
- **정보 부재 정직성:** 문서에 없는 담당자·일정·공수를 추측하지 않고 정보가 없다고 답하는 RAG 사례를 포함한다.
- **No-tool negative:** 정상 질문이지만 Tool이 필요 없는 사례를 넣어 불필요 호출률을 측정한다. 전체 dataset의 1/3이 아니라 Tool 선택을 검증하는 하위 사례 중 약 1/3을 no-tool로 구성한다.
- **부분 실패:** 여러 작업 중 일부만 성공했을 때 성공분과 실패분, 실패 원인을 구분하고 성공한 side effect를 중복 실행하지 않는지 확인한다.
- **Warm/cold 구분:** 지연시간 비교는 warm 실행을 기준으로 하고 cold start는 별도 관측값으로 기록한다.
- **사람 교차검증:** LLM Judge 결과 중 약 20%를 사람이 다시 판정하여 Pass/Fail 일치율과 점수 차이를 함께 기록한다. 무작위 표본만 고르지 않고 threshold 경계, Judge 불일치, 안전 관련 실패를 우선 포함한다. 개발 dataset 기준 최소 4개, 첫 전체 평가 30개 기준 최소 6개가 대상이다.

모든 사례에 Ragas와 DeepEval을 동시에 실행하지 않는다.

```text
RAG 사례
└─ Ragas + 필요한 일부 DeepEval metric

Agent 행동·trajectory 사례
└─ DeepEval + deterministic assertion

권한·격리 사례
└─ pytest deterministic assertion 중심
```

### 13.3 반복 실행과 확장

LLM 결과의 비결정성을 확인하기 위해 모든 사례를 무조건 여러 번 실행하지 않고 HITL, 병렬 Tool, side effect, 서브에이전트, RAG 경계 사례, timeout·부분 실패 등 핵심 개발 사례 10개만 3회 반복한다.

```text
일반 개발 사례 10개 × 1회 = 10회
핵심 개발 사례 10개 × 3회 = 30회
Holdout 사례       10개 × 1회 = 10회
────────────────────────────────
첫 전체 평가 실행 수             = 약 50회
```

dataset은 다음처럼 단계적으로 확장한다.

```text
PoC                         10개
개발·기준선                 20개
첫 전체 평가(holdout 포함)  30개
운영 안정화                 40~50개 이상
```

사례 수를 임의로 채우지 않고 운영 실패 발견, 버그 수정, 신규 tool/subagent 추가, 새로운 문서·업무 유형 추가, 모델·프롬프트 변경으로 인한 취약점 발견 시 회귀 사례를 추가한다.

### 13.4 평가 사례 schema

각 사례는 공통 필드와 평가 유형별 선택 필드를 포함한다.

```json
{
  "id": "EVAL-HITL-001",
  "split": "development",
  "input": "사용자 요청",
  "expected_outcome": "완료되어야 하는 목표",
  "required_tools": ["필수 도구"],
  "forbidden_tools": ["호출하면 안 되는 도구"],
  "acceptable_tool_paths": [["search", "create"]],
  "required_tool_order": [["search", "create"]],
  "expected_arguments": {},
  "argument_predicates": {},
  "max_calls_per_tool": {"create": 1},
  "allowed_retries": {"search": 1, "create": 0},
  "reference_answer": "필요한 경우만",
  "expected_document_ids": [],
  "expected_chunk_ids": [],
  "required_facts": [],
  "forbidden_claims": [],
  "must_acknowledge_missing_information": false,
  "expected_status": "SUCCESS",
  "must_report_failure_reason": false,
  "must_not_retry_successful_items": false,
  "max_tool_calls": 5,
  "requires_approval": true,
  "postconditions": ["sandbox Jira issue가 정확히 1건 생성됨"],
  "tags": ["hitl", "jira", "side_effect"]
}
```

모든 Agent가 하나의 고정된 trajectory만 따라야 한다고 가정하지 않는다. 여러 경로가 같은 목표를 안전하게 달성할 수 있으면 `acceptable_tool_paths`, argument predicate와 최종 `postconditions`로 허용 범위를 표현한다. 정확한 실행 순서는 업무 규칙상 필요한 구간에만 강제한다.

## 14. 최종 결론

현재 프로젝트에는 다음 전략이 가장 적합하다.

1. 가장 먼저 HITL 승인 tool-call의 `FAILED / STREAM_CLOSED` 오기록과 resume 매칭 문제를 수정하고 회귀 테스트로 고정한다.
2. 수정된 기록을 기준으로 Langfuse Python SDK v3 기준선을 저장하고 v4로 마이그레이션한다.
3. LangSmith callback, 자동 tracing 환경변수와 outbound 경로를 비활성화하거나 제거한다.
4. 프로젝트 공통 OpenTelemetry 계측과 Collector 구조를 단계적으로 도입한다.
5. OTel GenAI semantic convention을 우선하고 프로젝트 고유 값만 `skn.*`로 정의한다.
6. Langfuse를 통해 필요한 trace 구조, 필터, 평가 화면과 운영 지표를 학습한다.
7. DeepEval과 pytest로 Agent의 end-to-end, component, trajectory, 안전 규칙 회귀 테스트를 구축한다.
8. 문서 파싱·retriever는 deterministic 지표로 측정하고 Ragas는 RAG 응답의 문맥·근거성 평가에 사용한다.
9. 평가 dataset과 Ragas·DeepEval·자체 evaluator의 원시 결과는 프로젝트 내부를 정본으로 관리하고 Langfuse에도 전송한다.
10. 원문 tool payload는 기본 비수집하며 allowlist, opt-in, 크기 제한과 fail-closed 정책을 적용한다.
11. 프로젝트 전용 요약 UI는 실제 요구가 확인된 경우에만 선택적으로 고도화한다.
12. Langfuse 대체 플랫폼은 현재 확정 로드맵이 아닌 장기 조건부 선택지이며, 별도 Go 결정과 병행 운영 검증을 통과한 경우에만 Langfuse 제거를 검토한다.

핵심은 OpenTelemetry와 Langfuse를 경쟁 제품으로 보지 않는 것이다.

```text
OpenTelemetry = 실행 데이터를 만드는 표준 계측·전송 계층
Langfuse = 그 데이터를 저장·탐색·평가하는 완성된 플랫폼
Ragas/DeepEval = 품질 점수를 계산하는 평가 계층
```

초기에는 `OpenTelemetry + Langfuse`로 관측 요구사항을 발견하고, `DeepEval + pytest + Ragas`로 실제 품질을 검증하는 구성이 가장 균형 잡힌 선택이다. 장기적으로는 OpenTelemetry 자체가 아니라, OpenTelemetry를 기반으로 직접 구축한 수집·저장·분석·평가 플랫폼이 Langfuse를 대체한다.

## 15. 참고 자료

- OpenTelemetry 공식 문서: <https://opentelemetry.io/docs/>
- OpenTelemetry 개요: <https://opentelemetry.io/docs/what-is-opentelemetry/>
- OpenTelemetry GenAI semantic convention: <https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/>
- Langfuse 문서: <https://langfuse.com/docs>
- Langfuse Versions & Compatibility: <https://langfuse.com/docs/compatibility>
- Langfuse Python SDK v3 → v4: <https://langfuse.com/docs/observability/sdk/upgrade-path/python-v3-to-v4>
- Langfuse Existing OpenTelemetry Setup: <https://langfuse.com/faq/all/existing-otel-setup>
- Langfuse Experiments: <https://langfuse.com/docs/evaluation/experiments/experiments-via-sdk>
- Langfuse Scores API/SDK: <https://langfuse.com/docs/evaluation/evaluation-methods/scores-via-sdk>
- LangSmith Evaluation Concepts: <https://docs.langchain.com/langsmith/evaluation-concepts>
- LangSmith OpenTelemetry Evaluation: <https://docs.langchain.com/langsmith/evaluate-with-opentelemetry>
- LangSmith Self-hosting: <https://docs.langchain.com/langsmith/self-hosted>
- Ragas Metrics: <https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/>
- DeepEval Agent Evaluation: <https://deepeval.com/docs/getting-started-agents>
