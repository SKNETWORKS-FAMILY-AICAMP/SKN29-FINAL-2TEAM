# 2026-08-13_03 — `agent_platform.py` Repository·저장/발행 API 작업기록

> 정본 관계: 이 문서는 계약 문서가 아니라 **작업기록**이다. 계약(타입·이벤트·Repository
> 시그니처)은 여전히 `2026-08-13_02_Deep-Agent_런타임_공통_계약_v1.md`가 정본이고,
> 여기는 그 §6.1·§17.1(작업자 A: 데이터·빌더·도구 경계) 몫을 실제로 구현하면서
> 있었던 일과 실제 호출 검증 결과를 남긴다.

## 1. 한 일 요약

02 §17.1 작업자 A 몫 중 "Repository"와 "저장·발행 API" 두 항목을 끝냈다.

1. `backend/db/agent_platform.py`에 새 버전 스키마(`agents`/`agent_versions`/
   `agent_version_tools`/`agent_version_subagents`)용 Repository 3개 추가
2. `apps/agents/`에 저장·발행 API 엔드포인트 4개 추가(옛 비버전 엔드포인트와 나란히 존재)
3. `2026-08-13_agent_versioning.sql` 마이그레이션을 로컬 Docker DB에 실제 적용(49 → 53 테이블)
4. 실제 HTTP 호출로 전체 흐름 검증 — 발행 → 목록/상세 조회 → 새 버전 발행(버전 증가) →
   활성화/비활성화 → 구조 검증(자기 참조 거부) 전부 통과
5. 검증 중 실제 버그 하나 발견 — 새 코드는 고쳤고, 같은 패턴이 옛 엔드포인트에도
   있어 별도로 남겨 둠(§5)

## 2. Repository 3개 (`backend/db/agent_platform.py`)

### 2.1 `AgentVersionRepository` — 조회 전용, 실행 경로(Loader)용

- `get_definition(*, agent_id, agent_version_id, account_id, team_id) -> dict` — 02 §6.1 계약 그대로
- 반환 딕셔너리는 `AgentDefinition`(`services/agent_runtime/definitions.py`) 필드와 1:1
- `backend.db.errors`(`RecordNotFound`/`PermissionDenied`)만 던진다. `services.agent_runtime.exceptions`로의
  번역은 나중에 `loader.py`(작업자 B)의 몫 — Harness가 psycopg에 직접 안 붙는 것과 같은 경계

### 2.2 `AgentSubagentRepository` — 조회 전용

- `list_for_parent_version(*, parent_version_id, account_id, team_id) -> list[dict]`
- 비활성·권한 없는 자식도 목록에서 빼지 않는다(02 §6.1) — `is_active`/`can_execute`로 표시만 함
- `has_subagents`는 그 자식 버전 자신이 다시 부모인지(EXISTS 서브쿼리) — MVP 1단계 위임 제한 검증용

### 2.3 `AgentVersionCrudRepository` — 쓰기 전용, Builder API용 (신규 설계, 02엔 없던 부분)

02 문서는 Repository의 **조회** 계약(§6.1)만 못박아 뒀고, 쓰기 쪽(저장·발행)은 "저장·발행
API와 런타임 Factory는 같은 구조 검증 함수를 쓴다"(§7.1, §2 원칙10)는 제약만 있을 뿐
구체 API 설계는 없었다. 그래서 이 클래스와 아래 §3의 엔드포인트 모양은 이번에 새로
정한 것이다 — 결정 배경을 남긴다.

**"저장"과 "발행"은 한 동작이다.** `agent_versions`가 불변이라(02 §5.2: "발행된
`agent_versions` 행은 수정하지 않는다") "임시 저장 후 나중에 발행"이라는 중간 상태를
DB에 둘 수가 없다. 그래서:

- 저장 버튼을 누르는 순간 바로 새 불변 버전을 만든다(`publish()`)
- 저장 없이 미리 돌려보고 싶으면 `Loader.from_draft()`(발행 안 함, DB에 안 남음)를 쓰는
  별도 "테스트 실행" 경로로 간다 — 옛 `AgentBuilderTestRunAPIView`와 같은 자리(아직 새
  스키마용은 안 만듦, §6 남은 일 참고)

메서드:

- `list_for_team(account_id)` — 목록. `agents` LEFT JOIN `agent_versions`(현재 버전)
- `get(*, agent_id, account_id)` — 상세. 한 번도 발행 안 한 논리 에이전트도 조회는 됨(빈 기본값)
- `publish(*, agent_id, account_id, fields, tool_refs, subagents)` — 핵심.
  - `agent_id=None`이면 논리적 에이전트(`agents`)부터 만듦
  - 구조 검증: `_build_subagent_refs()`로 요청의 서브 에이전트 후보를 `SubagentReference`로
    조립 → `_team_dependency_graph()`로 팀 전체의 **지금 발행 중인** 부모-자식 관계 그래프를
    만듦 → `services.agent_runtime.subagents.validation.validate_subagents()` 호출.
    **`allow_subagents=False`로 고정** — MVP는 1단계 위임까지만 허용하므로, 고른 자식이
    이미 자기 자식을 갖고 있으면 여기서 막아야 한다.
  - 버전 번호는 `count(*)+1`(그 `agent_id`의 기존 버전 수)
  - 새 버전 INSERT 후 `agents.current_version_id`만 옮긴다 — 옛 버전 행은 안 건드림
    (이미 그 버전을 고정 참조하는 세션·부모가 있을 수 있어서, 02 §5.4·§5.5)
  - 전부 한 트랜잭션 — 중간에 검증 실패하면 아무것도 안 남음
- `set_status(*, agent_id, account_id, status)` — DRAFT/ACTIVE/DISABLED 전이

**⚠ `allow_subagents` 관련 발견.** `services/agent_runtime/factory.py`의
`AgentRuntimeFactory.build()`는 이 인자의 기본값이 `True`다. `validate_subagents()`의
검사 로직(`if not allow_subagents and ref.has_subagents: raise DelegationDepthError`)을
보면 `False`여야 "자식이 이미 손자를 가진 경우"를 실제로 거절한다 — `True`가 기본이면
MVP의 1단계 제한이 사실상 안 걸린다. 이번 API에서는 명시적으로 `False`를 넘겨서 문제
없지만, `factory.py`를 마저 구현할 사람(작업자 B)이 그 기본값도 같이 봐야 한다. 이번
작업 범위 밖이라 손 안 댔다.

## 3. 저장·발행 API (`apps/agents/`)

옛 비버전 엔드포인트(`/api/agents/`)와 완전히 나란히 존재한다. `apps/chat`·`apps/agents`의
실행 경로는 아직 이 스키마를 모른다 — 지금은 저장·조회만 가능하고, 실행에 실제로 쓰이는
것은 여전히 harness 경로의 `agent` 테이블뿐이다.

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/agents/versions/` | 팀의 논리적 에이전트 목록(현재 버전 스냅샷 포함) |
| POST | `/api/agents/versions/` | 새 논리적 에이전트 + 첫 버전 발행 |
| GET | `/api/agents/versions/<agent_id>/` | 상세(편집 화면 프리필용) |
| PUT | `/api/agents/versions/<agent_id>/` | 새 버전 발행. **일반적인 PUT과 달리 멱등하지 않다** — 같은 바디로 두 번 부르면 버전이 두 개 생긴다 |
| POST | `/api/agents/versions/<agent_id>/activate/` | DRAFT/DISABLED → ACTIVE. 활성화 시점에 모델·도구 재검증(그 사이 팀이 커스텀 모델을 지웠을 수 있음, 옛 `AgentActivateAPIView`와 같은 이유) |
| POST | `/api/agents/versions/<agent_id>/disable/` | ACTIVE → DISABLED. 무조건 통과 |

요청 바디는 02 §16 그대로: `name`/`description`/`system_prompt`/`model`/
`reasoning_effort`/`max_iterations`/`tool_refs`/`subagents[{child_agent_id,
child_version_id, alias, delegation_description}]`.

예외 매핑: `services.agent_runtime.exceptions.AgentRuntimeError`는
`_agent_runtime_error_response()`(신규)가 `HTTP_STATUS_BY_EXCEPTION`(02 §12)으로 바꾼다.
`type(exc).__mro__`를 순회해서 가장 구체적인 클래스를 먼저 찾는다 — 단순
`isinstance` 나열이나 dict 순서 의존 방식은 `SubagentPermissionError`(403)가
`SubagentValidationError`(409)의 하위 클래스라서 순서에 따라 잘못된 코드가 나올 수 있었다.

## 4. 마이그레이션 로컬 적용

`2026-08-13_agent_versioning.sql`을 RDS가 아니라 **로컬 Docker DB**에 적용했다. RDS는
현재 최원빈이 관리하는 인프라라 이 세션에서는 접근 권한이 없었다(연결 타임아웃 —
일시중지 상태이거나 보안그룹이 로컬 IP를 안 열어 둔 상태로 추정, 8/11 작업기록 참고).
AWS 배포 여부와는 무관하게, RDS는 이미 8/11부터 팀이 로컬 개발에 공유 DB로 쓰고
있었으므로 원래는 거기 적용하는 게 맞지만, 지금은 로컬로 대체했다 — RDS가 다시
열리면 같은 마이그레이션 파일을 한 번 더 돌리면 된다(멱등).

적용 도구: `DB/migrations/_apply_2026-08-13.py`(신규, 1회용) — `.env`를 셸에서
`source`하면 `DEFAULT_FROM_EMAIL`의 `<` 때문에 bash 문법 오류가 나고, Windows에
`psql` 클라이언트가 없어서 `psql -f` 대신 `psycopg`로 직접 문장을 나눠 실행하는
방식으로 만들었다. 인자로 URL을 주면 그걸 쓰고, 없으면 `.env`의 `DATABASE_URL`(RDS)을
읽는다.

결과: 로컬 DB 49 → 53 테이블, `chat_session`/`agent_run`에 `agent_version_id` 컬럼
확인 완료.

## 5. 실제 호출 검증과 발견한 버그

검증 도구: `apps/agents/_verify_versions_api.py`(신규, 1회용). 로컬 `web` 컨테이너가
`.env`의 `DATABASE_URL`(RDS)을 물려받아 로컬 DB를 못 보는 문제가 있어서, 그 컨테이너는
잠깐 내리고 로컬 venv로 `DATABASE_URL`을 로컬 DB로 override한 `manage.py runserver`를
띄워서 검증했다(끝나고 `docker compose up -d web`으로 원복).

검증 순서와 결과 — 전부 통과:

1. 로그인(테스트 계정 신규 가입 `POST /api/auth/signup/`으로 준비)
2. `POST /api/agents/versions/` — 발행, `version == 1` 확인
3. `GET /api/agents/versions/` — 목록에 보임
4. `GET /api/agents/versions/<id>/` — 저장한 값과 일치
5. `PUT /api/agents/versions/<id>/` — 두 번째 발행, `version == 2`로 증가, 첫 버전 안 건드려짐
6. `POST .../activate/`, `POST .../disable/` — 상태 전이 확인
7. 자기 자신을 서브 에이전트로 넣어 저장 시도 → **409** (`SelfReferenceError` → HTTP 매핑까지 실제로 동작)

**발견한 버그(1차 시도에서 500):** `_check_tool_refs()`(도구 참조 존재 확인, 기존
`apps/agents/api_views.py` 함수)가 내부에서 `AgentCrudRepository.team_tool_refs()` →
`_require_team()`을 부르는데, 팀이 없는 계정(신규 가입 직후 등)이면 여기서
`PermissionDenied`를 던진다. 이 호출이 **try/except 밖에서** 이뤄지고 있어서 500으로
그대로 샜다.

**같은 패턴이 옛 엔드포인트에도 있다.** `AgentListCreateAPIView.post()`,
`AgentActivateAPIView.post()`도 `_check_tool_refs()`를 try/except 밖에서 부른다 —
팀 없는 계정이 이 경로를 타면 똑같이 500이 날 수 있다. 이번 작업(새 버전 API 3곳)은
try/except로 감싸 고쳤지만, 옛 엔드포인트는 이번 작업 범위 밖이라 손대지 않았다.
팀에 공유하거나 별도로 고칠 것.

## 6. 남은 일 (02 §17.1 작업자 A 기준)

- [x] Repository
- [x] 저장·발행 API
- [ ] 빌더 UI — `frontend/src/pages/AgentEditPage/`는 전부 옛 비버전 API에 물려 있음. 새 UI 미착수
- [ ] `tools/adapters.py` — `services/harness/registry.py`의 내장 도구 13개를 `Tool`(injected_context 명시)로 감싸는 어댑터. 미착수
- [ ] `tools/loader.py`의 `ToolLoader.load()` 실제 구현 — 위 어댑터 완성 후
- [ ] "테스트 실행"(저장 안 하고 `from_draft()`로 미리 돌려보기) 엔드포인트 — 옛 `AgentBuilderTestRunAPIView`에 대응하는 새 스키마용. 이번엔 안 만듦
- [ ] `_check_tool_refs` 미보호 호출 옛 엔드포인트 2곳 수정(§5)
- [ ] `factory.py`의 `allow_subagents` 기본값 재검토(§2.3, 작업자 B 몫과 겹침)

## 7. 이번에 만들거나 고친 파일

- `backend/db/agent_platform.py` — `AgentVersionRepository`, `AgentSubagentRepository`, `AgentVersionCrudRepository` 추가
- `apps/agents/serializers.py` — `SubagentRefSerializer`, `AgentVersionPublishSerializer`, `agent_version_response()`
- `apps/agents/api_views.py` — `AgentVersionListCreateAPIView`, `AgentVersionDetailAPIView`, `AgentVersionActivateAPIView`, `AgentVersionDisableAPIView`, `_agent_runtime_error_response()`
- `apps/agents/api_urls.py` — `versions/` 하위 라우트 4개
- `DB/migrations/_apply_2026-08-13.py`(신규, 1회용 — 실행 후 지워도 됨)
- `apps/agents/_verify_versions_api.py`(신규, 1회용 — 회귀 검증용으로 남겨 둘지는 팀 판단)
