# 준(PM) 작업 To-Do — 설계 확정~개발 착수 (2026-08-10 작성)

> 실행은 Claude Code로 진행. 각 작업 시작 전에 이 문서 상단의 「공통 주의사항」을
> 세션에 먼저 읽힌다. 근거 문서: `docs/TO-BE/` 5종(전부 v1), 기존 시스템 사실관계는
> `docs/AS-IS/시스템_전체_설계.md`.

## 공통 주의사항 (Claude Code 세션마다 적용)

- **Django ORM·migrate 안 씀.** `DATABASES = {}`, 데이터 접근은 `backend/db/repositories.py`의 psycopg 직접 SQL. 스키마 변경은 `DB/schema.sql` 수정 + `DB/migrations/*.sql` 멱등 스크립트 + `docs/개발환경/DB_시작_가이드.md` §4.3에 팀원용 ALTER 기록.
- **`git add .` 금지.** CRLF churn 200+ 파일이 작업 트리에 있다. 반드시 경로 명시 스테이징, diff는 `--ignore-all-space`로 확인. `.gitattributes` 근본 해결은 팀 합의 전 보류.
- **`01_기획` 문자열 치환 금지** — 데모 데이터의 Drive 폴더명(schema.sql·tests·frontend에 등장). docs 폴더와 무관.
- 테스트는 `SimpleTestCase` + mock, DB 안 띄움. 루트에서 `npm install` 금지(→ `frontend/`).
- RunPod Worker는 별도 저장소(`choiwon10/SKN29-RUNPOD-WORKER`)가 실코드 — `runpod_worker/`는 읽기용 사본.

---

## 0. 지금 바로 — 저장소 정리 (5분)

- [ ] `git push origin main` — 8/10 작업 11커밋(발표 산출물 5 + docs 재구조화·TO-BE 6). 팀원이 분담표·설계안을 봐야 하므로 최우선.
- [ ] `_to_delete/git-stale-locks/` 폴더 삭제 (Cowork 세션이 못 지운 git lock 잔여물).
- [ ] `june` 브랜치를 main에 맞춤: `git branch -f june main && git push origin june`.
- [ ] `wonbin`(58커밋 뒤처짐)·`fix/login-session-routing`(미병합 `41841cc`) 처리를 팀에 물어보고 결정 — 병합할 내용인지 폐기인지.

## 1. 월~화 — Base Code 정리 (IA 처리표 실행)

근거: `docs/TO-BE/1_서비스구조_IA.md` §2 처리 표. 순수 정리 작업이라 설계 확정
전에 해도 안전한 것만 골랐다.

- [ ] **정적 화면 4종 제거**: `/workspace`, `/tasks/distribution`, `/tasks/recommendation`, `/tasks/result` — 라우트·페이지 컴포넌트·링크 제거. 로직 없음이 확인된 화면들(AS-IS §7)이라 삭제 리스크 없음. 완료 기준: 빌드 통과 + 남은 라우트에서 해당 경로 링크 0건.
- [ ] **라우팅 정본 단일화**: `frontend/src/routes.ts`(개발용 목록, 27개)와 `App.tsx`(정본, ~30개)의 불일치 해소 — routes.ts를 App.tsx에서 생성하거나 제거. 완료 기준: 화면 목록의 출처가 한 곳.
- [ ] **`/projects`의 「업무 분배 시작」 버튼 경로 확인만** (제거는 Chat 흡수 후 — 지금 지우면 추출 진입점이 사라진다). 코드 위치와 의존만 메모.
- [ ] **FE 구조 인벤토리**: pages/ 컴포넌트를 IA 5영역(Chat/Builder/Project/Settings/Admin)에 매핑한 표를 `docs/TO-BE/1_서비스구조_IA.md`에 추가 — 어떤 컴포넌트가 재사용되는지(특히 `/tasks/extraction`의 근거 열람 UI → Chat 확인 스텝).
- [ ] **BE 구조 인벤토리**: `apps/*`·`services/*`·`backend/*`의 역할·의존 방향을 짧게 정리해 `docs/TO-BE/2_아키텍처_초안.md` §2 표를 검증·보강. 특히 `services/orchestration/analysis_run_service.py`가 Harness로 일반화 가능한지 실제 코드 기준 판단.

## 2. 화 — Harness 분석 수합·아키텍처 확정 (지훈·준억·주연 결과 대기)

- [ ] 세 분석 문서(`docs/TO-BE/3_Harness_조사/*_분석.md`) 수합 → **공통 구조 비교표** 작성 (Loop / Context / Memory / Tool / MCP / Model 연결 × 3 repo).
- [ ] 비교표에서 우리가 채택할 구조 선정 → `2_아키텍처_초안.md` §3(Harness 골자)·§6(직접 구현 vs 프레임워크) 갱신 → **v2 = 확정안**.
- [ ] 확정에 따라 신규 스키마 7테이블(agent, agent_tool, mcp_server, chat_session, chat_message, agent_run, tool_call) 컬럼 수준 확정 → `DB/migrations/2026-08-1x_agent_platform.sql` 초안 작성 (아직 적용은 안 함 — 멘토링 후).

## 3. 화~수 — 시각화 (멘토링 필수 산출물 7종)

방식 제안: **Mermaid로 repo에 커밋**(리뷰·수정 가능) + 발표용은 나중에 Figma로
옮김. Claude Code로 Mermaid 초안을 빠르게 뽑고 팀 검토.

- [ ] 전체 서비스 화면 구조 (IA §1 기반)
- [ ] 사용자 주요 Flow 3종 (IA §3: 온보딩 / E2E / Agent 생성)
- [ ] Agent Builder 구조
- [ ] Agent 실행 구조 (요청→Loop→Tool→응답 시퀀스)
- [ ] Agent Harness Architecture (아키텍처 §1·§3 기반)
- [ ] Connector / MCP / Memory 연결 구조
- [ ] 기존 업무 추출 Agent가 들어가는 위치 (아키텍처 §2 매핑의 그림 버전)

저장 위치: `docs/TO-BE/diagrams/*.mermaid` (또는 md 내 코드블록).

## 4. 수 오전 — 멘토링 준비

- [ ] **8/12 질문 종합 1장** 작성: IA 미결정 4 + 아키텍처 질문 5 + 평가 질문 3 + E2E 미결정 4 = 16건을 중복 제거·우선순위 정렬해 `docs/TO-BE/0_멘토링_질문.md`로. 핵심 3개를 맨 위에: ① Harness 직접 구현 vs 프레임워크 ② 업무 분배(STEP 5) v1 제외 ③ 온디맨드 파싱 제외.
- [ ] 설계안 발표 순서 정리: 한 줄 정의 → IA → 아키텍처 → E2E → 평가 → 질문 (README 링크만 따라가면 되게).

## 5. 수 오후~목 — 개발 착수 (멘토링 확정 반영 후)

우선순위는 "Harness가 실제로 동작하는 것 > 화면 개수". 평가 설계의 전제
(**agent_run·tool_call 로그 적재를 첫 주에**)를 개발 순서에 반영한다.

- [ ] migrations 적용 + `DB/schema.sql` 갱신 + DB_시작_가이드 §4.3 기록 → 팀 공지 (미적용 팀원은 화면 에러 — 이월 리스크 5번).
- [ ] Harness 스켈레톤: Agent Loop 인터페이스 + Tool Registry + **실행 로그 적재부터** (`services/harness/` 신설, orchestration 흡수).
- [ ] Chat 스트리밍 엔드포인트: 기존 NDJSON 프로토콜 재활용, `chat_session`/`chat_message` 적재.
- [ ] Pre-built Agent 1호: `services/task_extraction`을 Harness 위에서 실행되게 재연결 (Priority 5).
- [ ] Builder CRUD (agent·agent_tool) — 화면은 최소, API 먼저.
- [ ] MCP Client 최소 구현: mcp_server 등록 → tool 목록 조회 → 호출 (Jira 대상, Priority 4).

## 6. 병행 확인 (내 담당 아님 — 상태만 챙김)

- 원빈: 전처리 E2E 안정화 + G-DOC·G-QUERY 골든셋 (평가 설계 §7)
- 지훈·준억·주연: 분석 화요일 공유 (`3_Harness_조사/README.md` 마감)
- 팀 회의 1회: G-TASK 골든셋 합의 (개발 1주차)
