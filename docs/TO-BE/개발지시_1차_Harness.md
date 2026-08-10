# 개발 지시서 1차 — Agent Platform 착수 (8/11 회의 확정 기반)

> Claude Code 세션용. **단계 순서대로 진행하고, 단계마다 커밋.** 모든 결정은
> 8/11 팀 회의 확정(아키 §3.1) 기준이며, 8/12 멘토링에서 뒤집힐 수 있는 부분은
> 각 단계에 ⚠로 표기 — 그 부분만 나중에 수정하면 되게 경계를 잡아뒀다.

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

## 단계 3 — Chat API

- `chat_session`/`chat_message` CRUD (팀 경계 `_require_team` 준수).
- 스트리밍 엔드포인트: `POST /api/chat/sessions/<id>/messages` → run_agent
  이벤트를 NDJSON으로 중계, chat_message 적재(스트림 완료 시 확정).
- **확인 게이트**: run이 `awaiting_confirmation` 상태로 멈추면 저장하고,
  `POST .../confirm`(선택 항목 포함)으로 재개. 승인 전 side-effect tool 실행
  금지 (회의 확정 ③).
- 에이전트 선택은 요청 body의 `agent_id` (수동 선택기 — 확정 ①).

## 단계 4 — Pre-built Agent 1호: 업무 추출 재연결

- `services/task_extraction`을 Harness의 tool 또는 전용 실행 경로로 감싸
  `업무 추출 에이전트`(is_prebuilt=true) 시드 데이터 등록.
- 추출 결과는 **chat_message.content에 구조화 저장(확정 ④ — 새로고침 소실
  문제 해결)**. Jira 등록 성공분만 task 테이블 적재는 단계 6 이후.
- 기존 `/tasks/extraction` 화면은 손대지 않는다(G3 — Chat E2E 통과 전 데모
  안전망).

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

## 단계 6 — MCP 최소 구조 (11_MCP_설계 §7 순서)

1. mcp_server/mcp_tool 등록·연결 테스트 API (initialize+list_tools → 저장).
   **SSRF 차단**(https만, 사설 IP 대역 거부 — 등록·호출 시 모두)·토큰 암호화.
2. MCP Client(호출·타임아웃 30s·오류 매핑 401/429/validation/timeout) →
   Registry 통합.
3. 자체 Jira MCP 서버: tool 3종(`jira_create_issues` 벌크·부분 실패 목록
   반환 / `jira_create_project` / `jira_get_issues`) — 기존 apps/connectors
   Jira REST 재사용, 별도 프로세스로 띄워 **일반 등록 플로우로만 접속**(특권
   경로 금지 — 11_MCP_설계 §0).

## 단계별 커밋·검증 규칙

- 단계당 1 커밋 이상, 메시지에 근거 문서 참조.
- 매 단계: 기존 테스트 289개 통과 + 신규 단위 테스트.
- FE 작업은 이 지시서 범위 밖 (AppShell·ChatPage는 Figma 확정안 기준 별도
  지시 예정 — API 계약이 먼저).

## ⚠ 멘토링(8/12 18:00) 민감 항목 요약

- 단계 5의 A vs A′ (extracted_text 보관으로 헤지 완료)
- 업무 분배 제외(Q2)·Jira 생성 단위(Q6) — 단계 6의 `jira_create_project`
  포함 여부만 영향
- 그 외 단계 1~4는 멘토링 결과와 무관하게 안전 (3/3 수렴 구조)
