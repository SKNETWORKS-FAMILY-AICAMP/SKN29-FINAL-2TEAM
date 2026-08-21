# Skill Middleware 설계 (2026-08-20)

받은 피드백 원문의 4개 절(방향/공유 방식/권한·저장 범위/등록 방식) 중, 이
시스템에 실제로 대응하는 엔티티가 있는 부분만 반영했다. **조직 공용
Skill과 그에 딸린 승인 계층(도메인 오너/플랫폼 관리자)은 뺐다** — 이유는
아래 "왜 조직 단위를 뺐는가"에서 근거를 든다.

## 0. 결론 — 무엇을 채택하고 무엇을 뺐나

| 피드백 항목 | 채택 여부 |
|---|---|
| Skill = 사내 업무 절차 재사용(구매 검토, Jira 이슈 생성 등) | 채택 |
| 이름·설명만 먼저 보고 필요한 것만 불러오는 구조(progressive disclosure) | 채택 — 이미 deepagents에 있음, 새로 안 만듦 |
| 개인 Skill 단위 | 채택 |
| 팀/프로젝트 Skill 단위 | 채택 — "팀" 하나로 통일(아래 이유) |
| **조직 공용 Skill** | **제외** |
| 팀 Skill = 팀장/도메인 오너 승인 | 채택하되 "팀장"만(도메인 오너 개념 없음) |
| (추가) 등록 실행 자체는 다른 쓰기 도구와 동일하게 HITL 확인 카드를 거친다 | 채택 — 피드백엔 없었지만 이 시스템의 기존 쓰기 도구 규칙과 일관되게 반영(§4.0) |
| 조직 Skill = 도메인 오너·플랫폼 관리자 승인 | **제외**(대상 자체가 없음) |
| 누구나 초안 작성 가능 | 채택 |
| 개인 Skill은 승인 없이 즉시 활성 | 채택 |
| 자연어 "이 작업 방식을 Skill로 등록해줘" → 초안 자동 생성 | 채택 |
| 이 기능 전체는 핵심 기능 안정화 이후 확장 과제 | 채택 — 이 문서는 설계만, 착수 시점은 아님 |

## 1. 먼저 확인한 것 — 새로 만들 필요가 없다

`deepagents==0.7.5`(설치된 실제 패키지, `deepagents/middleware/skills.py`)에
이미 `SkillsMiddleware`가 있다. 우리 프로젝트의 원칙("deepagents/langchain
재사용, 수정에는 근거 필요")에 따라 이걸 그대로 쓰는 걸 기본으로 삼는다.

### 1.1 `SkillsMiddleware`가 실제로 하는 일

- `before_agent` 훅에서 세션(state)당 한 번, 설정된 `sources`(경로 목록)를
  훑어 각 하위 디렉터리의 `SKILL.md`를 찾아 **YAML frontmatter만** 파싱한다
  (본문은 안 읽는다). `name`/`description`/`license`/`compatibility`/
  `metadata`/`allowed-tools`를 뽑아 `state["skills_metadata"]`에 담는다.
  이미 로드돼 있으면(체크포인트 이어받기) 다시 안 읽는다.
- `wrap_model_call` 훅에서 이 메타데이터 목록(이름 + 설명 + 파일 경로)을
  시스템 프롬프트에 주입한다. **본문은 여기서도 안 실린다.**
- 모델이 필요하다고 판단하면, 별도의 "get_skill" 같은 전용 도구 없이
  **`read_file`로 그 경로를 직접 읽는다** — `FilesystemMiddleware`가 이미
  제공하는 범용 파일 읽기 도구를 그대로 재사용한다. 이게 progressive
  disclosure의 실제 구현이다: 이름·설명은 항상 보이고, 본문은 필요할 때만
  토큰을 쓴다.
- 여러 `sources`를 등록하면 **나중 소스가 같은 이름의 스킬을 덮어쓴다**
  (라이브러리 자체 docstring: "base → user → project → team" 순서 레이어링
  예시가 있음) — 우리가 원하는 "여러 스코프를 순서대로 겹쳐 보여주기"를
  이미 지원한다.

근거: `deepagents/middleware/skills.py` — `_list_skills_with_errors()`,
`before_agent()`, `SKILLS_SYSTEM_PROMPT`, 모듈 상단 docstring(레이어링 예시).

### 1.2 `SKILL.md` 형식 — 이미 스펙이 있다

Agent Skills 스펙(`agentskills.io/specification`)을 그대로 검증한다.
`name`은 소문자·숫자·하이픈만, 64자 이내, **디렉터리명과 반드시 일치**,
연속 하이픈 금지. `description`은 1024자 이내. `license`/`compatibility`/
`metadata`/`allowed-tools`는 선택. 이 검증 로직(`_validate_skill_name`,
`_parse_skill_metadata`)이 라이브러리 안에 이미 있으므로, 우리가 만드는
초안 생성기도 이 형식을 그대로 따르면 된다 — 새 포맷을 정의할 필요가
없다.

### 1.3 배선 방법 — `create_deep_agent(skills=[...], backend=...)`

`skills`는 소스 경로 목록(`list[str]`)이고, `backend`는 그 경로들을 실제로
어디서 읽을지 정하는 객체다(`BackendProtocol`). **`skills`와 나머지 파일
도구(`ls`/`read_file`/Memory 등)가 같은 `backend` 인스턴스 하나를
공유한다** — `deepagents/graph.py`의 `create_deep_agent()`가 두 미들웨어
모두에 같은 `backend` 변수를 넘긴다.

## 2. 우리 시스템에 매핑

### 2.1 왜 조직 단위를 뺐는가

이 시스템의 테넌트 경계는 **팀**이다. `DB/schema.sql`의 `team` 테이블
주석이 명시한다: "팀은 조직도에서 유도하지 않고 팀장이 온보딩에서 이름을
붙여 명시적으로 만든다 — 그래야 팀원의 소속을 추론이 아니라 조회로 알 수
있다." 여러 팀을 묶는 "조직"이라는 플랫폼 엔티티 자체가 없다.
`mock_hr.org`는 고객사 HR의 조직도를 읽기 전용으로 미러링한 목(mock)
데이터일 뿐 — 우리 플랫폼이 쓰는 테이블이 아니고, 여러 팀이 공유하는
자원의 소유자가 될 수 없다.

권한 모델도 마찬가지다. `services/agent_runtime/runtime_policy.py`의
`AccountRole = Literal["leader", "member"]` — 역할은 이 둘뿐이다.
"도메인 오너"에 대응하는 역할이 없다. 플랫폼 전체를 다루는 `is_admin`
플래그는 있지만(`user_account.is_admin`), 그 컬럼 주석이 스스로 못박는다
— "API로 자기 자신·타인을 승격시키는 경로는 없고,
`backend/services/createDB/grant_admin.py`로만 켤 수 있다." 즉 일상적인
"이 Skill을 조직 전체에 배포해도 될까요?" 같은 승인 흐름에 쓰라고 만든
플래그가 아니다 — 여기 쓰려면 별도 승격 UI/API부터 새로 설계해야 하는데,
그 근거가 되는 엔티티(조직)조차 없다.

**정리**: 팀이 이미 이 시스템의 최상위 공유 단위이므로, "팀 Skill"이 사실상
피드백이 말한 "조직 공용 Skill" 역할을 한다. 별도 상위 계층을 추가하는 건
없는 개념(조직)과 없는 역할(도메인 오너)을 새로 만드는 것이라 지금
범위에서 뺀다. 나중에 실제로 여러 팀을 묶는 조직 엔티티가 생기면 그때
다시 검토한다.

### 2.2 두 단계로 축소

- **개인 Skill** — 작성자 본인 계정에만 보인다. 승인 없이 즉시 활성.
- **팀 Skill** — 같은 `team_id` 소속 전원에게 보인다. 팀장(`leader`) 승인
  후에만 활성.

## 3. 저장 구조 — Memory가 이미 쓰는 패턴을 그대로 재사용

새 백엔드 클래스를 만들 필요가 없다. `services/agent_runtime/memory/
backend.py`의 `build_memory_backend()`가 이미 같은 문제(경로별로 다른
저장소로 라우팅)를 풀어 놨다:

```python
CompositeBackend(
    default=StateBackend(),
    routes={
        MEMORY_USERS_PATH_PREFIX: StoreBackend(namespace=_personal_namespace),
    },
)
```

`StoreBackend`는 deepagents가 제공하는, `BackendProtocol`을 완전히
구현한(`ls`/`download_files`/`write_file` 등) LangGraph `Store`(우리
배포에서는 이미 켜져 있는 `PostgresStore`, `memory/store.py`의
`get_memory_store()`) 기반 백엔드다 — `SkillsMiddleware`가 요구하는
`ls`/`download_files`를 그대로 만족하므로 Skill에도 바로 쓸 수 있다.

Skill용 라우트를 같은 `CompositeBackend`에 두 줄 추가하는 것으로 충분하다
(라우트 접두사·namespace만 다르고 메커니즘은 Memory와 동일):

```python
routes={
    MEMORY_USERS_PATH_PREFIX: StoreBackend(namespace=_personal_namespace),
    SKILLS_PERSONAL_PATH_PREFIX: StoreBackend(namespace=lambda rt: ("skill", "personal", account_id)),
    SKILLS_TEAM_PATH_PREFIX:     StoreBackend(namespace=lambda rt: ("skill", "team", team_id)),
}
```

그리고 `create_root_graph(..., skills=[SKILLS_PERSONAL_PATH_PREFIX,
SKILLS_TEAM_PATH_PREFIX], backend=composite_backend)`로 넘긴다 — 목록
순서상 팀 Skill을 뒤에 두면(라이브러리의 "나중 소스가 우선" 규칙) 개인
Skill이 같은 이름의 팀 Skill을 실수로 가리는 사고를 피할 수 있다(팀
Skill이 더 넓은 합의를 거쳤으므로 우선하는 게 맞다).

## 4. 등록 흐름

### 4.0 승인은 두 층이다 — 혼동하지 않도록 먼저 구분

**층 1. 실행 전 본인 확인(HITL 확인 카드)** — 이 시스템은 부수효과 있는
쓰기 도구(`task_register`, `jira_create_issues` 등)를 실제로 실행하기
직전에 무조건 확인 카드를 띄우고, 요청한 본인이 승인 버튼을 눌러야 실행되게
되어 있다(`leader`/`member` 둘 다 자기 요청은 자기가 승인 —
2026-08-20 "팀원 업무등록 자기승인 HITL 허용" 결정과 동일한 구조).
Skill 등록도 결과적으로 `SKILL.md` 파일을 저장소에 쓰는 쓰기 동작이므로,
`skill_register` 같은 새 builtin 도구를 만들면 **다른 쓰기 도구와 똑같이
이 확인 카드를 거쳐야 한다** — 개인 Skill이든 팀 Skill이든 예외 없다.
초안을 만드는 것 자체(대화로 내용을 다듬는 것)는 확인이 필요 없지만,
그 초안을 실제로 저장하는 도구 호출 시점부터는 이 층이 적용된다.

**층 2. 팀장의 공개 승인** — 층 1을 통과해 실제로 저장까지 끝난 뒤에도,
팀 Skill은 팀 전체에 곧바로 보이지 않는다(아래 4.3). 이건 "내가 이
작업을 저장해도 되는가"가 아니라 "이 절차를 팀 전체가 표준으로 써도
되는가"를 묻는, 완전히 다른 질문이라 별도 승인자(팀장)가 따로 필요하다.
개인 Skill에는 이 층이 없다 — 층 1만 통과하면 바로 활성이다.

아래 4.1~4.3은 이 두 층을 어디에 배치하는지 순서대로 적는다.

### 4.1 초안 생성 — 누구나, 확인 카드 없음

사용자가 "이 작업 방식을 Skill로 등록해줘"라고 요청하면, 에이전트가 지금까지의
대화·처리 절차를 근거로 `SKILL.md` 초안(YAML frontmatter의 `name`/
`description` + 본문 절차)을 만들어 사용자에게 먼저 보여준다. `leader`/
`member` 둘 다 요청할 수 있다 — 작성 자체에 제한을 두지 않는다(피드백
그대로 채택). `name`이 스펙 검증(소문자·하이픈, 디렉터리명과 일치)을
통과하도록 에이전트가 직접 맞춘다. 이 단계는 아직 아무것도 저장하지
않으므로(대화 중 초안 문구일 뿐) 확인 카드가 필요 없다 — `write_todos`가
확인 없이 자유롭게 쓰이는 것과 같은 이유다.

### 4.2 개인 Skill — 확인 카드만 거치면 바로 활성

사용자가 초안을 승낙하면 `skill_register` 도구를 호출한다 — **여기서
층 1(확인 카드)이 뜬다.** 사용자가 승인 버튼을 누르면 그제서야
`/skills/personal/{account_id}/{skill-name}/SKILL.md` 경로에 실제로
쓴다. 이 경로가 이미 그 계정의 `sources` 목록에 포함돼 있으므로, 쓰는
순간이 곧 활성화다 — 층 2(팀장 승인)는 없다.

### 4.3 팀 Skill — 확인 카드 + 팀장 승인, 두 층 다 거쳐야 활성

마찬가지로 `skill_register` 호출 시 층 1(확인 카드)을 먼저 거친다. 승인을
누르면, 이번엔 활성 경로가 아니라 **`sources` 목록에 없는** 대기 경로(예:
`/skills/team-drafts/{team_id}/{skill-name}/SKILL.md`)에 저장한다. 이
경로는 `SkillsMiddleware`가 스캔하지 않으므로 어떤 에이전트도 이 시점엔
이 스킬을 볼 수 없다 — 이게 층 2(팀장 승인 전에는 안 보인다)를 구현하는
방식이다. 별도의 상태(status) 컬럼이나 플래그가 필요 없다: **경로 자체가
상태다.**

팀장이 승인하면(이 승인 행위 자체도 팀장 입장에선 하나의 확인 카드다 —
"이 초안을 팀 전체에 공개할까요?"), 그 파일을 대기 경로에서 활성 경로
(`/skills/team/{team_id}/{skill-name}/SKILL.md`, `sources`에 포함된 곳)로
옮긴다. 그 순간부터 같은 팀 소속 전원의 에이전트가 다음 세션부터 이
스킬을 인식한다. 승인 권한은 `leader` 역할 하나로 충분하다 —
`apps/accounts/permissions.py`의 `require_leader()`가 이미 이런 종류의
"팀장만" 게이트를 초대·팀 명부 등에 쓰고 있으므로, 같은 패턴을 그대로
재사용한다.

### 4.4 "스킬 추가해줘"는 어떻게 이 흐름으로 들어오는가 — 별도 라우터 없음

이 시스템엔 사용자 발화를 먼저 분류해서 갈라주는 라우터가 없다.
`apps/chat/api_views.py`의 `ChatMessageAPIView.post()`를 확인해 보면,
발화는 가드레일(개인정보 마스킹) 검사만 거치고 곧바로 Root 에이전트의
LLM 루프로 들어간다 — 의도 분류 코드는 어디에도 없다. 이건 이미 확정된
설계 원칙과도 같다: GP 위임 여부조차 "결정적 라우터로 비일관성을 0으로
만든다"는 방향은 채택하지 않고, Root가 `task` 도구 설명 문구 하나만 보고
매 턴 스스로 판단하게 되어 있다(2026-08-20 GP 재설계 문서).

Skill 등록도 같은 패턴을 따른다 — Root의 도구 목록에 `skill_register`를
추가하고, 그 설명에 "사용자가 지금까지의 절차를 스킬로 저장해 달라고
요청하면 이 도구를 불러라"라고 적어두면 끝이다. 별도 라우팅 계층을 새로
만드는 게 아니라, Root가 `task_register`/`jira_create_issues`를 지금
스스로 판단해서 부르는 것과 완전히 같은 방식으로 `skill_register`도
스스로 판단해서 부르게 하는 것이다.

## 5. Root/Child/GP 중 어디에 붙이는가

Memory가 이미 정해 둔 선례를 따른다 — Memory는 "Root에만 붙인다, Child는
메모리 없이 그대로 둔다"(MVP 축소, `memory/provider.py` docstring).
Skill도 같은 이유로 **Root에만 붙이는 것을 기본안으로 제안한다** — Child는
이미 특정 업무 전용으로 좁게 만들어진 서브 에이전트라 범용 Skill 목록이
필요할 이유가 약하고, GP는 조회 전용으로 제한된 상태라(2026-08-20 확정
사항) 쓰기 절차가 담긴 Skill을 실행할 수도 없다. 다만 이건 이 문서
단계의 제안이지 확정은 아니다 — 실제 착수 시점에 다시 확인이 필요하다.

## 6. 이번 문서에서 다루지 않은 것 (다음 단계)

피드백 스스로 "핵심 기능 안정화 이후 확장 과제"라고 못박은 항목들이라
설계만 해 두고 착수 대상엔 안 넣는다:

- 팀장이 대기 중인 Skill 초안을 보고 승인/반려하는 화면·API
- Skill 활성 목록을 팀원이 조회·수정·삭제하는 화면
- `allowed-tools` frontmatter로 Skill이 특정 도구만 쓰도록 제한하는 것
  (스펙엔 이미 있는 필드지만, 우리 쪽에서 그 값을 실제로 강제하는 로직은
  아직 없음 — 지금은 문서화 정보로만 취급)
- 같은 이름의 개인 Skill과 팀 Skill이 충돌할 때 사용자에게 알리는 UX(지금
  설계로는 조용히 팀 쪽이 이긴다 — §3의 순서 규칙)

## 7. 남은 결정 필요 사항

- 팀 Skill 승인을 "팀장 단독"으로 할지, 아니면 팀 안에 더 세분화된 역할이
  생기면(지금은 없음) 그때 넓힐지 — 지금은 `leader` 하나로 고정해 둔다.
- 대기 경로(`/skills/team-drafts/`)에 쌓인, 영영 승인 안 되는 초안을 언제
  치울지(보관 기간, 자동 정리 여부) — 아직 정책 없음.
- Skill 본문 안에 있는 절차 지시문을 "데이터가 아니라 실행할 지시"로
  취급하는 게 맞는지 — Memory/도구 결과와 달리 Skill은 원래 "읽고
  따르라"고 만드는 콘텐츠라 프롬프트 인젝션 방어 원칙(2026-08-19 적용,
  `RUNTIME_SCAFFOLD`)과 정면으로 다른 성격이다. 이건 착수 시점에 별도로
  다뤄야 한다.
