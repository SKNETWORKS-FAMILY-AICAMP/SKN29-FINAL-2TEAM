# 서비스 구조 (IA) — 초안 v1

> 2026-08-10 작성. 08/12 온라인 멘토링 리뷰 대상.
> 근거: `../회의록/2026-08-08_오프라인_멘토링.md` §13, 기존 화면 목록은
> `../AS-IS/시스템_전체_설계.md` §7과 `frontend/src/App.tsx`(라우팅 정본)에서 확인.

## 0. 설계 원칙

1. **홈은 Chat이다.** 기존에는 로그인 후 대시보드가 홈이었다. 새 구조에서 사용자가
   가장 먼저 만나는 화면은 Chat이고, 대시보드는 "Agent에게 요청하면 만들어 주는
   결과물"로 강등된다.
2. **타겟은 비개발자 실무자.** 화면 어디에도 Tool Calling·MCP·Agent Graph 같은
   개념을 그대로 노출하지 않는다. 사용자가 정하는 것은 "무슨 일을 하는
   에이전트인지 / 어떤 데이터를 참고할지 / 어떤 도구를 쓸지" 세 가지뿐이다.
3. **Platform과 Use Case를 화면에서도 구분한다.** 업무 추출·분배는 별도 메뉴가
   아니라 "기본 제공 Agent"로 Chat과 Builder 안에 나타난다.
4. **기존 화면은 폐기가 아니라 재배치.** 아래 §2의 처리 표가 전부다. 제거되는
   것은 로직 없는 정적 화면 4종뿐이다.

## 1. 새 IA — 5개 영역

```
[Chat]  ──────────── 핵심. Agent 선택 → 요청 → Tool 실행·근거 확인 → 결과
[Agent Builder] ──── Agent 목록 + 생성/편집 (Profile·Instruction·Model·Tool/MCP)
[Project] ────────── 프로젝트 단위 Context (문서·Jira 연결·추출 이력)
[Settings] ───────── 팀 · Connector · MCP · Model · Permission
[Admin(Ops)] ─────── 기존 운영자 콘솔 확장 (실행 현황·사용량은 여력 시)
```

### 화면 목록 초안

| 영역 | 화면 | 신규/기존 | 우선순위 |
|---|---|---|---|
| Chat | 대화 화면 (Agent 선택기, 스트리밍 응답, Tool 실행 표시, 근거 열람) | **신규** | P0 |
| Chat | 결과 확인 스텝 (Jira 등록 전 사용자 확인 — E2E STEP 6) | **신규** (extraction 화면 재활용) | P0 |
| Builder | Agent 목록 (기본 제공 + 팀 생성) | **신규** | P0 |
| Builder | Agent 생성/편집 — 이름·Description·Instruction·Model·Tool/MCP 선택 | **신규** | P0 |
| Project | 프로젝트 목록 / 상세 | 기존 유지·축소 | P1 |
| Project | 문서 관리 (등록→임베딩, 삭제 파일 정리) | 기존 유지 | P1 |
| Settings | Connector (Drive·Jira·HR) | 기존 재배치 | P1 |
| Settings | MCP Server 등록 | **신규** | P0 |
| Settings | Model 관리 (사용 가능 모델 목록·기본값) | **신규** | P2 |
| Settings | 팀·권한 | 기존 확장 | P1 |
| Admin | 운영자 콘솔 8종 | 기존 유지 | P2 |
| Admin | Agent 실행 현황·Token 사용량 | **신규** | 여력 |

P0 = E2E 데모에 필수. P1 = 데모 품질. P2 = 구조만 잡고 최소 구현.

## 2. 기존 화면 처리 표 (App.tsx 전체 라우트 기준)

| 기존 경로 | 처리 | 근거 |
|---|---|---|
| `/login` `/signup` `/invite-code` `/find-password` `/reset-password` | **유지** | 인증·초대는 방향과 무관 |
| `/onboarding/connectors` | **유지·확장** | 커넥터 연결은 그대로 필요. MCP 등록 진입점 추가 |
| `/onboarding/folders` | **유지** | Data Layer 입구. Settings > Connector에서도 접근 |
| `/onboarding/jira-project` | **재검토** | Jira가 Connector(부하 읽기)와 MCP(이슈 생성) 이중 역할이 됨. 온보딩 필수 단계에서 선택 단계로 |
| `/dashboard` | **재정의** | 홈 자리를 Chat에 내준다. 부하 계산 로직은 "부하 리포트 생성" Pre-built Tool로 재활용 (멘토링 §14) |
| `/files/new` (문서 관리) | **유지** | 등록→임베딩 흐름은 Data Layer 운영 화면으로 그대로. Project 영역 하위로 이동 |
| `/projects` | **유지·축소** | "업무 분배 시작" 버튼 제거. 추출은 Chat에서 Agent 호출로 |
| `/projects/:projectId` | **유지** | Jira 갱신·완료·삭제 그대로 |
| `/tasks/distribution/documents` | **흡수** | 기준 문서 1건 선택 UI는 Chat에서 Task Extraction Agent 실행 시의 입력 스텝으로 |
| `/tasks/extraction` | **흡수·재활용** | 중간발표 완료 지점. 근거 열람 UI를 Chat의 결과 확인 스텝으로 이식. E2E의 STEP 6(사용자 확인)이 이 화면의 후신 |
| ~~`/workspace`~~ | **제거 완료 (8/10)** | 정적, 로직 없음 |
| ~~`/tasks/distribution`~~ | **제거 완료 (8/10)** | 정적. 분배는 Pre-built Agent로 |
| ~~`/tasks/recommendation`~~ | **제거 완료 (8/10)** | 정적 |
| ~~`/tasks/result`~~ | **제거 완료 (8/10)** | 정적 |
| `/settings/team` | **확장** | Settings 허브로 승격: 팀·Connector·MCP·Model·Permission 탭 |
| `/ops/login` `/ops` (8종) | **유지** | Admin의 뼈대. Observability 항목은 여력 시 추가 |
| `/screens` `/dev/screens` | **유지** | 개발용 |

요약: 제거 4(전부 정적) · 흡수 2 · 재정의 1 · 재검토 1 · 나머지 유지/확장.

## 3. 사용자 흐름

### 흐름 A — 온보딩 (팀장)

가입 → 팀 생성 → Connector 연결(Drive 필수, Jira·HR 선택) → 폴더 선택 →
**Chat 진입** (기본 제공 Agent가 이미 보인다). 기존과 차이: Jira 프로젝트 선택이
필수 스텝에서 빠지고, 끝이 대시보드가 아니라 Chat이다.

### 흐름 B — 대표 E2E (실무자) = `5_E2E_시나리오.md`

Chat에서 Agent 선택 → "프로젝트 문서 참고해서 업무 정리하고 Jira에 등록해줘" →
문서 검색·추출 진행 표시(기존 NDJSON 스트리밍 재활용) → 결과 확인 스텝(근거
열람) → 승인 → Jira MCP Tool 실행 → 완료·근거 반환.

### 흐름 C — Agent 만들기 (팀장 또는 실무자)

Builder → 새 Agent → 이름·설명·지시문 작성 → Model 선택 → Tool/MCP 체크 →
저장 → Chat의 Agent 선택기에 즉시 노출. 별도 테스트 화면 없이 Chat에서 바로
써 본다(멘토링 §5).

## 4. 미결정 — 8/12에 확인할 것

1. Chat과 Project의 관계 — 대화가 프로젝트에 귀속되는가(프로젝트별 Chat), 팀
   레벨 Chat에서 프로젝트를 컨텍스트로 선택하는가. 검색 경계=팀 결정(AS-IS §6)과
   맞물린다.
2. `/onboarding/jira-project`의 최종 위치 — Connector 설정인가 Project 생성
   플로우인가.
3. Agent 편집 권한 — 팀 전체 공유인가, 만든 사람만 수정인가 (Permission 설계와
   함께).
4. 기존 대시보드 화면을 데모 자산으로 남길 것인가(리포트 생성 결과의 뷰어로
   재활용) 완전히 내릴 것인가.

## 5. FE 자산 인벤토리 — 무엇을 다시 쓰는가

> 2026-08-10 실측. 정적 4종 제거 후 `frontend/src/pages/` 24개 디렉터리 기준.
> 줄 수는 해당 디렉터리 `.tsx` 합계 — "새로 짜지 않아도 되는 양"의 근거다.

### 5.1 pages/ → IA 5영역 매핑

| 페이지 (줄) | IA 영역 | 처리 | 재사용 포인트 |
|---|---|---|---|
| `TaskExtractionPage` (297) | **Chat** | 흡수 | ★ **근거 열람 UI** — §5.2 참조. 최우선 이식 대상 |
| `PrimaryDocumentSelectPage` (304) | **Chat** | 흡수 | 기준 문서 1건 선택 → Agent 실행 입력 스텝 |
| `ProjectListPage` (342) | Project | 유지·축소 | 「업무 분배 시작」만 제거 (`ProjectListPage.tsx:149`) |
| `ProjectDetailPage` (394) | Project | 유지 | Jira 갱신·완료·삭제 |
| `NewFilesPage` (911) | Project | 유지 | 등록→임베딩 진행 표시. Data Layer 운영 화면 |
| `MainDashboardPage` (1090, 패널 8종) | — | 재정의 | 패널 단위로 분해해 "리포트 생성" Agent 결과 뷰어로 (미결정 §4-4) |
| `ConnectorOnboardingPage` (683) | Settings | 재배치 | Connector 연결 UI 그대로 + MCP 등록 진입점 추가 |
| `FolderSelectPage` (533) | Settings | 유지 | 폴더 트리 선택 |
| `JiraProjectSelectPage` (256) | Settings | 재검토 | 온보딩 필수 → 선택 단계 (미결정 §4-2) |
| `SettingsPage` (46) + `TeamLeaderSettingsPage` (556) + `TeamMemberSettingsPage` (204) | Settings | 확장 | `SettingsPage`는 역할 분기 래퍼(sessionStorage, DEV 전용 전환 버튼). Settings 허브 승격 시 탭 컨테이너로 |
| `Ops*Page` 8종 (2,809) | Admin | 유지 | 실행 현황·사용량 탭만 추가 |
| `LandingPage` (348) · 인증 5종 (792) | IA 외 | 유지 | 방향과 무관 |

**Builder 영역에 재사용할 기존 페이지는 없다** — Agent 목록·생성/편집은 전부 신규.
단 아래 공용 컴포넌트로 껍데기는 거의 채워진다.

### 5.2 이식 1순위 — 근거 열람 UI

`TaskExtractionPage.tsx`의 `TaskCard`(63–152행)가 E2E STEP 6(사용자 확인)의 원형이다.
Chat 결과 스텝으로 옮길 때 그대로 가져갈 것:

- **근거 토글** (121–149행) — 「원문 근거 N건」 접기/펴기. `blockquote`에 원문 +
  `doc_id · intent · 유사도 % · 「어떤 질의로 찾음」`
- **`missing_fields` 표기** (115–119행) — 빈 항목을 숨기지 않고 「근거 없어 비움」으로
  명시. *근거가 없어 안 채운 것*과 *모델이 놓친 것*을 사람이 구분하게 하는 장치
- **검색 단계 trace** (263–279행) — intent별 히트 수 + 모델·reasoning effort 표시
- `INTENT_LABEL`·`FIELD_LABEL` 매핑(8–27행) — 내부 enum → 실무자 언어

제약도 같이 넘어온다: 현재 결과를 **router state로만** 받아 새로고침하면 사라진다
(서버가 추출 결과를 저장하지 않음, 154–166행 주석). Chat으로 옮기면 `chat_message`
적재가 이 문제를 자동으로 해결한다 — 이식의 부수 효과가 아니라 이유 중 하나다.

### 5.3 공용 컴포넌트 20종 (`components/`)

`AvatarPicker` `Badge` `Button` `Card` `Checkbox` `Icon` `Input` `Modal` `Select`
`SkillList` `StepIndicator` `Toast` `ToggleSwitch` `TopNav` `PasswordChangeCard`
`OpsLayout` `OpsRouteGuard` `OpsUi` `RequireAuth` `SettingsLayout`

Chat·Builder 신규 화면은 이 위에 얹는다. 특히 `StepIndicator`(Agent 실행 단계
표시), `Modal`(Tool 승인), `Badge`(Tool 상태)는 바로 쓸 수 있다.
스타일은 Tailwind 없이 CSS Modules + `tokens.css` 변수만 — 신규 화면도 같은 규칙.

### 5.4 정리하면서 확인된 것 (조치 안 함)

- `pages/ConnectorTestPage/` — **빈 디렉터리**. 라우트·참조 0건
- 페이지가 경로 문자열을 직접 쓰는 곳 **26개 파일 71건**. `routes.ts`의 `PATHS`로
  모으면 좋지만 이번 정리 범위(화면 목록 정본 단일화) 밖이라 두었다
- `frontend/node_modules`가 비어 있었다 — 빌드 검증 전 `frontend/`에서 `npm install` 필요
