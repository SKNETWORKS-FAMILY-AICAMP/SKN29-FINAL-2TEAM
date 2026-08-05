# Agent1 MVP → LangGraph Agent 전환 작업기록

- 작업 시작: 2026-08-01 19:16 KST
- LangGraph 전환 시작: 2026-08-01 19:55 KST
- LangGraph 전환 완료: 2026-08-01 20:10 KST
- 실제 OpenAI API 검증 완료: 2026-08-01 20:13 KST
- 멘토 피드백·모델 비용 판단 기록 보강: 2026-08-01 20:22 KST
- GPT-5.6 Luna 전환·실호출 검증 완료: 2026-08-01 20:26 KST
- 파싱 팀 Docling Chunk 계약 반영 완료: 2026-08-01 20:35 KST

## 멘토 피드백과 반영 흐름

| 단계 | 멘토 피드백 핵심 | 변경 전 | 반영 결과 |
|---|---|---|---|
| MVP 범위 단순화 | 누락 안내, Snapshot, Human-in-the-loop는 후속으로 미루고 1→2→3번 Agent의 종단 흐름부터 만든다. 업무량 계산과 후보 분석은 현재 1번 Agent 내부에 둔다. | 보조 모듈과 예외 흐름이 바깥에 나뉜 복잡한 설계 | Agent1 범위를 `업무 추출 + 업무량 계산 + 후보 분석`으로 묶고, 선택 Connector 입력부터 Agent1 출력까지 하나의 MVP로 축소 |
| 첫 구현 범위 | 실제 Connector가 없으면 Mock 데이터를 사용해도 되므로, Connector 입력 함수와 Agent1 입출력을 먼저 동작시킨다. | 실제 Drive/Jira API와 `.env`가 없어 종단 실행 불가 | Drive·Jira·People Fixture와 선택 Source 수집 계층을 만들어 CLI에서 종단 시나리오 실행 |
| Agent 구조 재설계 | 세 함수를 코드가 무조건 호출하면 고정 Workflow일 뿐이다. LangGraph `StateGraph`와 GPT API를 사용하고, LLM이 요청과 데이터를 보고 Tool 사용 여부와 순서를 판단해야 한다. | `run_agent1`이 `_extract_tasks` → `_calculate_workloads` → `_analyze_candidates`를 항상 호출 | GPT Node와 `ToolNode`가 조건부 순환하는 StateGraph로 교체. 전체 분석·업무량만·설명 요청에 따라 각각 3개·1개·0개 Tool을 선택하도록 구현 및 테스트 |

핵심 변화는 **“정해진 함수 세 개를 실행하는 파이프라인”에서 “LLM이 필요한 Tool을 판단해 사용하는 Agent”로 전환한 것**이다. 다만 업무량과 후보 점수처럼 재현성이 필요한 계산은 LLM의 자유 생성에 맡기지 않고 결정론적 Tool로 유지했다.

## 수행 내용과 변경 파일

- `services/agent1/state.py`: 메시지·입력·Tool 결과·호출 이력을 보존하는 State
- `services/agent1/chunk_adapter.py`: 파싱 팀 Docling JSON을 Agent용 Canonical Chunk로 변환
- `services/agent1/tools.py`: LLM이 선택하는 업무 추출·업무량·후보 분석 Tool
- `services/agent1/graph.py`: GPT Node와 ToolNode가 조건부 순환하는 StateGraph
- `services/agent1/prompts.py`: Tool 선택과 계산 경계를 설명하는 System Prompt
- `services/agent1/service.py`: 선택 Source 입력 수집과 StateGraph 실행 진입점
- `services/agent1/demo.py`: 실제 GPT API 요청, 사용 모델명과 Tool 호출 이력을 보여주는 CLI
- `services/agent1/fixtures/*.json`: Drive Chunk·Jira Issue·People Mock 입력
- `tests/test_agent1_mvp.py`: 선택 Source, 종단 결과, 미지원 Connector 테스트
- `docs/3_설계/Agent1_MVP_Mock_파이프라인.md`: 구조·사용자 시나리오·설명 스크립트

## 변경 이유와 전후

첫 MVP의 `run_agent1`은 세 함수를 무조건 호출하는 고정 워크플로우였다. 멘토 피드백에 따라 이 오케스트레이션을 제거하고, GPT가 사용자 요청과 State를 보고 Tool 호출 여부와 순서를 선택하도록 StateGraph로 교체했다. 계산식과 Fixture는 Tool·입력 데이터로 재사용했다.

## 검증

- `python -X utf8 -m unittest -v tests.test_agent1_mvp`: Fake LLM·Docling Adapter 기반 테스트 7개 통과
- 전체 요청 3개 Tool 선택, 업무량 요청 1개 Tool 선택, 설명 요청 Tool 미사용 확인
- OpenAI Tool Schema 변환 확인: `extract_tasks`, `calculate_workloads`, `analyze_candidates`
- `python manage.py test tests --verbosity 1`: 전체 142개 테스트 통과
- 설치 확인: LangGraph 1.2.10, LangChain 1.3.14, langchain-openai 1.4.1, OpenAI SDK 2.52.0
- `.env`의 `OPENAI_API_KEY` 설정 여부를 값 노출 없이 확인
- `OPENAI_MODEL=gpt-4.1-mini`로 실제 API 호출 성공
- 실제 GPT가 `extract_tasks` → `calculate_workloads` → `analyze_candidates`를 선택하고 최종 결과를 생성하는 종단 실행 확인

## 제한과 다음 작업

- 문서 입력은 파싱 팀이 전달한 `hanwha.chunks.json`을 사용하고, Jira/People은 Mock이다.
- 실제 GPT 종단 실행은 검증을 완료했다. 다만 운영 전에는 요청 유형별 Tool 선택 정확도와 비용·지연시간을 평가해야 한다.
- RunPod와 실제 Jira Issue API·People Repository는 아직 연결하지 않았다.

## 파싱 팀 Chunk 계약 반영

- 입력 확인: Docling 2.117.0, Hybrid Chunking, 44개 Chunk, 6페이지, 총 5,785 토큰.
- `meta.doc_items`와 bbox 전체는 Prompt 크기가 크므로 Agent에 직접 전달하지 않는다.
- `document_id`, `chunk_id`, `file_name`, `page/pages`, `section`, `text/raw_text`, Parser 버전만 Canonical Chunk로 보존한다.
- State에는 원문 대조용 `raw_text`와 Parser 계보를 보존하되, LLM Prompt에는 문서 ID·Chunk ID·파일명·페이지·제목·`text`만 전달해 중복 토큰을 줄인다.
- `parser_status`가 성공이 아니거나 `chunk_id/text`가 없으면 Agent 실행 전에 차단한다.
- 업무 근거 저장 시 문서 ID, Chunk ID, 페이지, 원문 인용이 실제 입력과 모두 일치하는지 검증한다.
- OCR 오인식과 이미지 설명 잔재가 확인되어, 제품 소개·사양·마케팅 문구를 프로젝트 업무로 추측하지 않도록 Prompt 규칙을 추가했다.
- 로컬 계약 테스트 2개를 추가해 Hanwha 44개 변환과 실패 Parser 차단을 검증했다.
- Hanwha 원문 전체를 실제 OpenAI API로 보내는 종단 검증은 외부 전송에 대한 사용자 명시 승인 전까지 보류했다.

## 모델 비용 확인과 결정

2026-08-01 OpenAI 공식 모델 문서의 Standard API 100만 토큰 가격을 기준으로 확인했다.

| 모델 | 입력 | 출력 | 판단 |
|---|---:|---:|---|
| `gpt-4.1-mini` | $0.40 | $1.60 | 현재 Agent1 실호출과 Tool Calling 검증 완료 |
| `gpt-5.4-mini` | $0.75 | $4.50 | 사용자 제시 가격과 일치 |
| `gpt-5.4-nano` | $0.20 | $1.25 | 사용자 제시 가격과 일치. 단순 추출·분류·랭킹용 비용 후보 |
| `gpt-5.6-luna` | $0.20 | $1.20 | 공식 통합 가격표 재확인 후 사용자 제시 가격과 일치 |

- 최초에는 개별 Luna 모델 페이지의 `$1.00 / $6.00` 표시를 사용해 변경을 보류했으나, 사용자가 알려준 최신 공식 통합 Pricing 페이지를 직접 확인한 결과 Standard 단문맥 가격은 `$0.20 / $1.20`이었다. 상충 시 통합 Pricing 페이지를 현재 가격의 기준으로 삼아 판단을 정정했다.
- `gpt-5.6-luna`는 비용 민감·대량 처리용 모델이며 Function Calling을 지원하므로 Agent1의 추출·도구 라우팅 역할에 부합한다.
- 기본 모델과 로컬 `.env`를 `gpt-5.6-luna`로 변경했다.
- 현재 경로는 Chat Completions + Function Tools이므로 `reasoning_effort="none"`을 명시하고 지원 호환성이 불명확한 `temperature=0`은 제거했다.
- 실제 Luna 호출에서 `extract_tasks` → `calculate_workloads` → `analyze_candidates` 선택과 최종 결과 생성을 확인했다.
- 공식 근거: OpenAI 통합 `Pricing` 페이지와 GPT-5.6 모델 가이드.

## 2026-08-03 멘토 피드백 재검토와 최신 main 통합

- 검토·통합 시작: 2026-08-03 10:43 KST
- 최신 main 통합 완료: 2026-08-03 10:49 KST
- 영향 재검토 완료: 2026-08-03 10:52 KST
- 회귀 검증 완료: 2026-08-03 10:53 KST

### 검토 과정에서 확정·보완한 판단

| 항목 | 검토 결과 | 이유 |
|---|---|---|
| CLI 요약·디버그 출력 | `_print_summary`와 임시 `print(state)` 제거 대상으로 확정 | Agent 책임이 아니며 실행 결과를 이중 표현하고 내부 State를 노출할 수 있음 |
| 파싱 입력 범용화 | 특정 `hanwha.chunks.json` 구조를 직접 아는 코드를 Agent 경계 밖으로 이동하는 방향 | Agent는 특정 파일이 아니라 문서 파이프라인의 표준 Chunk 계약을 받아야 함 |
| Chunk 전달 | 단순 고정 Top-K가 아니라 직접 근거 + 같은 절/인접 문맥 + 일정·제약·역할·공수 보조 근거를 토큰 예산 안에서 구성 | 업무 근거가 한 Chunk에만 있지 않을 수 있으므로 검색 결과의 주변 문맥 확장이 필요함 |
| Jira·People 전달 | 상세 원천 데이터는 State/결정론적 Tool 입력으로 유지하고, LLM에는 업무 판단에 필요한 최소 요약만 전달 | 계산 재현성과 근거 추적은 유지하면서 매 LLM 순환의 중복 토큰과 불필요한 개인정보 노출을 줄임 |
| Tool 내부 조회 | 이번 최소 변경에는 포함하지 않고 Repository/검색 계층 연결 단계에서 재검토 | 멘토의 핵심은 불필요한 Prompt·분기 제거와 범용화이며, 모든 조회를 즉시 Tool 내부로 옮기라는 요구로 단정할 근거는 없음 |

### main 통합 결과

- `origin/main`을 갱신하고 `juneok` 브랜치를 `a13efb9`에서 `19cfab4`로 fast-forward 통합했다.
- 충돌은 없었으며 기존 Agent1 코드·테스트·설정 변경은 그대로 보존됐다.
- 이번 main 변경은 Docling 정규화·청킹 전략, 시스템 구성, 업무량 수식, 발표 자료 등 문서 중심이며 Agent1 코드를 직접 덮어쓴 변경은 없다.

### 통합 후 Agent1 영향

1. **문서 입력 계약을 다시 맞춰야 한다.** 최신 설계는 Chunk의 본문을 `text`, 제목 문맥까지 결합한 AI·임베딩 입력을 `contextualized_text`로 정의한다. 현재 전달 Fixture의 `text`(제목 포함)·`raw_text`(본문)와 의미가 다르므로 담당자와 최종 계약을 확인하기 전에는 한쪽 이름으로 성급히 고정하지 않는다.
2. **정규화 책임이 중복돼 있다.** main의 문서 파이프라인은 Raw `DoclingDocument`를 `NormalizedElement[]`로 정규화한 뒤 청킹하도록 설계됐다. 따라서 Agent1의 `normalize_docling_chunks`는 Raw Docling을 해석하는 범용 정규화기가 아니라, 최종 검색 Chunk DTO를 검증·변환하는 얇은 입력 Adapter로 축소하는 편이 맞다.
3. **관련 Chunk 선별 방향은 유효하지만 아직 연결 대상이 없다.** pgvector `vec_idx` 스키마는 있으나 실제 임베딩 저장·검색 경로는 TO-BE다. 지금은 테스트용 Selector/Fixture로 경계를 만들고, 검색 구현 이후 `retrieved_chunks` 공급부만 교체할 수 있어야 한다.
4. **업무량 Tool의 실제 데이터 Adapter가 필요하다.** 최신 조사 문서는 업무량을 `Σ remaining`, 가용용량을 근무시간·FTE·승인 휴가로 계산하며 실제 필드의 NULL 대체 정책도 요구한다. 현재 Fixture의 `remaining_hours`, `weekly_capacity_hours`, `absence_hours`는 실제 Jira/HR 계약과 다르므로 산식과 입력 Adapter를 별도 정렬해야 한다.
5. **Connector 현황을 정정한다.** Google Drive·Jira OAuth와 원문 다운로드는 AS-IS로 문서화됐고, RunPod 파싱·임베딩 및 pgvector 검색 연결은 TO-BE다. Agent의 Mock Connector는 실제 Connector가 전혀 없어서가 아니라 아직 Agent 입력 계약까지 이어지지 않은 구간을 대체한다.

### 검증과 다음 작업

- 통합 검증: fast-forward 완료, merge conflict 없음, Agent1 작업 파일 보존 확인.
- `python -X utf8 -m unittest -v tests.test_agent1_mvp`: Agent1 테스트 7개 통과.
- `python manage.py test tests --verbosity 1`: 전체 142개 테스트 통과.
- `git diff --check`: 오류 없음. 기존 작업 파일의 LF→CRLF 경고만 확인.
- 테스트 중 임시 `print(state)`가 전체 문서·Jira·People State를 출력하는 현상을 재현해 제거 필요성을 확인했다.
- 다음 구현 순서: 디버그 출력 제거 → 최종 Chunk DTO 합의 → 관련 문맥 Selector 경계 추가 → Prompt 최소화 → 실제 Jira/HR Adapter와 업무량 산식 정렬.
- `text/raw_text` 이름 변경과 검색 Top-K·토큰 예산 값은 파싱·검색 담당자 계약 및 실제 샘플 평가 후 확정한다.

## 2026-08-03 PPT용 Agent1 흐름 자료 작성

- 작업 시작: 2026-08-03 10:59 KST
- 작업 완료: 2026-08-03 11:01 KST
- 변경 파일: `docs/10_발표자료/Agent1_흐름_PPT_요약.md`
- 수행 내용: PPT 담당자가 Agent1의 입력, LLM 판단, 선택적 Tool 호출, State 순환, 최종 결과를 한눈에 이해할 수 있도록 Mermaid 흐름도와 Tool 책임 표, 현재/이후 구분, 30초 발표 문장을 작성했다.
- 변경 이유: 기존 설계 문서는 실행 방법과 코드 설명까지 포함해 발표 자료로 사용하기에는 정보량이 많았으므로, 실제 구현의 핵심과 아직 연결 전인 범위를 과장 없이 압축했다.
- 검증: 현재 `StateGraph`, `tools_condition`, 세 Tool, Mock/실제 영역 구분을 코드 및 최신 main 설계 문서와 대조했다. Mermaid 문법과 Markdown 구조는 정적 검토했다.
- 알려진 제한: 실제 Jira·People Adapter, RunPod 파싱·임베딩, pgvector 검색 연결은 아직 구현 전이며 슬라이드에서도 이후 연결로 명시했다.

## 2026-08-03 파싱·청킹 담당자 연동 협의서 작성

- 작업 시작: 2026-08-03 11:04 KST
- 작업 완료: 2026-08-03 11:06 KST
- 변경 파일: `docs/3_설계/Agent1_문서파싱청킹_연동_협의서.md`
- 수행 내용: 현재 Fixture와 최신 청킹 설계의 `text/raw_text/contextualized_text` 의미 차이, 제안 Chunk JSON 계약, 전체 저장과 관련 문맥 선별의 역할 경계, Agent 입력 검증 기준, 담당자 확인 질문과 완료 조건을 정리했다.
- 변경 이유: Agent가 특정 Hanwha 파일과 Docling 내부 구조에 종속되지 않고 검색 가능한 공통 Chunk를 입력받으려면 파싱·청킹 담당자와 필드 의미·식별자·근거 추적 계약을 먼저 확정해야 한다.
- 변경 전후: 구두로 남아 있던 불확실성을 담당자가 체크하며 합의할 수 있는 문서와 전달 메시지로 전환했다. 필드명은 확정하지 않고 협의용 제안안으로 명시했다.
- 검증: 현재 `normalize_docling_chunks`, 전달 Fixture 계약, `normalization_strategy.md`, `docling_hybrid_to_vector_db_easy.md`의 출력 예시를 상호 대조했다.
- 알려진 제한·다음 작업: 담당자 답변 전에는 필드명을 변경하지 않는다. 계약 확정 후 JSON Schema/Pydantic DTO와 정상·실패·저품질·표 포함 Fixture 계약 테스트를 반영한다.

### 협의서 명세 보강

- 작업 시작: 2026-08-03 11:08 KST
- 작업 완료: 2026-08-03 11:11 KST
- 사용자 수정사항을 기준본으로 유지한 채 문서 상태(`DRAFT`), MUST/SHOULD/MAY 표현 규칙, 문서 단위 Payload, 필드 타입·필수 여부·제약, 상태·품질 코드 초안, 검증 실패 처리, 버전 호환 원칙, 최소 계약 테스트를 추가했다.
- 기존 설명·질문·전달 메시지는 보존하고, 아직 담당자 합의가 필요한 값은 확정 명세가 아닌 제안안으로 표시했다.

## 2026-08-03 파싱·청킹 담당자용 Agent1 설계 흐름 공유

- 작업 시작: 2026-08-03 11:20 KST
- 작업 완료: 2026-08-03 11:26 KST
- 변경 파일: `docs/3_설계/Agent1_설계흐름_파싱청킹팀_공유.md`
- 수행 내용: 전체 서비스에서 Agent1의 위치, StateGraph 내부 흐름, Chunk 검색·문맥 확장·근거 연결, State와 Prompt의 차이, 현재 구현과 피드백 반영 목표, 표준 출력 및 파싱 팀 접점을 Mermaid와 예시로 정리했다.
- 변경 이유: 파싱·청킹 담당자가 단순 필드 명세뿐 아니라 자신들의 출력이 Agent 내부에서 왜 필요하고 어떻게 사용되는지 이해할 수 있는 설계 흐름 자료가 필요했다.
- 변경 전후: 연동 협의서는 필드 계약 중심으로 유지하고, 새 문서는 Agent 설계와 데이터 소비 흐름 중심으로 분리했다.
- 검증: 현재 `StateGraph`, 세 Tool, Chunk Adapter와 앞서 확정한 수정 계획 및 최신 문서 파이프라인 역할 경계를 대조했다. AS-IS와 TO-BE를 구분해 미구현 검색 경로를 구현 완료로 표현하지 않았다.
- 다음 작업: 담당자 피드백을 두 문서에 반영해 Chunk 계약을 확정한 뒤 Agent1 호환 Adapter와 Selector를 구현한다.

### Prompt 흐름 보강

- 파싱·청킹 담당자가 Chunk의 실제 소비 지점을 이해할 수 있도록 현재 `AGENT1_SYSTEM_PROMPT` 전문, 각 입력 블록의 의도, `_system_message()`의 실제 필드 전달 방식, AS-IS와 TO-BE Prompt 경계를 설계 공유 문서에 추가했다.
- 현재 MVP가 전체 Jira·People 데이터를 Prompt에 전달하는 사실을 숨기지 않고 한계로 표시했으며, 향후 관련 문맥과 최소 요약만 Prompt에 전달하고 상세 데이터는 State·결정론적 Tool에서 사용하는 계획을 명시했다.

- 보강 시작: 2026-08-03 11:29 KST
- 보강 완료: 2026-08-03 11:31 KST
- 실제 코드 대조 결과 현재 Prompt에는 `contextualized_text`, `quality_flags`, `source_refs`가 직접 전달되지 않고 `section`과 `text`가 사용됨을 명시했다. 또한 `extract_tasks`의 `evidence.quote`가 `text`에 포함되는 검증과 최종 필드 의미의 연관성을 추가 설명했다.

## 2026-08-03 멘토 피드백 기반 Agent1 경계 개선 구현

- 작업 시작: 2026-08-03 11:34 KST
- 작업 완료: 2026-08-03 11:44 KST

### 피드백과 변경 전후

| 피드백·검토 결과 | 변경 전 | 변경 후 |
|---|---|---|
| CLI·디버그 출력 제거 | `run_agent1()`이 전체 State를 `print`하고 `_print_summary`가 별도 형식으로 재출력 | 전체 State와 `_print_summary` 제거, CLI는 표준 Agent1 결과 JSON만 출력 |
| 특정 파싱 결과 종속 완화 | `hanwha.chunks.json`의 `raw_text/text/meta.headings/pages` 의미에 종속 | 기존 `raw_text/text`와 제안 `text/contextualized_text`를 모두 수용하는 호환 Adapter 적용 |
| 관련 문맥만 LLM에 전달 | 입력된 모든 Chunk가 Prompt 대상 | 요청·업무 용어 Seed, 같은 절·앞뒤 Chunk, 최대 Chunk 수와 토큰 예산을 적용하는 교체 가능 Selector 추가 |
| Jira·People Prompt 최소화 | Jira Issue와 People 개인 상세를 매 LLM 순환마다 직렬화 | 상세 데이터는 State와 결정론적 Tool에 유지하고 Prompt에는 역할·스킬 고유 목록만 전달 |
| 품질·근거 계약 보강 | `document_id/chunk_id/page/text` 중심 | 제목 경로·신뢰도, `contextualized_text`, 품질 플래그, source ID/ref, Parser 실행 메타 보존 |
| 사용자 결과와 내부 State 분리 | 최종 결과 외에 내부 State가 콘솔 노출 | `finalize`가 표준 결과, 선택 문맥 수, 품질 경고만 구성하고 서비스는 해당 결과만 반환 |

### 변경 파일

- `services/agent1/chunk_adapter.py`: 기존·제안 Chunk 계약 호환, 상태·중복 ID·본문·페이지 검증, 품질·계보 필드 정규화
- `services/agent1/context_selector.py`: 실제 Vector 검색 전 사용할 요청 기반 Seed·같은 절·인접 Chunk·토큰 예산 Selector
- `services/agent1/state.py`: 전체 Chunk와 LLM용 `context_chunks`, 품질 `warnings` 분리
- `services/agent1/graph.py`: 관련 Chunk와 역할·스킬 목록만 System Prompt에 전달, 표준 결과 요약·경고 추가
- `services/agent1/prompts.py`: Jira·People 상세 블록 제거, 역할·스킬 목록과 입력 품질 경고 블록 추가
- `services/agent1/service.py`: Selector 실행과 품질 경고 수집, 전체 State 출력 제거
- `services/agent1/demo.py`: `_print_summary`, `--json` 분기 제거, 표준 결과 JSON 단일 출력
- `tests/test_agent1_mvp.py`: 호환 계약, 중복 ID, 관련 문맥·인접 Chunk, Prompt 개인정보 최소화, State 미출력 테스트 추가
- Agent1 설계·연동 문서: 실제 반영된 Prompt와 AS-IS/TO-BE 상태로 갱신

### 검증 결과

- `python -X utf8 -m unittest -v tests.test_agent1_mvp`: Agent1 테스트 12개 통과
- `python -m compileall -q services/agent1`: 문법 검사 통과
- `python manage.py test tests --verbosity 1`: 전체 147개 테스트 통과
- `git diff --check`: 오류 없음. 기존 추적 파일의 LF→CRLF 경고만 확인
- 테스트에서 Jira Issue 키, 개인 이름, 근무시간 상세가 Prompt에 없고 역할·스킬 목록은 존재함을 확인
- 서비스 호출 중 표준 출력이 비어 있어 내부 State가 콘솔에 노출되지 않음을 확인

### 알려진 제한과 다음 작업

- 현재 Selector는 pgvector 연결 전의 로컬 어휘 기반 경계다. 실제 검색 품질을 대신하는 최종 구현이 아니며 검색 Provider 연결 후 교체한다.
- 파싱팀 합의 전이므로 두 Chunk 필드 표현을 모두 지원한다. 최종 계약 확정 후 JSON Schema/Pydantic DTO와 스키마별 지원 정책을 고정한다.
- 실제 Jira·People Repository Adapter 및 최신 업무량 산식·NULL 대체 정책 정렬은 이번 변경 범위에 포함하지 않았다.
- Hanwha 원문을 외부 LLM에 보내는 실제 API 종단 실행은 수행하지 않았고 Fake LLM 기반 Graph와 전체 회귀 테스트로 검증했다.

## 2026-08-03 Retriever 연동 피드백 확인 요청 작성

- 작업 시작: 2026-08-03 12:13 KST
- 작업 완료: 2026-08-03 12:15 KST
- 변경 파일: `docs/3_설계/Agent1_Retriever_연동_피드백_확인요청.md`
- 수행 내용: 파싱·청킹 담당자의 구두 피드백을 `업무량 필수 Node`와 `Agent 주도 검색 요청`으로 재구성하고, Agent가 필요로 하는 다섯 정보 유형, 최소 요청·응답 예시, 역할 분담, 확인 질문 3개와 메신저용 요약을 작성했다.
- 작성 기준: 상대가 요구한 “이 단계에서 Agent에 어떤 정보가 필요한지”에 먼저 답하고, 완성 명세를 강요하지 않도록 JSON은 조정 가능한 초안으로 표시했다. Agent 내부 수정과 Retriever 협의 범위를 분리했다.
- 검증: 현재 Agent1 Graph·Prompt·호환 Chunk Adapter 및 기존 연동 협의서와 대조했다. 아직 합의되지 않은 Retriever 필드나 동작은 구현 완료로 표현하지 않았다.
- 다음 작업: 담당자 답변으로 Query 생성 책임, 문맥 확장 책임, 반환 가능 필드를 확정한 뒤 Retriever Port와 Graph Node를 구현한다.

## 2026-08-03 Agent1 Retrieval 요구사항 2차안 작성

- 작업 시작: 2026-08-03 12:28 KST
- 작업 완료: 2026-08-03 12:31 KST
- 변경 파일: `docs/3_설계/Agent1_Retrieval_요구사항_2차안.md`, 기존 방향 확인 문서 상단 연결 안내
- 수행 내용: 방향성 합의 이후 Agent1이 결정해야 할 검색 Intent를 `TASK_CORE`, `ASSIGNMENT_REQUIREMENT`, `EXECUTION_CONDITION` 세 가지로 정리하고, 요청·응답 초안, 다중 근거, 누락 필드 처리, 역할 분담과 구현 가능 여부 확인 항목을 작성했다.
- 변경 이유: 기존 다섯 정보 유형은 판단 기준으로 유지하되 검색 요청 중복을 줄이고, 고정 Query·단일 근거·필수 공수로 인해 실제 업무가 누락되는 문제를 구현 전에 방지하기 위해서다.
- 결정 범위: MVP는 세 Intent를 한 번씩 검색하며 누락 필드 재검색은 후속으로 둔다. 검색 수치값은 초기 설정이며 계약 상수로 확정하지 않았다.
- 검증: 현재 `ExtractedTask`, 근거 검증 Tool, 문맥 Selector와 파싱팀 피드백을 대조했다. Retriever가 제공해야 할 값과 Agent가 내부적으로 처리할 값을 분리했다.
- 다음 작업: 파싱·청킹 팀이 요청 배열, 문맥 확장, 반환 필드, 빈 결과 처리를 확인하면 Retriever Port와 Graph Node 설계를 확정한다.

## 2026-08-03 파싱·청킹 팀 공유용 연동 플로우차트 작성

- 작업 시작: 2026-08-03 12:34 KST
- 작업 완료: 2026-08-03 12:37 KST
- 변경 파일: `docs/3_설계/Agent1_Retriever_연동_플로우차트.md`, Retrieval 2차안 연결 안내
- 수행 내용: 전체 분석 흐름, Agent-Retriever Sequence, 요청·응답 경계, 검색 결과·누락 데이터 처리, 현재와 목표 비교를 Mermaid로 정리했다.
- 변경 이유: 방향성과 세부 요구사항에 동의한 파싱·청킹 담당자가 자신의 처리 구간, Agent 요청 시점, 반환 필드와 업무량 필수 Node의 관계를 한눈에 이해할 수 있는 그림을 요청했다.
- 검증: Retrieval 2차안의 세 Intent, 다중 근거·누락 처리, 문맥 확장 책임과 일치하는지 대조했다. pgvector 연동은 목표 구조로 명시해 현재 구현과 구분했다.
- 다음 작업: 팀 피드백으로 실제 Retriever 호출 방식이 확정되면 다이어그램의 요청·응답 명칭을 코드 DTO와 일치시킨다.

## 2026-08-03 Notion 작업 흐름 요약 반영

- 작업 시작: 2026-08-03 12:41 KST
- 작업 완료: 2026-08-03 12:46 KST
- 대상: Notion `0803_에이전트1설계_임준억` 페이지
- 수행 내용: 기존에 첨부 파일 2개만 있던 페이지를 `현재 최신 상태 → 최종 공유 자료 2개 → 최초 상태와 1차 공유 → 파싱팀 피드백 → Agent1 세부 재검토 → 결정 요약 → 다음 단계` 순서로 재구성했다.
- 변경 이유: 처음 보는 사람도 파일이 만들어진 배경과 피드백에 따른 변경 흐름, 현재 기준 파일을 짧게 파악할 수 있도록 하기 위해서다.
- 보존 내용: 기존 `Agent1_Retrieval_요구사항_2차안.md`, `Agent1_Retriever_연동_플로우차트.md` 첨부 블록을 그대로 유지했다.
- 검증: 업데이트 후 Notion 페이지를 다시 조회해 최신 상태 Callout, 두 첨부 파일, 진행 흐름과 다음 단계가 정상적으로 표시되는 것을 확인했다.

## 2026-08-03 최신 main 통합

- 작업 시작: 2026-08-03 14:20 KST
- 작업 완료: 2026-08-03 14:26 KST
- 변경 기준: `origin/main` `19cfab4` → `84c1ed6`
- 수행 내용: `git fetch origin main --prune` 후 `git merge --ff-only origin/main`으로 최신 main을 현재 `juneok` 브랜치에 통합했다.
- 보존 확인: Agent1 코드·테스트·개인 설계 문서·작업기록은 untracked/modified 상태 그대로 보존됐고 충돌은 없었다.
- main 변경 핵심: `exist_task`에 `proj_source_id`, `estimate`, 중복 방지 인덱스를 추가하고 Jira 부하계산 To-Do 및 Connector 설계 문서를 갱신했다.
- 검증: `python manage.py test tests --verbosity 1` 전체 147개 통과, `git diff --check` 오류 없음.
- Agent1 영향: 실제 Jira Adapter는 기존 Fixture의 `remaining_hours`에서 `remaining`, `estimate`, `proj_source_id`, 기간 창·NULL·가용용량 가드 정책으로 정렬해야 한다. 이번 통합에서는 Agent1 계산 로직을 임의로 바꾸지 않았다.

## 2026-08-03 Node·Edge 데이터 흐름 자료 작성

- 작업 시작: 2026-08-03 15:45 KST
- 작업 완료: 2026-08-03 15:47 KST
- 변경 파일: `docs/3_설계/Agent1_노드_엣지_데이터흐름_파싱청킹팀.md`
- 수행 내용: 목표 Agent1 Graph의 7개 Node 역할과 State 읽기·쓰기, 10개 Edge별 논리적 전달 정보, 요청·응답 JSON 예시를 정리했다.
- 변경 이유: 파싱·청킹 팀이 전체 설계 설명이 아니라 각 Node의 책임과 Edge 통과 시 필요한 데이터 계약을 명확하게 요청했다.
- 표현 기준: LangGraph Edge가 객체를 직접 운반하는 것이 아니라 공유 State를 통해 다음 Node가 필요한 값을 읽는 구조임을 먼저 설명했다. 파싱·청킹 팀 접점인 Edge 2·3·4를 별도로 강조했다.
- 현재/목표 구분: 현재 `agent ↔ tools → finalize` 구현과 다르게, 업무량 필수 Node와 Retriever Node가 포함된 합의 목표 설계임을 문서 상단에 명시했다.
- 다음 작업: 파싱·청킹 팀이 요청 배열, Chunk 필드, 문맥 확장, 검색 결과 계약을 확인하면 DTO와 `retrieve_context` Node 구현으로 진행한다.

### Notion 페이지 반영

- 반영 시작: 2026-08-03 15:49 KST
- 반영 완료: 2026-08-03 15:53 KST
- 대상: Notion `0803_에이전트1설계_임준억`
- 수행 내용: `Agent1_노드_엣지_데이터흐름_파싱청킹팀.md`를 새 첨부로 업로드하고, 페이지 상단 최신 공유 자료를 2개에서 3개로 갱신했다.
- 보존 확인: 기존 최신 자료 2개와 사용자가 추가한 최초 공유·피드백 문서 첨부 및 Toggle 구조를 그대로 유지했다.
- 검증: 업데이트 후 페이지를 다시 조회해 새 Node·Edge 파일, 설명, 최신 자료 3개 문구가 표시되는 것을 확인하고 하단의 기존 2개 표기도 3개로 정정했다.

## 2026-08-03 Node·Edge 데이터 흐름 플로우차트 작성

- 작업 시작: 2026-08-03 16:27 KST
- 작업 완료: 2026-08-03 16:31 KST
- 변경 파일: `docs/3_설계/Agent1_노드_엣지_데이터흐름_플로우차트.md`
- 수행 내용: Node·Edge 명세를 기반으로 전체 영역 연결, 파싱·청킹 팀과 맞출 Edge 2·3·4, 실행 Sequence, 공통 State 변화, 확인 항목을 Mermaid 중심으로 시각화했다.
- 변경 이유: 파싱·청킹 담당자가 각 Node의 역할뿐 아니라 Edge 사이에서 필요한 정보가 실제 실행 순서상 어떻게 이동하는지 플로우차트로 요청했다.
- 반영 사항: 업무량 계산을 필수 Node로 표시하고, 추출 업무가 없을 때 후보 분석만 생략하며 업무량 결과는 유지하는 최신 방향을 반영했다.
- 검증: 기존 Node·Edge 명세의 7개 Node와 파싱·청킹 접점인 Edge 2·3·4의 필드 및 책임을 대조했다. 실제 Retriever 연동 전 합의용 TO-BE 문서라는 제한을 문서 상단에 명시했다.
- 다음 작업: 파싱·청킹 팀이 다섯 확인 항목에 답하면 요청·응답 DTO 및 `retrieve_context` Node 구현으로 전환한다.

## 2026-08-03 플로우차트 단독 이해 가능하도록 보강

- 작업 시각: 2026-08-03 16:35 KST
- 변경 파일: `docs/3_설계/Agent1_노드_엣지_데이터흐름_플로우차트.md`
- 변경 이유: 기존 플로우차트만으로는 파싱·청킹 팀이 다른 명세서를 함께 읽어야 했고, `ChunkRecord`, `RetrievalRequest`, `RetrievalResult`의 최소 계약이 분산되어 있었다.
- 반영 내용: 담당 경계, 최소 Chunk 필드와 `text`/`raw_text`/`contextualized_text` 관계, 요청·응답 JSON 예시, 세 Intent 의미를 문서 안에 추가했다.
- 검증: 문서 단독으로 파싱·청킹 → Retriever → Agent1의 입력·출력과 빈 검색 결과 처리 규칙을 설명할 수 있는지 확인했다.
- 제한/다음 작업: 필드명과 `retrieval_score` 제공 가능 여부는 파싱·청킹 팀 확인이 필요하며, 합의 후 DTO와 `retrieve_context` Node를 구현한다.

## 2026-08-03 보강 플로우차트 Notion 반영

- 반영 시각: 2026-08-03 16:35 KST
- 대상: Notion `0803_에이전트1설계_임준억`
- 수행 내용: `Agent1_노드_엣지_데이터흐름_플로우차트.md`를 새 첨부로 업로드하고 최신 공유 자료 4번으로 추가했다.
- 보존 확인: 기존 최신 자료 3개와 진행 흐름, 기존 첨부 구조를 유지했다.
- 검증: 페이지를 다시 조회해 새 파일명, 단독 이해용 설명, `text/raw_text/contextualized_text` 계약 설명이 표시되는 것을 확인했다.

## 2026-08-03 Retriever·Vector DB 범위 문서 분리

- 작업 시각: 2026-08-03 16:40 KST
- 변경 파일: `docs/3_설계/Agent1_Retriever_VectorDB_연동_파싱청킹팀_요약.md`
- 수행 내용: Jira·People·업무량 계산 내용을 제외하고, 파싱·청킹 → Vector DB → Retriever → Agent1의 검색 요청·Chunk 계약·검색 응답만 별도 요약했다.
- 변경 이유: 파싱·청킹 팀이 전체 Agent1 구조가 아니라 Vector DB에서 어떤 Chunk를 저장·검색·반환해야 하는지만 확인할 수 있도록 범위를 분리했다.
- 검증: 문서 전체에 업무량·후보 분석을 제외한다는 범위를 명시하고, 세 Intent·최소 Chunk 필드·빈 결과 규칙을 포함했다.

## 2026-08-03 Retriever 연동 핵심 범위로 재정리

- 작업 시각: 2026-08-03 16:45 KST
- 변경 파일: `docs/3_설계/Agent1_Retriever_VectorDB_연동_파싱청킹팀_요약.md`
- 변경 이유: 파싱·청킹 팀 요청에 따라 Docling·Drive 등 선행 과정과 업무량·후보 분석을 제외하고 LangGraph에서 실제 Retriever가 필요한 단계만 남겼다.
- 반영 내용: `plan_retrieval → retrieve_context → extract_tasks` 흐름, `RetrievalRequest`, `RetrievalResult`, 최소 Chunk 필드와 팀 확인 항목을 정리했다.
- 검증: Retriever 호출 시점과 입력·출력 계약이 문서 첫 부분에서 바로 확인되며, 범위 밖 Jira·People 내용이 제거된 것을 확인했다.

## 2026-08-03 Retriever Node명·Chunk 필드 통합 반영

- 작업 시각: 2026-08-03 16:50 KST
- 변경 파일: `docs/3_설계/Agent1_Retriever_VectorDB_연동_파싱청킹팀_요약.md`
- 변경 이유: 파싱·청킹 팀이 실제 LangGraph Node명을 확인할 수 있어야 하고, 기존 `contextualized_text`와 `text` 계약이 현재 합의된 `text`·`raw_text` 기준과 충돌했다.
- 반영 내용: `plan_retrieval`, `retrieve_context`, `extract_tasks` Node명과 역할을 명시하고, `text`는 검색·문맥용, `raw_text`는 원문 근거용으로 정리했다. `contextualized_text`는 현재 계약에서 제외하고 Adapter 변환 대상으로 표시했다.
- 검증: 요청·응답 JSON, 최소 필드 표, 확인 항목이 모두 `text` + `raw_text` 기준으로 일치하는지 확인했다.

## 2026-08-03 고정 업무 추출·Retriever Tool 루프 피드백 반영

- 작업 시작: 2026-08-03 16:51 KST
- 작업 완료: 2026-08-03 16:57 KST
- 최신 기준 파일: `docs/3_설계/Agent1_Retriever_VectorDB_연동_파싱청킹팀_요약.md`
- 피드백 핵심: Agent1은 사용자의 자유 요청을 분석해 플로우를 정하는 Agent가 아니라 고정된 업무 추출 플로우를 실행한다. 업무 추출 Agent가 현재 문서 정보의 부족을 판단하면 Retriever Tool을 호출하고, 새 Chunk를 받은 뒤 다시 판단하는 루프가 필요하다.
- 변경 전: `plan_retrieval → retrieve_context → extract_tasks`의 단발 Retrieval 구조와 사용자 요청 기반 동적 Query 생성으로 문서화했다.
- 변경 후: `extract_tasks_agent ↔ document_search_tools` Tool 루프로 수정했다. Query는 사용자 자유 요청이 아니라 현재 부족한 업무 정보에 맞춰 생성하며, 검색 종료 조건·검색 예산·빈 결과·누락 필드 처리를 포함했다.
- 필드 계약: Agent1 Retriever 연동은 `text`를 검색·LLM 문맥용, `raw_text`를 원문 인용용으로 사용하고 `contextualized_text`를 제외한다.
- 문서 점검: 기존 Retrieval 요구사항, Retriever 플로우차트, Node·Edge 문서, 파싱 연동 협의서, 초기 설계 공유 문서, MVP AS-IS 문서에 최신 기준 또는 과거 기록 표시를 추가했다. `Agent1_흐름_PPT_요약.md`는 고정 플로우·문서검색 Tool 루프 기준으로 전면 갱신했다.
- 코드 범위: 이번 단계에서는 코드를 수정하지 않았다. 현재 코드는 여전히 `agent ↔ tools → finalize`와 세 분석 Tool 선택 구조이므로 후속 구현에서 Graph를 재구성해야 한다.
- 검증: Agent1 관련 설계 문서에서 `plan_retrieval`, 사용자 요청 기반 Tool 선택, `contextualized_text`가 최신 기준처럼 읽히는 위치를 검색하고, 해당 문서 상단에 상태를 명시했다.
- 다음 작업: 문서 기준을 팀과 확인한 뒤 `extract_tasks_agent`, Retriever `ToolNode`, 반복 검색 State·종료 조건을 코드와 테스트에 반영한다.

## 2026-08-03 파싱·청킹 팀 최종 공유 문서 단일화

- 작업 시각: 2026-08-03 17:05 KST
- 최신 공유 파일: `docs/3_설계/Agent1_Retriever_연동_파싱청킹팀_최종공유.md`
- 수행 내용: 파싱·청킹 팀이 확인해야 할 `extract_tasks_agent ↔ document_search_tools` 위치, Tool 입력·출력, `text/raw_text` 계약, 반복 종료 기준, 확인 질문만 하나의 문서로 간추렸다.
- 제거한 중간 문서: Retrieval 2차안, 초기 피드백 확인서, 기존 Retriever 플로우차트, Node·Edge 명세·플로우차트, 초기 파싱팀 설계 공유, 상세 VectorDB 요약본.
- 제거 이유: `plan_retrieval`, 단발 `retrieve_context`, 사용자 요청 기반 Query 등 폐기된 방향이 여러 문서에 남아 최신 기준과 혼동될 가능성이 컸다.
- 보존 내용: 방향이 바뀐 과정과 제거 파일명은 이 작업기록에 유지했다. 사용자가 수정했던 `Agent1_문서파싱청킹_연동_협의서.md`와 현재 코드 AS-IS 설명인 `Agent1_MVP_Mock_파이프라인.md`는 삭제하지 않고 최신 문서 링크를 표시했다.
- 검증: 최종 공유 문서에는 Connector·Docling·Jira·People 세부 설명을 넣지 않았고 Retriever와 직접 이어지는 Node·Tool 계약만 포함했다.
- 다음 작업: 파싱·청킹 팀의 여섯 확인 항목 답변을 받은 뒤 코드 Graph와 Tool DTO를 수정한다.

## 2026-08-03 파싱·청킹 팀 피드백 — Agent1 전체 워크플로우 추가

- 피드백 시각: 2026-08-03 17:07 KST
- 변경 파일: `docs/3_설계/Agent1_Retriever_연동_파싱청킹팀_최종공유.md`
- 피드백 내용: Retriever 접점뿐 아니라 Agent1 전체 워크플로우와 각 Node명을 함께 보여달라는 요청을 받았다.
- 반영 내용: `START → extract_tasks_agent ↔ document_search_tools → calculate_workloads → route_after_analysis → analyze_candidates/finalize → END` 전체 Mermaid와 Node 역할 표를 문서 앞부분에 추가했다.
- 표현 기준: 전체 흐름은 고정이고, Agent 판단은 업무 추출 중 Retriever Tool 호출·반복 여부에만 들어간다는 경계를 명시했다.
- 검증: 전체 Node명, 필수 업무량 Node, 업무 존재 분기, Retriever Tool 루프가 하나의 그림에서 확인되는지 점검했다.

## 2026-08-03 업무량 필수 Node 실제 코드 반영

- 작업 시작: 2026-08-03 17:14 KST
- 작업 완료: 2026-08-03 17:23 KST
- 변경 파일: `services/agent1/graph.py`, `prompts.py`, `tools.py`, `service.py`, `tests/test_agent1_mvp.py`, `docs/3_설계/Agent1_MVP_Mock_파이프라인.md`, `PROJECT_CONTEXT.md`
- 변경 이유: 문서에는 업무량 필수 Node와 고정 업무 추출 흐름을 반영했지만 실제 Graph는 여전히 LLM이 세 분석 Tool의 사용 여부를 선택하는 구조였다.
- 변경 전: `START → agent ↔ tools → finalize`, LLM이 업무량 Tool을 생략할 수 있었다.
- 변경 후: `START → extract_tasks_agent ↔ task_tools → calculate_workloads → analyze_candidates/finalize → END`로 변경했다. 업무량은 항상 실행하고 후보 분석은 추출 업무가 있을 때만 실행한다.
- Prompt 변경: 사용자 자유 요청에 따른 Tool 선택 지시를 제거하고 업무 추출 전용 고정 목표와 `extract_tasks` 1회 호출 규칙을 적용했다.
- 근거 검증: `raw_text`가 있으면 원문 인용 검증에 우선 사용한다.
- 검증 결과: `python -X utf8 -m unittest -v tests.test_agent1_mvp` 12개 통과, `python manage.py test tests --verbosity 1` 전체 147개 통과.
- 알려진 제한: `document_search_tools/search_document_chunks` Retriever Tool 루프는 아직 구현하지 않았다. 파싱·청킹 팀과 Tool 입출력 계약을 확정한 뒤 다음 단계에서 연결한다.

## 2026-08-03 현재 Graph 기준 파싱·청킹 팀 문서 재작성

- 작업 시각: 2026-08-03 17:27 KST
- 변경 파일: `docs/3_설계/Agent1_Retriever_연동_파싱청킹팀_최종공유.md`
- 수행 내용: 방금 실제 반영한 `extract_tasks_agent ↔ task_tools → calculate_workloads → analyze_candidates/finalize` Graph와 앞으로 추가할 `document_search_tools/search_document_chunks` 분기를 한 문서에서 구분했다.
- 변경 이유: 기존 공유 문서는 Retriever Tool 루프를 목표 구조로만 표시해 현재 구현된 `task_tools`와 업무량 필수 Node 상태를 구분하기 어려웠다.
- 계약 내용: Retriever Tool 입력, `text/raw_text` 기반 Chunk 출력, 빈 결과와 시스템 오류 구분, 반복 검색 종료 조건을 명시했다.
- 다음 작업: 파싱·청킹 팀의 여섯 확인 항목 답변을 받은 뒤 Tool DTO와 Tool명 기반 Graph 분기를 구현한다.

## 2026-08-03 Retriever 초기 검색 범위 명확화

- 작업 시각: 2026-08-03 17:32 KST
- 변경 파일: `docs/3_설계/Agent1_Retriever_연동_파싱청킹팀_최종공유.md`
- 확인 내용: Vector DB는 선택 문서 범위의 Chunk를 검색 대상으로 비교할 수 있지만, Agent1에 전체 Chunk를 전달하지 않는다.
- 반영 내용: 초기에는 `TASK_CORE` Query로 Top-K Seed와 요청한 주변 문맥만 받고, 추가 정보가 부족할 때만 다른 Intent로 반복 검색하도록 명시했다.
- 현재/목표 구분: 현재 Mock은 전체 Chunk를 State에 적재한 뒤 로컬 Selector로 Prompt 입력을 줄이는 임시 구조이며, 실제 연동에서는 Retriever 반환 Chunk만 `context_chunks`에 누적한다.
- 다음 작업: 초기 Top-K·문맥 확장 반환 방식까지 포함한 일곱 확인 항목을 파싱·청킹 팀과 확정한다.

## 2026-08-03 Agent1 실제 사용 기준 문서 정보 최소화

- 작업 시각: 2026-08-03 17:38 KST
- 변경 파일: `docs/3_설계/Agent1_Retriever_연동_파싱청킹팀_최종공유.md`
- 판단 기준: 현재 `ExtractedTask`와 후보 계산 코드가 실제 사용하는 문서 정보만 Retriever 우선 요구사항으로 선정했다.
- 필수 정보: 명시적인 수행 업무와 원문 근거. 둘 중 하나라도 없으면 업무를 생성하지 않는다.
- 조건부 정보: 담당 역할, 기술·스킬, 예상 공수. 업무 발견 후 부족할 때만 추가 검색한다.
- 제외한 필수 요구: 일정, 우선순위, 의존성, 리스크, 완료 기준은 현재 Agent1 후보 계산에서 사용하지 않으므로 MVP 필수 검색 정보에서 제외했다.
- 변경 이유: 장래 확장 필드까지 모두 요구하면 초기 검색 범위와 파싱·청킹 팀 계약이 불필요하게 커지고 현재 구현과 맞지 않는다.
- 다음 작업: 누락 역할·스킬·공수를 업무에 보존하는 `missing_fields` 출력 계약은 Agent1 State/Schema 수정 단계에서 반영한다.

## 2026-08-03 Retriever 문서 정보 범위 재검토

- 작업 시각: 2026-08-03 17:46 KST
- 변경 파일: `docs/3_설계/Agent1_Retriever_연동_파싱청킹팀_최종공유.md`
- 재검토 이유: 앞선 최소화 판단이 현재 후보 점수 코드만 기준으로 삼아, Agent1 결과를 이어받는 업무 분배·검증 단계의 정보 요구를 충분히 반영하지 못했다.
- 변경 전: 일정, 우선순위, 의존성, 리스크, 완료 기준을 현재 MVP 필수 검색 범위에서 제외했다.
- 변경 후: 기간·마감일과 우선순위는 배정용 조건부 정보로, 의존성·제약·리스크·완료 기준·산출물은 관련 Chunk에서 보존할 정보로 복원했다.
- 검색 원칙: 역할·스킬·공수·기간처럼 배정 계산을 막는 누락은 추가 검색하고, 그 밖의 문맥은 초기·추가 검색 결과에 있으면 함께 추출한다. 모든 필드마다 별도 검색을 강제하지 않으며, 문서에 없으면 추측하지 않는다.
- 구현 차이: 현재 `ExtractedTask` Schema에는 아직 일정·우선순위·의존성·제약·리스크·완료 기준과 `missing_fields`가 없다. 이번 변경은 Retriever 연동 목표 계약이며 코드 Schema 반영은 후속 작업이다.

## 2026-08-03 Agent1 Task 문맥·누락 처리 코드 반영

- 작업 시작: 2026-08-03 17:40 KST
- 작업 완료: 2026-08-03 17:42 KST
- 변경 파일: `services/agent1/state.py`, `tools.py`, `prompts.py`, `tests/test_agent1_mvp.py`, `docs/3_설계/Agent1_MVP_Mock_파이프라인.md`, `docs/3_설계/Agent1_Retriever_연동_파싱청킹팀_최종공유.md`, `PROJECT_CONTEXT.md`
- 변경 이유: Retriever 계약 문서에 복원한 일정·우선순위·의존성·제약·리스크·완료 기준이 실제 Task Schema와 Prompt에는 없어 결과에서 유실되는 상태였다.
- 변경 전: 역할·스킬·공수는 필수여서 하나라도 문서에 없으면 명시적인 업무도 저장하기 어려웠고, 일정·우선순위 등의 보존 필드와 누락 상태가 없었다.
- 변경 후: 명시적인 업무와 원문 근거를 Task 생성 기준으로 두고, 배정 문맥은 선택형으로 보존한다. Tool이 `missing_fields`를 재계산하며 후보 분석은 `READY/LIMITED/BLOCKED` 상태를 반환한다.
- 검증 추가: 확장 문맥 보존, 핵심 필드 누락 시 Task 유지·후보 차단, 시작일·마감일 역전 차단 테스트를 추가했다.
- 검증 결과: `python -X utf8 -m unittest -v tests.test_agent1_mvp` 15개 통과, `python manage.py test tests --verbosity 1` 전체 150개 통과, `python -m compileall -q services\agent1` 통과.
- 알려진 제한: 현행 업무량은 주간 가용시간 기준이므로 기간·마감일은 아직 실제 기간별 용량 계산에 사용되지 않는다. Retriever 반복 검색도 아직 미구현이다.

## 2026-08-03 Agent1 검색 기준·Retriever 품질 기준 반영

- 작업 시작: 2026-08-03 17:50 KST
- 작업 완료: 2026-08-03 18:02 KST
- 변경 파일: `services/agent1/context_selector.py`, `service.py`, `tests/test_agent1_mvp.py`, `docs/3_설계/Agent1_Retriever_연동_파싱청킹팀_최종공유.md`, `docs/3_설계/Agent1_MVP_Mock_파이프라인.md`, `docs/7_참고자료/Agent1_기초_학습노트.md`, `PROJECT_CONTEXT.md`
- 피드백: 검색을 하려면 Agent가 기준을 구성해야 하고, 검색 단계는 그 기준에 맞는 문서를 얼마나 잘 찾는지 평가해야 한다.
- 확인 결과: 방향은 타당하다. 기존 문서에는 Intent와 입출력 필드는 있었지만 Query 구체화, 초기 검색 범위의 커버리지, Agent·Retriever 책임 경계, 검색 품질 평가 방법이 부족했다.
- 코드 변경 전: 임시 Selector가 사용자 자유 요청과 업무 용어를 합쳐 초기 문맥을 선택했다.
- 코드 변경 후: 초기 문맥은 고정 `TASK_CORE` 기준으로 선택한다. Selector는 `TASK_CORE`, `ASSIGNMENT_REQUIREMENT`, `EXECUTION_CONDITION`별 용어 기준과 선택 Query를 받을 수 있다.
- 문서 변경: Agent 검색 판단 기준, Retriever 검색·순위 기준, 정답 Chunk 기반 평가 항목, 긴 문서에서 단일 일반 Query Top-K를 피하는 원칙을 추가했다.
- 학습 자료: Agent·Workflow·State·Node·Edge·Tool·Retriever의 차이와 현재 Agent1 경계를 쉬운 예시로 정리했다.
- 검증 결과: `python -X utf8 -m unittest -v tests.test_agent1_mvp` 16개 통과, `python manage.py test tests --verbosity 1` 전체 151개 통과, `python -m compileall -q services\agent1` 통과.
- 알려진 제한: 실제 Vector Retriever와 반복 Tool 호출은 아직 미구현이다. 품질 수치 기준은 대표 문서의 정답 Chunk 세트를 만든 뒤 확정해야 한다.

## 2026-08-03 Agent1·Agent2 후보 분석 책임 분리

- 작업 시작: 2026-08-03 18:20 KST
- 작업 완료: 2026-08-03 18:36 KST
- 변경 파일: `services/agent1/graph.py`, `state.py`, `service.py`, `prompts.py`, `tools.py`, `tests/test_agent1_mvp.py`, Agent1 설계·Retriever 공유·PPT·학습 문서, `PROJECT_CONTEXT.md`
- 판단 근거: 기획서 v5와 AI 모델링 설계는 후보 생성과 담당자 추천을 업무 분배 Agent 책임으로 정의한다. 현재 `analyze_candidates`도 Task·People·WorkloadResult·Jira 이력으로 사람을 비교하므로 Agent2 성격이다.
- 변경 전: Agent1 Graph가 업무 추출과 업무량 계산 뒤 `analyze_candidates`까지 실행하고 상위 3명만 반환했다.
- 변경 후: Agent1은 업무 추출 뒤 업무량을 반드시 계산하고 종료한다. 후보 분석 코드는 Agent1에서 제거했으며 Agent2 구현은 후속 담당 범위로 남겼다.
- 업무량 위치: 멘토 피드백을 유지해 Agent1 Workflow의 필수 결정론적 Node로 남긴다. LLM의 추론 책임에는 포함하지 않는다.
- 근거 구조 재검토: 현재 단일 `evidence`는 유지하되, 역할·공수·일정 등이 서로 다른 Chunk에 있을 때를 위해 `evidence_refs[].supports` 목표안을 공유 문서에 명시했다. 근거 필드 매핑은 Retriever가 아닌 Agent1 책임이다.
- 정리: 검토 중 만들었던 임시 `services/agent2` 후보 분석 파일과 테스트는 사용자 결정에 따라 제거했다. Agent2는 현재 미구현이다.
- 검증 결과: `python -X utf8 -m unittest -v tests.test_agent1_mvp` 15개 통과, `python manage.py test tests --verbosity 1` 전체 150개 통과, `python -m compileall -q services\agent1` 통과.
- 알려진 제한: Agent2 전체 분배 Graph와 후보 분석은 아직 없으며, 복수 근거 Schema도 아직 코드에는 미반영이다.

## 2026-08-03 멘토 보고용 진행 정리

- 작업 시각: 2026-08-03 18:45 KST
- 생성 파일: `docs/10_발표자료/Agent1_멘토님_진행보고_2026-08-03.md`
- 목적: 멘토·파싱청킹 팀 피드백, 실제 코드 변경, 협업 내역, 완료·미구현 범위, 검증 결과와 확인 질문을 한 문서에서 설명할 수 있도록 정리했다.
- 표현 원칙: Retriever 연동 기준 설계와 실제 반복 Tool 구현을 구분하고, Agent2·복수 근거·실데이터 업무량 계산은 미구현으로 명시했다.

## 2026-08-03 멘토 보고 핵심 요약 추가

- 생성 파일: `docs/10_발표자료/Agent1_멘토님_핵심요약_2026-08-03.md`
- 목적: 상세 작업기록과 별도로 멘토님께 현재 역할, 구현 완료 범위, 미구현 범위, 확인 질문을 30초 내 설명할 수 있는 문서 제공

## 2026-08-04 main 통합 및 Agent1 중간발표 AS-IS 재정의

- 작업 시작: 2026-08-04 10:00 KST
- 작업 완료: 2026-08-04 10:10 KST
- main 통합: `84c1ed6`에서 `24c31e0`으로 fast-forward. 기존 수정·신규 Agent1 파일은 보존됐다.
- main 영향: 실제 Jira 미완료 이슈 수집과 기간별 결정론적 업무량 계산 `services/workload/calculator.py`가 추가됐다. 원빈님 노트북의 `calculate_workloads`는 실제 부하 계산이 아닌 Placeholder이므로 교체 대상이다.
- 멘토 피드백 재확인: `RuleBasedExtractionAgent`, `MockQueryAgent`, 고정 업무 결과, 규칙 기반 Query Fallback은 제거·재검토 대상이다. 샘플 문서와 테스트 Chunk는 실제 판단을 재현하는 Fixture로 유지할 수 있다.
- 생성 파일: `docs/3_설계/에이전트1관련/Agent1_중간발표_ASIS_정리.md`
- AS-IS 변경 전: 전달 노트북 전체 Graph에 Mock Agent, InMemory 검색, 가짜 업무량, 후보 Placeholder가 함께 있어 발표에서 구현 범위가 불명확했다.
- AS-IS 변경 후: 중간발표 Agent1을 `대표 요청 문서 → 추출 Agent ↔ Query 생성 Agent·Retriever → 근거 기반 Task`로 한정하고, Mock·Placeholder와 실연동 확인 항목을 분리했다.
- 검증 방법: 8월 3일 멘토링 STT의 코드 리뷰 구간과 전달받은 명세·프롬프트·다이어그램·노트북을 대조했다.
- 알려진 제한: 이 단계에서는 원본 노트북 코드와 기존 `services/agent1`을 수정하지 않았다. 실제 Retriever·Connector 연동 상태는 후속 점검이 필요하다.
- 바로 다음 작업: 정리된 AS-IS의 노드 책임, 데이터 계약, 종료 조건, 실제 실행 가능 범위를 점검한 뒤 TO-BE 로직 개선점을 우선순위화한다.

## 2026-08-04 Agent1 AS-IS 점검 및 TO-BE 로직 개선 후보 도출

- 작업 시작: 2026-08-04 10:10 KST
- 작업 완료: 2026-08-04 10:25 KST
- 생성 파일: `docs/3_설계/에이전트1관련/Agent1_ASIS_점검과_TOBE_개선후보.md`
- 점검 범위: 원빈님 명세·프롬프트·다이어그램·노트북, 멘토링 STT 코드 리뷰, 최신 main의 업무량 계약과 계산 모듈
- 핵심 문제 1: 문서 전체 기준 Stage를 한 번씩 진행해 여러 업무 후보의 역할·공수·일정 근거가 서로 섞일 수 있다.
- 핵심 문제 2: RetrievedChunk가 검색 당시 Intent 하나에 묶여, 한 Chunk가 여러 필드를 지지해도 다른 단계에서 재사용하기 어렵다.
- 핵심 문제 3: `extract_tasks_agent`가 근거 충분성, 검색 여부, Stage 전환, 최종 구조화를 함께 담당한다.
- TO-BE 우선순위: 업무 후보별 필드 수집 → 필드별 근거 매핑 → Evidence Validator 분리. 검색 수렴도 기반 종료와 Validation 상태 확장은 후속 순위로 정리했다.
- 평가 기준: 업무 후보 재현율, 필드 근거 정확도, 근거 없는 값 생성률, 평균 검색 횟수, 중복 Chunk 비율, 미결 상태 정확성
- 변경 이유: 추상적인 ‘고도화’가 아니라 현재 AS-IS 로직에서 재현 가능한 문제와 측정 가능한 개선 방향을 중간발표에 제시하기 위해서다.
- 검증: 문서 간 Node·State·DTO·라우팅을 교차 대조하고, 최신 업무량 구현과 Placeholder의 의미 차이를 확인했다. 코드 변경은 수행하지 않았다.
- 알려진 제한: 실제 다중 업무 문서와 정답 Chunk 평가셋으로 문제를 재현하지는 않았다. 발표 전 최소 1개 다중 업무 샘플로 AS-IS 결과를 확인해야 한다.
- 바로 다음 작업: 원빈님이 전달할 실제 코드와 Retriever 계약을 받으면 AS-IS 문서와 차이를 확인하고, 발표 데모에 필요한 최소 수정만 반영한다.

## 2026-08-04 Mock 자료 보존 범위 재검토

- 작업 시각: 2026-08-04 10:30 KST
- 재검토 이유: 앞선 문서의 ‘샘플 요청 문서와 테스트 Chunk는 유지’ 표현이 Mock 데이터를 실제 데모 실행 경로에 남겨도 된다는 뜻으로 오해될 수 있었다.
- STT 근거: 멘토는 Rule-based·Mock Agent와 하드코딩 결과를 제거하라고 했지만, 실제 샘플 문서를 넣어 판단과 검색을 테스트해야 한다고도 했다.
- 변경 전: 샘플 요청 문서와 테스트 Chunk를 포괄적으로 유지 대상으로 표현했다.
- 변경 후: 대표 요청 문서·생성 Chunk·예상 결과는 테스트 Fixture로 조건부 보존하고, 노트북 내장 `SAMPLE_CHUNKS`와 Mock Provider는 실제 연동 경로에서 제거·격리한다. 검색 실패 시 Fixture Fallback은 허용하지 않는다.
- 변경 파일: `docs/3_설계/에이전트1관련/Agent1_중간발표_ASIS_정리.md`
- 검증: 원빈님 노트북의 `SAMPLE_CHUNKS`, `InMemoryVectorRetriever`, 기존 `services/agent1`의 Fixture Provider 사용 위치를 확인했다.
- 바로 다음 작업: 실제 데모가 Fixture 경로인지 Connector·Retriever 경로인지 실행 설정과 진입점에서 구분한다.

## 2026-08-04 Agent1 실제 실행 진입점 이중 점검

- 작업 시각: 2026-08-04 10:40 KST
- 1차 확인: 기존 데모는 Fixture Source를 선택하고 `load_agent1_input()`은 Provider 생략 시 `MockConnectorProvider`를 자동 사용한다. 원빈님 노트북도 기본 Mock Agent·InMemory Retriever 경로다.
- 독립 재검토: 프로젝트 전체에서 Agent1 API 호출, 실제 Retriever Adapter, `search_document_chunks` 구현을 다시 검색했다. Agent1 사용처는 데모와 테스트뿐이며 pgvector 검색 예제는 Agent1에 연결되지 않았다.
- 결론: 현재 실행 가능한 Agent1은 Fixture 기반 로컬 데모다. 두 Agent·실제 Retriever AS-IS는 설계 후보이지 통합 완료 구현이 아니다.
- 문서 반영: `Agent1_중간발표_ASIS_정리.md`에 실제 실행 경로 점검 결과를 추가했다.
- 다음 작업: 운영 Service가 Mock Provider를 기본 선택하지 않도록 의존성 주입 경계를 만들고, 데모·테스트에서만 Fixture Provider를 명시적으로 전달하는 최소 수정안을 작성한다.

## 2026-08-04 내부 확정과 외부 확인 대기 분리

- 작업 시각: 2026-08-04 10:50 KST
- 사용자 결정: 다른 담당자와 소통해야 하는 항목은 우선 제외하고, 현재 로컬 자료만으로 확정 가능한 AS-IS·TO-BE 정리를 먼저 진행한다.
- 생성 파일: `docs/3_설계/에이전트1관련/Agent1_내부확정안과_외부확인대기.md`
- 내부 확정: AS-IS 목적·노드·DTO·분기, Mock 제거 기준, 최종 Stage 종료 보장, 중복 Query 처리, 검증 표현, 필수 근거 보존, Placeholder 제외를 정리했다.
- 내부 TO-BE: 업무 후보별 근거 상태, 필드별 근거 연결, Evidence Validator 분리, 검색 수렴도 기반 종료로 제한했다.
- 외부 확인 대기: 실제 Retriever DTO, Chunk 최종 필드명, Retriever 준비 시점, 원빈님 추가 코드, PPT 최종 표현은 현재 결론과 분리했다.
- 재검토 결과: `FINAL_EXTRACTION`에서 잘못된 `ADVANCE`가 반복될 수 있는 종료 문제와, 검색 점수 기준 전역 Top-20 절단이 초기 직접 근거를 제거할 수 있는 문제를 추가로 확인했다.
- 코드 변경: 없음. 설명·설계 확정이 우선이라는 회의 방향을 유지했다.
- 다음 작업: 중간발표용 한 장 AS-IS/TO-BE와 사용자 설명·예상 질문 자료를 작성한다.

## 2026-08-04 내부 문제점 재검토

- 작업 시각: 2026-08-04 11:00 KST
- 요청: 앞서 제시한 내부 문제점이 실제 코드에 근거하고 중요도가 합리적인지 다시 검토했다.
- 최종 Stage 반복: 실제 가능하지만 Prompt가 정상적으로 `FINALIZE`를 반환하면 발생하지 않는다. 핵심 구조 문제에서 방어 로직 누락으로 등급을 낮췄다.
- Top-20 절단: 코드상 초기 근거 유실 가능성은 있으나 샘플에서 재현된 장애는 아니다. ‘검증 완료 문제’가 아닌 ‘재현 테스트가 필요한 위험’으로 표현을 수정했다.
- 중복 Query Fallback: 하드코딩은 사실이지만 Fallback 자체를 전면 금지할 근거는 없다. 재생성 횟수와 종료 상태가 없는 것이 핵심 문제로 정정했다.
- 입력 검증: 색인 완료를 확인한다는 문서와 ID 포함 관계만 확인하는 코드의 불일치는 확정했다.
- 추가 발견: `QueryPlan.context_expansion`은 정의돼 있지만 `vector_search_node`에서 Retriever에 전달되지 않아 현재 노트북에서는 동작하지 않는다.
- 변경 파일: `docs/3_설계/에이전트1관련/Agent1_내부확정안과_외부확인대기.md`
- 코드 변경: 없음.

### 2026-08-04 Canva 중간발표 슬라이드 반영

- 작업 시작·완료: 2026-08-04 (Canva 편집 세션)
- 수행 내용: Agent1 MVP 흐름과 AS-IS→TO-BE 로직 개선 내용을 Canva 기존 템플릿에 맞춰 2개 슬라이드로 재구성했다.
- 변경 내용: SVG를 단순 이미지로 삽입하지 않고 제목·텍스트·도형·선 등 Canva 편집 가능한 네이티브 컴포넌트로 작성했다. 원본 27페이지와 28페이지 사이에 배치했다.
- 검증: Canva 그리드에서 페이지 순서를 확인하고, 두 슬라이드의 Agent1/Query 생성 Agent/Retriever/근거 검증 흐름과 필드 단위 개선 내용을 DOM 텍스트로 확인했다.
- 제한·다음 작업: Canva 최종 발표 환경에서 글꼴과 간격을 한 번 더 확인한다.

## 2026-08-04 Agent1 기초 학습 노트 최신화

- 작업 시작: 2026-08-04 10:40 KST
- 작업 완료: 2026-08-04 10:46 KST
- 변경 파일: `docs/7_참고자료/Agent1_기초_학습노트.md`
- 변경 이유: 기존 학습 노트가 과거 `services/agent1` 구조와 새 두 Agent·Retriever 설계를 함께 설명해 실제 구현, 중간발표 AS-IS, TO-BE가 혼재돼 있었다.
- 변경 전: 업무 추출 Tool과 업무량 계산 중심의 기존 구조, 앞으로 만들 Retriever를 설명했다.
- 변경 후: 세 상태를 먼저 분리하고, 최신 AS-IS Graph의 Node·Edge·데이터 흐름, 문서 범위 검증의 실제 범위, QueryPlan 옵션, 미구현 `context_expansion`, Mock과 Fixture 경계, TO-BE 우선순위를 학습 순서로 재구성했다.
- 검증 방법: 전달받은 노트북의 `QueryPlan`, `validate_selection_node`, `vector_search_node` 구현과 프롬프트·내부 확정 문서를 다시 대조했다.
- 검증 결과: 현재 입력 검증은 `primary_document_id` 존재 및 `document_ids` 포함 관계만 확인하며, `context_expansion`은 Retriever 호출에 전달되지 않는다는 점을 문서에 명시했다.
- 알려진 제한: 실제 Retriever 계약과 색인 준비 상태 API가 확정되지 않아 입력 준비 검증과 문맥 확장의 구현 방식은 TO-BE로 남겼다.
- 바로 다음 작업: 중간발표 AS-IS 코드 반영 전 실제 Retriever 계약을 확인하고, 발표 범위에 필요한 최소 로직 수정 항목을 확정한다.

## 2026-08-04 Agent1 자체 수정과 연동 확인 경계 정리

- 작업 시작: 2026-08-04 10:50 KST
- 작업 완료: 2026-08-04 11:00 KST
- 변경 파일: `docs/3_설계/에이전트1관련/Agent1_내부확정안과_외부확인대기.md`
- 변경 이유: 모든 불확실성을 외부 확인 대기로 미루지 않고, 기존 의도를 보존하는 자체 수정과 작성자·연동 담당자 확인이 필요한 계약을 구분하기 위해서다.
- 변경 전: 실제 Retriever DTO와 구현 시점 등 외부 확인 항목만 포괄적으로 기록했다.
- 변경 후: 자체 수정 6개, 원빈님 의도 확인 5개, 파싱·청킹/Retriever 연동 확인 8개로 분류하고 각 질문과 확인 전 기본 처리 방식을 명시했다.
- 추가 점검: `QueryPlan.intent`가 `SearchNeed.intent`와 일치하는지 코드가 검증하지 않으며, 검색 범위와 시도 횟수가 LLM 출력 Intent에 영향을 받는 문제를 확인했다.
- 결정: Stage·Action·Intent 강제는 기존 Prompt를 코드로 보장하는 수정이므로 자체 적용 가능하다. Chunk Intent 의미, 문맥 확장 실행 주체와 실제 검색 계약은 담당자 확인 대상으로 둔다.
- 검증 방법: 전달 노트북의 `SearchNeed`, `QueryPlan`, `vector_search_node`, `stage_attempts` 및 Graph Edge를 Prompt·명세와 교차 대조했다.
- 알려진 제한: 원빈님과 파싱·청킹/Retriever 팀의 답변 전에는 확인 대상 기능을 구현 완료로 표현하지 않는다.
- 바로 다음 작업: 확인 질문을 공유하고, 외부 답변과 무관한 AS-IS 안전장치·설명 정정을 코드 반영 목록으로 확정한다.

## 2026-08-04 Agent1 중간발표용 로직 개선안 작성

- 작업 시작: 2026-08-04 11:05 KST
- 작업 완료: 2026-08-04 11:17 KST
- 생성 파일: `docs/10_발표자료/Agent1_중간발표_ASIS_TOBE_로직개선안.md`
- 작업 범위: 코드 구현 없이 Agent1 AS-IS 한계와 TO-BE 로직 개선 방향을 중간발표 슬라이드 단위로 구성했다.
- 변경 이유: 원빈님이 실제 통합을 진행 중이므로 Node·DTO 세부 구현을 선행하지 않고, 통합 결과와 무관하게 유지되는 개선 논리와 평가 기준을 먼저 확정하기 위해서다.
- 핵심 내용: 업무 후보별 근거 상태, 필드별 근거 매핑, Evidence Validator 분리, 검색 수렴도 기반 종료를 Agent1 TO-BE로 정리했다.
- 범위 구분: Agent2 후보·분배와 Agent3 검증은 Agent1 개선안에 섞지 않고 전체 Multi-Agent 후속 로드맵으로 표시했다.
- 발표 안전장치: AS-IS가 통합 중이라는 상태, 아직 검증되지 않은 검색 제한값, Mock·Placeholder 제외, 연동 후 재확인 항목을 명시했다.
- 검증 방법: 최신 AS-IS 정리, 내부 확정·외부 확인 대기 문서, 전달 노트북의 Graph·DTO, 멘토 피드백 기반 작업기록을 교차 대조했다.
- 알려진 제한: 실제 통합 코드와 다중 업무 평가 결과가 아직 없으므로 문제의 재현 결과와 정확한 적용 Node는 통합 후 확정해야 한다.
- 바로 다음 작업: 발표 자료를 사용자와 검토한 뒤 슬라이드 수와 표현을 확정하고, 통합 코드 수령 후 AS-IS 대조표를 추가한다.

### 2026-08-04 2차 재구성

- 작업 시작: 2026-08-04 11:17 KST
- 작업 완료: 2026-08-04 11:26 KST
- 사용자 피드백: 서비스 전체 발표에서 Agent1만 7장을 사용하는 것은 과하고, 발표 시점에는 MVP 종단 연결이 완료된 상태를 목표로 하므로 `통합 중` 중심 표현이 어색하다는 의견을 반영했다.
- 변경 전: Agent1 내용을 본문 7개 슬라이드로 나누고 현재 통합 중인 상태를 주요 전제로 표시했다.
- 변경 후: 본문 필수 2장과 선택 로드맵 1장으로 압축하고, Node·평가·Q&A·검증 항목은 발표자 노트로 이동했다. 발표 본문은 Agent1 종단 연결 완료를 가정한다.
- 시각 개선: Mermaid에 AS-IS 회색, Agent 파란색, 판단 노란색, 결과 초록색의 일관된 색 체계를 적용하고 슬라이드별 배치 지침을 추가했다.
- 정확성 보완: Agent2·3은 후속 로드맵으로 분리하고, TO-BE 일부는 확정 장애가 아니라 다중 업무 평가가 필요한 개선 가설임을 명시했다.
- 안전장치: 발표 직전 실제 종단 실행·Mock 제거·근거 반환·Intent 일치 여부를 확인하는 체크리스트를 추가했다.
- 코드 변경: 없음.

### 2026-08-04 PPT용 SVG 다이어그램 추가

- 작업 시작: 2026-08-04 11:30 KST
- 작업 완료: 2026-08-04 11:35 KST
- 생성 파일: `docs/10_발표자료/assets/agent1/agent1-mvp-flow.svg`, `agent1-asis-tobe.svg`, `agent-roadmap.svg`
- 변경 파일: `docs/10_발표자료/Agent1_중간발표_ASIS_TOBE_로직개선안.md`
- 변경 이유: PPT에서 Mermaid를 직접 사용하기 어려울 수 있어 동일한 정보 구조를 유지한 편집 가능한 벡터 이미지를 제공하기 위해서다.
- 디자인 기준: 1600×900, 흰 배경, 포인트 색상 `#508cff`, 한글 UTF-8, Pretendard·Noto Sans KR·맑은 고딕 폰트 fallback을 공통 적용했다.
- 변경 후: 각 Mermaid 아래에 대응 SVG 미리보기와 원본 링크를 함께 배치해 Mermaid 원본과 발표용 이미지를 동시에 유지했다.
- 검증: XML 파싱, SVG 내 한글 문자열, Markdown 참조 경로와 3개 다이어그램의 정보 대응 관계를 확인한다.
- 알려진 제한: PPT가 시스템 글꼴을 대체할 수 있으므로 최종 삽입 환경에서 Pretendard 또는 맑은 고딕 렌더링을 한 번 확인해야 한다.

### 2026-08-04 Agent1 내부 Agent 계층 표현 보완

- 작업 시작: 2026-08-04 11:45 KST
- 작업 완료: 2026-08-04 11:55 KST
- 피드백: AS-IS 비교 그림에서 Query 생성 Agent가 생략돼 TO-BE에서 새로 추가되는 것처럼 보이고, `Agent1` 전체와 내부 Agent Node의 관계가 불명확하다는 의견을 반영했다.
- 근거 확인: `업무근거_쿼리생성_에이전트_다이어그램.md`에서 AS-IS가 `업무 추출 Agent → Query 생성 Agent → Retriever → 업무 추출 Agent` Loop임을 재확인했다.
- 변경 파일: 중간발표 로직 개선안 Markdown, `agent1-mvp-flow.svg`, `agent1-asis-tobe.svg`
- 변경 전: 슬라이드 2 AS-IS를 추출 Agent와 Intent별 Chunk만으로 압축했다.
- 변경 후: AS-IS와 TO-BE 양쪽에 Query 생성 Agent와 Retriever를 모두 표시했다. TO-BE 변경점은 Query Agent 추가가 아니라 업무별·필드별 근거 관리와 Evidence Validator·Task Extractor 책임 분리임을 명시했다.
- 계층 정리: `Agent1 = 전체 LangGraph Workflow`, 내부 LLM 판단 Node는 `업무 추출 Agent`와 `Query 생성 Agent` 두 개로 설명한다.
- 검증: 두 SVG를 1600×900으로 실제 렌더링해 한글, Node 구분, Loop 방향과 라벨 겹침을 확인했다.
- 코드 변경: 없음.
