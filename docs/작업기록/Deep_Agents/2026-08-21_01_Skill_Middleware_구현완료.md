# Skill Middleware 구현 완료

정본 설계: `2026-08-20_16_Skill_Middleware_설계.md` (93줄 축약판). 이 문서에
적힌 흐름·스코프·저장 구조를 그대로 코드로 옮겼다.

## 무엇을 만들었나

### 1. Skill 전용 저장 경로 — `services/agent_runtime/skills/`

`memory/backend.py`의 `MEMORY_USERS_PATH_PREFIX` 패턴을 그대로 따랐다.
경로 문자열 자체는 계정마다 다르지 않은 고정값이고, 격리는 전부
`StoreBackend(namespace=...)` 클로저가 담당한다.

- `/skills/personal/{name}/SKILL.md` — namespace `("skill", "personal", account_id)`
- `/skills/team/{name}/SKILL.md` — namespace `("skill", "team", team_id)`

`SkillsProvider`(`skills/provider.py`)는 `.sources()`와
`.routes(account_id, team_id)` 두 메서드만 노출한다 — `MemoryProvider`와
같은 얇은 어댑터 형태다.

### 2. Root / GP / Child 배선 — deepagents 실제 소스로 확인한 대로

설치된 `deepagents/graph.py`(`create_deep_agent()`)를 직접 읽어서 확인한
사실:

- Root는 `skills=`를 넘기면 자동으로 `SkillsMiddleware`가 붙는다(818행).
- deepagents 기본 general-purpose는 같은 `skills` 목록을 자동 상속한다
  (761행) — 단, caller가 GP를 직접 안 만들었을 때만.
- 이 프로젝트는 `factory.py`에서 `gp_spec`을 항상 직접 만들어 넘기므로
  위 자동 상속 경로를 안 탄다. 그 외 모든 서브에이전트(우리 GP 포함,
  Child 전부)는 스펙 dict에 `skills` 키가 있을 때만 붙는다(676행).

그래서 배선은 이렇게 했다: **Root**는 `skills=` 전달만으로 자동 처리.
**GP**는 `build_general_purpose_spec(..., skills=skill_sources)`로 Root와
같은 목록을 명시적으로 넣어 deepagents 기본 동작을 재현. **Child**는
기본 없음 — 필요해지면 그 서브에이전트 정의에만 개별로
`skills=[...]`를 넣으면 된다(새 메커니즘이 아니라 deepagents가 이미
지원하는 옵트인 경로).

### 3. `skill_register` 도구 — `services/harness/registry.py`

`side_effect=True`라 기존 `HumanInTheLoopMiddleware` 확인 카드가 그대로
뜬다(내용 미리보기 + 등록/취소 버튼, 새 UI 없음). 담당 범위:

- 이름 검증 — deepagents의 private `_validate_skill_name`과 같은 규칙을
  재구현(소문자·하이픈만, 1~64자, 앞뒤/연속 하이픈 금지, import는 안 함 —
  private 함수라 이 프로젝트의 "public 이름만 import" 원칙에 안 맞음)
- `scope=TEAM`이면 요청자가 `leader`인지 확인(아니면 그 자리에서 거부)
- `SKILL.md` 생성(YAML frontmatter + 본문)과 저장 경로 확정

leader 판정은 `RuntimeContext.role`을 도구 핸들러에 주입해서 확인한다.
`apps/accounts/permissions.py`의 `require_leader()`는 DRF 뷰 레이어용
(`Response | None` 반환)이라 도구 핸들러 안에서는 못 쓴다 — 그래서
`tools/loader.py`의 `CONTEXT_VALUES`에 `account_role` 키를 새로 추가하고
`tools/adapters.py`가 `skill_register`에 한해 이걸 주입하도록 배선했다.

## 바뀐/새로 만든 파일

**신규**
- `services/agent_runtime/skills/__init__.py`
- `services/agent_runtime/skills/backend.py`
- `services/agent_runtime/skills/provider.py`
- `tests/test_skills_backend.py`

**수정**
- `services/agent_runtime/memory/backend.py` — `build_memory_backend()`에
  `extra_routes` 파라미터 추가(Skill 라우트를 Memory와 같은 backend
  인스턴스에 합치기 위함 — deepagents는 filesystem/memory/skills가 같은
  `backend=`를 공유해야 한다)
- `services/agent_runtime/memory/provider.py` — `extra_routes`를 그대로
  전달만 함(Skill을 직접 알지는 못함)
- `services/agent_runtime/compat/deepagents_v075.py` —
  `build_general_purpose_spec()`/`create_root_graph()`에 `skills` 파라미터
  추가
- `services/agent_runtime/factory.py` — `skills_provider` 의존성 추가,
  Root/GP 양쪽에 같은 `skill_sources` 배선, `memory_provider`가 없으면
  `skills_provider`가 있어도 무시(Skill이 Memory 위에 얹히는 구조라서)
- `services/agent_runtime/bootstrap.py` — `AgentRuntimeFactory`에
  `SkillsProvider()` 연결
- `services/agent_runtime/tools/loader.py` — `CONTEXT_VALUES`에
  `account_role` 추가
- `services/agent_runtime/tools/adapters.py` — `skill_register` 전용 주입
  경로 추가, 도구 개수 참조 14→15 갱신
- `services/harness/registry.py` — `_validate_skill_name`,
  `_skill_register`, `BUILTIN_TOOLS["skill_register"]` 추가
- `tests/test_adapters.py`, `tests/test_bootstrap.py`,
  `tests/test_factory.py`, `tests/test_harness.py`,
  `tests/test_memory_backend.py`, `tests/test_deepagents_compat.py` — 위
  변경들에 대응하는 테스트 추가/갱신

## 검증

바뀐 파일과 관련된 테스트 10개 모듈(`test_memory_backend`,
`test_skills_backend`, `test_adapters`, `test_tool_loader`, `test_factory`,
`test_bootstrap`, `test_harness`, `test_runtime_policy`,
`test_middleware_permissions`, `test_deepagents_compat`)을 수정 전
원본(`/tmp/skn_orig5`)과 수정 후(`/tmp/skn_repo5`) 양쪽에서 똑같이 돌려
실패 목록을 `diff`로 비교했다.

- 원본: 실패 13건(전부 이 세션 이전부터 있던 것 — 10건은 이 샌드박스가
  실 DB에 접속 못 해서 나는 에러, 3건은 이미 낡아 있던 테스트)
- 수정 후: 실패 12건 — 원본과 완전히 같은 목록에서 딱 하나만 빠졌다:
  `test_real_registry_has_exactly_thirteen_tools`. 이건 애초에 도구가
  13개였다가 8/20에 `get_current_datetime`이 추가되며 14개가 된 뒤로 갱신이
  안 된 낡은 테스트였는데, 이번에 `skill_register`가 15번째 도구가 되며
  이름·기댓값을 같이 고쳐서 지금은 통과한다.

신규 `test_skills_backend.py` 6개 모두 통과. 결론: 이번 변경으로 인한
새 회귀는 0건이고, 지나가다 발견한 낡은 테스트 1건을 같이 고쳤다.

## 다음 단계 (이번 범위 아님, 설계 문서에도 명시됨)

- 개인/팀 스킬 목록 조회·수정·삭제 화면 — 이름 옆 "(팀)"/"(개인)" 태그
  표시도 여기서
- `allowed-tools` frontmatter 적용 — 하게 되더라도 권한을 더 여는 용도가
  아니라 좁히는 용도로만
- Skill 본문을 "데이터"로 취급하는 프롬프트 인젝션 방어 검토
