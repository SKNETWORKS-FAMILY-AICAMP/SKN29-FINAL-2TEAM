# 개발 지시서 6차 — UI/UX 주제 정합성 개선

> 출처: Cowork 코드 실사(8/11 오후, HEAD `7ad5b5f` 기준). 5차가 "AS-IS처럼
> 보인다"는 겉면을 고쳤다면, 6차는 **"비개발자가 AI Agent를 직접 만들고
> 활용하는 Platform"이라는 주제를 화면이 못 받치는 지점**을 고친다.
> **순서 = 주제 방어력 순.** 단계마다 브라우저 확인 의무, 단계당 1커밋 이상,
> `git add .` 금지.
>
> **먼저 읽을 것 — 이 문서의 1·2·3단계는 백엔드 변경이 거의 없다.**
> 필요한 데이터·API가 이미 있는데 화면이 안 쓰고 있는 경우가 대부분이다.
> 각 단계의 「이미 있는 것」 블록을 확인하고 시작하라.

---

## 단계 1 — Chat을 대화로 만든다 (최우선 · 프론트 전용)

**원인 1**: `ChatPage.tsx`의 사용자 발화가 `const [sent, setSent] = useState<string | null>(null)`
— **단일 문자열**이다. 응답도 `live: LiveChat | null` 하나뿐. 두 번째 발화를
보내면 `setSent(text)`가 덮어써서 **첫 턴이 화면에서 사라진다.** 홈 화면
이름이 Chat인데 실제 동작은 요청-응답 1회용 실행기다. QA 1차의
"못써먹을 정도" 판정에서 5차에 적힌 4건보다 이쪽 기여가 클 가능성이 높다.

**원인 2**: `openSession()`이 `[...detail.messages].reverse().find(role === 'agent')`
— 저장된 메시지 중 **마지막 에이전트 답 하나만** 복원한다. 나머지는 서버가
갖고 있는데 화면이 버린다.

**원인 3**: 입력창이 `disabled={waitingConfirm || streaming || !agentId}`.
승인 대기 중에는 아무 말도 못 한다 — "3번은 빼고 다시 뽑아줘"가 불가능하고
체크박스로만 소통해야 한다. Agent Platform이 아니라 폼 위저드다.

**이미 있는 것 (백엔드 변경 불필요)**
- `getSession()` → `ChatSessionDetail.messages: ChatMessage[]` — **전체 턴**을
  이미 반환한다(`api/chat.ts`). `content.events`에 카드 재현용 이벤트가 턴마다 들어 있다.
- `ChatMessageRepository.list_for_session`(`backend/db/agent_platform.py:268`)이
  그 원본. 서버는 이미 다 저장하고 있다.

**작업**
1. `ChatPage`의 상태를 **턴 배열**로 바꾼다.
   - `sent: string | null` → `turns: Turn[]` (`{ user: string; live: LiveChat | null }`).
   - 새 발화는 `setTurns(prev => [...prev, { user: text, live: null }])`로 **덧붙인다**.
   - 스트림 중 `reduce` 결과는 **마지막 턴의 `live`만** 갱신한다.
     (`setTurns(prev => prev.map((t, i) => i === prev.length - 1 ? { ...t, live: next } : t))`)
2. `openSession()`을 전체 복원으로 바꾼다.
   - `detail.messages`를 순서대로 훑으며 `role === 'user'`에서 턴을 열고,
     이어지는 `role === 'agent'`의 `content.events`를
     `events.reduce(reduce, { ...emptyLive(), running: false })`로 접어 그 턴에 붙인다.
   - `selected`는 **마지막 턴에만** 적용한다(과거 턴의 확인 카드는 읽기 전용).
3. 과거 턴의 `ConfirmCard`는 `onApprove`를 넘기지 않아 **버튼이 비활성**이 되게 한다.
   (이미 `onApprove?: () => void` optional — 안 넘기면 된다. 승인은 마지막 턴만.)
4. 스크롤. `.stream`에 `ref`를 달고 턴이 늘거나 `live`가 갱신될 때 하단 고정
   (`scrollTop = scrollHeight`). 사용자가 위로 스크롤한 상태면 따라가지 않는다.
5. 승인 대기 중 입력창을 **연다** — `disabled={streaming || !agentId}`로 줄인다.
   - ⚠ **선행 확인**: 서버에 pending confirmation이 남은 채로
     `POST /chat/sessions/<id>/messages/`를 보내면 어떻게 되는지 확인하라
     (`ChatMessageRepository.latest_pending_confirmation`,
     `backend/db/agent_platform.py:313`). 다음 중 하나로 처리한다.
     - (a) 서버가 pending을 무시하고 새 턴을 시작한다면 → 화면에서 그대로 보내되,
       직전 턴의 확인 카드에 「승인하지 않고 넘어감」 표시를 남긴다.
     - (b) 서버가 거부한다면 → 발화 전에 `confirmMessage(token, id, [])`(0건 승인)로
       pending을 닫고 보낸다. **0건 승인이 실제로 아무것도 만들지 않는지 반드시 실호출로 확인**
       (`selected === undefined`가 전체 승인이므로 `[]`와 혼동 금지 — `api/chat.ts` 주석).
     - 어느 쪽이든 결과 블록에 무엇이었는지 적는다.

**브라우저 확인**: ① 한 대화에서 발화 3번 → 3턴이 모두 화면에 남는다.
② 새로고침 → 3턴이 그대로 복원된다. ③ 확인 카드가 뜬 상태에서 입력창에
타이핑·전송이 된다. ④ 과거 턴의 「Jira에 등록」 버튼은 눌리지 않는다.

---

## 단계 2 — Builder에 반복 루프를 만든다 (프론트 전용)

**원인**: "비개발자가 코딩 없이 만든다"가 제품의 한 줄 정의인데, 그 주장을
받치는 화면이 가장 얇다.

1. **복제 버튼이 없다.** `AgentListPage.tsx` 주석대로 v1 고정(Q12)으로 뺐다.
   결과: 비개발자가 시작할 수 있는 유일한 지점이 **빈 폼**이다. 실제로는
   "기본 제공을 조금 고쳐 쓰기"가 압도적 다수 경로다.
2. **테스트가 없다.** 저장 버튼 문구 "저장하고 Chat에서 써보기"는 테스트 부재를
   카피로 덮은 것. 지시문이 안 먹히면 Chat → 에이전트 → 편집 → Chat 왕복
   4클릭이다. 프롬프트는 한 번에 되는 물건이 아닌데 반복 루프가 가장 비싸다.
3. **지시문 지원이 placeholder 한 줄뿐.** 비개발자가 제일 못 하는 게 이건데
   예시도 템플릿도 없다.
4. **어휘가 개발자 것이다.** `reasoning_effort`를 "응답 방식 · 낮음(low)"으로
   노출하는데 비개발자에게 의미가 없고, `maxIterations`는
   **state만 있고 입력 UI가 없다**(`AgentEditPage.tsx` — `useState(6)` 후 body에만 실림).
   어려운 건 보여주고 조절은 안 되는 반쪽.

**이미 있는 것 (백엔드 변경 불필요)**
- `createAgent(token, body)` / `getAgent(token, id)` 모두 존재(`api/agents.ts`).
  **복제 = 기존 값을 프리필해 create 하는 것**이라 서버는 손댈 게 없다.
- prebuilt 편집 차단은 서버 403이고 화면도 이미 안내한다 — 복제는 그 제약을
  우회하는 게 아니라 **정상 경로**다(새 에이전트를 만드는 것).

**작업**
1. **복제**. `AgentListPage` 기본 제공 카드에 「복제해서 편집」 버튼 추가
   (기존 주석의 "복제 버튼은 넣지 않는다"는 이 지시서로 대체 — 근거는 Q12 재상정, 아래 §Q1).
   - `navigate(PATHS.agentNew + '?from=' + agent.agent_id)`.
   - `AgentEditPage`에서 `useSearchParams()`로 `from`을 읽어 `getAgent`로 프리필.
     `name`은 `` `${원본이름} (복사본)` ``, `is_prebuilt` 경고는 띄우지 않는다
     (새로 만드는 것이므로 403 대상이 아니다).
   - 팀 에이전트 카드에도 같은 버튼을 단다.
2. **왕복 1클릭**. 저장 후 목적지에 복귀 경로를 심는다.
   - `handleSave` 성공 시 `navigate(PATHS.chat + '?agent=' + saved.agent_id + '&back=' + saved.agent_id)`.
   - `ChatPage`에서 `agent` 쿼리가 있으면 `agentId` 초기값으로 쓰고,
     `back`이 있으면 `.agentBar`에 「편집으로 돌아가기」 버튼을 띄운다
     (`navigate(PATHS.agentEdit.replace(':agentId', back))`).
   - 이것으로 편집 → 시험 → 편집이 각 1클릭이 된다. 별도 시험 실행 화면은
     만들지 않는다(세션이 지저분해지고 범위가 커진다).
3. **지시문 지원**. 「행동 지시」 카드에 프리셋 칩 3개를 둔다 — 누르면 textarea에
   본문을 넣는다(덮어쓰기 전 내용이 있으면 확인).
   - 「회의록 정리」 / 「업무 추출」 / 「자료 조사·요약」 — 문안은 시드 에이전트
     (`seed_agents.py`)의 instruction에서 가져와 재사용한다. **새로 지어내지 말 것**
     — 실제로 도는 문장이어야 예시로서 값이 있다.
   - textarea 아래에 글자 수와 한 줄 안내: "무엇을 / 어떤 순서로 / 모르면 어떻게 할지
     — 세 가지가 들어가면 충분합니다."
4. **어휘·유령 상태 정리**.
   - `EFFORT_OPTIONS` 라벨에서 영문 코드를 뺀다: `낮음 (빠름)` / `보통` / `높음 (느림)` /
     `아주 높음 (가장 느림)`. value는 그대로.
   - `MODEL_OPTIONS`도 같은 원칙 — 모델 ID는 부제로 내리고 제목은 용도로.
   - `maxIterations`: **입력 UI를 만들거나 상태를 지운다.** 권장은 지우고
     서버 기본값을 쓰는 것 — 비개발자가 정할 값이 아니다. 서버가 필수로 받으면
     상수 `DEFAULT_MAX_ITERATIONS = 6`으로 이름을 주고 주석에 "화면에서 정하지 않는다"를 남긴다.
5. **Builder 진입 유도**. `ChatPage` 빈 화면의 starter 목록 **맨 끝**에
   「+ 새 에이전트 만들기」 타일을 추가한다(`navigate(PATHS.agentNew)`).
   - 현재는 `agents.length === 0`일 때만 배너가 뜬다 — 기본 제공이 하나라도 있으면
     플랫폼의 핵심 행동으로 가는 길이 홈에서 사라진다.

**브라우저 확인**: ① 기본 제공 카드 「복제해서 편집」 → 값이 채워진 편집 화면 →
저장 → Chat에서 그 에이전트가 선택된 상태 → 「편집으로 돌아가기」로 복귀.
② 프리셋 칩 3개가 각각 textarea를 채운다. ③ Chat 빈 화면에 만들기 타일이 보인다.

---

## 단계 3 — Observability 최소판 (백엔드 조회 함수 + API 1개 + 패널 1개)

**원인**: 멘토링 우선순위 2번(Harness — Observability)과 6번(평가 설계,
중간발표 최대 약점)이 **화면에 한 조각도 없다.** `AgentListPage` 카드에
사용 횟수·최근 실행·실패가 없어서 비개발자가 자기 에이전트를 개선할 근거를
화면에서 얻지 못한다. `OpsAuditPage`(674줄)에 로그가 있지만 **별도 로그인의
운영자 콘솔**이라 만든 사람은 못 본다.

**이미 있는 것 (여기가 핵심 — 새로 만들 게 거의 없다)**
- `agent_run` 테이블: `run_id · session_id · agent_id · parent_run_id · status
  (RUNNING/DONE/FAILED/CANCELLED) · iterations · token_in · token_out ·
  started_at · ended_at` — `DB/schema.sql:850`.
- `tool_call` 테이블: `run_id · tool_ref · input_summary · status(PENDING/OK/FAILED) ·
  error_code · duration_ms · created_at` — **선기록 패턴**이라 죽은 호출도 남는다.
- 인덱스 `ix_agent_run_session`, `ix_tool_call_run` 존재.
- 쓰기는 이미 돌고 있다: `AgentRunRepository.start/finish`(`:91`, `:105`),
  `ToolCallRepository.begin/end`(`:134`, `:148`).
- **없는 것은 조회 함수뿐이다.**

**작업**
1. `backend/db/agent_platform.py`의 `AgentRunRepository`에 조회 두 개 추가.
   - `list_recent(*, agent_id: str, account_id: str, limit: int = 10)` —
     해당 팀 소유 에이전트인지 확인 후 `agent_run`을 `started_at DESC`로 limit개.
     각 행에 그 run의 `tool_call` 요약(`OK`/`FAILED` 건수, 실패 시 `error_code` 목록)을 붙인다.
   - `summary(*, agent_id: str, account_id: str)` — 총 실행 수, 성공률,
     최근 7일 실행 수, 평균 소요(`ended_at - started_at`).
   - ⚠ FK가 없는 테이블이다. **팀 소유 검증을 SQL에서 직접 해야 한다** —
     `AgentCrudRepository.get(agent_id=, account_id=)`(`:579`)과 같은 방식으로 막을 것.
     남의 팀 `agent_id`를 넣으면 빈 결과가 나와야 한다.
2. API 1개 신설. `apps/agents/api_urls.py`에
   `path("<str:agent_id>/runs/", AgentRunListAPIView.as_view(), name="api_agent_runs")`.
   - ⚠ **`tools/` 라우트보다 뒤, `<str:agent_id>/`보다 앞**에 둘 것 — 기존 주석과 같은 이유.
   - 응답: `{ summary: {...}, runs: [{ run_id, status, iterations, started_at,
     duration_ms, tool_calls: [{ tool_ref, status, error_code, duration_ms }] }] }`.
   - `input_summary`는 내보내지 않는다(자격증명 회피가 설계 의도다 — 스키마 주석).
3. 프론트.
   - `api/agents.ts`에 `listAgentRuns(token, agentId)` 추가.
   - `AgentEditPage` 맨 아래에 **「최근 실행」 카드**: 최근 5건을 표로
     (시각 · 상태 배지 · 회전 수 · 도구별 OK/실패 · 소요). 실패 행은 `error_code`를 그대로 보인다.
     - 데이터가 0건이면 "아직 실행 기록이 없습니다"만 — **가짜 행을 만들지 않는다**
       (`ChatCards.tsx`의 mock 금지 원칙과 같다).
   - `AgentListPage` 카드 하단 메타에 한 줄 추가: `실행 12회 · 성공 10 · 최근 8/11`.
     `summary`가 없으면 그 줄을 아예 안 그린다.
4. **문구 하나를 반드시 넣는다.** 최근 실행 카드 아래:
   "실패한 실행의 사유를 보고 지시문이나 도구 구성을 고치세요." — 관측이
   장식이 아니라 **개선 루프의 입력**이라는 게 발표에서 말할 지점이다.

**브라우저 확인**: Chat에서 에이전트를 2~3회 돌린 뒤(하나는 일부러 실패시켜서)
편집 화면 하단에 그 실행들이 뜨고, 실패 행에 `error_code`가 보인다.
다른 팀 계정으로 같은 `agent_id`를 호출하면 빈 결과.

---

## 단계 4 — 정직 표기 원칙을 화면 전체에 맞춘다 (데모 사고 방지 · 각 30분 이하)

**원인**: `ChatCards.tsx`는 "mock을 없앴다 — 카드가 기본값을 들고 있으면 연동
안 된 것과 데이터 없는 것을 구별 못 한다"고 주석까지 달며 엄격한데, 다른 화면은
정반대다. **같은 제품 안에서 원칙이 화면마다 다르다.** 데모 중 클릭 두 번이면 드러난다.

1. **`ModelTab.tsx`** — `MODELS` 배열이 상수다. "평균 응답 2.4초/19.3초",
   "쿼터 제한" 전부 하드코딩. `defaultModel`은 `useState`만 하고 **아무 데도 저장하지 않는다**.
   - 조치: 실 API가 없으므로 **저장되는 척을 없앤다.** 라디오를 지우고 읽기 전용 표로 바꾼 뒤,
     상단에 `noticeNeutral`로 "지금은 에이전트를 만들 때 모델을 고릅니다. 팀 기본값 지정은
     아직 제공하지 않습니다." 한 줄. 지연 수치는 근거가 있으면 출처를 적고,
     없으면 열을 지운다. **꾸미지 말 것.**
2. **`PermissionsTab.tsx`** — 토글 하나 없는 정적 표.
   - 조치: 표는 유지하되 카드 제목 아래에 "현재 적용 중인 고정 정책입니다 — 화면에서
     바꿀 수 없습니다."를 명시. 기존 `noticeWarning`(에이전트 소유·가시성 미정)은 그대로 둔다
     — 그건 정직한 표기다.
3. **`/screens` 개발용 인덱스** — `routes.ts`의 `ROUTES`에
   "대시보드 (구 · 처분 대기)", "문서 관리 (구)" 라벨이 그대로 있고 라우트가 살아 있다.
   데모 중 누가 열면 미완성 화면이 목록으로 보인다.
   - 조치: `App.tsx`에서 `/screens`·`/dev/screens`를 `import.meta.env.DEV`일 때만 등록한다.
     `ROUTES` 상수와 페이지는 그대로 둔다(개발 중 유용하다). **프로덕션 빌드에서만 사라진다.**
   - 확인: `npm run build && npm run preview` 후 `/screens`가 랜딩으로 떨어지는지.
4. **죽은 알림 벨** — `AppShell.tsx`의 bell 버튼에 `onClick`이 없다.
   "몇 분 걸립니다 · 창을 닫지 않아도 됩니다"라고 안내하는 장시간 작업 제품에서
   알림은 장식이 아니다.
   - 조치(택1, **권장은 (a)**):
     (a) **버튼을 지운다.** 없는 기능을 아이콘으로 약속하지 않는다. 가장 싸고 정직하다.
     (b) 남긴다면 최소 기능을 붙인다 — 스트림이 끝났는데 탭이 백그라운드면
     `document.title`을 「✓ 완료 — halil」로 바꾸고 포커스 시 되돌린다. 벨은 그 토글.

**브라우저 확인**: 프로덕션 빌드에서 `/screens` 접근 불가. 설정 4개 탭을 순회해
"저장되는 척하는 컨트롤"이 하나도 없다.

---

## 단계 5 — Chat 에이전트 선택기 톤 통일 (1커밋짜리)

**원인**: 5차 단계 2가 절반만 됐다. `AppShell`의 프로젝트 선택기는 공용 `Select`로
바뀌었는데(`aebf3e8`), **`ChatPage.tsx`의 에이전트 선택기는 아직 raw `<select
className={styles.agentPicker}>`다.** 하필 가장 자주 보는 화면에 톤 불일치가 남았다.

- 공용 `Select`(`components/Select`)로 교체. `disabled`·`aria-label` 유지.
- 옵션 라벨의 `' (기본 제공)'` 접미사는 유지 — 출처 구분은 정보다.
- 브라우저 확인: 열림 상태 포함, 상단바 선택기와 같은 톤인지 나란히 비교.

---

## 단계 6 — 연결 IA를 사용자 언어로 (⚠ 범위 큼 — 시간 부족 시 6-1만)

**원인 1**: `McpTab`의 안내문이 "읽기만 하는 연결(Drive·HR)은 Connector 탭에,
실제로 무언가를 만드는 연결은 여기에"인데 — **대표 시나리오인 Jira가 이 분류의
반례다.** 수집도 하고 등록도 한다. 비개발자는 "Jira 연결"을 찾으러 탭 두 개를 왕복한다.
Connector/MCP는 **우리 아키텍처 구분**이지 사용자 멘탈모델이 아니다.

**원인 2**: MCP 등록 폼이 "서버 주소(https) + 인증 토큰" raw 입력이다.
비개발자 플랫폼을 표방하면서 여기만 개발자 콘솔이고, 카탈로그·프리셋이 없다.

**원인 3**: `routes.ts` 주석은 "문서는 팀 소속이라 프로젝트로 좁히지 않는다"인데,
사이드바에 '문서' 항목이 없고 `PATHS.documents`가 **프로젝트 메뉴의 `match` 배열**에
얹혀 있다(`APP_NAV_ITEMS`). 팀 소속 리소스가 프로젝트 하위처럼 활성화된다.

**작업**
1. **(6-1 · 최소, 이것만이라도)** 두 탭을 **하나의 「연결」 탭**으로 합치지 말고,
   각 탭 상단 안내문을 사용자 언어로 다시 쓴다.
   - Connector 탭: "**우리 문서와 데이터를 가져오는 곳**입니다. 여기서 연결한 데이터가
     에이전트의 답변 근거가 됩니다."
   - MCP 탭: "**에이전트가 바깥에 무언가를 만들 수 있게 하는 곳**입니다.
     Jira 이슈 등록처럼 결과가 남는 일은 여기서 연결합니다."
   - 각 탭 하단에 상호 링크 한 줄: "Jira처럼 **가져오기와 등록을 둘 다** 하는 서비스는
     양쪽에 연결이 필요합니다 → [Connector 탭]".
     **이 문장이 핵심이다** — 사용자가 왕복해야 한다는 사실을 숨기지 말고 안내한다.
2. **(6-2)** MCP 등록 폼 위에 프리셋 칩을 둔다 — 「Jira」 「DeepWiki」.
   누르면 `name`과 `endpoint_url`이 채워지고 토큰만 받는다.
   - DeepWiki 주소는 QA에서 쓰는 `https://mcp.deepwiki.com/mcp`(current_status 참조).
   - 프리셋은 **화면 상수**로 두되 주석에 "카탈로그 API가 생기면 옮긴다"를 남긴다.
3. **(6-3)** 문서의 자리를 바로잡는다.
   - `APP_NAV_ITEMS`에서 `PATHS.documents`를 프로젝트의 `match`에서 빼고
     **독립 항목 「문서」**(icon: `folder` 아님 — `file-text` 계열)로 추가, 위치는 프로젝트 아래.
   - 사이드바 5항목이 부담이면 프로젝트 항목의 라벨을 「프로젝트 · 문서」로 바꾸는 대신
     **DocumentsPage 안에 프로젝트 필터**를 두는 방향도 가능 — 어느 쪽이든
     "문서는 팀 소속"이라는 주석과 화면이 어긋나지 않게 할 것.

**브라우저 확인**: 설정 두 탭의 안내문이 서로를 가리키고, Jira 프리셋으로
등록 → 연결 확인이 통과한다. 사이드바에서 문서 진입 시 프로젝트 항목이
활성화되지 않는다.

---

## 멘토링에서 결정받을 것 (8/12 18:00 · 0_멘토링_질문에 합류)

**Q1 — 기본 제공 에이전트 복제를 허용하는가.**
현재 v1은 복제 없음(Q12 연장). 그 결과 비개발자의 유일한 시작점이 빈 폼이고,
"코딩 없이 만든다"는 주장의 근거가 가장 얇아진다. 단계 2는 **허용을 전제로**
작성했다. 반려되면 단계 2-1만 빼고 나머지(왕복·프리셋·어휘)는 그대로 유효하다.

**Q2 — 대화 중 에이전트 교체를 계속 막는가.**
`ChatPage`의 `disabled={Boolean(sessionId)}`. 이유(앞선 턴이 다른 스캐폴드로
만들어지면 근거가 흔들린다)는 타당하지만, 결과적으로 **화면이 "대화당 에이전트 1개
고정"을 못 박는다** — 멘토링에서 말한 Agent-to-Agent 여지와 정반대다.
발표에서 확장성을 말할 때 화면이 반증이 된다. 선택지:
(a) 유지하고 발표에서 "v1 의도적 제약"으로 명시 / (b) 교체 시 새 대화를 자동 분기 /
(c) 한 대화 안에서 턴별 에이전트를 허용하고 턴에 에이전트 이름을 표시.

**Q3 — 평가 지표를 제품 화면에 노출하는가, 발표 자료로만 두는가.**
골든셋·`coarse_recall`(0.291 > 0.150 > 0.108) 수치는 있는데 화면에는 없다.
단계 3의 실행 기록이 "제품 안의 검증 근거"로 쓸 수 있는 유일한 자리다.
여기에 품질 지표까지 얹을지, 4_평가_설계는 문서로만 갈지 확정 필요.

**Q4 — 알림(단계 4-4).** 지울지 최소 기능을 붙일지. 장시간 작업이 제품의
기본 동작이라 "나중에"가 계속 미뤄져 왔다.

---

## 착수 순서와 예상 소요

| 순 | 단계 | 범위 | 예상 | 비고 |
|---|---|---|---|---|
| 1 | 단계 1 | FE only | 3~4h | 주제 방어 직결. **가장 먼저** |
| 2 | 단계 4 | FE only | 1~1.5h | 데모 사고 확률 최고, 개당 30분 이하 |
| 3 | 단계 5 | FE only | 15m | 1커밋 |
| 4 | 단계 2 | FE only | 2~3h | Q1 반려 시 2-1만 제외 |
| 5 | 단계 3 | BE+FE | 3~4h | 조회 함수·API 1개·패널 1개 |
| 6 | 단계 6-1 | FE only | 30m | 문구만 |
| 7 | 단계 6-2·6-3 | FE only | 1~2h | 여력 시 |

**멘토링(8/12 18:00) 전에 최소 1·4·5까지.** 이 셋이면 "화면이 대화이고,
저장되는 척하는 컨트롤이 없다"까지는 방어된다. 2·3은 Q1·Q3 답을 받고
그 자리에서 착수해도 늦지 않다.

**5차 단계 4(온보딩 제거)가 아직 남아 있다.** 이 문서보다 우선순위가 높은지
PM 판단 필요 — 온보딩 제거는 신규 계정 첫인상이고, 6차 단계 1은 기존 계정
매 순간의 문제다. Cowork 판단으로는 **6차 단계 1이 먼저**다.

## 완료 후

단계별 결과 블록을 이 문서에 추가(형식은 1~5차와 동일). 단계 1 완료 시점에
QA 체크리스트 **B(Chat E2E)**를 다시 돌린다 — 5차 기준으로 짠 B가 단일 턴을
전제하고 있다면 다중 턴 항목을 v4로 보강할 것.
