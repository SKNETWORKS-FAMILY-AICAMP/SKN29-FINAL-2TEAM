# People DB (HR) 스키마 문서

> 대상 파일: `peopledb_mock_v13.sql`
> 범위: 조직·인력·스킬·근무일정·휴가·외부 계정 매핑(People DB)만 다룬다. Jira/Drive 쪽 테이블, 분석·추천·검증 레이어는 별도 문서(`DB설계_검토_및_가이드.md` 9.1절)를 참고.

## 구조 한눈에 보기 (Layout)

```
Org (조직 계층: 회사/부서/파트/비용센터)
      │
      │ org_id
      ▼
    Person (직원 기준정보 + 현재 조직/직급/재직상태)
      │
      ├── level_id ──▶ Level (직급 체계)
      │
      ├── person_id ──▶ PersonSkill ──▶ Skill (스킬 마스터)
      │
      ├── person_id ──▶ Sched (주당 근무시간/FTE)
      │
      ├── person_id ──▶ Absence (휴가/휴직 기간)
      │
      └── person_id ──▶ Link (Jira/Google 외부 계정 이메일)
```

Person이 중심이고, 나머지 5개 테이블(Skill/PersonSkill, Sched, Absence, Link)은 모두 `person_id`로 Person에 매달리는 1:N 또는 N:M 관계다. Org와 Level은 Person이 참조하는 마스터 테이블이다. 위 화살표는 전부 **DB가 강제하는 FK가 아니라 "설계상" 참조 관계**다(아래 0.2절 참고). 아래 각 절은 이 8개 테이블을 위에서 아래 순서로 하나씩 설명한다.

---

## 0. 이 스키마의 성격

**Workday API 응답을 그대로 복제한 것이 아니다.** `수집_데이터_보고서_2팀_v2`에 명시된 원칙 그대로 "Workday Worker·Supervisory Organization 구조를 **참고한** 비식별 합성 데이터이며 실제 API **응답 재현이 아니다**"를 따른다. 실제로 다른 점:

- `person_id`는 우리가 발급하는 짧은 코드(예: `PB001`)다. Workday의 원본 `id`는 별도로 `person.wd_worker_id`에 참조용으로만 보관한다. Workday `id`를 PK로 직접 쓰지 않는 이유: (1) 형식 종속 — Workday `id` 형식이 우리가 원하는 형식이라는 보장이 없어, 그대로 PK로 쓰면 이를 참조하는 모든 컬럼의 타입 안정성이 원천 시스템 포맷에 묶인다. (2) 다중 소스 대응 — Workday 없이 수동으로 등록되는 사람(예: 계약직을 Workday 반영 전에 먼저 추가)이 있을 수 있어, PK가 "Workday에서 왔다"는 전제에 의존하면 안 된다. (3) 원천 교체 내성 — 나중에 Workday를 다른 HR 시스템으로 바꾸거나 마이그레이션해도, 내부 PK와 이를 참조하는 수십 개 테이블은 그대로 두고 `wd_worker_id` 컬럼값만 갱신하면 된다. 실제 연동 시점에는 "Workday `id` → `wd_worker_id`로 기존 행 찾기 → 있으면 UPDATE, 없으면 새 코드로 INSERT" 방식의 upsert로 동기화한다. 이는 Jira 연동에 쓰는 `link` 패턴과 동일한 방식이라, 설계상 새로 만드는 개념이 아니다.
- `link`는 Workday에 없는 개념이다. 우리 시스템이 Jira/Google 계정을 사람과 연결하기 위해 만든 테이블이다.
- Workday의 실제 REST 응답은 중첩된 하나의 JSON 객체지만, 우리는 이를 여러 정규화된 테이블로 분리했다(Canonical Model 원칙).

이렇게 하는 이유: 원천 시스템(Workday)의 필드명·구조에 종속되지 않아야, 나중에 원천이 바뀌거나 추가돼도(다른 HR 시스템, 수동 입력 등) 하위 로직(부하 계산, 업무 배정)을 고치지 않아도 되기 때문이다.

### 0.1 ID 형식: 테이블별 접두사 + 일련번호

모든 PK는 `VARCHAR(5)` 내외의 짧은 코드다. UUID를 안 쓰는 이유:
- **가독성**: 쿼리 결과에서 `PB003`은 바로 눈에 들어오지만 UUID는 사람이 구분·기억하기 어렵다. 57명 규모의 목업/데모에서는 이 차이가 크다.
- **디버깅 편의**: 회의 중 "PB003 근무일정 확인해봐"(=백엔드파트 3번) 같은 대화가 UUID보다 훨씬 자연스럽다.
- **접두사로 테이블 즉시 구분**: 어떤 값을 봐도 `A`=조직, `P`=사람, `S`=스킬처럼 바로 알 수 있다.

| 테이블 | 접두사 | 예시 | 규칙 |
|---|---|---|---|
| `org` | `A` | `A001`~`A009` | 1부터 시작, 등록 순서 |
| `level` | `L` | `L1`~`L8` | 기존 `code` 값을 그대로 PK로 사용(사원=L1 ~ 대표이사=L8) |
| `person` | `P`+팀문자 | `PB001`~`PB009` 등 | 아래 별도 설명 참고 — 다른 테이블과 규칙이 다름 |
| `skill` | `S` | `S001`~`S014` | 1부터 시작 |
| `sched` | `W` | `W001`~`W057` | 1부터 시작, 행 순서 |
| `absence` | `B` | `B001`~`B023` | 1부터 시작, 행 순서 |
| `link` | `I` | `I001`~`I070` | 1부터 시작, 행 순서 |

**`person`만 다른 규칙을 쓰는 이유**: 처음엔 다른 테이블처럼 `P0000`부터 등록 순서대로 계속 증가하는 방식이었는데, 사람이 늘어날 때마다 그냥 +1이 되는 방식은 이 번호만 보고 어느 팀인지 알 수 없어 가독성이 떨어진다는 문제가 있었다. 그래서 `person_id`는 **"P + 팀문자 + 팀 내 3자리 일련번호"** 형식으로 바꿨다:

| 팀문자 | 소속 | 예시 |
|---|---|---|
| `X` | 경영진(회사 `A001`/개발본부 `A002`) | `PX001`(대표이사), `PX002`(개발본부장) |
| `B` | 백엔드파트(`A003`) | `PB001`~`PB009` |
| `F` | 프론트엔드파트(`A004`) | `PF001`~`PF008` |
| `N` | 기획팀(`A005`) | `PN001`~`PN010` |
| `D` | 디자인팀(`A006`) | `PD001`~`PD008` |
| `Q` | QA팀(`A007`) | `PQ001`~`PQ009` |
| `M` | 마케팅팀(`A008`) | `PM001`~`PM011` |

이렇게 하면 `PB003`이라는 값만 봐도 "백엔드파트 소속"임을 바로 알 수 있고, 새 팀원이 들어와도 그 팀 안에서만 번호가 늘어나서 다른 팀 번호에 영향이 없다. 각 조직의 관리자(`org.mgr_id`)는 해당 팀의 `001`번으로 지정돼 있다(예: 백엔드파트 관리자는 `PB001`).

알아두면 좋은 트레이드오프: `VARCHAR(5)`는 접두사 1글자 + 숫자 4자리가 한계라 테이블당 최대 9,999건까지만 표현된다. 지금은 57명 규모 목업이라 문제없지만, 실제 프로덕션(수만 명 규모 Workday 테넌트)으로 그대로 가져가면 자릿수를 늘려야 한다. 또한 짧은 코드는 UUID와 달리 중앙에서 순번을 관리해야 충돌을 막을 수 있다 — 지금은 Python 생성 스크립트 하나가 전부 만들기 때문에 문제없지만, 여러 곳에서 동시에 사람을 등록하는 실제 서비스가 되면 시퀀스/카운터 설계가 별도로 필요하다.

### 0.2 FK 제약 없음

컬럼은 관계를 나타내지만(예: `person.org_id`가 `org.org_id`를 가리킴), DB에 `REFERENCES` 제약은 걸려 있지 않다. 즉 DB가 실제로 그 값의 존재를 검사하지 않는다 — 참조 관계는 컬럼명과 주석으로만 표시된다.

**이렇게 한 이유**: FK 제약이 있으면 삽입 순서(부모 먼저)와 삭제 순서(자식 먼저)를 지켜야 한다. 특히 `org.mgr_id`↔`person.org_id`처럼 서로를 참조하는 순환 구조에서는 "조직을 관리자 없이 먼저 넣고 → 사람을 넣고 → UPDATE로 관리자 채우기"라는 2단계 삽입이 강제된다. 이 순서 제약 없이 자유롭게 다루기 위해 FK를 빼기로 했다.

**트레이드오프(알고 있어야 함)**: DB가 참조 무결성을 검사하지 않으므로, `person.org_id`에 존재하지 않는 `org.org_id` 값을 넣어도 DB가 막지 못하고, `org`에서 행을 지워도 그걸 참조하던 `person` 행들이 자동으로 어떻게 되지 않는다(고아 참조가 조용히 생길 수 있음). 지금 목업 데이터는 참조 무결성을 코드로 전수 재검사해서 고아 참조 0건임을 확인했지만, 앞으로 데이터를 수동으로 추가·수정할 때는 이 안전장치가 없다는 걸 감안해야 한다.

### 0.3 이름 짓는 규칙

일반적인 DB 네이밍 가이드는 "무리한 축약보다 명확성"을 우선하라고 권장한다(아래 출처 참고) — 과도한 축약은 스키마를 모르는 사람에게 오히려 혼란을 준다는 게 정설이다. 그래서 무조건 줄이지 않고 아래 원칙을 따랐다:

1. 이미 널리 쓰이는 표준 축약어만 사용(`org`, `mgr`, `emp`, `tz`, `yos` 등).
2. 줄였을 때 다른 뜻으로 오해될 수 있는 단어는 그대로 둔다 — 예: `proficiency`→`prof`는 "professor"로 헷갈릴 수 있어 축약 안 함, `confidence`→`conf`는 "configuration"과 헷갈려서 축약 안 함, `category`→`cat`도 축약 안 함.
3. 테이블명·컬럼명 모두 스키마 전체에 일관되게 적용.

---

## 1. 테이블 목록 요약

| 테이블 | 한 줄 설명 | 필수 여부 |
|---|---|---|
| `org` | 조직 계층(회사/부서/파트/비용센터) | 필수 |
| `level` | 직급 체계 | 필수 |
| `person` | 직원 1명의 기준정보 | 필수 |
| `skill` | 스킬 정의(마스터) | 필수 |
| `person_skill` | 사람-스킬 보유 관계 | 필수 |
| `sched` | 근무 시간·FTE | 필수 |
| `absence` | 휴가·휴직 일정 | 필수 |
| `link` | 외부 계정(Jira/Google) 연결 | 필수 |

---

## 2. `org`

**저장하는 정보**: 조직 하나(회사/부서/파트/비용센터)의 계층 구조.

| 필드 | 의미 | 필수/선택 |
|---|---|---|
| `org_id` | 내부 PK. `A001`~ 형식 | 필수 |
| `org_type` | COMPANY/DEPARTMENT/COST_CENTER/SUPERVISORY | 필수 |
| `name` | 조직명 | 필수 |
| `up_org_id` | 상위 조직(자기참조, FK 아님·설계상 참조) | 필수 — 계층 구조 표현의 핵심 |
| `mgr_id` | 이 조직의 관리자(`person.person_id` 참조, FK 아님) | 필수 |
| `status` | ACTIVE 등, 조직 개편·폐지 시 비활성화 처리용 | 추가 권장 |

**연결 관계**: `person.org_id`가 이 테이블을 참조(소속). `mgr_id`가 `person.person_id`를 참조(관리자). 자기 자신을 참조하는 `up_org_id`로 회사→부서→파트 계층을 표현. 이 참조들은 DB FK가 아니라 설계상 관계다(0.2절 참고).

**왜 필요한가**: 부서/회사/비용센터를 각각 별도 테이블로 만들지 않고 `org_type`으로 필터링하는 이유는, Workday 조사 결과 이 세 개념이 실제로 하나의 Organizations 리소스를 타입만 다르게 조회하는 구조로 확인됐기 때문이다(별도 리소스가 아님). Workday REST에는 `common/v1/organizations`(부서/디비전/비용센터, 타입·활성상태로 필터링 가능)와 `common/v1/organizations/{id}`(계층·관리자 지정·위치 등 반환)가 실제로 존재한다. 다만 `common/v1/supervisoryOrganizations`라는 별도 엔드포인트도 존재해서, SUPERVISORY 타입은 REST 레벨에서 완전히 같은 리소스가 아니라 별도 경로로 조회해야 할 가능성이 있다 — 필드 레벨 문서가 로그인 게이트 뒤에 있어 완전히 확정은 못 했다. 지금 우리 테이블 구조(하나의 `org` 테이블 + `org_type` 컬럼)는 어느 쪽이든 안전하다: 실제 연동 시 두 엔드포인트를 각각 호출해서 같은 테이블에 다른 타입으로 적재하면 되기 때문이다.

---

## 3. `level`

**저장하는 정보**: 직급 체계(사원~대표이사, 8단계).

| 필드 | 의미 | 필수/선택 |
|---|---|---|
| `level_id` | 내부 PK. `L1`~`L8` — 기존 `code`와 값이 동일(의도된 중복, 아래 참고) | 필수 |
| `code` | 안정적 코드값(L1~L8) | 추가 권장 — 직급명이 바뀌어도(예: "과장"→"매니저") 코드 기반 비교가 깨지지 않음 |
| `name` | 표시명 | 필수 |
| `rank_ord` | 순위(비교·정렬용) | 필수 |
| `status` | 폐지된 직급 처리용 | 추가 권장 |

**테이블명/`level_id`에 대해**: Workday의 실제 용어는 "Job Level"/"Management Level"이다(Job Profile을 구성하는 요소 중 하나). 우리 테이블은 이 중 순수한 서열(사원→대리→과장→...→대표이사) 축만 다루므로 "Job Level"에 더 가깝고, "Management Level"(Workday에서는 Supervisor/Individual Contributor 같은 관리자 분류축으로 쓰이기도 함)과는 다른 개념이다. `level_id`와 `code`가 같은 값인 이유는, 원래 `code`가 이미 "안정적인 짧은 식별자"였기 때문에(L1~L8) PK로 그대로 재사용한 것이다 — 8행뿐인 마스터 테이블이라 중복이 해가 되지 않고, PK만 봐도 코드를 알 수 있어 편하다.

**연결 관계**: `person.level_id`가 참조(FK 아님, 설계상 참조).

**왜 필요한가**: 업무 배정 시 "이 업무는 대리 이상만 가능" 같은 책임수준 검증에 `rank_ord`가 직접 쓰인다. Workday REST API에서 Job Level 확인이 안 되고 SOAP에서만 확인됐다(근거는 약함) — "Workday에 확실히 있다"고 과장하지 않는다. 다만 `rank_ord`/`code` 자체는 Workday 원본 필드 매핑과 무관하게 우리 시스템(업무 배정 로직)에 필요해서 유지한다.

---

## 4. `person`

**저장하는 정보**: 직원 1명의 식별·조직·역할·재직 상태 기준정보.

| 필드 | 의미 | 필수/선택 | 성격 |
|---|---|---|---|
| `person_id` | 내부 PK. `P`+팀문자+3자리 번호(예: `PB001`) 형식, 팀별로 구분됨(0.1절 참고). Workday ID를 그대로 쓰지 않음 | 필수 | Person |
| `emp_id` | 사번 | 필수 | Person |
| `name` | 표시명(Workday `descriptor` 대응) | 필수 | Person |
| `email` | HR 이메일(Workday `primaryWorkEmail`) | 필수 | Person |
| `phone` | 연락처 | 선택 | Person |
| `job_role` | 직함(Workday `businessTitle`) | 필수 | Employment |
| `org_id` | 소속 조직(FK 아님, 설계상 참조) | 필수 | Employment |
| `level_id` | 직급(FK 아님, 설계상 참조) | 필수 | Employment |
| `is_mgr` | 관리자 여부 | 선택(참고 아래 항목) | Employment |
| `loc` | 근무지 | 선택 | Employment |
| `wk_type` | 고용 형태 — Employee/Contingent만 사용(실제 Workday는 Employee/Contingent Worker/Pending Worker/Nonworker 4종. 재직 중인 정규·계약직만 모델링 대상이라 2종만 채택) | 선택 | Employment |
| `emp_status` | ACTIVE/TERMINATED만 사용(실제 Workday는 Active/Paid·Unpaid Leave/Suspended/Terminated/Retired/Deceased 등 더 세분화됨. Leave는 `absence`로 대체, Suspended/Retired/Deceased는 이번 스코프에서 미지원 — 알려진 한계로 기록) | 필수 | Employment |
| `yos` | 근속연수(years of service). Workday가 계산하여 제공하는 값이며, 내부에서 재계산하지 않는다 | 선택 | Employment |
| `wd_worker_id` | Workday 원본 ID 참조용 | 선택(추적성 목적) | Person |

**"성격" 열에 대해**: `job_role`~`yos`는 개념적으로는 Workday의 Worker(불변에 가까운 신원)가 아니라 Employment(조직배치·고용조건, 자주 바뀔 수 있음)에 속하는 값들이다. 지금은 별도 테이블로 물리적으로 분리하지 않고 `person` 한 테이블에 같이 두고 있다 — 어떤 기능(부하 계산/업무 배정/추천)도 과거 조직·직급 이력을 조회하지 않아 "현재 상태"만 저장해도 충분하기 때문이다. 다만 이 컬럼들이 논리적으로는 Employment 그룹이라는 걸 여기 표시해뒀다 — 나중에 조직 이동/승진 이력 추적이 실제로 필요해지면, 이 그룹 전체를 `employment` 테이블(`eff_from`/`eff_to` 포함)로 그대로 떼어내면 된다.

**연결 관계**: `org_id`→`org`, `level_id`→`level`(둘 다 FK 아님). `person_skill`/`sched`/`absence`/`link`가 이 테이블을 참조(역시 FK 아님).

**왜 필요한가**: 업무 배정의 최종 대상. 사람과 관련된 다른 모든 테이블이 이 테이블의 PK를 중심으로 연결된다.

**`emp_status`를 ACTIVE/TERMINATED로 좁힌 이유**: ON_LEAVE/SABBATICAL 같은 일시적 상태를 여기 정적 값으로 두면 `absence`(날짜 범위 데이터)와 내용이 중복되고, 휴직 종료 후 갱신을 깜빡하면 데이터가 stale해진다. "지금 추천 가능한 사람"은 `emp_status='ACTIVE' AND 오늘 날짜가 absence 범위 밖`으로 계산하는 게 더 정확하다.

**`is_mgr`의 중복성**: `org.mgr_id`로도 같은 정보를 알 수 있어 개념적으로는 중복이다. 조회 편의(서브쿼리 없이 바로 필터링) 때문에 유지를 추천하지만, 스키마를 더 줄이고 싶다면 제거해도 기능상 문제는 없다.

---

## 5. `skill` / `person_skill`

**저장하는 정보**: 스킬 마스터 목록과, 사람별 보유 스킬·숙련도·신뢰도.

`skill` 필드:

| 필드 | 의미 | 필수/선택 |
|---|---|---|
| `skill_id` | 내부 PK. `S001`~ 형식 | 필수 |
| `name` | 스킬명 | 필수 |
| `category` | Technical/Design/Management/Marketing 등 자유 텍스트(CHECK 미적용) | 필수 |
| `descr` | 스킬 설명 | 추가 권장 — 근거는 아래 참고 |
| `status` | 폐기된 스킬 처리용 | 추가 권장 |

`person_skill` 필드:

| 필드 | 의미 | 필수/선택 |
|---|---|---|
| `person_id`, `skill_id` | 복합 PK(둘 다 FK 아님, 설계상 참조) | 필수 |
| `proficiency` | BEGINNER/INTERMEDIATE/ADVANCED | 필수 |
| `source` | HR/RESUME/AI_INFERRED/USER_ADDED — 이 정보가 어디서 왔는지 | 필수 |
| `verify_status` | VERIFIED/SELF_REPORTED/UNKNOWN | 필수 |
| `confidence` | 신뢰도(0~1) | 선택 |
| `verified_at` | 최종 확인 시각 | 선택 |

**연결 관계**: `person_skill`이 `person`과 `skill`을 다대다로 연결.

**왜 필요한가**: 업무 적합성 판단(Skill 매칭)의 근거. `source`/`verify_status`/`confidence`를 넣은 이유는 스킬 정보가 전부 HR 시스템에서 검증된 값이 아니라, 이력서·AI 추론·본인 입력 등 신뢰도가 다른 여러 경로로 들어올 수 있기 때문이다. 스킬이나 숙련도가 확인 안 됐다고 무조건 "부적합"으로 단정하지 않고 `UNKNOWN` 상태의 조건부 후보로 남겨두기 위한 설계다.

Workday의 실제 WorkerSkill 모델은 proficiency(레벨: Not Applicable/Beginner/Intermediate/Experienced/Advanced/Expert)와 endorsement(동료·매니저의 확인)로 구성된다 — 우리 `verify_status`(VERIFIED/SELF_REPORTED/UNKNOWN)가 이 endorsement 개념과 대응한다. 다만 Workday의 WorkerSkill은 "Workday라는 단일 출처" 안에서만 동작하면 되는 반면, 우리 시스템은 HR 동기화 + 이력서 파싱 + AI 추론 + 본인 입력까지 여러 출처의 스킬 정보를 같이 다뤄야 한다. 그래서 `source`(어디서 왔는지)와 `confidence`(추론 신뢰도)는 Workday에 없는, 우리 시스템 요구사항에서 나온 필드다.

**`descr`이 필요한 이유**: Workday 자신도 Skills Cloud에서 스킬을 이력서·직무기술서 같은 문서와 "같은 언어(스킬 그래프)"로 표현해서 텍스트 임베딩 기반으로 매칭한다(아래 출처 참고). 우리 프로젝트도 ChromaDB 임베딩으로 문서·업무를 매칭하는 파이프라인을 쓰므로, `skill.descr`이 있으면 스킬명 완전일치가 아니라 "이 업무 설명과 의미적으로 가까운 스킬"을 임베딩으로 찾는 매칭이 가능해진다.

**뺀 것**: Workday의 실제 Skill 객체(`id`, `name`, `locale`, `category`, `description`) 중 `locale`(언어)만 뺐다. 단일 언어(한국어) 데모에는 `locale`이 의미가 없어서다.

**`category`가 자유 텍스트인 이유**: Workday Skills Cloud는 고정된 카테고리 리스트가 아니라 머신러닝 기반 스킬 온톨로지(그래프)로 스킬 간 관계를 표현하는 방식이라, `category`가 테넌트마다 설정 가능한 값일 가능성이 높다. 또한 `skill`/`person_skill`은 사람들이 계속 새로운 스킬을 등록하며 자라나는 오픈 리스트라, `category`를 고정값으로 잠가두면 새 스킬이 기존 카테고리에 안 맞을 때마다 `ALTER TABLE`이 필요해지는 마찰이 생긴다. 오타 방지는 애플리케이션 레벨(입력 시 드롭다운 등)에서 처리하는 게 더 맞는 지점이다.

---

## 6. `sched` / `absence`

**저장하는 정보**: 근무 시간 기준값과 휴가·휴직 일정.

`sched` 필드:

| 필드 | 의미 | 필수/선택 |
|---|---|---|
| `sched_id` | 내부 PK. `W001`~ 형식 | 필수 |
| `person_id` | FK 아님, 설계상 참조 | 필수 |
| `wk_hours` | 실제 주당 근무시간(Workday `scheduled_Weekly_Hours` 대응) | 필수 |
| `def_wk_hours` | 포지션 기준 주당 근무시간(Workday `default_Weekly_Hours` 대응). 예: 40시간 포지션에 20시간만 근무하면 `wk_hours=20`, `def_wk_hours=40` | 필수 |
| `fte` | Full Time Equivalent 비율(0~1). Workday는 `full_Time_Equivalent_Percentage`(0~100)로 반환하므로 저장 시 100으로 나눠 소수로 변환 | 필수 |
| `tz` | 근무 시간대 | 추가 권장(현재 전원 KST라 당장은 영향 없음) |
| `eff_from`/`eff_to` | 유효 기간 | 필수 |

`absence` 필드:

| 필드 | 의미 | 필수/선택 |
|---|---|---|
| `absence_id` | 내부 PK. `B001`~ 형식 | 필수 |
| `person_id` | FK 아님, 설계상 참조 | 필수 |
| `absence_type` | 연차/육아휴직/안식월 등 | 필수 |
| `start_at`/`end_at` | 기간 | 필수 |
| `status` | APPROVED 등 | 필수 |

**연결 관계**: 둘 다 `person_id`로 `person`을 참조(FK 아님).

**왜 필요한가**: 부하율 계산식(`총근무용량 = 기간내근무일 × 일기준근무시간 × FTE`, `유효가용용량 = 총근무용량 − 휴가·부재`)의 직접 입력값. 이 계산이 없으면 "이 사람이 지금 얼마나 여유가 있는지" 자체를 알 수 없어 추천 로직이 성립하지 않는다. `wk_hours`/`fte`는 Microsoft Workday HCM Connector 문서(`worker_Position_Data.scheduled_Weekly_Hours`/`default_Weekly_Hours`/`full_Time_Equivalent_Percentage`)에 기재된 Workday 표준 데이터이며 조회 가능한 필드다. 다만 어떤 API 경로(Staffing API, HCM Connector, SOAP `Get_Workers`)를 쓰느냐에 따라 실제로 어느 하위 리소스에서 반환되는지가 달라질 수 있고, REST `/workers/{id}`가 모든 필드를 항상 포함하지는 않으므로, 실 연동 시점에는 정확한 엔드포인트/필요 권한 확인이 한 차례 필요하다.

---

## 7. `link`

**저장하는 정보**: 사람과 외부 시스템(Jira, Google) 계정의 연결.

| 필드 | 의미 | 필수/선택 |
|---|---|---|
| `link_id` | 내부 PK. `I001`~ 형식 | 필수 |
| `person_id` | FK 아님, 설계상 참조 | 필수 |
| `sys_type` | JIRA 또는 GOOGLE만 | 필수 |
| `ext_email` | 마이페이지에서 본인이 등록한 이메일 | 필수 |
| `reg_at` | 등록 시각 | 선택 |

**연결 관계**: `person_id`로 `person`을 참조(FK 아님). HR 이메일은 이미 `person.email`에 있으므로 여기 포함하지 않는다.

**왜 필요한가**: Jira 이슈에는 "담당자: jira_account_abc123"만 나오는데, 이 사람이 People DB에서 누구인지 알아야 부하율 계산·업무 배정이 가능하다.

**설계가 단순한 이유**: 실제 운영 방식이 "마이페이지에서 본인이 직접 이메일을 등록"하는 자기신고형이라, CANDIDATE/AMBIGUOUS 같은 "애매한 후보" 상태 자체가 발생하지 않는다. 중복 등록만 `UNIQUE(sys_type, ext_email)`(같은 이메일을 두 사람이 등록 못 함)과 `UNIQUE(person_id, sys_type)`(한 사람당 시스템별 이메일 1개)로 DB 레벨에서 막는다.

**3개 이메일(HR/Jira/Google) 수집과의 관계**: 마이페이지 화면에는 이메일 입력란이 3개(HR/Jira/Google) 보이지만, DB에 새로 저장해야 하는 건 2개(Jira, Google)뿐이다. HR 이메일은 계정 생성 시점에 이미 `person.email`에 들어가 있는 시스템 기준값이라, 이걸 `link`에 또 저장하면 같은 정보가 두 곳에 있게 돼 동기화 문제만 생긴다. 마이페이지의 "HR 이메일" 입력란은 신규 등록이 아니라 "이미 저장된 값을 본인이 재확인/표시"하는 조회성 필드로 보면 된다.

동일 인물 판별 흐름: Jira 이슈에 담당자 이메일이 `user007@halil.com`으로 찍혀 있으면 → `link WHERE sys_type='JIRA' AND ext_email='user007@halil.com'`로 `person_id` 조회 → 그 `person_id`로 `person` 테이블을 보면 이름·HR 이메일·조직 등 전체 신원이 나온다. Google Drive 문서의 소유자 이메일도 동일하게 `sys_type='GOOGLE'`로 조회하면 같은 `person_id`에 도달한다.

`sys_type CHECK (... IN ('JIRA','GOOGLE'))`은 지금 필요한 두 외부 시스템과 정확히 일치한다. 나중에 Slack 같은 세 번째 외부 계정을 붙이게 되면 `ALTER TABLE ... DROP CONSTRAINT ... ADD CONSTRAINT ... CHECK (... IN ('JIRA','GOOGLE','SLACK'))`로 값 하나 추가하면 되는 구조라, 미리 확장해둘 필요는 없다.

---

## 8. 종합 평가

**강점**: 8개 테이블 모두 실제 사용처(부하 계산, 조직도, 업무 매칭, 외부 계정 연결)가 명확하고, 불필요한 원천별 raw 스테이징 테이블 없이 바로 canonical 테이블로 들어가는 단순한 구조다. Workday 조사에서 확인된 필드만 사용한다.

**약점**:
1. 실제 사용 계획이 없는 필드는 추가하지 않는 게 원칙인데, 지금까지 여러 차례 외부 피드백을 반영하며 스키마가 계속 늘어나는 경향이 있었다.
2. `is_mgr`가 `org.mgr_id`와 개념적으로 중복된다.
3. `wk_type`(Employee/Contingent)과 `emp_status`(ACTIVE/TERMINATED)는 영어 Workday enum 값 그대로 저장한다 — 나머지 컬럼명·주석은 한글/영문이 섞여 있어도 되지만, 상태값 자체를 한글로 바꾸면 나중에 실제 Workday API 응답과 문자열 매핑을 새로 짜야 해서 번거롭다. 원본 enum 값 그대로가 실 연동 시 더 안전하다.
4. `CALENDAR_EVENT`(휴가 외 일정) 포함 여부가 최종 확정이 안 돼 이번 버전에서는 제외했다. 필요해지면 `person_id`로 연결되는 별도 테이블로 쉽게 추가할 수 있는 구조다.
5. `person`이 식별정보(이름/이메일, "Person" 성격)와 자주 바뀔 수 있는 배치정보(조직/직급/재직상태, "Employment" 성격)를 한 테이블에 같이 갖고 있다(4절 표의 "성격" 열 참고). 어떤 기능도 과거 조직 이력을 조회하지 않아 물리적으로 분리하지 않기로 했다 — 나중에 조직 이동 이력 추적이 실제로 필요해지면 Employment 성격 컬럼들을 effective-dated 테이블로 그대로 떼어내면 된다.
6. `emp_status`가 ACTIVE/TERMINATED 2종뿐이라, 실제 Workday에 있는 Suspended(직위해제)/Retired(퇴직)/Deceased(사망) 같은 상태는 표현할 수 없다. 지금 스코프(현직 정규·계약직 57명)엔 영향 없지만, 실 연동 시 이 상태의 사람이 들어오면 어느 쪽으로도 분류가 안 되는 데이터가 생길 수 있다.
7. FK 제약이 없어서(0.2절) DB가 참조 무결성을 검사하지 않는다. 지금은 생성 스크립트로만 데이터를 만들어서 문제가 없지만, 사람이 수동으로 데이터를 추가/수정하는 단계가 생기면 실수로 존재하지 않는 `person_id`/`org_id` 등을 참조 컬럼에 넣어도 DB가 막아주지 못한다.
8. ID가 `VARCHAR(5)` 짧은 코드라 테이블당 최대 9,999건까지만 표현 가능하다. 지금 목업(최대 57건)엔 문제없지만, 실제 프로덕션 규모로 확장하면 자릿수를 늘려야 한다.

**주의**: `mock_hr.skill`/`mock_hr.worker_skill` 같은 테이블명은 원본 조사 문서에서 이미 SUPERSEDED(사용 안 함)로 명시된 설계이므로, 개념(검증 상태, 신뢰도 등)만 참고하고 테이블명·물리 스키마 자체는 채택하지 않았다.