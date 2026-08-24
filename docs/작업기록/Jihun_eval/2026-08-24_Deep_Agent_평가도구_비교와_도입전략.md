# Deep Agent 평가 도구 비교와 단계적 도입 전략

- 작성일: 2026-08-24
- 작성 목적: Deep Agent의 성능 평가·검증을 위한 도구별 역할을 구분하고, 현재 프로젝트에 적용할 평가 및 관측성 구성을 결정한다.
- 비교 대상: Langfuse, LangSmith, OpenTelemetry, Ragas, DeepEval

## 1. 배경

현재 프로젝트는 LangGraph/Deep Agents 기반으로 동작하며 다음과 같은 복합 실행 구조를 가진다.

- 루트 에이전트와 서브에이전트 위임
- LLM 및 여러 도구 호출
- RAG 기반 문서 검색
- 메모리 및 체크포인트
- HITL 승인·거부·재개
- 병렬 실행, timeout, 실패 복구
- 사용자·팀·테넌트별 권한과 데이터 격리

Langfuse와 LangSmith에는 실행 추적 연동만 완료된 상태다. 비교 검토 결과 신규 평가 체계에서는 LangSmith를 사용하지 않고 Langfuse를 초기 중앙 관측·평가 플랫폼으로 사용하기로 결정했다. 앞으로는 단순히 실행 내역을 보는 것을 넘어, Agent가 목표를 달성했는지, 올바른 도구를 안전하고 효율적으로 사용했는지, 모델이나 프롬프트 변경으로 성능이 저하되지 않았는지를 검증해야 한다.

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
- 호출된 도구와 인자, 결과, 오류
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

- Langfuse를 초기 중앙 관측·평가 플랫폼으로 사용한다.
- 기존 LangSmith 설정과 callback은 별도 구현 작업에서 비활성화하거나 제거한다.
- LangGraph 고유 구조의 디버깅이 필요해지더라도 우선 OpenTelemetry span과 프로젝트 이벤트 모델을 보강한다.
- 향후 요구사항이 바뀌면 특정 플랫폼 종속 연동보다 OpenTelemetry 호환 백엔드를 우선 검토한다.

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
- LLM/Agent용 span attribute 규격을 팀에서 설계해야 한다.
- Collector와 저장 백엔드 운영이 필요할 수 있다.
- 민감정보 필터링을 잘못 구성하면 prompt나 도구 인자가 외부로 전송될 수 있다.

## 6. OpenTelemetry UI와 저장소를 직접 만들 경우

OpenTelemetry용 저장소와 UI를 자체 개발하면 기술적으로 Langfuse를 사용하지 않아도 된다. 그러나 이 경우 단순 로그 화면이 아니라 사실상 작은 LLM 관측 플랫폼을 직접 만드는 셈이다.

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

범용 APM은 HTTP와 DB 호출을 잘 보여주지만 다음 정보는 프로젝트에서 별도로 정의해야 한다.

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

예시 attribute는 다음과 같다.

```text
agent.name
agent.version
agent.parent_id
llm.model
llm.input_tokens
llm.output_tokens
tool.name
tool.arguments
retrieval.document_ids
evaluation.task_success
evaluation.faithfulness
```

### 6.3 평가 및 운영 기능

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
└─ Langfuse

전체 Agent 회귀 평가
└─ DeepEval + pytest

RAG 전용 평가
└─ Ragas

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
- OpenTelemetry: Django부터 Agent, tool, DB까지 공통 계측 및 백엔드 중립성 확보
- LangSmith: Langfuse와의 역할 중복을 피하기 위해 사용하지 않음

## 10. 단계적 도입 전략

### 10.1 1단계: OpenTelemetry와 Langfuse 병행

현재 구현과 목표 구조를 구분한다. 현재 코드는 Langfuse의 LangChain callback을 사용하며, Langfuse SDK가 내부적으로 OpenTelemetry provider와 전송을 구성한다. 아직 프로젝트가 직접 관리하는 공통 OpenTelemetry 계측 계층과 Collector를 구축한 상태는 아니다.

```text
현재
Deep Agent → Langfuse LangChain callback
                 └─ Langfuse SDK 내부 OpenTelemetry 처리

목표
Deep Agent → 프로젝트 공통 OpenTelemetry 계측 → OpenTelemetry Collector
                                            ├─ Langfuse
                                            └─ 자체 관측·평가 플랫폼
```

이 단계에서는 Langfuse를 완성된 UI이자 요구사항 발견 도구로 사용한다. 실제 운영 과정에서 팀이 자주 확인하는 화면과 필터, 필요한 지표, 부족한 기능을 기록한다.

필수로 표준화할 metadata 예시는 다음과 같다.

- trace_id, session_id, user_id_hash, tenant_id
- agent_name, agent_version, subagent_name
- model, input/output token, cost
- tool_name, tool_result, success, latency
- 검색 문서 ID와 retrieval score
- HITL 승인·거부·재개 상태
- 평가 점수와 오류 유형
- prompt 및 runtime profile version

민감한 원문과 tool arguments는 저장 전에 애플리케이션 계층에서 우선 마스킹한다. Collector의 필터링은 추가 방어선으로 사용하며, Collector 설정 하나에 개인정보 보호를 전적으로 의존하지 않는다.

### 10.2 2단계: 실제 UI 요구사항 수집

Langfuse를 사용하면서 다음을 확인한다.

- 실패 분석에 실제로 사용하는 필터
- 가장 자주 확인하는 span과 attribute
- 모델·프롬프트·Agent 버전 비교 방식
- Ragas·DeepEval 점수를 보는 단위
- 성공률, 비용, 지연 중 우선하는 지표
- 개발자와 운영자의 화면 요구 차이
- Langfuse에서 부족하거나 불편한 기능

### 10.3 3단계: 프로젝트 전용 요약 UI 추가

처음부터 Langfuse 전체를 복제하지 않는다. 먼저 OTLP 수신, trace·평가 결과 저장, 검색·집계 API, 보존·삭제 정책을 갖춘 뒤 운영 의사결정에 필요한 요약 화면부터 만든다.

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

### 10.4 4단계: Langfuse 유지·축소·제거 판단

자체 UI가 안정된 뒤 다음 조건을 기준으로 Langfuse 유지 여부를 결정한다.

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

Deep Agent는 최종 답변만 평가해서는 안 된다. 목표 달성, 과정, 효율, 안전성을 분리해 본다.

| 평가 영역 | 추천 지표 | 평가 방법 |
|---|---|---|
| 최종 성공 | Task Success Rate | DeepEval/custom rubric |
| 도구 선택 | Tool Selection Accuracy | deterministic + DeepEval |
| 인자 정확성 | Argument Accuracy | schema/business rule 검사 |
| 실행 효율 | 평균 step/tool/LLM 호출 수 | trace 집계 |
| 지연 | p50/p95 end-to-end latency | Langfuse/OpenTelemetry |
| 비용 | 성공 작업당 token 및 비용 | Langfuse 집계 |
| RAG 검색 | Context Precision/Recall | Ragas |
| 근거성 | Faithfulness | Ragas 또는 DeepEval |
| 안전성 | 승인·권한 위반율 | pytest deterministic test |
| 안정성 | timeout·실패·복구 성공률 | trace + 장애 주입 테스트 |
| 위임 품질 | subagent 선택 및 결과 활용 | custom evaluator |
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

## 13. 초기 평가 dataset 제안

초기부터 50~100개를 구축하면 평가 비용과 실행시간뿐 아니라 실패 원인 분석 부담이 커진다. PoC는 대표 사례 10개로 시작하고, 초기 기준선은 약 20개로 구성한다.

| 유형 | 초기 기준선 | 주요 검증 |
|---|---:|---|
| 기본 Agent 업무 | 4개 | 요청 이해, 목표 달성, 최종 응답 |
| RAG 문서 질의 | 4개 | 검색 정확성, faithfulness, relevancy |
| Tool 호출 | 3개 | 도구 선택, 인자 정확성 |
| 서브에이전트 위임 | 2개 | 위임 대상과 결과 활용 |
| HITL 승인·거부 | 2개 | 승인 전 실행 방지와 거부 처리 |
| 실패·timeout·재시도 | 2개 | 오류 처리와 복구 |
| 권한·데이터 격리 | 2개 | 금지 도구와 tenant/user 격리 |
| 모호하거나 실행 불가능한 요청 | 1개 | 무리한 실행과 환각 방지 |
| 합계 | **20개** | |

모든 사례에 Ragas와 DeepEval을 동시에 실행하지 않는다.

```text
RAG 사례 4개
└─ Ragas + 필요한 일부 DeepEval metric

Agent 행동 사례 14개
└─ DeepEval + deterministic assertion

권한·격리 사례 2개
└─ pytest deterministic assertion 중심
```

dataset은 다음처럼 단계적으로 확장한다.

```text
PoC             10개
초기 기준선      20개
첫 배포          30~40개
운영 안정화      50개 이상
```

사례 수를 임의로 채우지 않고 운영 실패 발견, 버그 수정, 신규 tool/subagent 추가, 새로운 문서·업무 유형 추가, 모델·프롬프트 변경으로 인한 취약점 발견 시 회귀 사례를 추가한다.

각 사례에 다음 정보를 포함한다.

```json
{
  "input": "사용자 요청",
  "expected_outcome": "완료되어야 하는 목표",
  "required_tools": ["필수 도구"],
  "forbidden_tools": ["호출하면 안 되는 도구"],
  "expected_arguments": {},
  "reference_answer": "필요한 경우만",
  "expected_sources": [],
  "max_tool_calls": 5,
  "requires_approval": true,
  "tags": ["hitl", "jira", "side_effect"]
}
```

## 14. 최종 결론

현재 프로젝트에는 다음 전략이 가장 적합하다.

1. 초반에는 OpenTelemetry와 Langfuse를 함께 사용한다.
2. 현재 Langfuse callback 중심 구조에서 프로젝트가 직접 관리하는 OpenTelemetry 계측과 Collector 구조로 단계적으로 전환한다.
3. Langfuse를 통해 필요한 trace 구조, 필터, 평가 화면과 운영 지표를 학습한다.
4. DeepEval과 pytest로 Agent의 end-to-end, component, 안전 규칙 회귀 테스트를 구축한다.
5. Ragas는 RAG 구간의 검색 품질과 답변 근거성 평가에 한정한다.
6. 평가 dataset과 Ragas·DeepEval·자체 evaluator의 원시 결과는 프로젝트 내부를 정본으로 관리하고 Langfuse에도 전송한다.
7. LangSmith는 Langfuse와 역할이 중복되므로 사용하지 않으며 기존 연동은 비활성화하거나 제거한다.
8. 필요한 UI가 구체화되면 수집·저장·조회 계층을 먼저 마련하고 프로젝트 전용 요약 화면부터 만든다.
9. 자체 플랫폼이 정량적인 기능·성능·보안 기준을 충족하고 병행 운영 검증을 통과한 뒤에만 Langfuse를 제거한다.

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
- Langfuse 문서: <https://langfuse.com/docs>
- Langfuse Experiments: <https://langfuse.com/docs/evaluation/experiments/experiments-via-sdk>
- Langfuse Scores API/SDK: <https://langfuse.com/docs/evaluation/evaluation-methods/scores-via-sdk>
- LangSmith Evaluation Concepts: <https://docs.langchain.com/langsmith/evaluation-concepts>
- LangSmith OpenTelemetry Evaluation: <https://docs.langchain.com/langsmith/evaluate-with-opentelemetry>
- LangSmith Self-hosting: <https://docs.langchain.com/langsmith/self-hosted>
- Ragas Metrics: <https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/>
- DeepEval Agent Evaluation: <https://deepeval.com/docs/getting-started-agents>
