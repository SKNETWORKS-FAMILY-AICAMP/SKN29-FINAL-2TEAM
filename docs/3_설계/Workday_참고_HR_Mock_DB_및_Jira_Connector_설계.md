# Workday 참고 자료 및 Jira Connector 조사 설계

> **문서 상태: 참고 조사 이력(SUPERSEDED)**  
> 현재 구현 기준은 `기획서_v5_AI프로젝트운영코파일럿.md`와 `Canonical Data Model` 폴더의 문서다. 1차 구현에서는 PostgreSQL **People DB**의 `person`, `organization`, `responsibility_level`, `skill`, `person_skill`, `work_schedule`, `person_absence`, `external_identity` 테이블을 사용한다. 아래의 `mock_hr.*`, HR Mock DB, OrgGraph 설계는 구현하지 않으며 Workday 관련 내용은 향후 실제 HR Connector 검토용 참고 자료로만 사용한다. Jira Connector 조사 내용은 현재 구현 참고로 유효하다.

- 작성일: 2026-07-22
- 적용 대상: AI 프로젝트 운영 코파일럿
- 목적: Workday 데이터 구조를 참고한 내부 HR Mock DB와 실제 Jira Connector의 데이터 수집·정규화 기준을 정의한다.

## 1. 설계 방향

본 프로젝트는 HR 데이터와 Jira 데이터를 다음과 같이 분리하여 구현한다.

```text
내부 HR Mock DB
→ HR Repository
→ PersonSnapshot / OrgGraph
                         ↘
                          Identity Mapping
                         ↗
실제 Jira Connector
→ Discovery / Issue Read
→ ExistingTaskSnapshot
```

- HR 데이터는 Workday의 Worker·Supervisory Organization 구조를 참고해 PostgreSQL `mock_hr` 스키마로 구성한다.
- HR Mock DB의 FTE·숙련도·부재 기간·책임수준은 추천에 필요한 내부 정규화 필드다.
- 실제 Workday의 특정 REST 응답과 동일한 필드라고 설명하지 않는다.
- Jira는 실제 Jira Cloud Connector를 연결하고, 고객사별 프로젝트·필드·보드 설정을 Discovery한 후 조회한다.
- HR 데이터와 Jira 사용자는 별도의 Identity Mapping으로 연결한다.

## 2. Workday 공식 구조에서 확인한 범위

Workday의 공개 Workers 및 Supervisory Organizations 문서에서 다음 구조를 확인할 수 있다.

| 구분 | 확인 가능한 값 | 프로젝트 활용 |
| --- | --- | --- |
| Worker | `id`, `descriptor` | 직원 식별자·표시명 |
| 업무 정보 | `businessTitle`, `primaryWorkEmail` | 역할 표시·사용자 매핑 |
| 관리자 | `isManager` | 관리자 여부 |
| 조직 | `primarySupervisoryOrganization` | 주 소속 조직 |
| 근무 위치 | `location` | 위치·시간대 조건의 기준 |
| 조직 관리자 | Supervisory Organization의 `manager` | 조직도 생성 |
| 직속 부하 | `/workers/{id}/directReports` | 관리자·직속 부하 관계 |
| 휴가 잔여량 | `timeOffSummary` | 참고 정보 |

다음 항목은 기본 Workers REST 응답만으로 확정하기 어렵다.

- 재직 상태
- FTE
- 기준·예정 근무시간
- 실제 휴가 시작일·종료일과 승인 상태
- 직원이 실제로 보유한 Skill과 숙련도
- 책임수준·직급 체계
- 근무 시간대

실제 Workday 연동 시에는 SOAP `Get_Workers`, Workday Query Language(WQL), Reports-as-a-Service(RaaS), Absence/Staffing 서비스 또는 고객사별 보고서의 추가 검증이 필요하다.

## 3. PostgreSQL HR Mock DB

### 3.1 스키마

```sql
CREATE SCHEMA IF NOT EXISTS mock_hr;
```

권장 테이블은 다음과 같다.

```text
mock_hr.worker
mock_hr.supervisory_organization
mock_hr.job_profile
mock_hr.job_assignment
mock_hr.responsibility_level
mock_hr.location
mock_hr.skill
mock_hr.worker_skill
mock_hr.work_capacity
mock_hr.absence
```

모든 주요 테이블은 멀티테넌트 확장을 고려해 `tenant_id`를 포함한다.

### 3.2 `mock_hr.worker`

| 필드 | 타입 예시 | 필수 여부 | 의미 |
| --- | --- | --- | --- |
| `tenant_id` | `varchar(50)` | 필수 | 고객사 식별자 |
| `worker_id` | `varchar(50)` | 필수 | 내부 직원 식별자 |
| `employee_number` | `varchar(50)` | 선택 | 사번 |
| `descriptor` | `varchar(200)` | 필수 | 직원 표시명 |
| `primary_work_email` | `varchar(320)` | 조건부 필수 | Jira·Google 사용자 매핑 후보 |
| `employment_status` | `varchar(30)` | 필수 | `ACTIVE`, `LEAVE`, `TERMINATED` |
| `primary_org_id` | `varchar(50)` | 필수 | 주 소속 조직 |
| `primary_job_assignment_id` | `varchar(50)` | 필수 | 주 직무 배정 |
| `location_id` | `varchar(50)` | 선택 | 근무 위치 |
| `is_manager` | `boolean` | 필수 | 관리자 여부 |
| `hire_date` | `date` | 선택 | 입사일 |
| `termination_date` | `date` | 선택 | 퇴사일 |
| `source_updated_at` | `timestamptz` | 필수 | HR 데이터 변경 시각 |

`employment_status`, 입·퇴사일 등은 프로젝트에 필요한 내부 정규화 필드다.

### 3.3 `mock_hr.supervisory_organization`

| 필드 | 타입 예시 | 의미 |
| --- | --- | --- |
| `tenant_id` | `varchar(50)` | 고객사 식별자 |
| `org_id` | `varchar(50)` | 조직 식별자 |
| `org_name` | `varchar(200)` | 조직명 |
| `org_type` | `varchar(30)` | `TEAM`, `DEPARTMENT`, `DIVISION` 등 |
| `parent_org_id` | `varchar(50)` | 상위 조직 |
| `manager_worker_id` | `varchar(50)` | 조직 관리자 |
| `active` | `boolean` | 활성 조직 여부 |
| `source_updated_at` | `timestamptz` | 변경 시각 |

조직도 생성 시 `parent_org_id`로 계층을 만들고, `manager_worker_id`로 관리자 관계를 연결한다.

### 3.4 `mock_hr.job_profile`

| 필드 | 타입 예시 | 의미 |
| --- | --- | --- |
| `tenant_id` | `varchar(50)` | 고객사 식별자 |
| `job_profile_id` | `varchar(50)` | 직무 프로필 식별자 |
| `job_code` | `varchar(50)` | 직무 코드 |
| `job_name` | `varchar(200)` | 직무명 |
| `job_family` | `varchar(100)` | 직무군 |
| `default_responsibility_level_id` | `varchar(50)` | 기본 책임수준 |
| `active` | `boolean` | 활성 여부 |

### 3.5 `mock_hr.job_assignment`

| 필드 | 타입 예시 | 의미 |
| --- | --- | --- |
| `tenant_id` | `varchar(50)` | 고객사 식별자 |
| `assignment_id` | `varchar(50)` | 직무 배정 식별자 |
| `worker_id` | `varchar(50)` | 직원 식별자 |
| `job_profile_id` | `varchar(50)` | 직무 프로필 |
| `business_title` | `varchar(200)` | 현재 직책 |
| `responsibility_level_id` | `varchar(50)` | 책임수준·직급 |
| `employment_type` | `varchar(30)` | `FULL_TIME`, `PART_TIME`, `CONTRACTOR` |
| `primary_flag` | `boolean` | 주 직무 여부 |
| `effective_from` | `date` | 적용 시작일 |
| `effective_to` | `date` | 적용 종료일 |

직원과 직무 배정을 분리하여 겸직과 직무 변경 이력을 처리할 수 있게 한다.

### 3.6 `mock_hr.responsibility_level`

| 필드 | 타입 예시 | 의미 |
| --- | --- | --- |
| `tenant_id` | `varchar(50)` | 고객사 식별자 |
| `level_id` | `varchar(50)` | 책임수준 식별자 |
| `level_code` | `varchar(30)` | 예: `L1`, `L2`, `LEAD` |
| `level_name` | `varchar(100)` | 표시명 |
| `level_rank` | `integer` | 비교 가능한 순위 |
| `active` | `boolean` | 활성 여부 |

추천 제약조건에서 요구 책임수준 이상인지 비교할 때 `level_rank`를 사용한다.

### 3.7 `mock_hr.location`

| 필드 | 타입 예시 | 의미 |
| --- | --- | --- |
| `tenant_id` | `varchar(50)` | 고객사 식별자 |
| `location_id` | `varchar(50)` | 위치 식별자 |
| `location_name` | `varchar(200)` | 위치명 |
| `country_code` | `varchar(10)` | 국가 코드 |
| `timezone` | `varchar(100)` | IANA 시간대 |
| `work_mode` | `varchar(30)` | `OFFICE`, `REMOTE`, `HYBRID` |

### 3.8 `mock_hr.skill` 및 `mock_hr.worker_skill`

`mock_hr.skill`:

| 필드 | 타입 예시 | 의미 |
| --- | --- | --- |
| `tenant_id` | `varchar(50)` | 고객사 식별자 |
| `skill_id` | `varchar(50)` | Skill 식별자 |
| `skill_name` | `varchar(200)` | Skill명 |
| `normalized_name` | `varchar(200)` | 정규화된 Skill명 |
| `category` | `varchar(100)` | Skill 분류 |

`mock_hr.worker_skill`:

| 필드 | 타입 예시 | 의미 |
| --- | --- | --- |
| `tenant_id` | `varchar(50)` | 고객사 식별자 |
| `worker_id` | `varchar(50)` | 직원 |
| `skill_id` | `varchar(50)` | Skill |
| `proficiency_level` | `integer` | 숙련도. 값이 없으면 `NULL` |
| `verification_status` | `varchar(30)` | `VERIFIED`, `SELF_REPORTED`, `UNKNOWN` |
| `confidence` | `numeric(5,4)` | Skill 정보 신뢰도 |
| `source_type` | `varchar(30)` | `HR`, `RESUME`, `AI_INFERRED`, `USER_ADDED` |
| `last_verified_at` | `timestamptz` | 최종 검증 시각 |

Skill 또는 숙련도가 없으면 불충족으로 단정하지 않고 `UNKNOWN` 조건부 후보로 처리한다.

### 3.9 `mock_hr.work_capacity`

| 필드 | 타입 예시 | 의미 |
| --- | --- | --- |
| `tenant_id` | `varchar(50)` | 고객사 식별자 |
| `worker_id` | `varchar(50)` | 직원 |
| `effective_from` | `date` | 적용 시작일 |
| `effective_to` | `date` | 적용 종료일 |
| `default_weekly_hours` | `numeric(6,2)` | 회사 기준 주당 시간 |
| `scheduled_weekly_hours` | `numeric(6,2)` | 직원 예정 주당 시간 |
| `fte` | `numeric(5,4)` | FTE |
| `capacity_override_hours` | `numeric(6,2)` | 별도 용량 조정 |
| `timezone` | `varchar(100)` | 근무 시간대 |

권장 계산식:

```text
FTE = scheduled_weekly_hours / default_weekly_hours

총 근무용량 = scheduled_weekly_hours
유효 가용용량 = 총 근무용량 - 휴가·부재 - 고정 일정
잔여 가용시간 = 유효 가용용량 - 기존 업무 잔여 공수
부하율 = 현재 할당량 / 유효 가용용량
```

- 유효 가용용량이 0이면 부하율 계산은 `BLOCKED` 처리한다.
- 부하율이 100%를 초과하면 과부하 위험으로 표시한다.
- `scheduled_weekly_hours`에 이미 FTE가 반영된 경우 FTE를 다시 곱하지 않는다.

### 3.10 `mock_hr.absence`

| 필드 | 타입 예시 | 의미 |
| --- | --- | --- |
| `tenant_id` | `varchar(50)` | 고객사 식별자 |
| `absence_id` | `varchar(50)` | 부재 식별자 |
| `worker_id` | `varchar(50)` | 직원 |
| `absence_type` | `varchar(30)` | `PAID_LEAVE`, `SICK_LEAVE`, `BUSINESS_TRIP`, `LEAVE_OF_ABSENCE` |
| `start_at` | `timestamptz` | 시작 시각 |
| `end_at` | `timestamptz` | 종료 시각 |
| `absence_hours` | `numeric(6,2)` | 가용시간 차감 시간 |
| `status` | `varchar(30)` | `REQUESTED`, `APPROVED`, `CANCELLED` |
| `source_updated_at` | `timestamptz` | 변경 시각 |

`timeOffSummary`는 휴가 잔여량이므로 기간별 가용시간 계산에 직접 사용하지 않는다. 실제 가용시간 계산에는 기간별 부재 데이터가 필요하다.

## 4. HR Repository와 PersonSnapshot 매핑

HR Repository는 `mock_hr` 테이블을 조회해 추천에 필요한 형태로 정규화한다.

```text
mock_hr.worker
+ supervisory_organization
+ job_assignment / job_profile
+ responsibility_level
+ worker_skill / skill
+ work_capacity
+ absence
+ location
→ PersonSnapshot
```

`PersonSnapshot` 권장 필드:

```json
{
  "personId": "W-001",
  "employeeNumber": "E-1001",
  "displayName": "김철수",
  "workEmail": "kim@example.com",
  "employmentStatus": "ACTIVE",
  "organizationId": "ORG-PLATFORM",
  "managerPersonId": "W-010",
  "jobProfileId": "JOB-BACKEND",
  "businessTitle": "Backend Engineer",
  "responsibilityLevel": {
    "code": "L3",
    "rank": 3
  },
  "skills": [
    {
      "skillId": "SK-PYTHON",
      "name": "Python",
      "proficiencyLevel": 4,
      "verificationStatus": "VERIFIED",
      "confidence": 0.95
    }
  ],
  "capacity": {
    "defaultWeeklyHours": 40,
    "scheduledWeeklyHours": 40,
    "fte": 1.0,
    "timezone": "Asia/Seoul"
  },
  "absences": [],
  "asOf": "2026-07-22T09:00:00+09:00",
  "sourceVersion": "mock-hr-20260722-01"
}
```

## 5. 조직도 생성 기준

```text
supervisory_organization.parent_org_id
→ 조직 계층 생성

supervisory_organization.manager_worker_id
→ 조직 관리자 연결

worker.primary_org_id
→ 직원 소속 연결
```

검증 규칙:

- 존재하지 않는 상위 조직을 참조하면 `BLOCKED`
- 조직 계층 순환이 발견되면 `BLOCKED`
- 조직 관리자와 Worker가 매핑되지 않으면 해당 조직은 `PARTIAL_RESULT`
- 동일 Worker가 여러 주 조직을 가지면 충돌로 기록하고 PM 또는 관리자의 확인을 요청한다.
- `employment_status != ACTIVE`인 직원은 기본 후보군에서 제외한다.

## 6. Jira Connector

### 6.1 최초 연결 Discovery

| 순서 | API | 목적 |
| ---: | --- | --- |
| 1 | `GET /rest/api/3/field` | 시스템·커스텀 필드 발견 |
| 2 | `GET /rest/api/3/project/search` | 접근 가능한 프로젝트 확인 |
| 3 | `GET /rest/api/3/users/search` | 전체 Jira 사용자 확인 |
| 4 | `GET /rest/api/3/user/search?query=` | 특정 사용자·`accountId` 검색 |
| 5 | `GET /rest/agile/1.0/board` | 프로젝트 보드 확인 |
| 6 | `GET /rest/agile/1.0/board/{boardId}/configuration` | Scrum/Kanban, 추정 방식·필드 확인 |
| 7 | `GET /rest/agile/1.0/board/{boardId}/sprint` | Sprint 지원 여부 확인 |

Story Point·시작일·Sprint·Team 등은 사이트마다 필드 ID가 다르므로 Discovery 결과를 저장해야 한다.

### 6.2 Discovery 결과 저장

```text
integration.jira_connection
integration.jira_field_mapping
integration.jira_project_config
integration.jira_board_config
```

`integration.jira_connection`:

| 필드 | 의미 |
| --- | --- |
| `tenant_id` | 고객사 식별자 |
| `cloud_id` | Jira Cloud 식별자 |
| `base_url` | Jira 사이트 URL |
| `auth_status` | 인증 상태 |
| `last_discovered_at` | 마지막 Discovery 시각 |
| `last_successful_sync_at` | 마지막 성공 동기화 시각 |

`integration.jira_field_mapping`:

| 필드 | 의미 |
| --- | --- |
| `tenant_id` | 고객사 식별자 |
| `project_id` | 프로젝트 ID |
| `logical_field` | 내부 논리 필드명 |
| `jira_field_id` | Jira 실제 필드 ID |
| `jira_field_name` | Jira 표시명 |
| `schema_type` | 필드 타입 |
| `required_for_feature` | 필요한 기능 |
| `verified_at` | 검증 시각 |

`logical_field` 예시:

```text
START_DATE
DUE_DATE
STORY_POINTS
SPRINT
TEAM
ORIGINAL_ESTIMATE
REMAINING_ESTIMATE
TIME_SPENT
```

`integration.jira_board_config`:

| 필드 | 의미 |
| --- | --- |
| `board_id` | 보드 ID |
| `project_id` | 프로젝트 ID |
| `board_type` | `SCRUM`, `KANBAN` |
| `estimation_type` | `TIME`, `STORY_POINTS`, `ISSUE_COUNT`, `NONE` |
| `estimation_field_id` | 추정 필드 ID |
| `sprint_supported` | Sprint 지원 여부 |

### 6.3 기존 업무 조회

기본 이슈 조회는 Enhanced JQL Search를 사용한다.

```http
POST /rest/api/3/search/jql
```

조회 대상 필드:

```text
id
key
summary
project
assignee
status
priority
created
updated
duedate
timetracking
timeoriginalestimate
timeestimate
timespent
START_DATE로 매핑된 custom field
STORY_POINTS로 매핑된 custom field
SPRINT로 매핑된 custom field
```

필드 ID는 고정하지 않고 `jira_field_mapping` 결과를 사용한다.

보드·Sprint 이슈 목록은 Jira Software Enhanced API 사용을 고려한다.

```http
GET /rest/software/1.0/board/{boardId}/issue
GET /rest/software/1.0/board/{boardId}/sprint/{sprintId}/issue
```

- 페이지네이션은 `nextPageToken`을 사용한다.
- Enhanced 목록 API는 전체 `total`을 반환하지 않을 수 있다.
- 이슈 수가 필요하면 전용 approximate-count API를 사용한다.

상세 Worklog는 필요한 경우에만 조회한다.

```http
GET /rest/api/3/issue/{issueIdOrKey}/worklog
```

Time Tracking이 비활성화되었거나 권한이 없으면 Worklog 기반 계산을 사용하지 않는다.

## 7. ExistingTaskSnapshot 매핑

```json
{
  "taskId": "10001",
  "issueKey": "AI-101",
  "projectId": "10010",
  "assigneeAccountId": "abc123",
  "status": "IN_PROGRESS",
  "statusCategory": "IN_PROGRESS",
  "priority": "HIGH",
  "startAt": "2026-07-20",
  "dueAt": "2026-07-30",
  "originalEstimateSeconds": 144000,
  "remainingEstimateSeconds": 72000,
  "timeSpentSeconds": 72000,
  "storyPoints": 8,
  "sprintId": 37,
  "updatedAt": "2026-07-22T10:00:00Z",
  "sourceVersion": "jira-updated-at",
  "dataStatus": "SUCCESS"
}
```

공수 계산 모드:

```text
Time Tracking 사용 가능
→ HOURS

시간 데이터 없음 + Story Point 필드 확인
→ POINTS

시간·Story Point 모두 없음
→ PROXY + PARTIAL_RESULT
```

Velocity는 Jira 원본 필드로 저장하지 않는다. 완료 Sprint의 추정값 합계와 Sprint 수를 이용해 계산하는 파생 데이터로 관리한다.

## 8. Identity Mapping

HR 직원과 Jira 사용자는 별도의 매핑 테이블로 연결한다.

```text
integration.identity_mapping
- tenant_id
- person_id
- external_system
- external_account_id
- email_snapshot
- match_method
- mapping_status
- confidence
- confirmed_by
- confirmed_at
- updated_at
```

매핑 우선순위:

```text
MANUAL_CONFIRMED
→ 기존 저장된 Jira accountId
→ 확인된 업무 이메일 정확 일치
→ 후보 매핑
→ UNMAPPED
```

- Jira 이메일은 개인정보 설정 때문에 숨겨질 수 있으므로 이메일만으로 매핑을 강제하지 않는다.
- Jira에서는 `accountId`를 최종 외부 식별자로 사용한다.
- 매핑 충돌 또는 동명이인은 자동 확정하지 않는다.
- 관리자가 수동 확정·해제할 수 있어야 한다.
- 매핑 실패 시 전체 요청을 중단하지 않고 해당 직원의 Jira 업무량을 제외한 `PARTIAL_RESULT`로 전달한다.

## 9. Feature Readiness Check 기준

### 9.1 조직도 생성

필수 데이터:

- `worker.worker_id`
- `worker.primary_org_id`
- `supervisory_organization.org_id`
- `supervisory_organization.parent_org_id`
- `supervisory_organization.manager_worker_id`

조직 참조 오류나 계층 순환이 있으면 `BLOCKED` 처리한다.

### 9.2 후보 생성

필수 데이터:

- 직원 식별자
- 재직 상태
- 역할·직무
- 소속 조직

조건부 필수 데이터:

- Task가 책임수준을 요구하면 `responsibility_level`
- Task가 필수 Skill을 요구하면 `worker_skill`

Skill 데이터가 없으면 불충족으로 단정하지 않고 `UNKNOWN` 조건부 후보로 처리한다.

### 9.3 업무 부하 계산

필수 데이터:

- `scheduled_weekly_hours` 또는 계산 가능한 근무용량
- 계산 대상 기간
- 기존 Jira 업무의 담당자·기간·잔여 공수 또는 대체 추정값

선택·보완 데이터:

- 기간별 휴가·부재
- Google Calendar 일정
- 고정 회의시간

Jira Time Tracking이 없으면 Story Point 또는 Proxy 모드로 전환하고 제한 사항을 표시한다.

### 9.4 Identity Mapping

- HR 직원과 Jira `accountId` 매핑 성공: 해당 직원의 Jira 업무량 포함
- 매핑 실패: 해당 직원의 Jira 업무량 제외 + `PARTIAL_RESULT`
- 여러 Jira 계정이 동일 직원과 연결: 충돌 처리 후 수동 확인 전까지 확정하지 않음

### 9.5 FeatureReadinessResult

```json
{
  "featureId": "WORKLOAD_ANALYSIS",
  "status": "PARTIAL_RESULT",
  "executableFunctions": ["HR_CAPACITY", "ORG_CONSTRAINT"],
  "blockedFunctions": [],
  "missingData": ["JIRA_IDENTITY_MAPPING:W-019"],
  "limitations": ["W-019의 Jira 업무량 제외"],
  "assumptions": [],
  "confidence": 0.78,
  "remediationActions": [
    {
      "action": "CONFIRM_IDENTITY_MAPPING",
      "owner": "PM_OR_ADMIN"
    }
  ],
  "checkedAt": "2026-07-22T11:00:00+09:00",
  "policyVersion": "policy-v1",
  "snapshotVersion": "snapshot-v1"
}
```

## 10. 동기화 기준

### 10.1 HR Mock DB

- `source_updated_at`을 기준으로 변경 데이터를 조회한다.
- 추천 요청이 시작되면 해당 시점의 `PersonSnapshot`과 조직 데이터를 고정한다.
- 추천 실행 중 HR 원천 데이터가 바뀌어도 현재 실행에는 자동 반영하지 않는다.
- PM이 새로고침을 요청하거나 TTL이 만료되면 새 Snapshot을 생성한다.

### 10.2 Jira

- 초기 동기화는 프로젝트 범위의 전체 JQL 조회로 수행한다.
- 이후 동기화는 `updated` 기준과 중복 허용 구간을 사용한다.
- 페이지네이션은 `nextPageToken`을 저장하며 순차적으로 처리한다.
- 마지막 동기화 시각과 약간 겹치는 조회 구간을 사용해 경계 시점 누락을 방지한다.
- 동일 이슈는 `issueId + updatedAt` 기준으로 멱등 upsert한다.
- Jira API 오류와 Rate Limit은 재시도하고, 최대 횟수 초과 시 최신성 제한을 포함한 `PARTIAL_RESULT` 또는 `BLOCKED`로 전달한다.

## 11. 최종 구현 경계

| 영역 | 구현 방식 | 출력 |
| --- | --- | --- |
| HR | PostgreSQL `mock_hr` | `PersonSnapshot`, `OrgGraph` |
| Jira | 실제 Jira Cloud Connector | `ExistingTaskSnapshot` |
| 사용자 연결 | Identity Mapping | `personId ↔ accountId` |
| 데이터 판정 | Feature Readiness Check | `FeatureReadinessResult` |
| 업무량 계산 | 규칙·수식 기반 코드 | `WorkloadResult` |
| 추천 | 후보 생성·적합도·충돌 분석 | `RecommendationResult` |
| Jira 쓰기 | 중간평가 이후 확장 | 승인된 배정 반영 |

## 12. 구현 우선순위

1. `mock_hr` 테이블 DDL 확정
2. 중간발표용 HR Seed 데이터 작성
3. HR Repository 및 `PersonSnapshot` 매핑 구현
4. Jira 인증 및 Discovery 구현
5. Jira Field Mapping 저장 구조 구현
6. Enhanced JQL Search 기반 Issue Read 구현
7. `ExistingTaskSnapshot` 정규화 구현
8. Identity Mapping 구현
9. Feature Readiness Check 구현
10. Workload·Recommendation·Validation 종단 시나리오 연결

## 13. 공식 참고자료

### Workday

- [Reference: Workers](https://developer.workday.com/documentation/dan1370797991225)
- [Reference: Supervisory Organizations](https://developer.workday.com/documentation/dan1370797989680/ReferenceSupervisoryOrganizations)
- [Workday REST API Fundamentals](https://developer.workday.com/documentation/GUID-85810465-bcfb-4fdf-a26d-55eaff3968a8-enHYPHENus/)
- [Get Workers SOAP Guide](https://developer.workday.com/documentation/GUID-1f289b82-801e-434e-9e5a-aef66bc35179/GetWorkers)
- [Workday Query Language](https://developer.workday.com/documentation/GUID-6546152a-bcf0-447d-8d64-230f9e2ac291-enHYPHENus)
- [Skill Lookup REST APIs](https://developer.workday.com/documentation/GUID-3c1e275c-91ef-42bc-8c58-7e48164fd992/SkillLookupRESTAPIs)
- [Skill Inference REST API](https://developer.workday.com/documentation/GUID-c4c74d93-4b44-4fef-bfcd-5439a89432e5-enHYPHENus/SkillInferenceRESTAPI)

### Jira

- [Jira Cloud REST API v3](https://developer.atlassian.com/cloud/jira/platform/rest/v3/intro/)
- [Issue Fields](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-fields/)
- [Issue Search](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/)
- [Projects](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-projects/)
- [User Search](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-user-search/)
- [Issue Worklogs](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-worklogs/)
- [Jira Software Board API](https://developer.atlassian.com/cloud/jira/software/rest/api-group-board/)
- [Jira Software Sprint API](https://developer.atlassian.com/cloud/jira/software/rest/api-group-sprint/)
- [Jira Software Changelog](https://developer.atlassian.com/cloud/jira/software/changelog/)
