# 개발 지시서 1차 — Agent Platform 착수 (8/11 회의 확정 기반)

> Claude Code 세션용. **단계 순서대로 진행하고, 단계마다 커밋.** 모든 결정은
> 8/11 팀 회의 확정(아키 §3.1) 기준이며, 8/12 멘토링에서 뒤집힐 수 있는 부분은
> 각 단계에 ⚠로 표기 — 그 부분만 나중에 수정하면 되게 경계를 잡아뒀다.

## 진행 현황 (2026-08-11 기준)

**단계 1~6 전부 완료.** 지시 원문은 「무엇을 요청했는가」의 기록이라 그대로
두고, 단계마다 아래에 **결과** 블록으로 실제 구현·이탈·검증을 붙였다.

| 단계 | 상태 | 커밋 |
|---|---|---|
| 1 DB 마이그레이션 | 완료 | `71dd585` |
| 2 Harness 스켈레톤 | 완료 | `f5d3898` · `5ef4f1d`(수정) · `e5b9e5f`(수정) |
| 3 Chat API | 완료 | `bfd356b` |
| 4 업무 추출 재연결 | 완료 | `dac1ba8` |
| 5 문서 메타 파이프라인 | 완료(1건 보류) | `dd99911` |
| 6 MCP 최소 구조 | 완료(**C안으로 방향 변경**) | `c02d940` · `cac1c6c` |

기존 테스트 289개 → **379개 전부 통과.** 화면(2차 지시서 A~D)은 별도 커밋
`23b5816`·`56c5a2a`·`b34073f`·`43d1a68`·`e628b7c`.

**단위 테스트만으로는 두 번 놓쳤다.** 모델 호출 계약과 진행 이벤트 충돌은 실제로
돌려 본 뒤에야 드러났다(각 단계 결과 참고). 그래서 단계마다 임시 DB·실제 PDF·
실제 모델로 한 번씩 돌려 확인했고, 무엇을 어떻게 확인했는지 결과 블록에 적었다.

## 공통 주의사항 (매 세션 필독)

- **Django ORM·migrate 안 씀.** `DATABASES = {}`. 데이터 접근은 `backend/db/repositories.py`의 psycopg 직접 SQL. 스키마 변경 = `DB/schema.sql` 갱신 + `DB/migrations/*.sql` 멱등 스크립트 + `docs/개발환경/DB_시작_가이드.md` §4.3에 팀원용 ALTER 기록 + 팀 공지(미적용 팀원은 화면 에러).
- **`git add .` 금지** (CRLF churn). 경로 명시 스테이징, `git diff --ignore-all-space`로 확인.
- **`01_기획` 문자열 치환 금지** (데모 데이터 값).
- 테스트는 `SimpleTestCase` + mock, DB 안 띄움. 기존 `def test_` 289개 깨뜨리지 않기.
- 참조 문서: 아키텍처(`docs/TO-BE/2_아키텍처_초안.md` — §3.1이 확정 사항), MCP(`11_MCP_설계.md`), 평가(`4_평가_설계.md`), E2E(`5_E2E_시나리오.md`), Harness 구조 근거(`3_Harness_조사/공통구조_비교_회의자료.md`).

## 단계 1 — DB 마이그레이션 (모든 것의 전제)

`DB/migrations/2026-08-11_agent_platform.sql` (멱등, IF NOT EXISTS):

```
agent          id PK · team_id FK · name · description · instruction TEXT ·
               model VARCHAR · reasoning_effort VARCHAR · max_iterations INT DEFAULT 10 ·
               is_prebuilt BOOL · status(ACTIVE/ARCHIVED) · created_by · created_at · updated_at
agent_tool     id PK · agent_id FK · tool_ref VARCHAR      -- 내장 tool 식별자 또는 'mcp:<mcp_tool.id>'
mcp_server     id PK · team_id FK · name · endpoint_url · auth_token_enc ·
               status(CONNECTED/ERROR/UNCHECKED) · last_checked_at · created_by
mcp_tool       id PK · server_id FK · name · description TEXT · input_schema JSONB ·
               enabled BOOL · discovered_at
chat_session   id PK · team_id FK · account_id FK · agent_id FK · proj_id FK NULL ·
               title · created_at · updated_at
chat_message   id PK · session_id FK · role(user/agent/system) · content JSONB ·
               created_at                                   -- content에 카드(근거·확인·결과) 구조 포함
agent_run      id PK · session_id FK · agent_id FK · parent_run_id FK NULL ·
               status(RUNNING/DONE/FAILED/CANCELLED) · iterations INT ·
               token_in INT · token_out INT · started_at · ended_at
tool_call      id PK · run_id FK · tool_ref · input_summary TEXT · status(PENDING/OK/FAILED) ·
               error_code VARCHAR NULL · duration_ms INT · created_at
doc_meta       doc_id PK/FK · summary TEXT · doc_type · keywords TEXT[] ·
               summary_vec vector(768) · extract_status(OK/FAILED/UNSUPPORTED) · extracted_at
```

`DB/schema.sql` 동기화 + DB_시작_가이드 §4.3 기록. 완료 기준: 신규 로컬 DB에
schema.sql 1회 적용으로 전 테이블 생성, 기존 테이블 무변경.

> **결과 — 완료 (`71dd585`)**
>
> 9개 테이블 신설. `schema.sql`·§4.3·변경 이유 표까지 반영.
>
> **PK를 둘로 나눴다.** 이 스키마의 `VARCHAR(5)`는 접두사 2자 + 숫자 3자라
> **테이블당 999행이 상한**인데(`backend/db/codes.py`), 대화 한 번에 수십 줄씩
> 쌓이는 `chat_message`·`agent_run`·`tool_call`은 데모 도중에도 넘긴다. 로그성
> 테이블은 `doc_block`·`chunk`·`vec_idx` 선례대로 UUID, 사람이 만드는 설정
> (`agent`·`mcp_server`·`mcp_tool`)만 기존 코드 체계.
>
> 그 밖의 이탈 3건 — `agent_tool`은 대리키 없이 복합 PK(순수 조인 테이블),
> `agent_run.session_id`는 NULL 허용(단계 2가 `run_agent`를 대화 비종속으로
> 못박았는데 NOT NULL이면 모순), `doc_meta.extracted_text`를 지금 추가(단계 5 ⚠의
> A′ 대비 — 마이그레이션 1회로 끝난다).
>
> 검증: 빈 DB에 `schema.sql` 1회 → public 49 + mock_hr 8. 옛 DB에 마이그레이션
> **2회** 적용해도 컬럼·인덱스가 `schema.sql` 결과와 완전 일치(멱등). 기존 40개
> 테이블 354개 컬럼 무변경.

## 단계 2 — Harness 스켈레톤 (`services/harness/` 신설)

**로그 적재부터 만든다 — 평가의 전제.**

1. `runner.py` — **`run_agent(agent_id, user_input, context) -> 이벤트 제너레이터`
   순수 함수** (chat_session 비종속 — A2A 대비, 회의자료 §3-⑨). Loop:
   스캐폴드+instruction 합성 → 모델 호출 → tool_call 판단 → 실행 → 결과 반영
   → 반복. **하드 상한 `agent.max_iterations`(기본 10) 코드 강제.**
2. `scaffold.py` — 공통 스캐폴드 고정 템플릿 (계획·툴 상한 권고·"근거 없이
   추측 금지"). agent 레코드에 저장하지 않음(코드 상수).
3. `registry.py` — Tool Registry: 내장 tool 2종 등록(`document_search`,
   `workload_report` — 후자는 services/workload 래핑) + mcp_tool 로드.
   Agent별 허용 목록(agent_tool) 필터.
4. `trace.py` — **선기록 패턴**: tool_call을 PENDING으로 먼저 INSERT → 실행 →
   status/error_code/duration 갱신. agent_run 시작/종료 기록.
5. 이벤트 규약: 기존 NDJSON 타입(`api_views.py:1070-1092`) 재사용 + 신규 타입
   최소 추가(`tool_call_started/finished`, `awaiting_confirmation`).

완료 기준: mock 모델로 "입력→내장 tool 1회→응답" Loop가 돌고 agent_run·
tool_call 행이 남는 단위 테스트.

> **결과 — 완료 (`f5d3898`, 수정 `5ef4f1d`·`e5b9e5f`)**
>
> `services/harness/` 4개 파일 + `backend/db/agent_platform.py`.
>
> **이탈: SQL을 `trace.py`가 아니라 `backend/db/agent_platform.py`에 뒀다.**
> `services/` 중 psycopg에 직접 붙는 모듈이 0개이고 전부 `backend/db` 경유다
> (`document_pipeline.py`가 같은 선례). 공통 주의사항의 "데이터 접근은
> backend/db"와 충돌해서 이쪽을 택했다. `trace.py`는 선기록 순서만 맡는다.
>
> 상한 초과 시 `error`가 아니라 `complete=false` + `stopped_reason` 인 `result`를
> 낸다. 거기까지 한 일은 버려지지 않으니 실패로 적으면 거짓이고, 성공처럼
> 뭉개지도 않는다.
>
> **⚠ 실호출로만 드러난 것 2건 (단위 테스트는 전부 통과했는데 실제로는 한 번도
> 못 돌던 상태였다):**
> 1. `chat.completions` + `reasoning_effort=`는 이 계정·모델의 계약이 아니다.
>    `services/task_extraction`이 이미 쓰던 **Responses API**가 맞다. 추론 모델은
>    `function_call`을 되돌려 줄 때 **짝이 되는 `reasoning` 아이템을 함께 요구**
>    한다(없으면 400). `status`는 되돌려 보낼 수 없다(400). → 메시지 목록을
>    Responses API의 input 아이템 그대로 들고 다니게 바꿨다(`5ef4f1d`).
> 2. Loop의 `stage`(회전 1/4)와 도구의 `stage`(파이프라인 1/5)가 같은 타입이라
>    화면에서 구별이 안 됐다. 진행 카드가 1/4 → 1/5 → 2/5 → 2/4로 튄다.
>    → 도구가 흘린 이벤트에 `tool_ref`·`tool_call_id`를 붙인다(`e5b9e5f`).
>    화면 규칙: **`tool_ref`가 있으면 그 도구의 진행, 없으면 Loop의 회전.**
>
> 테스트가 잡은 버그 1건: 모델이 `team_id`를 인자로 보내면 서버 주입값과 키가
> 겹쳐 `TypeError`로 죽었다 — 덮어쓰기가 아니라 크래시라 테넌트 방어가 아예
> 동작하지 않았다.
>
> 검증: 단위 24개 + 임시 DB에서 선기록 왕복(DONE/FAILED·duration·error_code·
> 한글 input_summary) + **실제 모델로 끝까지 1회**(도구 호출 → 근거 반영 →
> 근거를 밝힌 답변, 2회전, 797/116 토큰).

## 단계 3 — Chat API

- `chat_session`/`chat_message` CRUD (팀 경계 `_require_team` 준수).
- 스트리밍 엔드포인트: `POST /api/chat/sessions/<id>/messages` → run_agent
  이벤트를 NDJSON으로 중계, chat_message 적재(스트림 완료 시 확정).
- **확인 게이트**: run이 `awaiting_confirmation` 상태로 멈추면 저장하고,
  `POST .../confirm`(선택 항목 포함)으로 재개. 승인 전 side-effect tool 실행
  금지 (회의 확정 ③).
- 에이전트 선택은 요청 body의 `agent_id` (수동 선택기 — 확정 ①).

> **결과 — 완료 (`bfd356b`)**
>
> `apps/chat/` 신설. `GET·POST /api/chat/sessions/`, `GET·DELETE .../<id>/`,
> `POST .../<id>/messages/`(NDJSON 스트림), `POST .../<id>/confirm/`.
>
> **확인 게이트 설계를 바꿨다.** 재개를 "원래 입력으로 `run_agent` 재호출"로
> 만들면 모델이 재실행 때 **다른 인자를 고를 수 있다** — 사용자가 승인한 것과
> 실제로 실행되는 것이 달라진다. 외부를 바꾸는 게이트에서 그건 승인이 아니다.
> 그래서 `awaiting_confirmation`에 재개 정보(그 시점 대화 + 그 호출)를 실어
> 보내고, confirm이 그대로 돌려주면 **모델 호출 없이 그 호출부터** 이어 돈다.
>
> 같은 이유로 **confirm body는 실행할 인자를 받지 않는다.** 화면이 보낸 인자로
> 외부 시스템이 바뀌면 게이트가 아무것도 막지 못한다. 받는 것은 체크한 항목의
> 인덱스뿐이고, 인자에 목록이 둘 이상이면 짐작하지 않는다(짐작하면 사용자가 뺀
> 항목이 그대로 올라간다).
>
> 적재 순서를 갈랐다 — **사용자 발화는 스트림 전에 확정**, 에이전트 답은 스트림
> 완료 시 카드 한 벌로. 답 없는 대화는 다시 물으면 되지만 질문이 사라진 대화는
> 복구할 수 없다. 재개 정보는 화면으로 내보내지 않는다(모델 대화 상태·도구 원본).
>
> 에이전트는 대화를 열 때 고르고 중간에 바꾸지 않는다 — 갈면 앞선 턴이 다른
> 스캐폴드·다른 도구로 만들어진 것이 되어 이어지는 답의 근거가 흔들린다.
>
> 검증: 단위 17개 + 임시 DB(팀 2개)로 남의 팀 403 3종·남의 팀 에이전트 403·
> 잘못된 형식 session_id가 500 아닌 404 + **실제 서버 HTTP E2E**(아래 참고).

## 단계 4 — Pre-built Agent 1호: 업무 추출 재연결

- `services/task_extraction`을 Harness의 tool 또는 전용 실행 경로로 감싸
  `업무 추출 에이전트`(is_prebuilt=true) 시드 데이터 등록.
- 추출 결과는 **chat_message.content에 구조화 저장(확정 ④ — 새로고침 소실
  문제 해결)**. Jira 등록 성공분만 task 테이블 적재는 단계 6 이후.
- 기존 `/tasks/extraction` 화면은 손대지 않는다(G3 — Chat E2E 통과 전 데모
  안전망).

> **결과 — 완료 (`dac1ba8`)**
>
> 지시서가 「tool 또는 전용 실행 경로」로 열어 둔 것을 **진행을 흘리는 tool**로
> 만들었다. 평범한 tool로 감싸면 두 가지가 깨진다 — ①안쪽이 4단계 검색 + 1단계
> 정리라 몇 분이 걸리는데 그 진행을 삼키면 화면이 멈춘 것과 구별되지 않는다
> (기존 `/tasks/extraction` 화면은 이미 보여 주고 있어서 Chat이 명백히 못한
> 물건이 된다) ②업무 20건을 바깥 모델에 그대로 돌려주면 한 번 더 요약하면서
> 근거가 흔들리고 토큰도 그만큼 든다.
>
> handler가 제너레이터면 Runner가 중계하고 `return` 값을 모델에게 준다. 진행·
> 결과는 이벤트로 나가 `chat_message.content`에 구조화되어 남고(확정 ④), 모델이
> 받는 것은 건수·경고·기준 문서 이름뿐이다.
>
> **기준 문서와 프로젝트는 모델이 고르지 않는다.** 어느 문서로 뽑았는지가 결과
> 전체의 전제라 사람의 결정이어야 한다 — `proj_id`는 세션이 정하고, 기준 문서는
> 이미 골라 둔 `doc_role='PRIMARY'`를 쓴다.
>
> `backend/services/createDB/seed_agents.py` 신설(멱등, 팀별). `grant_admin.py`와
> 같은 이유로 API가 아니다 — `is_prebuilt=true`를 API로 만들 수 있으면 「우리가
> 제공하는 것」과 「팀이 만든 것」의 구분이 무의미해진다. DB_시작_가이드 §6.2 기록.
>
> **G3 무손상**: `/tasks/extraction` 화면도 그 API도 변경 목록에 없다.
>
> 검증: 단위 + 임시 DB 시드 멱등 + **실제 HTTP·실제 모델로 업무 11건 추출**
> (136초, 근거 20건). 모델이 업무 목록을 다시 나열하지 않고 건수·경고만 말한
> 것까지 확인 — "요약만 돌려준다" 설계가 의도대로 동작했다.

## 단계 5 — 문서 메타 파이프라인 (A안, 확정 ⑥)

- 폴더 스캔 시(기존 신규 파일 감지 로직에 연결): CPU 텍스트 추출(PDF 텍스트
  레이어; 실패 시 `extract_status=FAILED`, hwp는 UNSUPPORTED) → LLM 요약·유형·
  키워드(mini급 모델 1회) → 요약 임베딩 1개 → `doc_meta` 적재.
- `document_search` tool의 coarse 단계를 doc_meta.summary_vec으로, 미처리
  후보는 기존 RunPod 파이프라인 온디맨드 호출(캐시 = 기존 chunk/vec_idx 적재
  유지)로 연결.
- ⚠ 멘토링 민감: coarse가 요약만으로 부족하다는 결론이 나오면 tsvector 전문
  인덱스 추가(A′ — `12_문서처리_방식_비교.md` §5). **doc_meta에 원문 추출
  텍스트를 버리지 말고 `extracted_text` 컬럼으로 보관**해 두면 A′ 전환이
  인덱스 추가만으로 끝난다.
- 평가 준비: 요약 품질 검증용 **문서 단위 Recall(coarse) 측정 스크립트**
  자리(`tests/eval/`) 마련 — G-QUERY 골든셋 입력 형식만 정의.

> **결과 — 완료, 1건 보류 (`dd99911`)**
>
> `services/document_meta/`(추출·요약), `DocMetaRepository`,
> `POST /api/team/documents/meta/`, `tests/eval/`. `pypdf` 신규 의존성.
>
> **이탈 — 후킹을 「폴더 스캔」이 아니라 「다운로드 다음 단계의 별도
> 엔드포인트」로.** 스캔 시점에는 원문 바이트가 없어 CPU 추출을 할 수 없고,
> 다운로드 응답 안에서 처리하면 요약 임베딩의 RunPod 콜드 스타트(최대 10분)가
> 다운로드를 통째로 붙잡는다. 등록 → 다운로드 → 처리와 같은 모양이다.
>
> **이탈 — 「mini급 모델」이 `SUPPORTED_MODELS`(sol·terra·luna)에 없다.** 가장
> 싼 luna(`OPENAI_PLAN_MODEL`)를 쓴다.
>
> **보류 — 미처리 후보의 온디맨드 RunPod 호출은 넣지 않았다.** 그 경로는
> 비동기(submit → 폴링 → ingest)라 채팅 한 턴이 GPU 콜드 스타트를 포함해 몇
> 분을 붙잡는다. 대신 coarse가 고른 문서 중 색인 안 된 것을 `not_indexed`로
> 돌려준다 — 조용히 빼면 에이전트가 "관련 문서가 없다"고 답하는데 실제로는
> 있는 상태가 된다. **자동 처리를 붙일지는 판단이 필요하다**(`submit_document_job`
> → `_await_job` → `ingest`로 25줄 정도, 상한과 진행 표시가 같이 필요).
>
> coarse가 없는 팀은 예전처럼 팀 문서 전체를 훑는다 — 파이프라인 안 돌린 팀의
> 검색이 죽으면 안 된다.
>
> **⚠ 실제 PDF에서만 드러난 결함 1건.** 폰트 CMap이 없는 PDF가 18,961자를
> 뱉는데 전부 같은 글자였다(`"SK 네네네네 Family AI 네네"` — `네`가 5,972/8,119).
> 글자 수 검사만으로는 `OK`로 통과하고, 그 헛소리로 만든 요약의 임베딩이 coarse
> 검색을 오염시킨다. 한글 최빈 글자 비율로 거른다 — 실측 **정상 0.031 / 깨진 것
> 0.736**이라 경계 0.30, 한글 100자 미만이면 판정하지 않는다(영문 문서 보호).
>
> A′ 대비 완료: 추출 원문을 `doc_meta.extracted_text`에 보관한다.
>
> 검증: 단위 17개 + 저장소의 실제 PDF 2건(정상 18,325자 OK / 깨진 것 FAILED) +
> 임시 DB에서 문서 4건 상태별(원문 없는 문서 pending 제외, upsert 멱등, FAILED는
> 요약 벡터가 없어 coarse 자동 제외, 남의 팀 0건).

## 단계 6 — MCP 최소 구조 (11_MCP_설계 §7 순서)

1. mcp_server/mcp_tool 등록·연결 테스트 API (initialize+list_tools → 저장).
   **SSRF 차단**(https만, 사설 IP 대역 거부 — 등록·호출 시 모두)·토큰 암호화.
2. MCP Client(호출·타임아웃 30s·오류 매핑 401/429/validation/timeout) →
   Registry 통합.
3. 자체 Jira MCP 서버: tool 3종(`jira_create_issues` 벌크·부분 실패 목록
   반환 / `jira_create_project` **— ⚠ Q6(Jira 생성 단위) 결정 대기, 이
   tool만 보류하고 나머지 먼저 진행(8/12)** / `jira_get_issues`) — 기존 apps/connectors
   Jira REST 재사용, 별도 프로세스로 띄워 **일반 등록 플로우로만 접속**(특권
   경로 금지 — 11_MCP_설계 §0).

> **결과 — 1·2 완료 (`c02d940`), 3은 C안으로 방향 변경 (`cac1c6c`)**
>
> **1·2 (플랫폼 쪽) 완료.** `services/mcp/security.py`(SSRF) ·
> `services/mcp/client.py`(JSON-RPC 2.0) · `McpServerRepository` ·
> `apps/mcp/`(등록·연결 테스트·삭제) · Registry 통합.
>
> 공식 SDK를 쓰지 않는다 — 필요한 것은 `initialize`·`tools/list`·`tools/call`
> 셋뿐이고 전부 JSON-RPC 한 번씩인데, SDK를 넣으면 stdio·SSE 세션 관리까지
> 딸려 온다. 의존성 0.
>
> SSRF는 **등록 시와 호출 시 모두** 검사한다(DNS 리바인딩 대비). 대역을 손으로
> 나열하지 않고 `ip_address.is_global`로 판정한다(나열하면 IPv6 쪽에서 빠지는
> 것이 생긴다). 이름 하나가 공인·사설 주소를 함께 주면 막는다. 토큰은 암호화
> 저장, 목록 API는 `has_token`만 주고, Registry는 Tool 객체에 토큰을 담지 않고
> 실행 직전에 꺼낸다. 연결 실패해도 등록은 남기고 ERROR 표시(§3).
>
> ### ⚠ 3번 — 자체 Jira MCP 서버를 띄울 수 없다
>
> **설계 §5와 §4-1이 서로 막는다.** §5는 「Django와 같은 호스트의 별도 프로세스」로
> 띄워 「일반 등록 플로우로만 접속」하라는데, §4-1 SSRF 차단이 정확히 그 주소
> (`localhost`·`127.0.0.1`·사설 대역)를 막는다. 예외를 두면 시연하려는 방어를
> 시연 중에 끄는 셈이다.
>
> 공식 Atlassian MCP로 대신할 수도 없다. **실측(2026-08-11)**:
>
> ```
> POST https://mcp.atlassian.com/v1/sse  (initialize)
> → 401  WWW-Authenticate: Bearer realm="OAuth", error="invalid_token"
> ```
>
> OAuth 액세스 토큰을 요구하므로, 정적 토큰 하나를 저장하는 우리 모델로는 붙어도
> **만료(보통 1시간) 뒤 끊긴다.** MCP용 OAuth 플로우는 별도 기능이다.
>
> ### C안 확정 (팀 결정) — 기본 tool은 우리가 제공, MCP는 확장 경로
>
> Jira 등록·조회를 **내장 tool**로 넣었다(`cac1c6c`). 데모 핵심 흐름을 남의
> 서비스와 남의 토큰 수명에 매달지 않는다 — Jira Connector는 이미 OAuth로 붙어
> 있어 추가 인프라가 0이다. MCP는 「사용자가 자기 서버를 추가로 붙이는」 확장
> 경로로 남고, 그 경로는 이미 완성돼 있다.
>
> 기존 Jira 클라이언트는 **읽기 전용**이어서 `create_jira_issues`를 새로 만들었다.
> 신경 쓴 곳 셋 — ①**부분 실패를 그대로 반환**(성공분만 주면 화면이 "20건 등록"
> 이라 말하는데 실제로는 17건이 된다) ②필수값 누락은 **보내기 전에** 거른다
> (보내면 영어 오류가 오고 어느 이슈 것인지 되짚기 어렵다) ③Jira가 준
> `failedElementNumber`를 원래 순번으로 되돌린다(걸러낸 건이 있으면 어긋나서,
> 그대로 쓰면 **엉뚱한 업무에 실패 사유가 붙는다**). `description`은 ADF로 감싼다.
>
> `jira_create_issues`는 `side_effect=true`라 승인 게이트를 타고,
> `jira_get_issues`는 읽기라 타지 않는다. 두 도구 모두 `account_id`를 서버가
> 주입한다 — Connector 자격증명이 계정별이라 모델이 정하면 남의 Jira를 건드린다.
>
> 시드 에이전트 도구 4종(`task_extraction`·`document_search`·`jira_create_issues`·
> `jira_get_issues`), 상한 4→6(가장 긴 정상 흐름이 4회전).
> 프론트 `mockAgents.ts`의 tool id도 같은 계약으로 맞췄다 — **MCP 도구 목록은
> 이제 그 상수가 아니라 Settings > MCP에 등록된 서버에서 온다**(화면 연결 필요).
>
> 검증: 단위 31개 + SSRF를 mock 없이 **실제 DNS**로(9종 차단 / `example.com`·
> `mcp.atlassian.com` 통과) + 임시 DB(토큰이 평문으로 저장되지 않음·복호화 왕복·
> 사라진 도구 정리·서버 삭제 시 `agent_tool` 연쇄 정리·남의 팀 403/404).
> **`jira_create_issues` 실호출은 미검증** — 실제 Jira에 이슈가 생기는 도구다.

## 단계별 커밋·검증 규칙

- 단계당 1 커밋 이상, 메시지에 근거 문서 참조.
- 매 단계: 기존 테스트 289개 통과 + 신규 단위 테스트.
- FE 작업은 이 지시서 범위 밖 (AppShell·ChatPage는 Figma 확정안 기준 별도
  지시 예정 — API 계약이 먼저).

> **결과 — 지켰다.** 289 → **379개 통과.** 단계마다 1커밋 이상, 수정은 별도
> 커밋으로 갈랐다.
>
> **다만 단위 테스트만으로는 부족했다.** 이번에 실호출로만 드러난 것이 셋이다 —
> 모델 API 계약(단계 2), 진행 이벤트 타입 충돌(단계 2), 깨진 PDF 추출(단계 5).
> 셋 다 단위 테스트는 전부 통과하는 상태였다. **다음 지시서에는 단계마다
> 「실제로 한 번 돌려 확인할 것」을 완료 기준에 같이 적는 편이 낫다.**

## E2E 관통 확인 (2026-08-11)

단계 3·4 뒤에 실제 서버 + 실제 모델 + 실제 DB로 한 번 뚫었다. 확인된 것:

| 구간 | 결과 |
|---|---|
| 마이그레이션 → `project_copilot` | 49개 테이블, 기존 데이터 무손상 |
| `seed_agents.py` | `AG001 업무 추출 에이전트` 생성 |
| 인증 → 세션 생성 | 201 / 팀 없는 계정 403 |
| 스트림(도구 없음) | `stage → result` |
| 스트림(`document_search` ×2) | 근거 인용 답변, 44초 |
| 스트림(`task_extraction`) | 업무 11건·근거 20건, 136초 |
| 새로고침 재현 | `GET`으로 복원(23kB 카드), 재개 정보 미노출 |
| 실행 로그 | `agent_run` DONE, `tool_call` OK / 131,315ms |

`tool_call.duration_ms`가 38,283ms(RunPod 콜드) → 1,336ms(웜)로 떨어진 것까지
기록됐다 — 로그가 실측을 담고 있다는 증거다.

**함정 하나**: Windows 셸에서 `curl -d '{"title":"한글"}'`는 cp949로 나가 서버가
`JSON parse error`를 낸다. 브라우저는 UTF-8이라 무관하지만 curl 테스트에서 바로
걸린다 — `--data-binary @파일.json`을 쓸 것.

## ⚠ 멘토링(8/12 18:00) 민감 항목 요약

- 단계 5의 A vs A′ (extracted_text 보관으로 헤지 완료) — **그대로 유효.**
  판단 근거를 만들 `tests/eval/coarse_recall.py`도 자리를 잡았다. 골든셋만
  채우면 숫자가 나온다.
- 업무 분배 제외(Q2)·Jira 생성 단위(Q6) — **C안 확정으로 영향이 줄었다.**
  `jira_create_project`가 필요해지면 자체 MCP 서버가 아니라 내장 tool 하나를
  더하면 된다.
- Q16(데모 대표 MCP를 자체 래핑으로 갈 것인가 — 11_MCP_설계 §8) — **철회.**
  C안으로 정리됐다. 대신 물을 것이 바뀌었다: **정적 토큰만 받는 지금 모델로
  「사용자가 자기 MCP를 붙인다」가 성립하는가.** 호스팅형 MCP는 OAuth를 요구해
  (Atlassian 실측 401) 한 시간 뒤 끊긴다. MCP용 OAuth 지원을 v1에 넣을지 결정 필요.
- 그 외 단계 1~4는 멘토링 결과와 무관하게 안전 (3/3 수렴 구조)

## 후속 판단이 필요한 것

1. **MCP OAuth 지원** — 위 Q16 대체 항목. 안 하면 MCP 확장은 정적 토큰을 주는
   서버(주로 자체 호스팅)로 한정된다.
2. **미처리 문서 온디맨드 처리**(단계 5 보류) — 채팅 한 턴이 GPU 콜드 스타트를
   포함해 몇 분을 붙잡는 문제. 붙인다면 상한과 진행 표시가 같이 필요하다.
3. **`agent_run` 토큰이 도구 안에서 쓴 토큰을 안 센다.** 업무 추출 실호출에서
   `token_in=1377`로 기록됐는데 실제 대부분은 안쪽 sol·xhigh가 썼다. 평가 §4가
   이 값으로 비용을 재면 한 자릿수 이상 틀린다. 고치려면
   `extract_tasks_stream`이 usage를 내보내야 하는데, 그건 「감싸되 손대지 말라」고
   한 기존 서비스를 바꾸는 일이라 판단으로 남긴다.
4. **`jira_create_issues` 실호출 미검증** — 실제 Jira에 이슈가 생긴다. 지울 수
   있는 프로젝트를 정해 부분 실패까지 확인할 것.
5. **Settings > MCP 화면 연결**(11_MCP_설계 §7-4) — API는 준비됐다. FE 지시서 범위.
6. **`.gitattributes`(`* text=auto eol=lf`)** — CRLF churn의 근본 해결. 전 파일이
   한 번 리터치되므로 별도 커밋으로.
