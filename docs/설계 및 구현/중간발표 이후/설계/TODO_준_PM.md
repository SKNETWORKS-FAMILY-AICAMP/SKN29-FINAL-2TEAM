# 준(PM) 작업 To-Do — 설계 확정~개발 착수 (2026-08-10 작성 · 8/10 저녁 갱신)

> ## ⛔ 이 문서는 끝났다 (2026-08-15)
>
> **8/10~8/12 의 착수 계획서였고, 그 구간은 전부 지났다.**
> 아래 체크박스는 **더 이상 사실이 아니다** — 남은 일을 여기서 찾지 말 것.
>
> - **앞으로 할 일 → [`작업목록.md`](작업목록.md)** 가 유일한 정본이다.
> - **실행 이력 → git 히스토리**(8/10 이후 커밋 300건 이상).
>
> 지우지 않는 이유는 하나다 — `3_Harness_조사/Deep-Agent_활용_설계_정리.md` 가
> **§3 의 「멘토링 필수 산출물 7종」을 인용**한다. 그 절만 참조용으로 살아 있다.

> **멘토링: 8/12(수) 18:00.** 수요일 낮까지가 준비 시간, 개발 착수는 목요일부터.

> 실행은 Claude Code로 진행. 각 작업 시작 전에 이 문서 상단의 「공통 주의사항」을
> 세션에 먼저 읽힌다. 근거 문서: `docs/설계 및 구현/중간발표 이후/설계/` (설계 7종 + 이 문서), 기존 시스템
> 사실관계는 `docs/설계 및 구현/중간발표 이전/시스템_전체_설계.md`.
>
> **진행 현황 (8/10 저녁)**: 0단계 푸시·브랜치 동기화 완료. 1단계 Base Code 정리
> 5건 완료. 설계 문서 0·6~10번은 Cowork 설계 세션 산출물. 이 전부를 `june`에
> 커밋해 `main`에 병합했다 — **원격 푸시는 아직**.
> **최대 리스크: Harness 분석 3종이 아직 0건**(`3_Harness_조사/`에 README뿐) — 2단계 전체가 여기 물려 있다.
>
> ---
>
> **⚠ 이 문서는 8/10에서 멈춰 있다 (8/11 확인).** 아래 2·5단계의 체크박스가
> 실제와 다르다. 실제 진행은 **개발 지시서 1~5차의 「실행 결과」 블록**이 정본이다.
>
> - **최대 리스크였던 Harness 분석 3종은 해소됐다** — `3_Harness_조사/`에
>   claw-code·deep-agents·opencode 분석 + 공통구조 비교표까지 들어와 있다.
> - **5단계(개발 착수) 항목은 대부분 끝났다** — Harness 스켈레톤·Chat 스트리밍·
>   Agent CRUD·MCP Client·Pre-built Agent 재연결 전부 구현됐고, 화면도 4·5차에서
>   Chat 중심으로 정리됐다.
> - **남은 것**: 브라우저 QA(`QA_체크리스트_브라우저.md` A·B·C, PM 몫) ·
>   `작업목록.md`(남은 일 정본) · 원격 푸시.

## 공통 주의사항 (Claude Code 세션마다 적용)

- **Django ORM·migrate 안 씀.** `DATABASES = {}`, 데이터 접근은 `backend/db/repositories.py`의 psycopg 직접 SQL. 스키마 변경은 `DB/schema.sql` 수정 + `DB/migrations/*.sql` 멱등 스크립트 + `docs/설계 및 구현/중간발표 이후/개발환경/DB_시작_가이드.md` §4.3에 팀원용 ALTER 기록.
- **`git add .` 금지.** CRLF churn 200+ 파일이 작업 트리에 있다. 반드시 경로 명시 스테이징, diff는 `--ignore-all-space`로 확인. `.gitattributes` 근본 해결은 팀 합의 전 보류.
- **`01_기획` 문자열 치환 금지** — 데모 데이터의 Drive 폴더명(schema.sql·tests·frontend에 등장). docs 폴더와 무관.
- 테스트는 `SimpleTestCase` + mock, DB 안 띄움. 루트에서 `npm install` 금지(→ `frontend/`).
- RunPod Worker는 별도 저장소(`choiwon10/SKN29-RUNPOD-WORKER`)가 실코드 — `runpod_worker/`는 읽기용 사본.

---

## 0. 지금 바로 — 저장소 정리

- [x] `git push origin main` — ✅ 8/10 완료. 원격 main = `3881c76` (12커밋 전부 반영 확인)
- [x] `june`·팀 브랜치 동기화 — ✅ june·jihun·juneok·juyeon 전부 `3881c76`
- [x] **미커밋 전부 커밋 + `june`→`main` 병합** — ✅ 8/10. 설계 문서 신규 6종(0·6·7·8·9·10) + 1단계 코드 변경 + 인벤토리 갱신
- [ ] **`git push origin main`·`june`** — 아직. 위 커밋들이 로컬에만 있다
- [ ] `_to_delete/git-stale-locks/`(765K, 빈 lock 파일)·`sync.bundle`(21M) 삭제 (tar.gz 2개·산출물·이미지는 본인 판단)
- [ ] `wonbin` 브랜치 — `origin/wonbin`=`6370beb`, `origin/main` 대비 앞섬 1 (파싱 발표문서 2개 + png). 원빈님과 병합 시점 협의
- [ ] `fix/login-session-routing`(`41841cc`) — **원격에 없는 로컬 전용 브랜치**. 병합/폐기 결정
- [x] `git fetch --all --prune` — ✅ 8/10 완료. 로컬 `june` 8 behind, `wonbin` 85 behind (원격 기준으로 정리하면 됨)

## 1. 월~화 — Base Code 정리 (IA 처리표 실행)

근거: `docs/설계 및 구현/중간발표 이후/설계/1_서비스구조_IA.md` §2 처리 표. 순수 정리 작업이라 설계 확정
전에 해도 안전한 것만 골랐다.

- [x] **정적 화면 4종 제거** — ✅ 8/10. 라우트·페이지 디렉터리 4개 삭제, 참조 0건, `npm run build` 통과. `frontend/README.md` 화면 표도 갱신
- [x] **라우팅 정본 단일화** — ✅ 8/10. `routes.ts`에 `PATHS` 상수를 두고 `App.tsx`가 참조. 경로 문자열 선언은 이제 한 곳. `/ops` 하위는 절대경로 자식 라우트(react-router v7 허용 — 부모 경로로 시작하면 됨)
- [x] **`/projects`의 「업무 분배 시작」 버튼 경로 확인** — ✅ `ProjectListPage.tsx:149-154` → `/tasks/distribution/documents`. 프로젝트 선택을 다음 화면에 위임하는 구조라 **의존은 이 한 줄뿐**. 제거는 Chat 흡수 후
- [x] **FE 구조 인벤토리** — ✅ `1_서비스구조_IA.md` §5 추가 (pages 24개 → IA 5영역 매핑, 근거 열람 UI 이식 지점 행 번호까지, 공용 컴포넌트 20종)
- [x] **BE 구조 인벤토리** — ✅ `2_아키텍처_초안.md` §2.1 추가. **`analysis_run_service.py`는 12줄 패스스루로 흡수할 로직 없음 → Harness는 신규 작성**. §2 표의 해당 행 정정. 재사용 자산은 NDJSON 이벤트 규약·진행 이벤트 타입·실행 레코드 패턴 3종

### 1단계에서 나온 후속거리 (조치 안 함)

- 페이지가 경로 문자열을 직접 쓰는 곳 **26개 파일 71건** — `PATHS`로 모을 수 있으나 이번 범위 밖
- `frontend/src/pages/ConnectorTestPage/` **빈 디렉터리**
- `apps/integrations`·`apps/recommendations`·`services/readiness`·`services/recommendation` **빈 껍데기** — 분배 관련은 "재판단"이 아니라 "처음부터 만든다"가 맞다
- `frontend/node_modules`가 비어 있었다 → `frontend/`에서 `npm install` 실행함

## 2. 화 — Harness 분석 수합·아키텍처 확정 (지훈·준억·주연 결과 대기)

> **마감 화요일 오전. 8/10 현재 0건 도착** — 오늘 중 리마인드 필요. 마감을 넘기면
> 비교표 없이 아키텍처를 확정하거나, 멘토링 핵심 질문 1번(Harness 구현 방식)을
> 열린 채로 가져가야 한다. 예비 시간은 수요일 낮 하루뿐.

- [ ] 세 분석 문서(`3_Harness_조사/*_분석.md`) 수합 → **공통 구조 비교표** (Loop/Context/Memory/Tool/MCP/Model × 3 repo). ※ Cowork 설계 세션에서 진행 예정
- [ ] 비교표 기반 채택 구조 선정 → `2_아키텍처_초안.md` §3·§6 갱신 → **v2 확정**. 시각화 ⑤(Harness)도 갱신.
- [ ] 신규 스키마 7테이블 컬럼 확정 → `DB/migrations/2026-08-1x_agent_platform.sql` 초안 (적용은 멘토링 후).

## 3. 화~수 — 시각화 (멘토링 필수 산출물 7종)

- [x] Mermaid 초안 7종 — ✅ 8/10 `docs/설계 및 구현/중간발표 이후/설계/6_시각화.md` (화면 구조 / 온보딩·Builder Flow / E2E 시퀀스 / Builder / Harness / Connector·MCP·Memory / 추출 Agent 재배치)
- [ ] 팀 검토 → 수정 반영 (Harness 분석 결과로 ⑤ 갱신 포함)
- [ ] 발표용 Figma 변환 (필요한 것만)

## 4. 수 낮 — 멘토링 준비 (멘토링 18:00)

- [x] **8/12 질문 종합 1장** — ✅ 8/10 `docs/설계 및 구현/중간발표 이후/설계/0_멘토링_질문.md` (14건, 각 질문에 우리 제안 첨부. 핵심 3: Harness 구현 방식 / 분배 STEP 5 제외 / 온디맨드 파싱 제외)
- [x] 설계안 발표 순서 정리 — ✅ 8/12 오전. `0_멘토링_질문.md` 상단 "진행 순서" 블록(7단계, 시간 배분 포함). 질문지는 결정 보고 4·미결 4·평가 3·기타로 재편됨.

## 5. 목~ — 개발 착수 (멘토링 확정 반영 후)

우선순위는 "Harness가 실제로 동작하는 것 > 화면 개수". 평가 설계의 전제
(**agent_run·tool_call 로그 적재를 첫 주에**)를 개발 순서에 반영한다.

- [ ] migrations 적용 + `DB/schema.sql` 갱신 + DB_시작_가이드 §4.3 기록 → 팀 공지 (미적용 팀원은 화면 에러).
- [ ] Harness 스켈레톤: Agent Loop 인터페이스 + Tool Registry + **실행 로그 적재부터** (`services/harness/` 신설 — 신규 작성. 재사용은 NDJSON 규약·이벤트 타입·실행 레코드 패턴 3종, 아키 §2.1).
- [ ] Chat 스트리밍 엔드포인트: 기존 NDJSON 프로토콜 재활용, `chat_session`/`chat_message` 적재.
- [ ] Pre-built Agent 1호: `services/task_extraction`을 Harness 위에서 실행되게 재연결 (Priority 5).
- [ ] Builder CRUD (agent·agent_tool) — 화면은 최소, API 먼저.
- [ ] MCP Client 최소 구현: mcp_server 등록 → tool 목록 조회 → 호출 (Jira 대상, Priority 4).

## 6. 병행 확인 (내 담당 아님 — 상태만 챙김)

- 원빈: 전처리 E2E 안정화 + G-DOC·G-QUERY 골든셋 (평가 설계 §7). ※ `6370beb`는 파싱 발표자료 문서(paser.01/02 + 파이프라인 png) — 골든셋 아님, 별도 확인 필요
- 지훈·준억·주연: 분석 화요일 공유 (`3_Harness_조사/README.md` 마감)
- 팀 회의 1회: G-TASK 골든셋 합의 (개발 1주차)
