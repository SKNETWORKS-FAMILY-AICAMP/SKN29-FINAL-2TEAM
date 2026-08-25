# Deep Agents From Scratch 분석

> 2026-08-10 작성. 담당: 지훈. 마감: 월(8/10) 분석 → 화(8/11) 공유
> (`3_Harness_조사/README.md` 분담표).
> 목적: repo 학습이 아니라 우리 Agent Harness(`../2_아키텍처_초안.md` §3) 설계
> 근거 만들기. 마지막 절은 "적용할 것 / 적용하지 않을 것과 이유"로 끝낸다는
> 산출 규칙을 따른다.

**저장소 정정**: `README.md` 분담표의 링크(`braincrew-lab/deep-agents-from-scratch`)는
존재하지 않는다. 공개적으로 확인되는 원본은 **`langchain-ai/deep-agents-from-scratch`**
(LangChain Academy 연계 교육 자료, MIT License, ★703)다. 회의록 §25에 이미 이
정정이 메모돼 있다. 같은 팀이 만든 프로덕션 버전 **`langchain-ai/deepagents`**
("The batteries-included agent harness", ★27.5k)도 실제 제품에서 이 패턴들이
어떻게 완성되는지 확인하는 용도로 같이 봤다.

## 1. 전체 Architecture

5개 노트북이 순서대로 쌓이는 구조다. 별도 프레임워크가 아니라 **기본 ReAct
루프 위에 세 가지 패턴(Planning·File System·Sub-agent)을 하나씩 얹는 실습**이다.

| 노트북 | 추가되는 것 |
|---|---|
| `0_create_agent` | LangGraph `create_agent`의 기본 ReAct(Reason→Act) 루프 — 이후 전부의 토대 |
| `1_todo` | TODO 리스트 기반 작업 계획(Task Planning) |
| `2_files` | Agent State에 저장되는 가상 파일시스템 (Context Offloading) |
| `3_subagents` | `task()` 툴로 하위 에이전트에 위임 (Context Isolation) |
| `4_full_agent` | 위 세 가지 + 실제 웹 검색을 합친 완성형 리서치 에이전트 |

저자들이 이 세 패턴을 뽑은 근거는 "장시간(long-horizon) 작업을 하는 실제
에이전트들의 공통 관찰"이다 — Manus는 평균 툴콜 50회, Claude Code는 코딩을
넘어선 범용 작업에 쓰인다. 즉 Deep Agent는 특정 기술이 아니라 **툴콜 수가 많고
오래 걸리는 작업에서 컨텍스트가 터지지 않게 하는 엔지니어링 패턴의 묶음**이다.

## 2. Agent 실행 흐름 (Loop)

기본은 표준 ReAct: 요청 → 모델이 다음 행동 결정 → Tool 실행 → 결과를 컨텍스트에
반영 → 반복 → 종료 판단. `1_todo`부터는 이 루프에 "계획 갱신"이 끼어든다 — 매
스텝마다 `write_todos()`로 상태(pending/in_progress/completed)를 갱신하며
진행한다. 저자들은 이를 "recitation"(계획을 반복해서 되뇌기)이라 부르는데,
스텝 수가 늘어나도 에이전트가 처음 목적을 잃지 않게 하는 장치다.

## 3. Context 유지 방식

`2_files.ipynb`가 핵심이다. 대화 이력을 계속 프롬프트에 누적하는 대신
`ls()`/`read_file()`/`write_file()`/`edit_file()` 툴로 **Agent State 안의 가상
파일시스템**에 중간 결과를 내려놓는다("Context Offloading"). 필요할 때만 다시
읽어 들이므로 토큰 사용량이 스텝 수에 비례해 무한정 늘지 않는다. 프로덕션 버전
(`deepagents`)은 여기에 "긴 스레드 요약(summarize)"까지 더해 Context
Management를 완성한다.

## 4. Memory 구조

교육용 저장소의 가상 파일시스템은 Agent State에 저장되므로 같은 thread의 대화
턴에서는 유지될 수 있다. 다만 별도의 cross-thread Persistent Memory를 핵심
기능으로 다루지는 않는다. 세션을 넘어서는 기억은 프로덕션 `deepagents`가
"pluggable state and store backends for cross-session recall" 형태로 제공한다.
즉 세션 간 기억은 기본 Loop의 필수 요소가 아니라 선택 가능한 확장 기능이다.

## 5. Tool 호출 구조

기본 Tool 호출은 일반적인 함수콜(모델이 스키마를 보고 고르는 방식)과 같다.
차별점은 **위임 자체가 하나의 Tool이라는 점**이다 — `3_subagents.ipynb`의
`task()` 툴은 "이 하위 작업을 이런 성격의 서브 에이전트에게 맡겨라"를 모델이
스스로 호출하는 구조다. 서브 에이전트는 좁은 Tool 세트와 별도 컨텍스트
윈도우를 가져서, 부모 에이전트의 컨텍스트가 하위 작업 세부사항으로 오염되지
않는다(Context Isolation). 서로 독립적인 작업은 병렬 실행도 지원한다.

## 6. MCP 연결

`deep-agents-from-scratch` 노트북 자체에는 MCP가 등장하지 않는다(Tavily 웹
검색 API를 직접 툴로 감싸 쓴다). MCP 지원은 프로덕션 `deepagents`에서 "Tools —
bring your own functions or **any MCP server**"로 명시된다. 즉 이 교육 자료가
보여주는 건 MCP 자체가 아니라 MCP Tool이 나중에 얹힐 자리, 즉 "Tool Registry +
실행 로그" 구조다 — 우리 아키텍처 §3의 Tool Execution 행과 같은 자리다.

## 7. LLM·Model 연결 구조

`create_agent(model="openai:gpt-5.5", ...)`처럼 모델 문자열을 바꿔 끼우는
방식이고, "Tool Calling만 지원하면 어떤 LLM이든 동작한다"(model-agnostic)는
원칙을 못박는다. 다만 이 저장소가 보여주는 건 **에이전트 하나에 모델 하나**
방식이지, 런타임에 작업 난이도를 보고 모델을 바꾸는 라우팅은 다루지 않는다.

## 8. 여러 Agent·Tool 연결 방식

부모 에이전트 하나가 "Agent Registry" 형태로 여러 서브 에이전트 정의를 들고
있다가 상황에 따라 `task()`로 호출한다. 서브 에이전트끼리 직접 통신하지 않고
항상 부모를 거치는 스타(star) 토폴로지다 — 지난 논의에서 얘기한 "에이전트가
다른 에이전트를 Tool처럼 호출"하는 그림과 같다. 프로덕션 버전은 여기에
Human-in-the-loop(툴 실행 전 승인/수정/거부)와 Skills(필요할 때 불러 쓰는
재사용 행동 묶음)를 추가했다.

## 9. 우리 Harness에 적용할 것 / 적용하지 않을 것과 이유

| 패턴 | 적용 여부 | 이유 |
|---|---|---|
| Task Planning (TODO 상태 관리) | **적용** | 업무 추출 파이프라인(AS-IS §6)이 이미 1~5단계 고정 순서로 동작한 전례가 있다. 이미 아는 순서(추출→분배 등)는 매번 새로 짓게 두지 않고 instruction에 순서 그대로 박아 넣으며, Planning(TODO)은 그 순서를 실행·추적하는 용도로 쓴다. 순서를 미리 모르는 임의의 Builder 에이전트라면 계획 자체를 에이전트가 세운다 — 두 경우 모두 아키텍처 §3 Context 관리 행의 "단기 동작"에 포함된다. |
| Sub-agent Delegation (`task()`) | **여지만** | 아키텍처 §3에 "Agent-to-Agent = 여지만, 완성 목표 아님(멘토링 §6-4)"로 이미 정해져 있다. 위임 호출 자체는 단순하지만(재사용 가능한 Loop 함수를 한 번 더 부르는 정도), 권한 상속·budget 전파·순환 위임 방지·취소/timeout·동시성 제어까지 갖춰야 안전하게 운영 가능한데 이건 별도 범위다. 에이전트를 Tool처럼 등록하는 인터페이스 자리는 만들되, 여러 에이전트가 실제로 얽히는 시나리오를 8월에 완성하려 하지 않는다. |
| Context Offloading (가상 파일시스템) | **구조만 — 이번 조사로 확정** | 아키텍처 §3의 "Compaction·장기 Memory는 구조만"이 이 조사 결과를 반영해 확정하기로 되어 있던 항목이다. `chunk`/`doc` 테이블은 검색용 지식 저장소일 뿐 실행 중 scratch 공간과 역할이 달라 대체재로 보지 않는다. 대표 E2E는 툴콜 상한(정상 2~3회, 최대 5회)과 Tool 결과 크기 제한·잘라내기/요약 정책을 함께 적용하므로 우선순위가 낮다. Sub-agent 위임으로 스텝 수가 늘거나 큰 중간 결과를 여러 단계에서 다시 사용해야 하면 그때 최소 버전(ls/read_file/write_file)을 붙인다. |
| Persistent Memory (세션 간 기억) | **비적용** | 메모리 저장 자체가 근거 없는 값을 만들어내는 건 아니라 AS-IS §10과 직접 충돌하는 건 아니다(출처·타임스탬프를 같이 저장하면 오히려 근거 추적에 쓸 수 있다). 대신 (1) 팀·테넌트 간 기억 격리, (2) 오래된 판단의 최신성 무효화, (3) 세션 간 기억까지 포함하면 평가 범위가 한 번에 커진다는 세 가지 운영 부담이 8월 범위에 비해 크므로 이번엔 만들지 않는다. |
| Human-in-the-loop (툴 실행 전 승인) | **적용 (필수)** | 이미 "1차 확인 화면"이 있고 `5_E2E_시나리오.md` STEP 6이 정확히 이 자리다. Deep Agent가 Jira에 이슈를 만들기 전에도 같은 확인 단계를 반드시 거쳐야 한다. |
| Model-agnostic 연결 (모델 문자열 교체) | **적용** | 스키마 초안의 `agent.model` 컬럼과 정확히 같은 설계다. 다만 이 저장소는 "에이전트당 모델 하나"만 보여주므로, 단계별 모델 분리(Luna/Sol) 경험은 이 repo에서 새로 배우는 게 아니라 우리가 이미 가진 자산(AS-IS §6)을 그대로 쓴다. |
| MCP 연결 | **참고만** | 교육 자료엔 MCP 예제가 없어 그대로 가져올 코드가 없다. 다만 "Tool Registry에 MCP Tool을 얹는다"는 자리 배치는 아키텍처 §4(MCP 실행 구조)와 일치해 구조 확인 용도로만 썼다. 이 저장소는 신뢰된 자체 API(Tavily)만 다뤄 인증정보 보호·SSRF 방지 같은 운영 이슈를 다루지 않는다 — 사용자가 임의 MCP 서버 URL을 등록하는 우리 구조에서는 이 부분을 `Deep-Agent_활용_설계_정리.md` §4에서 별도로 채운다. |
| Shell access / Skills | **비적용** | 코딩 에이전트(Claude Code류)에 최적화된 기능이라 프로젝트 운영 코파일럿에는 해당 사항이 없다. |

**한 줄 결론**: 이 저장소에서 실제로 가져갈 판단은 "Planning은 동작하게,
Sub-agent와 Context Offloading은 자리만 만들고, Persistent Memory는 하지
않는다" 세 가지다. 이는 아키텍처 초안 §3의 기존 방향과 어긋나지 않고, 오히려
그 문서가 "미확정"으로 남겨 둔 Context 관리 행에 근거를 채워 넣는다.
