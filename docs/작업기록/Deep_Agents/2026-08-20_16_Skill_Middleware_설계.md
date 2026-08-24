# Skill Middleware 설계

Skill = 반복되는 업무 절차를 적어 둔 문서. **새 Tool 권한을 주지 않는다** —
어떤 도구를 실행할 수 있는지는 지금 있는 `RBAC → RuntimePolicy → HITL`
체계가 그대로 맡고, Skill 미들웨어는 그 앞에 아무것도 끼워 넣지 않는다.

## 동작 흐름

1. 사용자: "이 방식을 스킬로 등록해줘" → Root가 지금까지 대화를 근거로
   `SKILL.md` 초안(YAML frontmatter + 절차 본문)을 만들어 먼저 보여준다.
   아직 아무 데도 저장하지 않는다.
2. 사용자가 승낙하면 `skill_register` 도구를 부른다. `side_effect=True`
   도구라 기존 `HumanInTheLoopMiddleware` 확인 카드가 그대로 뜬다 — 내용
   미리보기 + **등록**/**취소** 버튼. 새 UI를 따로 안 만들고 기존 쓰기
   도구(`task_register` 등)와 같은 메커니즘을 재사용한다.
3. **개인 스킬**: 누구나 요청 가능. `등록`을 누르면 그 즉시 활성 — 별도
   승인 단계 없음. 본인 계정에서만 보인다.
4. **팀 스킬**: `leader`만 요청할 수 있다 — 팀원이 "팀 스킬로 등록해줘"라고
   하는 경로 자체가 없다. `skill_register`가 `scope=TEAM`인데 요청자가
   `leader`가 아니면 그 자리에서 거부한다(팀 명부·초대에 이미 쓰는
   `require_leader()`와 같은 패턴, `apps/accounts/permissions.py`).
   `leader`가 `등록`을 누르면 그 즉시 팀 전체에 활성 — 여기도 별도 승인
   단계가 없다(등록 자체가 이미 팀장의 결정이라 또 승인받을 대상이 없다).
5. 다음 그래프 조립 시점부터 해당 계정/팀의 활성 스킬 목록에 반영된다.

## 스코프 — 개인 / 팀, 조직 단위는 없음

이 시스템의 테넌트 경계는 **팀**이다(`team` 테이블 — 팀장이 온보딩에서
명시적으로 만듦). 여러 팀을 묶는 "조직" 엔티티도, `leader`/`member` 외의
"도메인 오너" 역할도 없다(`runtime_policy.AccountRole`). 그래서 조직 공용
Skill과 그 승인 계층은 설계에서 뺀다 — "팀 스킬"이 사실상 그 역할을
대신한다.

## 저장 구조 — Store만 사용

승인 대기 상태가 없어졌으므로(위 4번) 상태·승인자·반려사유를 추적할 DB
테이블도 필요 없다 — 지난 개정에서 제안했던 `skill` 테이블은 뺀다. 본문은
`StoreBackend`(Memory가 쓰는 것과 같은 메커니즘, `PostgresStore`)에 그대로
둔다.

- 개인: `/skills/personal/{account_id}/{name}/SKILL.md`
- 팀: `/skills/team/{team_id}/{name}/SKILL.md`

개인 스킬의 계정 간 격리는 경로 명명 규칙이 아니라 **backend namespace**가
보장한다 — Memory의 `_personal_namespace`(`memory/backend.py`)처럼,
`account_id`가 요청을 처리하는 서버 쪽에서 닫히는 값이라 다른 계정 것을
가리킬 방법이 없다.

같은 이름의 개인/팀 스킬이 같이 있으면 `SkillsMiddleware`는 나중 소스(팀)를
우선 로드한다(라이브러리 자체 규칙). 지금은 이름 자체를 못 바꾸므로, 스킬
목록을 보여주는 화면에서는 이름 옆에 **"(팀)"** / **"(개인)"** 태그를 붙여
사람이 구분할 수 있게 한다.

## `skill_register`가 담당하는 것

일반 `write_file`로 직접 쓰게 하면 저장 경로 우회·이름 검증 누락·개인/팀
혼동이 생길 수 있어 전용 도구로 둔다. 담당 범위:

- `SKILL.md` 생성(초안 → 스펙에 맞는 frontmatter+본문)
- 이름 검증(소문자·하이픈, 디렉터리명과 일치 — 라이브러리의
  `_validate_skill_name` 재사용)
- `scope` 검증 — `TEAM`이면 요청자가 그 팀의 `leader`인지 확인
- 저장 경로 결정(위 두 경로 중 하나로 확정)

## Root / GP / Child — deepagents 방식 그대로 재현

실제 설치된 `deepagents/graph.py`(`create_deep_agent()`)를 확인한 결과:

- **메인 에이전트(Root)**: `skills=` 인자를 넘기면 자동으로
  `SkillsMiddleware`가 붙는다(818행).
- **deepagents 기본 general-purpose**: 같은 top-level `skills` 목록을
  자동으로 물려받는다(761행) — 단 이건 caller가 GP를 따로 지정하지 않았을
  때만 타는 경로다.
- **그 외 서브에이전트(우리 GP 포함)**: 자동 상속이 없다. 각 서브에이전트
  스펙 dict에 `skills` 키가 있을 때만 붙는다(676행) — 우리 프로젝트는
  `gp_spec`을 직접 만들어 넘기므로(`factory.py`) deepagents 기본 GP 경로를
  안 타고, 이 "옵트인" 경로를 탄다.

그래서 이렇게 배선한다: **Root는 자동으로 붙는다.** **GP**는 Root와 같은
`skills` 목록을 `gp_spec["skills"]`에 명시적으로 넣어, deepagents 기본
동작(Root와 GP가 같은 스킬을 본다)을 그대로 재현한다. **Child**는 기본
없음 — 특정 Child에 필요해지면 그 서브에이전트 정의에만 `skills=[...]`를
개별로 넣는다. 이것도 새로 만드는 게 아니라 deepagents가 이미 지원하는
서브에이전트별 옵트인 방식 그대로다.

## 다음 단계 (이번 착수 범위 아님)

- 개인/팀 스킬 목록 조회·수정·삭제 화면 (위 "(팀)"/"(개인)" 태그도 여기서
  적용)
- `allowed-tools` frontmatter 강제 적용 — 하게 되더라도 새 권한을 여는
  용도가 아니라 기존 권한을 더 좁히는 용도로만
- Skill 본문의 절차 지시문을 "데이터"로 취급할지 프롬프트 인젝션 방어
  원칙과 맞춰 보는 것 (`RUNTIME_SCAFFOLD`)
