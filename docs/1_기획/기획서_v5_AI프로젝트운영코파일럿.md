# AI 프로젝트 운영 코파일럿 기획서 v5

> 문서 상태: 프로젝트 통합 기획서  
> 작성일: 2026-07-24  
> 대상: 100~300명 규모 개발 프로젝트를 운영하는 대기업 PMO, 컨설팅사, SI사  
> 제품 범위: 데이터 연결·검증, 업무 추출, 업무량 분석, 담당자 추천, 추천 결과 검증, PM 의사결정 지원

관련 설계 보드: [AI 프로젝트 운영 코파일럿 전체 흐름](https://www.figma.com/board/lJCWw2jKwewFjb5QC5SsSx/AI-%ED%94%84%EB%A1%9C%EC%A0%9D%ED%8A%B8-%EC%9A%B4%EC%98%81-%EC%BD%94%ED%8C%8C%EC%9D%BC%EB%9F%BF-%EC%A0%84%EC%B2%B4-%ED%9D%90%EB%A6%84?node-id=129-1132&t=ximbCPjlFbiceauC-1)

---

## 0. 기획서 요약

AI 프로젝트 운영 코파일럿은 조직·역량·업무량·일정·프로젝트 문서를 통합 분석하여 PM에게 업무별 담당자 후보와 검증 가능한 근거를 제공한다. 시스템은 업무를 자동 배정하지 않으며, 최종 결정은 PM이 승인·수정·반려한다.

본 기획서는 제품 목표, 사용자 흐름, 데이터 수집과 정규화, 비정형 문서 구조화, Project Knowledge Model, Task 추출, Feature Readiness, 업무량 계산, 후보 추천, 제약조건 검증, 화면 구성, 보안, 평가 및 개발 추진 계획을 하나의 기준으로 정의한다.

### 0.1 핵심 제품 결정

| 구분 | 결정 |
|---|---|
| 제품 성격 | AI가 추천·대안·근거·검증 결과를 제공하고 PM이 최종 결정 |
| 인력 데이터 | 1차 구현은 내부 PostgreSQL People DB에 합성 데이터를 구성하고 실제 HR Connector는 후속 확장 |
| 업무 추출 | EXTRACTED, GENERATED, USER_ADDED, AI_SUGGESTED_MISSING_TASK로 출처 구분 |
| 문서 처리 | 다운로드 → 원본 저장 → 구조 보존 파싱 → Document Block → 의미 분류·정보 추출 → 통합·클러스터링 → Project Knowledge Model |
| Vector 검색 | 전체 분석의 주축이 아니라 유사 정보 통합·과거 업무·원본 근거 검색을 보조 |
| 변경 감지 | Drive Changes API의 pageToken 기반 증분 동기화와 주기적 보정 |
| 데이터 검증 | 원천 검증 → Canonical 정규화 → AnalysisSnapshot 생성 → Feature Readiness → 추천 검증 |
| 추천 입력 | 추천 요청 직전 최신성을 확인하고 불변 Snapshot 생성 |
| 사용자 식별 | 내부 personId 중심 Identity Mapping, 외부 계정 매핑 실패는 영향 범위에 따라 부분 결과 처리 |
| 실행 제어 | Orchestrator가 병렬 실행·상태·재시도·사용자 승인 대기를 관리 |
| 저장 구조 | PostgreSQL + Vector DB + Object Storage 역할 분리 |
| 단계별 범위 | 1차 구현은 추천·검증 결과 출력까지, Jira 쓰기는 후속 단계 |

---

## 1. 프로젝트 개요

### 1.1 제품 정의

AI 프로젝트 운영 코파일럿은 조직·역량·현재 업무량·휴가·일정·프로젝트 문서를 함께 분석하여 PM에게 업무별 담당자 후보와 검증 가능한 근거를 제공하는 의사결정 지원 시스템이다.

완전 자동 업무 배정 시스템이 아니다. AI가 추천하더라도 최종 배정의 승인·수정·반려 권한과 책임은 PM에게 있다.

### 1.2 해결하려는 문제

- 직원·조직·직무·책임수준은 HR 계열 시스템에 있다.
- Skill과 숙련도는 인력 DB 또는 문서에 있다.
- 기존 프로젝트 업무량과 일정은 Jira에 있다.
- 휴가·출장·회의·근무 위치는 Calendar에 있다.
- 신규 프로젝트 역할·일정·업무는 Drive 문서에 비정형으로 있다.
- 회사별 근무일·공휴일·기준 근무시간·권한 정책이 다르다.

이 때문에 PM은 특정 인력에 업무를 집중시키거나 휴가·기존 마감·역할 제한을 놓치고, 추천 근거를 설명하기 어렵다.

### 1.3 핵심 가치

1. 분산된 프로젝트 운영 데이터를 동일한 기준으로 정규화한다.
2. 업무 적합도와 기간별 가용성을 함께 계산한다.
3. 추천 담당자와 최소 1명의 대안 후보를 제공한다.
4. 누락 데이터·가정·신뢰도·검증 상태·원본 근거를 표시한다.
5. PM의 승인·수정·반려를 모든 최종 결정 앞에 둔다.

### 1.4 비목표

- PM 승인 없는 자동 인사 결정
- 성과 평가·승진·보상 자동화
- 1차 구현 단계의 실제 HR/Workday API 연동
- 모든 사내 문서의 무차별 수집
- 1차 구현 단계의 Jira 자동 쓰기
- Skill 정보 부재를 곧바로 역량 부족으로 판정하는 것

---

## 2. 타깃 사용자와 대표 시나리오

### 2.1 타깃 사용자

| 사용자 | 주요 목표 | 시스템에서 수행하는 작업 |
|---|---|---|
| PM/PMO | 일정·역량·가용성을 고려한 배정 | 문서 범위 선택, Task 확인, 추천 검토, 승인·수정·반려 |
| Delivery Manager | 인력 집중과 병목 통제 | 프로젝트 간 충돌·업무 집중·가용성 확인 |
| 프로젝트 운영자 | 데이터 연결과 품질 관리 | Connector 설정, 매핑 예외 처리, 동기화 상태 확인 |
| 감사·보안 담당자 | 근거와 변경 이력 확인 | 접근 기록, 추천 근거, PM 결정, 데이터 사용 범위 확인 |

### 2.2 대표 사용자 시나리오

1. 운영자가 내부 People DB의 준비 상태를 확인하고 Jira와 Google Drive를 연결한다.
2. 시스템이 원천 연결과 필드·형식·권한을 검사한다.
3. PM이 신규 프로젝트 문서가 있는 Drive 폴더 또는 파일 범위를 선택한다.
4. 문서 파이프라인이 문서 구조를 보존해 Block으로 변환하고 의미 정보를 추출·통합해 Project Knowledge Model을 생성한다.
5. 업무 추출 Agent와 결정론적 업무량 계산 모듈이 병렬 실행된다.
6. PM이 AI가 분해한 업무를 승인·수정·반려한다.
7. 확인된 NewTaskSnapshot과 WorkloadResult로 후보를 생성한다.
8. 검증 Agent가 필수 제약조건과 근거·누락·신뢰도를 검사한다.
9. 추천 담당자, 대안, 적합도, 업무 부하, 위험, 원본 근거, 검증 상태를 출력한다.
10. PM이 결과를 검토하고 DecisionRecord를 저장한다. Jira 반영은 후속 쓰기 기능이 활성화된 경우에만 실행한다.

---

## 3. 설계 원칙과 책임 경계

### 3.1 설계 원칙

- **Human-in-the-loop**: Task 분해 직후와 최종 배정 직전에 사람이 확인한다.
- **Evidence-first**: 추천 결론보다 근거·출처·Snapshot 시점을 함께 저장한다.
- **Deterministic where possible**: 시간·휴가·부하율·필수조건은 규칙과 수식으로 계산한다.
- **Bounded LLM**: LLM은 비정형 문서 해석과 PM용 설명에 사용하고 최종 제약 판정을 맡기지 않는다.
- **Partial degradation**: 선택 데이터 또는 외부 ID 매핑이 부족해도 가능한 범위의 결과를 제공한다.
- **Tenant-configurable policy**: 필수 필드, 가중치, 조직 제한, 기준 근무시간은 고객 정책으로 설정한다.
- **Traceability**: 입력 문서 청크, 계산식, 검증 결과, PM 조치를 추적할 수 있어야 한다.

### 3.2 LLM·코드·PM 역할

| 주체 | 담당 범위 | 담당하지 않는 범위 |
|---|---|---|
| LLM | 업무·역할·일정 추출, 의미 검색, 설명 생성, 누락 업무 제안 | 휴가 시간 계산, 필수조건 최종 판정, 자동 배정 확정 |
| 규칙·수식 코드 | 부하율, 가용시간, 일정 중복, 필수조건, 충돌, 준비도, 근거 존재 확인 | 비정형 문서 의미 해석 |
| PM | Task 분해 확인, 추천 승인·수정·반려, 예외 판단 | 시스템 계산과 출처 기록의 임의 삭제 |

---

## 4. 데이터 소스와 Connector 전략

### 4.1 데이터 소스별 역할

| 소스 | 수집 목적 | 주요 데이터 | 현재 범위 |
|---|---|---|---|
| 내부 People DB | 조직·인력 기준정보 | 직원, 조직, 직무, 재직, Skill, 숙련도, FTE, 근무시간, 휴가, 위치, 시간대, 책임수준 | 1차 구현(합성 데이터) |
| Jira | 기존 프로젝트 업무량과 일정 | 담당자, 상태, 우선순위, 날짜, 공수, Story Point, Sprint, Velocity, 갱신시각 | 읽기 우선 |
| Google Drive | 신규 프로젝트 업무와 근거 | 기획서, 요구사항, 명세서, 회의록, 이력서 | 선택 폴더/파일 |
| Google Calendar | 개인 가용성 보정 | 휴가, 출장, 미팅, 근무 위치 | 후속 확장 |
| 회사 정책 | 계산 기준 | 근무일, 공휴일, 기준 근무시간, 시간대, 조직·권한 제한 | 관리자 설정 |
| 실제 HR/Workday Connector | 운영 환경의 조직·인력 기준정보 | 고객사 HR 시스템에서 허용된 범위 | 후속 확장 |

### 4.2 내부 People DB와 합성 데이터 채택

1차 구현의 조직·인력 데이터는 PostgreSQL 내부 People DB에서 제공한다. 스키마는 향후 실제 HR 데이터도 수용할 수 있는 공통 구조로 설계하고, 중간 시연에서 저장하는 레코드만 합성 데이터로 구성한다. 애플리케이션의 People Repository가 테이블을 읽어 PersonSnapshot과 조직도 데이터를 생성한다.

| 물리 테이블 | 목적 | 주요 필드 |
|---|---|---|
| organization | 조직과 상하위 구조 | organization_id, parent_organization_id, name, status |
| person | 직원 기준정보 | person_id, employee_id, name, email, job_title, employment_status, responsibility_level_id, manager_person_id, location, timezone |
| person_organization | 직원 소속과 겸직 | person_id, organization_id, relation_type, valid_from, valid_to |
| skill | Skill 기준정보 | skill_id, skill_name, category |
| person_skill | 직원별 Skill과 숙련도 | person_id, skill_id, proficiency_level, verified_at |
| work_schedule | 근무시간과 FTE | person_id, effective_from, effective_to, weekly_hours, fte |
| person_absence | 휴가·휴직·부재 | person_id, absence_type, start_at, end_at, availability_impact |
| responsibility_level | 책임수준 기준 | responsibility_level_id, level_code, name, rank_order |
| identity_link | Jira·Google 사용자 매핑 | person_id, system_type, external_id, mapping_status |

People DB와 합성 데이터는 다음 원칙으로 관리한다.

- 모든 레코드에 created_at, updated_at, source_system, source_version을 둔다.
- 합성 여부는 테이블명이 아니라 `data_origin=SYNTHETIC`, `dataset_version`으로 구분한다.
- 테스트 시나리오별 Seed 데이터를 버전 관리한다.
- 추천 로직은 People DB 테이블을 직접 조회하지 않고 People Repository와 PersonSnapshot을 통해서만 접근한다.
- 향후 실제 HR/Workday Connector가 추가되어도 Snapshot 이후의 업무량·추천·검증 로직은 변경하지 않는다.
- 중간 시연 데이터는 실제 직원 정보가 아닌 비식별 합성 데이터만 사용한다.

#### People DB 합성 데이터 처리 흐름

~~~mermaid
flowchart LR
    A["시나리오별 합성 Seed 데이터"] --> B["PostgreSQL People DB"]
    B --> C["필수 컬럼·참조키·값 형식 검증"]
    C --> D["People Repository"]
    D --> E["PersonSnapshot 생성"]
    D --> F["조직도 관계 생성"]
    E --> G["Feature Readiness Check"]
    F --> G
    G --> H["업무량 분석·담당자 추천"]
~~~

합성 데이터 수정은 관리용 Seed 또는 제한된 내부 관리 기능을 통해 수행한다. 추천 요청 시 updated_at, source_version, dataset_version을 확인하고, 변경이 있으면 새로운 Snapshot을 생성한다.

### 4.3 Jira 최초 연결 Discovery

회사마다 필드와 프로젝트 구성이 다르므로 최초 연결 시 다음을 실행한다.

- /field: 공수·날짜·Story Point 필드 식별
- /project/search: 대상 프로젝트 범위 선택
- /users/search: 사용자와 accountId 확인
- /board: Scrum/Kanban 보드와 Sprint 구조 확인

결과는 고객별 ConnectorProfile에 저장하고 필드 매핑을 버전 관리한다.

### 4.4 외부 Connector 공통 계약

다음 계약은 Jira, Google Drive와 후속 Google Calendar·HR Connector에 적용한다. 내부 People DB에는 외부 인증·Rate Limit·페이지네이션을 적용하지 않는다.

- 인증 상태와 권한 범위 확인
- 연결 테스트와 원천 필드 탐색
- 전체·증분 동기화
- 페이지네이션과 Rate Limit 처리
- 원천 ID, 수정시각, 삭제·권한회수 상태 전달
- 원천 스키마 버전과 내부 매핑 버전 기록
- 재시도 가능한 오류와 사용자 조치 오류 구분

---

## 5. 저장소와 핵심 데이터 객체

### 5.1 저장소 역할 분리

| 저장소 | 저장 대상 | 선택 이유 |
|---|---|---|
| PostgreSQL | 사람, 조직, Skill, 업무, ID 매핑, 문서 구조, Project Knowledge Model, Snapshot, 추천·검증 결과 | 관계·정합성·버전·감사 |
| Vector DB(pgvector 또는 Chroma) | 검색 보조용 임베딩과 청크 메타데이터 | 유사 정보·과거 업무·원본 근거 검색 |
| Object Storage | 원본 PDF/DOCX/PPTX와 파싱 산출물 | 원본 보존, 재파싱, 근거 추적 |

초기 구현은 운영 단순성을 위해 PostgreSQL+pgvector를 우선 선택할 수 있다. Vector 인터페이스는 교체 가능하게 분리한다.

### 5.2 핵심 객체

| 객체 | 목적 | 주요 필드 |
|---|---|---|
| PersonSnapshot | 추천 시점 인력 상태 | personId, 조직, 직무, 책임수준, Skill, FTE, 근무시간, 휴가, 위치, ID 매핑 |
| ExistingTaskSnapshot | Jira 이슈를 통일된 업무 단위로 정규화 | 담당자, 기간, 상태, 예상·잔여·사용 공수, Story Point, Sprint, 일정 중복 |
| CalendarEventSnapshot | 후속 Calendar 연동 시 기간별 이벤트 반영 | 유형, 시작·종료, 참석 상태, 가용성 영향 |
| DocumentIndex | 문서·Block·검색 인덱스 상태 | 문서 ID, 파일 버전, Block, 메타데이터, ACL, 임베딩 버전 |
| KnowledgeItem | 문서에서 추출한 의미 정보 | objective, scope, requirement, decision, constraint, milestone, risk, acceptance, ownership |
| ProjectKnowledgeModel | 프로젝트 전체 지식의 통합 모델 | 지식 항목, Feature Cluster, 관계, 최신성, 출처 |
| NewTaskSnapshot | PM 확인을 마친 신규 업무 | 업무, 역할, 기간, 공수, 우선순위, 조건, 출처 |
| WorkloadResult | 사람·기간별 부하·가용성 계산 | 총 근무용량, 유효 가용용량, 현재 할당량, 잔여 가용시간, 부하율, 충돌, 계산 근거 |
| RecommendationResult | 업무별 추천과 대안 | 후보, 점수, 근거, 위험, 가정, 신뢰도, 출처 |
| ValidationResult | 데이터·제약·근거 검증 | PASS/CONDITIONAL_PASS/REJECT, 검사, 누락, 제한 |

### 5.3 공통 추적 필드

모든 Snapshot과 결과에는 tenantId, schemaVersion, mappingVersion, sourceUpdatedAt, lastSyncedAt, snapshotAsOf, createdAt, sourceRefs, dataReadinessStatus를 둔다.

---

## 6. Identity Mapping 설계

### 6.1 내부 식별자

추천과 감사의 기준은 외부 시스템 ID가 아닌 내부 personId다.

~~~text
personId
 ├─ HR_EMPLOYEE_ID
 ├─ WORK_EMAIL
 ├─ JIRA_ACCOUNT_ID
 ├─ GOOGLE_USER_ID
 └─ CALENDAR_ID
~~~

### 6.2 매핑 우선순위

1. 운영자가 확정한 기존 IdentityLink
2. People DB의 employee_id와 사전 등록 외부 ID
3. 검증된 회사 이메일 완전 일치
4. 이름+조직+직무의 복합 일치 후보
5. 수동 확인 대기

이름 단독 일치나 LLM 추정만으로 자동 확정하지 않는다.

| 상태 | 의미 | 추천 처리 |
|---|---|---|
| MATCHED | 단일 사용자로 확정 | 전체 계산 |
| CANDIDATE | 후보가 있으나 확인 필요 | 확인 후 사용 |
| AMBIGUOUS | 복수 후보 | 관련 부하 계산 차단 또는 조건부 |
| UNMATCHED | 대응 ID 없음 | 해당 소스 데이터만 제외 |
| CONFLICT | 서로 다른 사람으로 연결된 정황 | 자동 사용 금지 |

People DB의 employee_id와 Jira accountId 매핑이 실패해도 전체 흐름을 중단하지 않는다. 해당 직원의 Jira 업무량을 확인할 수 없음을 PARTIAL_RESULT 근거로 기록하고 신뢰도를 낮춘다. 단, 고객 정책상 Jira 업무량이 필수면 해당 기능은 BLOCKED다.

- 매핑은 유효 시작·종료 시각을 가진다.
- 합치기·분리·수동 확정은 감사 로그에 남긴다.
- 기존 추천은 당시 매핑 버전을 유지한다.
- 매핑 변경 후 관련 Snapshot은 재생성 대상으로 표시한다.

---

## 7. 조직도 생성 로직

### 7.1 입력 우선순위

1. organization의 parent_organization_id
2. person의 manager_person_id
3. person_organization의 소속 관계
4. 운영자가 보완한 예외 관계
5. 문서 추출 조직 정보는 참고 근거로만 사용

### 7.2 생성 절차

~~~mermaid
flowchart LR
    A["조직·직원 원천 데이터 수집"] --> B["원천 필드·ID 형식 검증"]
    B --> C["조직 ID와 직원 ID 정규화"]
    C --> D["조직 상하위 엣지 생성"]
    C --> E["관리자-구성원 엣지 생성"]
    D --> F["충돌·순환·고아 노드 검사"]
    E --> F
    F --> G["예외 규칙 적용 또는 수동 확인"]
    G --> H["버전이 있는 OrganizationHierarchy 생성"]
~~~

### 7.3 정합성 규칙

- 한 직원은 한 시점에 하나의 주 소속 조직을 가진다. 겸직은 보조 관계로 표현한다.
- 자기 자신을 관리자로 참조할 수 없다.
- 관리자 그래프 순환은 CONFLICT로 분리한다.
- 상위 조직이 없는 조직은 루트 후보로 표시한다.
- 직원 레코드가 없는 관리자는 외부 관리자 노드로 보존한다.
- manager_id와 조직 소속·책임수준 데이터가 충돌하면 자동 확정하지 않고 예외를 남긴다.
- 퇴사자는 현재 조직도에서 제외하되 과거 Snapshot에는 유지한다.

출력 OrganizationHierarchy는 organizationNodes, personNodes, reportsToRelations, belongsToRelations, conflicts, sourceRefs, validFrom, snapshotAsOf를 포함한다. 이는 Graph DB가 아니라 PostgreSQL의 조직·직원 관계 테이블을 조회해 생성하는 논리 객체다.

---

## 8. Google Drive 문서 구조화와 보조 검색

### 8.1 수집 범위

운영자 또는 PM은 포함할 Drive 폴더·파일, 하위 폴더 포함 여부, 문서 역할, 제외 패턴, 보안 등급, 접근 그룹, 동기화 주기를 설정한다. 모든 Drive 문서를 수집하지 않으며 선택 범위와 원본 ACL을 모두 만족하는 문서만 처리한다.

### 8.2 전체 프로젝트 구조화 흐름

~~~mermaid
flowchart LR
    A["Google Drive 문서"] --> B["파일 목록·권한·버전 확인"]
    B --> C["파일 다운로드"]
    C --> D["원본 Object Storage 저장"]
    D --> E["PDF·DOCX 구조 보존 파싱"]
    E --> F["Document Block 생성"]
    F --> G["메타데이터·ACL·원본 위치 부착"]
    G --> H["의미 분류·정보 추출"]
    H --> I["동일 정보 통합·클러스터링"]
    I --> J["Project Knowledge Model"]
    J --> K["업무 구조 추출"]
    K --> L["NewTaskDraft"]
    G -.-> M["Embedding·Vector DB"]
    M -.-> H
~~~

### 8.3 파싱·청킹

| 형식 | 처리 | 보존 구조 |
|---|---|---|
| PDF | 텍스트·페이지 좌표 | 페이지, 제목, 표 위치 |
| DOCX | 문단·표·제목 계층 | heading path, 표, 문단 순서 |
| PPTX | 슬라이드 텍스트·노트 | 슬라이드 번호, 제목, 요소 순서(후속) |
| Google Docs | Drive export 또는 Docs API | 제목 계층, 문단, 표(후속) |
| 스캔 문서 | OCR | 페이지, 위치, OCR 신뢰도(후속) |

- Parent 단위인 Document Block은 제목·문단·표·목록 경계를 보존한다.
- 검색용 Child Chunk는 Block을 참조하며 기본 500~800 토큰, 중첩 80~120 토큰을 사용한다.
- 표는 헤더와 행 의미가 깨지지 않게 처리하고 요구사항 번호·일정 표 식별자를 보존한다.
- Project Knowledge Model 생성은 전체 선택 문서의 Block을 빠짐없이 대상으로 한다.
- 청크 해시가 같으면 임베딩을 다시 만들지 않는다.

### 8.4 메타데이터 계약

~~~json
{
  "tenantId": "TENANT001",
  "documentId": "DOC001",
  "driveFileId": "1AbCdEf",
  "fileName": "2026_AI_Project.pdf",
  "mimeType": "application/pdf",
  "department": "AI Platform",
  "owner": "PM 김철수",
  "createdAt": "2026-07-01T09:00:00+09:00",
  "modifiedAt": "2026-07-20T15:30:00+09:00",
  "version": "v3",
  "security": "Internal",
  "project": "AI Assistant",
  "documentRole": "PROJECT_PLAN",
  "page": 5,
  "blockId": "BLK-018",
  "chunk": 18,
  "headingPath": ["일정", "개발 2단계"],
  "contentHash": "sha256:...",
  "aclPrincipals": ["group:pmo@example.com"],
  "parserVersion": "parser-1.0",
  "embeddingVersion": "embed-1.0",
  "indexedAt": "2026-07-22T10:00:00+09:00"
}
~~~

Document Block은 원본 구조화와 출처 추적의 기준이며, Child Chunk는 검색 전용 파생 데이터다. Vector 고유 키는 tenantId:driveFileId:fileRevision:chunk:embeddingVersion으로 구성한다.

### 8.5 Project Knowledge Model 구성

LLM은 각 Document Block에서 다음 의미 유형을 구조화한다.

- objective, scope
- requirement
- decision, constraint
- milestone, dependency
- risk
- acceptance_criteria
- role_or_ownership

추출 결과는 KnowledgeItem으로 저장하고, 여러 문서에서 같은 기능이나 요구사항을 설명하는 항목은 FeatureCluster로 통합한다. 최신 버전·상충 관계·원본 출처를 함께 보존한 Project Knowledge Model이 Task 추출의 기준 입력이 된다.

### 8.6 AI의 보조 RAG 검색 절차

~~~mermaid
flowchart LR
    A["지식 모델 또는 특정 업무의 보완 필요"] --> B["검색 목적·Semantic Type 결정"]
    B --> C["tenant·project·ACL·문서 역할 필터"]
    C --> D["Vector 유사도 검색"]
    D --> E["키워드·요구사항 ID 검색 결합"]
    E --> F["재순위화·중복 제거"]
    F --> G["상위 청크와 인접 청크 구성"]
    G --> H["보완 근거·유사 과거 업무 확인"]
    H --> I["기존 지식·업무와 연결"]
    I --> J["문장·페이지·Block·Chunk 근거 연결"]
~~~

- Hybrid Search(Vector+키워드)를 사용한다.
- ACL과 tenantId는 검색 전에 필터링한다.
- RAG는 전체 문서 누락 여부를 판단하거나 프로젝트 전체 업무 구조를 직접 생성하지 않는다.
- 주요 용도는 유사한 표현 통합, 과거 Jira 업무 검색, 추가 근거 확인, PM의 근거 질의다.
- 각 구조화 필드와 Task는 최소 하나의 sourceRef를 가진다.
- 근거 없는 내용은 사실로 추출하지 않고 제안 업무 또는 assumption으로 구분한다.

---

## 9. Task 추출 및 분석 로직

### 9.1 Task 출처 유형

| 유형 | 의미 | 기본 처리 |
|---|---|---|
| EXTRACTED | 문서에 명시된 업무 구조화 | 원문 근거 필수 |
| GENERATED | 상위 요구를 실행 가능한 하위 업무로 분해 | 상위 요구 근거와 생성 이유 필수 |
| AI_SUGGESTED_MISSING_TASK | 문서에 없지만 의존성·품질상 필요하다고 AI가 제안 | 자동 확정 금지, PM 승인 필수 |
| USER_ADDED | PM이 직접 추가 | 사용자와 추가 사유 기록 |

### 9.2 추출 단계

1. 프로젝트 문서 범위와 문서 역할을 확인한다.
2. 선택 문서 전체에서 생성된 Project Knowledge Model의 목표·범위·요구사항·결정·제약·일정·위험·완료 조건·담당 영역을 확인한다.
3. LLM이 지식 항목과 Feature Cluster를 기준으로 Task 후보와 의존관계를 구조화한다.
4. 필요한 경우에만 RAG로 유사 표현·과거 Jira 업무·추가 원문 근거를 보완한다.
5. 코드가 필수 필드, 날짜, 공수 단위, 중복, 상하위 관계를 검사한다.
6. 유사 Task는 자동 삭제하지 않고 중복 후보로 묶는다.
7. 누락 필드는 문서 근거가 있으면 보정하고, 없으면 사용자 입력 대상으로 표시한다.
8. 의존성상 누락된 업무는 AI_SUGGESTED_MISSING_TASK로 분리한다.
9. NewTaskDraft를 PM 확인 화면에 제공한다.

### 9.3 NewTaskDraft 예시

~~~json
{
  "draftId": "NTD-001",
  "projectId": "PRJ-001",
  "title": "Jira 업무량 수집 Connector 구현",
  "description": "기존 프로젝트의 담당자별 잔여 공수와 일정을 정규화한다.",
  "sourceType": "GENERATED",
  "parentRequirementId": "REQ-12",
  "requiredRole": "Backend Engineer",
  "requiredSkills": [
    {"skill": "Jira REST API", "level": 3, "required": true}
  ],
  "responsibilityLevel": "IMPLEMENTER",
  "estimatedHours": 40,
  "startDate": "2026-08-03",
  "dueDate": "2026-08-14",
  "priority": "HIGH",
  "dependencies": ["NTD-000"],
  "assumptions": [],
  "confidence": 0.87,
  "sourceRefs": [
    {"documentId": "DOC001", "page": 5, "chunk": 18, "quoteHash": "sha256:..."}
  ]
}
~~~

### 9.4 PM 업무 분해 확인

| PM 조치 | 처리 |
|---|---|
| 승인 | Draft를 불변 NewTaskSnapshot으로 확정 |
| 수정 | Task명·역할·공수·일정·우선순위·조건을 수정하고 이력 저장 후 확정 |
| 반려 | 문서 또는 분해 조건을 보완한 뒤 다시 추출 |

PM 확인 이전에는 담당자 추천을 실행하지 않는다. 잘못 분해된 업무를 기준으로 추천하는 오류를 차단하기 위한 단계다.

---

## 10. 업무 분배 필수 데이터와 Feature Readiness

### 10.1 데이터 중요도

| 등급 | 정의 | 누락 시 처리 |
|---|---|---|
| 필수 | 기본 추천에 항상 필요 | BLOCKED |
| 조건부 필수 | 선택한 계산·정책·역할에 필요 | 해당 기능 또는 추천 BLOCKED |
| 선택 | 있으면 정확도와 설명력을 높임 | PARTIAL_RESULT |

### 10.2 업무 분배 필수 데이터

#### 사람·조직

| 구분 | 데이터 |
|---|---|
| 필수 | personId, 이름, 재직 상태, 주 소속 조직, 직무/역할, 책임수준, 기간별 근무 가능 상태 |
| 조건부 필수 | 필수 Skill과 숙련도, FTE/기준 근무시간, 휴가, 위치·시간대, 조직 제한, 권한 |
| 선택 | 근속기간, 자격증, 과거 유사 프로젝트, 선호 업무, 협업 관계 |

#### 기존 업무

| 구분 | 데이터 |
|---|---|
| 필수 | 업무 ID, 담당자 또는 매핑 상태, 상태, 제목, 최근 갱신시각 |
| 조건부 필수 | 시작일·마감일, 예상·잔여·사용 공수, Story Point, Sprint, Velocity |
| 선택 | 우선순위, 컴포넌트, 라벨, 변경 이력, Worklog, 의존성 |

#### 신규 업무

| 구분 | 데이터 |
|---|---|
| 필수 | 프로젝트, Task명, 설명, 필요 역할, 기간, 공수, 우선순위, PM 확인 상태 |
| 조건부 필수 | 필수 Skill, 책임수준, 권한, 조직 제한, 선행 업무, 위치·시간대 |
| 선택 | 산출물, 검토자, 저장소, 위험 라벨 |

#### 정책

| 구분 | 데이터 |
|---|---|
| 필수 | 기준 시간대, 근무일, 기준 근무시간, 추천 가중치 기본값 |
| 조건부 필수 | 공휴일, 최대 부하율, 조직 간 제한, 권한 규칙, 프로젝트 우선순위 정책 |

### 10.3 데이터 검증과 실행 순서

1. **원천 데이터 검증**: 연결 성공, 권한, 필드 존재, 값 형식, 페이지네이션, 수정시각, ID 중복을 정규화 전에 검사한다.
2. **Feature Readiness Check**: Snapshot 생성 후 요청 기능을 실행할 수 있는지 판단한다.

전체 실행 순서는 **원천 검증 → Canonical 정규화 → Identity Mapping → AnalysisSnapshot 생성 → Feature Readiness → Agent·계산 실행**으로 고정한다. Feature Readiness는 원천 레코드가 아니라 분석 시점에 고정된 Snapshot을 기준으로 판정한다.

Feature Readiness는 추천 정답 여부가 아니라 계산과 검증에 필요한 데이터가 준비되었는지를 평가한다.

### 10.4 상태 모델

| 내부 상태 | 화면 의미 | 처리 |
|---|---|---|
| SUCCESS | 준비 완료 | 전체 기능 실행 |
| PARTIAL_RESULT | 조건부 준비 | 제한·누락·가정과 함께 실행 |
| BLOCKED | 실행 차단 | 필수 데이터 또는 사용자 입력 보완 |

세부 사유는 READY, CONDITIONAL, NOT_READY, USER_INPUT_REQUIRED 코드로 표현한다.

### 10.5 기능별 검사

| 기능 | 필수 검사 | 실패 처리 |
|---|---|---|
| Skill 적합도 | Task 필수 Skill과 후보 Skill | Skill 없음은 불충족이 아니라 UNKNOWN, 조건부 후보 |
| 시간 기반 부하율 | FTE, 근무시간, 기간, 공수 | 시간 계산 차단, 대체 지표가 있으면 조건부 |
| Sprint 기반 부하율 | Story Point, Sprint, Velocity | Sprint 계산 차단, 시간 방식 검토 |
| 휴가 반영 | 휴가/Calendar와 기간 | 정책상 필수면 차단, 아니면 가정 표시 |
| 조직 제한 | 조직도와 조직 정책 | 판정 불가 시 차단 |
| Jira 업무량 | Jira ID 매핑과 업무 | 매핑 실패자는 PARTIAL_RESULT, 정책상 필수면 제외 |

모든 결과에는 missingData, limitations, assumptions, confidence, dataReadinessStatus, validationStatus를 표시한다.

---

## 11. Snapshot 생성 및 갱신

### 11.1 원칙

- 원천 실시간 조회 결과를 추천 로직에 직접 전달하지 않는다.
- 추천 요청 직전에 소스별 최신성을 확인하고 정규화 Snapshot을 만든다.
- 추천이 시작되면 입력 Snapshot은 변경하지 않는다.
- 원천 데이터가 바뀌어도 기존 추천은 당시 snapshotAsOf를 유지한다.
- 재추천 시 새 Snapshot과 새 결과를 만든다.

### 11.2 생성 트리거

| 트리거 | 처리 |
|---|---|
| 최초 Connector 연결 | 전체 동기화 후 초기 Snapshot |
| 추천 요청 | 최신성 확인, 필요한 소스만 증분 갱신 후 Snapshot |
| PM 수동 새로고침 | 대상 소스 즉시 동기화 후 새 Snapshot |
| 원천 변경 이벤트 | Source Registry 갱신, 관련 Snapshot을 STALE 후보로 표시 |
| 매핑·정책 변경 | 영향받는 Snapshot 재생성 |

### 11.3 소스별 기본 최신성

| 소스 | 데모 기본 기준 | 추천 요청 시 |
|---|---|---|
| 내부 People DB | 데이터 변경 즉시 | updated_at·source_version·dataset_version 기준 변경분 반영 |
| Jira | 15분 | 대상 프로젝트 갱신 |
| Calendar | 후속 연동 시 15분 | 추천 기간 이벤트 갱신 |
| Drive | 변경 이벤트 우선, 최대 60분 보정 | 대상 폴더 변경 확인 |
| 회사 정책 | 변경 즉시 | 정책 버전 변경 시 재검사 |

기준값은 고객사 설정으로 변경 가능하다.

### 11.4 시간 필드 구분

- sourceUpdatedAt: 원천 데이터 마지막 변경시각
- lastSyncedAt: Connector 마지막 동기화 시각
- snapshotAsOf: 추천 입력 데이터 기준시각
- pageToken/changeToken: 다음 변경분 조회 커서이며 Snapshot 시각이 아님

추천 결과는 사용한 모든 Snapshot ID, 정책 버전, 계산 버전을 저장해 재현 가능하게 한다.

---

## 12. 증분 인덱싱 및 동기화

### 12.1 Drive 신규·수정 파일 감지

~~~mermaid
flowchart LR
    A["최초 폴더 전체 조회"] --> B["Source Registry 생성"]
    B --> C["초기 pageToken 저장"]
    C --> D["Push 알림 또는 주기 실행"]
    D --> E["Changes API로 변경 목록 조회"]
    E --> F{"변경 유형"}
    F -->|"신규"| G["다운로드·파싱·청킹·인덱싱"]
    F -->|"수정"| H["새 revision 처리·이전 청크 비활성화"]
    F -->|"삭제"| I["검색 제외·보존정책 적용"]
    F -->|"권한 변경"| J["ACL 재계산"]
    G --> K["Registry·pageToken 갱신"]
    H --> K
    I --> K
    J --> K
~~~

Push 알림은 변경 사실만 알리므로 실제 변경 내역은 Changes API로 조회한다. 알림 누락에 대비해 주기적 보정 동기화를 함께 실행한다.

### 12.2 Source Registry

| 필드 | 의미 |
|---|---|
| sourceId | Drive file ID 등 원천 고유 ID |
| parentScopeId | 선택 폴더/프로젝트 |
| revisionId | 원천 버전 |
| contentHash | 내용 중복·변경 판단 |
| modifiedAt | 원천 수정시각 |
| syncStatus | NEW/PROCESSING/INDEXED/FAILED/REMOVED/ACCESS_REVOKED |
| lastProcessedAt | 마지막 처리시각 |
| retryCount | 재시도 횟수 |
| parserVersion | 파서 버전 |
| embeddingVersion | 임베딩 버전 |

### 12.3 멱등성·재시도·삭제

- 동일 revisionId와 처리 버전은 한 번만 인덱싱한다.
- 파싱과 임베딩은 독립적으로 재시도한다.
- 일시 오류는 자동 재시도하고 권한·암호화 문서·형식 오류는 사용자 조치 대상으로 보낸다.
- 삭제 파일은 검색에서 즉시 제외하고 원본·감사 데이터는 보존정책을 따른다.
- ACL 회수 시 해당 사용자의 검색 결과에서 즉시 제외한다.

### 12.4 다른 소스

- Jira: updated 기준 JQL과 마지막 성공 커서를 사용하고 삭제·권한 변경을 보정 조회한다.
- Calendar: 후속 연동 시 syncToken으로 이벤트 생성·변경·삭제를 반영한다.
- 내부 People DB: updated_at, source_version, dataset_version으로 변경분을 식별하고 Snapshot 재생성 대상을 표시한다.
- 체크포인트는 성공 후 커밋하며 실패 시 이전 체크포인트에서 재개한다.

---

## 13. 업무량·가용성과 추천 로직

### 13.1 기간별 가용용량과 부하율

~~~text
총 근무용량 = 기간 내 근무일 × 일 기준 근무시간 × FTE
유효 가용용량 = 총 근무용량 - 휴가·부재시간 - 고정 비프로젝트 일정시간
현재 할당량 = 해당 기간에 배분된 기존 업무 잔여시간
잔여 가용시간 = max(0, 유효 가용용량 - 현재 할당량)
현재 부하율 = 현재 할당량 / 유효 가용용량 × 100
배정 후 부하율 = (현재 할당량 + 신규업무 배정시간) / 유효 가용용량 × 100
~~~

- 공휴일과 개인 시간대는 회사 정책을 적용한다.
- 기존 업무 잔여 공수는 전체 잔여량이 아니라 평가 기간 안에 수행하도록 배분된 시간만 사용한다.
- 유효 가용용량이 0이면 부하율을 계산하지 않고 해당 기간 배정을 BLOCKED 처리한다.
- 100%를 초과하는 배정 후 부하율은 과부하 위험으로 검증 결과에 표시한다.
- Jira 공수가 없고 Story Point만 있으면 팀 Velocity 기반 별도 방식을 쓰고 가정을 표시한다.
- 시간과 Story Point를 직접 합산하지 않는다.
- 데이터가 부족하면 계산 방식별 Readiness를 먼저 판정한다.

### 13.2 업무 분배 처리 4단계와 실행 주체

1. **후보 생성**: 업무 분배 Agent가 Task별 후보 생성을 요청하고, 규칙 기반 후보 필터가 재직·역할·책임수준·조직·권한 Hard Constraint를 적용해 적격 후보군을 반환한다.
2. **업무 적합도 계산**: 규칙·점수 계산 코드가 Skill, 유사 경험, 역할 적합성, 출처 신뢰도를 후보별 지표로 계산한다.
3. **기간별 업무량·가용성 계산**: 업무량 계산 모듈이 기존 업무, 휴가·부재, FTE, 일정 중복을 반영해 WorkloadResult를 생성한다.
4. **배분안 구성과 위험 분석**: 규칙 기반 위험 분석 코드가 프로젝트 충돌·업무 집중·병목 지표를 계산하고, 업무 분배 Agent가 계산 결과를 비교해 추천 담당자·대안 후보·추천 근거를 구성한다.

업무 분배 Agent는 계산식을 직접 수행하거나 계산값을 임의로 변경하지 않는다. 계산 모듈과 규칙 코드가 생성한 적합도·가용성·위험 지표를 입력으로 받아 프로젝트 전체 관점의 배분안을 구성하고 PM이 이해할 수 있는 설명을 제공한다.

### 13.3 Skill UNKNOWN

필수 Skill 데이터가 없으면 불충족으로 단정하지 않고 UNKNOWN인 CONDITIONAL 후보로 남긴다. 데이터가 존재하며 필수 수준 미달이면 부적합으로 처리한다.

### 13.4 적합도 기본식

~~~text
총 적합도 = Skill 적합도 35%
          + 역할·책임수준 적합도 20%
          + 기간 가용성 25%
          + 유사 업무 경험 10%
          + 협업·프로젝트 연속성 10%
          - 충돌·집중 위험 패널티
~~~

가중치는 고객 정책으로 조정한다. 점수만으로 확정하지 않고 구성요소와 데이터 준비도를 함께 표시한다.

### 13.5 추천 결과 필수 출력

- 추천 담당자와 최소 1명의 대안
- 추천·대안별 근거
- 업무 적합도와 기간별 업무 부하
- 프로젝트 충돌·업무 집중·병목 위험
- 누락 데이터와 제한 사항
- 적용 가정과 신뢰도
- 데이터 준비 상태와 검증 상태
- 원본 문서·원천 레코드 출처

---

## 14. Orchestrator·Agent·검증·PM 흐름

### 14.1 전체 흐름

~~~mermaid
flowchart TB
    A["프로젝트 분석 요청"] --> B["Orchestrator"]
    B --> C["업무 추출 Agent"]
    B --> D["업무량 계산 모듈<br/>규칙·수식 기반"]
    C --> E["NewTaskDraft"]
    E --> F{"PM 업무 분해 확인"}
    F -->|"승인·수정"| G["확정 NewTaskSnapshot"]
    F -->|"반려"| C
    D --> H["WorkloadResult"]
    G --> I["업무 분배 Agent"]
    H --> I
    I --> J["검증 Agent"]
    J --> K{"검증 결과"}
    K -->|"PASS / CONDITIONAL_PASS"| L["추천 + 검증 결과"]
    K -->|"REJECT"| M["추천 폐기 또는 데이터·조건 수정"]
    L --> N{"PM 최종 결정"}
    N -->|"수정"| J
    N -->|"반려"| O["사유별 이전 단계 회귀"]
    N -.->|"승인·후속 단계"| P["Jira 반영"]
~~~

업무 추출과 업무량 계산은 병렬 실행한다. 업무 추출 Agent에서 업무량 계산 모듈로 직접 연결하지 않는다.

### 14.2 Orchestrator 책임

- 실행 순서와 병렬 작업 관리
- 작업 상태와 Snapshot ID 전달
- 재시도·타임아웃·Fallback
- Feature Readiness에 따른 분기
- PM 승인 대기와 재개
- Agent 입력·출력 스키마 검사
- 운영 로그와 추적 ID 연결

Orchestrator는 의미 추출이나 추천 점수를 계산하는 Agent가 아니다. 실패 처리는 ReAct가 아니라 Retry, Fallback, Human-in-the-loop로 구분한다.

### 14.3 검증 Agent 필수 검사

- 역할·필수 Skill·책임수준
- 조직 제한과 권한
- 휴가·휴직 중복
- 일정 충돌과 최대 부하율
- 추천 근거 존재 여부
- 원본 출처 접근 가능 여부
- 데이터 누락·가정·신뢰도
- 결과 스키마와 계산 버전

| 결과 | 의미 | 후속 |
|---|---|---|
| PASS | 필수조건 충족, 근거 충분 | PM 검토 가능 |
| CONDITIONAL_PASS | UNKNOWN 또는 선택 데이터 누락 | 제한 표시 후 PM 검토 |
| REJECT | 필수조건 위반 또는 근거 없음 | Jira 반영 금지, 폐기 또는 수정 |

### 14.4 PM 결정과 회귀

| 조치/사유 | 이동 위치 |
|---|---|
| 승인 | 후속 쓰기 기능이 활성화된 경우에만 Jira 반영 |
| 후보·일정·공수 수정 | 검증 Agent로 직접 재전송 |
| Task 분해 오류 | 업무 추출 단계 |
| 인력·조건 변경 필요 | 업무 분배 단계 |
| 데이터 누락·오류 | Connector/Data 단계 |
| 단순 검증조건 수정 | 검증 Agent |

REJECT 결과는 Jira에 연결하지 않는다.

---

## 15. 아키텍처 레이어

### 15.1 논리 아키텍처

~~~mermaid
flowchart TB
    A["1. 경험 계층<br/>PM 화면·운영 화면·API"]
    B["2. 승인·실행 계층<br/>Task 확인·PM 결정·Jira 쓰기 게이트"]
    C["3. Orchestration 계층<br/>병렬 실행·상태·재시도·HITL"]
    D["4. 도메인 지능 계층<br/>Task 추출·부하 분석·분배·검증"]
    E["5. Feature Readiness 계층<br/>기능별 준비도·정책 검사"]
    F["6. 정규화·지식 모델·Snapshot 계층<br/>Canonical Model·Project Knowledge Model·버전"]
    G["7. 수집·문서 처리 계층<br/>Connector·구조 보존 파싱·Block·보조 검색"]
    H["8. 저장 계층<br/>PostgreSQL·Vector DB·Object Storage"]
    I["데이터 소스<br/>내부 People DB·Jira·Drive·정책<br/>(Calendar 후속)"]
    I --> G --> H
    H --> F --> E --> D --> C --> B --> A
~~~

수집 계층은 저장소에 기록하고 정규화 계층은 저장된 원천과 인덱스를 읽는다. 도식은 책임의 상향 흐름을 단순화했다.

### 15.2 레이어별 책임

| 계층 | 책임 | 산출물 |
|---|---|---|
| 경험 | 연결, Task 확인, 추천, 검증, 감사 UI | 사용자 입력·결정 |
| 승인·실행 | 승인 게이트, PM 수정, 외부 쓰기 통제 | DecisionRecord, Jira write command |
| Orchestration | 병렬 실행, 상태, 재시도, 승인 대기 | WorkflowRun |
| 도메인 지능 | 추출, 부하, 후보, 점수, 위험, 검증 | Task/Workload/Recommendation/Validation |
| Feature Readiness | 기능별 필요 데이터와 정책 검사 | ReadinessReport |
| 정규화·지식 모델·Snapshot | Canonical Model 변환, 지식 통합, 요청 시점 고정 | Project Knowledge Model, Snapshot |
| 수집·문서 처리 | 인증, Discovery, 동기화, 구조 보존 파싱, 보조 검색 | RawRecord, DocumentIndex, DocumentBlock |
| 저장 | 원본·관계·벡터·버전 보존 | 영속 데이터 |

### 15.3 보안·운영 횡단 계층

- Tenant 격리, RBAC, 프로젝트 권한, Row Level Security
- Drive 원본 ACL 기반 검색 필터
- 전송·저장 암호화와 Secret Manager
- PII 마스킹과 최소 수집
- 운영 로그, 감사 로그, 메트릭, 분산 추적
- 데이터 보존·삭제 정책

운영 로그는 장애 분석용 기술 이벤트이고 감사 로그는 누가 어떤 데이터와 추천을 조회·변경·승인했는지 증명하는 기록이다.

---

## 16. 화면 설계

### 16.1 화면 구조

| 화면 | 목적 | 핵심 구성 |
|---|---|---|
| 1. 데이터 연결·범위 | Connector와 대상 범위 구성 | 연결 상태, 권한, 동기화, Drive 폴더, Jira 프로젝트 |
| 2. 데이터 준비도 | 추천 전 문제 확인 | SUCCESS/PARTIAL_RESULT/BLOCKED, 누락, 해결 방법, 새로고침 |
| 3. 업무 추출 확인 | AI Task 분해 검토 | 문서, Task 표, 출처, 유형, 신뢰도, 수정·승인·반려 |
| 4. 추천·검증 결과 | 후보와 근거 비교 | 추천, 대안, 적합도, 부하 타임라인, 위험, 검증, 출처 |
| 5. PM 최종 결정 | 최종 조정과 재검증 | 후보·일정·공수 편집, 영향, 재검증, 승인·반려 |
| 6. 동기화·감사 | 운영 상태 추적 | Source Registry, 실패 재처리, 매핑 예외, WorkflowRun, 감사 |

### 16.2 데이터 연결 화면

~~~text
┌──────────────────────────────────────────────────────────────────────┐
│ 프로젝트: AI Assistant                    [새로고침] [추천 시작]    │
├───────────────────────┬──────────────────────────────────────────────┤
│ Connector 상태        │ 프로젝트 데이터 범위                        │
│ ● People DB 준비      │ Drive: /AI Assistant/기획 [폴더 변경]       │
│ ● Jira 정상           │ 역할: 기획서, 요구사항, 회의록              │
│ ○ Calendar 후속 연동  │ Jira: AIP, PLATFORM                         │
│ ● Drive 정상          │ 기간: 2026-08-01 ~ 2026-10-31              │
│                       │ 보안: Internal / PMO 그룹                   │
└───────────────────────┴──────────────────────────────────────────────┘
~~~

### 16.3 Feature Readiness 화면

~~~text
┌──────────────────────────────────────────────────────────────────────┐
│ 데이터 준비도: PARTIAL_RESULT                    snapshot 예정 10:20 │
├──────────────────┬──────────────┬────────────────────────────────────┤
│ 기능             │ 상태         │ 누락/조치                          │
│ 역할 후보 생성   │ SUCCESS      │ -                                  │
│ Skill 적합도     │ PARTIAL_RESULT│ 3명 Skill 데이터 없음             │
│ 시간 기반 부하율 │ SUCCESS      │ -                                  │
│ Jira 업무량      │ PARTIAL_RESULT│ 1명 accountId 매핑 필요 [해결]    │
│ 조직 제한 검사   │ SUCCESS      │ -                                  │
└──────────────────┴──────────────┴────────────────────────────────────┘
│ [원천 데이터 보기] [수동 새로고침] [조건부로 계속]                  │
└──────────────────────────────────────────────────────────────────────┘
~~~

### 16.4 업무 추출 확인 화면

- 좌측: 원본 문서와 선택된 근거 문장
- 중앙: Task, 출처 유형, 역할, 공수, 기간, 우선순위
- 우측: 누락 필드, 중복 후보, AI 제안 누락 업무, 신뢰도
- 하단: 승인, 수정 후 승인, 반려 및 재추출

AI_SUGGESTED_MISSING_TASK는 일반 추출 Task와 다른 배지로 구분한다.

### 16.5 추천·검증 화면

~~~text
┌──────────────────────────────────────────────────────────────────────┐
│ Task: Jira 업무량 수집 Connector 구현     검증: CONDITIONAL_PASS     │
├─────────────────────┬────────────────────┬───────────────────────────┤
│ 추천: 이민준        │ 대안 1: 박서연     │ 대안 2: 최도윤            │
│ 적합도 88           │ 적합도 82          │ 적합도 76                  │
│ 예상 부하 72%       │ 예상 부하 64%      │ 예상 부하 58%              │
│ Skill 92 / 가용 81  │ Skill UNKNOWN      │ 일정 충돌 위험             │
├─────────────────────┴────────────────────┴───────────────────────────┤
│ 위험: 8/10 마감 중복 · 박서연 Skill 숙련도 누락                     │
│ 가정: Jira 잔여 공수가 최신이며 고정 회의 6시간/주 적용             │
│ 근거: DOC001 p.5 chunk 18 · Jira AIP-132 · PersonSnapshot PS-21     │
│ [근거 보기] [후보/일정/공수 수정] [반려] [승인]                    │
└──────────────────────────────────────────────────────────────────────┘
~~~

1차 구현의 승인은 DecisionRecord까지만 저장한다. Jira 반영은 후속 기능으로 표시한다.

### 16.6 공통 상태 규칙

- 숫자 옆에 기준 기간과 Snapshot 시각을 표시한다.
- PARTIAL_RESULT와 CONDITIONAL_PASS는 이유와 해결 방법을 함께 표시한다.
- REJECT는 승인/Jira 반영 버튼을 제공하지 않는다.
- 출처 클릭 시 문서 페이지·청크 또는 원천 레코드를 확인한다.
- PM 수정 시 어떤 검증이 무효화되는지 표시한다.

---

## 17. 결과 출력 스키마

### 17.1 RecommendationResult 예시

~~~json
{
  "recommendationId": "REC-20260722-001",
  "taskSnapshotId": "NTS-001",
  "snapshotAsOf": "2026-07-22T10:20:00+09:00",
  "dataReadinessStatus": "PARTIAL_RESULT",
  "recommendedCandidate": {
    "personId": "P-102",
    "fitScore": 88,
    "projectedLoadRate": 72,
    "reasons": [
      "필수 역할 일치",
      "Jira API 유사 업무 경험",
      "잔여 가용시간 충족"
    ]
  },
  "alternatives": [
    {
      "personId": "P-118",
      "fitScore": 82,
      "projectedLoadRate": 64,
      "conditions": ["Skill 숙련도 데이터 확인 필요"]
    }
  ],
  "risks": ["추천자의 2026-08-10 기존 업무 마감과 중복"],
  "missingData": ["P-118의 Jira REST API 숙련도"],
  "limitations": ["Worklog가 없는 이슈는 잔여 공수 기준 사용"],
  "assumptions": ["주 40시간, 공휴일 정책 v2 적용"],
  "confidence": 0.84,
  "sourceRefs": [
    "DOC001:p5:c18",
    "JIRA:AIP-132",
    "PERSON_SNAPSHOT:PS-21"
  ],
  "calculationVersion": "allocation-1.0"
}
~~~

### 17.2 ValidationResult 예시

~~~json
{
  "validationId": "VAL-20260722-001",
  "recommendationId": "REC-20260722-001",
  "status": "CONDITIONAL_PASS",
  "checks": [
    {"code": "ROLE_MATCH", "status": "PASS"},
    {"code": "REQUIRED_SKILL", "status": "UNKNOWN", "personId": "P-118"},
    {"code": "ORG_POLICY", "status": "PASS"},
    {"code": "LEAVE_OVERLAP", "status": "PASS"},
    {"code": "SCHEDULE_CONFLICT", "status": "WARN"},
    {"code": "EVIDENCE_PRESENT", "status": "PASS"}
  ],
  "blockingReasons": [],
  "conditions": ["대안 후보의 Skill 숙련도 확인"],
  "validatedAt": "2026-07-22T10:21:12+09:00",
  "validatorVersion": "validation-1.0"
}
~~~

---

## 18. 단계별 구현 범위

### 18.1 2026년 8월 6일 핵심 시연 범위 — 우선 실선

시연은 하나의 종단 시나리오가 중단 없이 동작하는 것을 최우선 목표로 한다.

1. 내부 People DB의 합성 Seed에서 직원·조직·Skill·FTE·휴가를 읽어 PersonSnapshot과 기본 조직도를 생성한다.
2. Jira 대상 프로젝트의 기존 업무를 읽어 ExistingTaskSnapshot으로 정규화한다.
3. 선택한 Drive의 텍스트 기반 PDF 1건을 다운로드하고 구조 보존 파싱·Document Block·메타데이터를 생성한다.
4. 의미 정보를 추출·통합한 Project Knowledge Model에서 신규 Task를 만들고 PM이 업무 분해를 확인한다.
5. Feature Readiness가 필수 데이터와 제한 사항을 판정한다.
6. 유효 가용용량 기준으로 부하율을 계산하고 추천자와 최소 1명의 대안을 생성한다.
7. 검증 Agent가 역할·Skill·조직·휴가·일정·근거를 검사한다.
8. RecommendationResult와 ValidationResult 화면에서 근거·위험·가정·Snapshot 시각을 확인한다.

다음 기능은 핵심 시연의 선행조건으로 두지 않는다.

- 이미지 PDF OCR
- Drive 신규 파일 자동 감지와 증분 인덱싱
- Google Calendar 실연동
- Jira 쓰기
- 관리자 KPI 대시보드

### 18.2 1차 전체 구현 범위 — 실선

- 내부 People DB 테이블, 제약조건, 시나리오별 합성 Seed 데이터
- 직원·조직·Skill·FTE·휴가의 PersonSnapshot 변환
- Jira Discovery와 읽기, ExistingTaskSnapshot 정규화
- Drive 선택 폴더 수집, PDF/DOCX 구조 보존 파싱, Document Block, Knowledge Item, Project Knowledge Model
- Drive 변경 감지와 증분 인덱싱
- People DB의 근무시간·휴가·부재 기반 가용성 반영
- Identity Mapping과 매핑 실패 부분 결과
- 조직도 생성과 충돌 검사
- Feature Readiness Check
- Task 추출과 PM 확인
- 기간별 업무량과 후보 추천
- 필수 제약조건 검증
- RecommendationResult와 ValidationResult 화면
- 원본 근거와 Snapshot 시각 확인

### 18.3 후속 확장 범위 — 점선

- PM 승인 결과의 Jira 쓰기
- 실제 HR/Workday Connector 어댑터 구현 검토
- Google Calendar 실연동
- OCR·PPTX·Google Docs 처리
- 조직별 정책 편집 UI 고도화
- 운영 결과와 PM 결정 이력을 활용한 가중치 보정
- 다중 프로젝트 최적화와 시나리오 비교
- 관리자 KPI 대시보드: 추천 승인율, PM 수정률, AI 추천과 최종 배정의 차이
- Slack/Teams 알림
- 운영 모니터링·장애 대응 고도화

---

## 19. 품질 평가 계획

### 19.1 평가 항목

| 영역 | 지표 | 목표 예시 |
|---|---|---|
| 문서 처리 | 파싱 성공률, 청크 출처 보존율 | 95% 이상, 출처 100% |
| Task 추출 | 필수 필드 정확도, PM 수정률 | 필수 필드 F1 0.85 이상 |
| 데이터 준비도 | 실제 차단 원인 탐지율 | 필수 누락 100% 탐지 |
| 조직도 | 순환·고아·충돌 탐지 | 테스트 케이스 100% |
| 업무량 | 수작업 기준 계산과 오차 | ±5% 이내 |
| 추천 | Hard Constraint 위반 | 0건 |
| 설명 | 추천 근거 출처 연결률 | 100% |
| 운영 | 증분 동기화 중복 처리 | 동일 revision 중복 0건 |

### 19.2 최소 테스트 데이터셋

- 직원 20~30명, 조직 4~6개, 관리자 계층 3단계
- 동일 이름, Jira 미매핑, 겸직, 퇴사자, 조직 순환 오류
- Skill 완전/부분/없음 후보
- FTE 1.0/0.5, 휴가 중복, 시간대 차이
- Jira 이슈 50건 이상, 공수/Story Point 혼합, 지연·미갱신 이슈
- 프로젝트 문서 PDF/DOCX 각 2개 이상, 수정 버전과 신규 파일
- 신규 Task 8~12개, 의존성과 누락 업무 제안
- PASS, CONDITIONAL_PASS, REJECT가 모두 발생하는 추천 시나리오

---

## 20. 보안·개인정보·감사

- Connector는 최소 권한 읽기 Scope로 시작한다.
- Jira 쓰기 권한은 후속 단계에서 별도 승인과 계정으로 분리한다.
- 문서 검색은 원본 Drive ACL과 프로젝트 권한을 모두 검사한다.
- Skill·휴가·업무량은 추천 목적에 필요한 최소 필드만 수집한다.
- 민감한 휴가 사유는 저장하지 않고 가용성 영향 시간만 사용한다.
- 추천 화면은 역할 기반으로 노출 범위를 제한한다.
- 원본, 임베딩, Snapshot, 결과, 로그마다 보존기간을 정의한다.
- 운영 로그에는 원문·PII를 기본 기록하지 않는다.
- 감사 로그에는 요청자, 입력 Snapshot, 후보 변경, 검증, 승인·반려, 외부 쓰기 여부를 기록한다.
- 모델 입력·출력에 tenant, 접근권한, 데이터 분류 정책을 적용한다.

---

## 21. 주요 위험과 대응

| 위험 | 영향 | 대응 |
|---|---|---|
| People DB 공통 구조와 실제 고객사 HR 데이터 차이 | 실환경 전환 시 매핑 비용 증가 | People Repository와 PersonSnapshot 경계를 유지하고 고객별 필드 매핑으로 흡수 |
| Skill 데이터 부정확 | 잘못된 후보 배제 | UNKNOWN 조건부 후보, PM 확인, 신뢰도 하향 |
| Jira 필드 차이 | 공수 계산 실패 | 최초 Discovery, 고객별 매핑, 방식별 Readiness |
| 외부 ID 매핑 오류 | 타인의 업무량 결합 | 강한 키 우선, 이름 단독 자동 매핑 금지, 충돌 수동 해결 |
| 문서 변경 미반영 | 오래된 Task 추출 | Changes API+Push+주기 보정, 추천 직전 최신성 확인 |
| 문서 구조화 누락·LLM 환각 | 누락 또는 근거 없는 Task 생성 | 전체 Block 처리, 출처 필수, 스키마 검사, 제안 업무 분리, PM 확인 |
| 개인 업무 과다 노출 | 개인정보·노무 위험 | 최소 데이터, RBAC/RLS/ACL, 휴가 사유 미수집 |
| 추천 점수 과신 | 자동 결정처럼 사용 | 점수 구성 공개, 대안·위험·가정 표시, PM 최종 결정 |
| 원천 변경 후 결과 불일치 | 감사·재현 불가 | 불변 Snapshot과 계산·정책 버전 저장 |

---

## 22. 확정 의사결정

1. 제품은 자동 배정기가 아니라 AI 프로젝트 운영 코파일럿이다.
2. 최종 업무 배정 책임은 PM에게 있다.
3. 1차 구현의 인력 데이터는 PostgreSQL 내부 People DB에 합성 데이터로 구성한다.
4. 실제 HR/Workday API 연동은 후속 확장으로 분리한다.
5. 업무 추출과 업무 부하 분석은 병렬 실행한다.
6. Task 추출 직후 PM 확인을 필수로 둔다.
7. 후보 생성과 배분안 구성은 업무 분배 Agent의 책임이며, 적격성·적합도·가용성·위험 계산은 규칙·수식 기반 코드가 수행한다.
8. 시간·부하·휴가·필수조건은 결정론적 코드로 계산·검증한다.
9. Skill 데이터가 없으면 불충족이 아니라 UNKNOWN으로 처리한다.
10. REJECT는 Jira에 반영하지 않는다.
11. PM 수정 결과는 검증 Agent로 직접 보내 재검증한다.
12. 문서 원본은 Object Storage, 문서 구조·지식 모델·관계 데이터는 PostgreSQL, 검색 보조용 임베딩은 Vector DB에 저장한다.
13. Drive는 선택 폴더만 인덱싱하고 ACL을 검색에 적용한다.
14. 추천 시점 Snapshot은 불변으로 저장한다.
15. 8월 6일 핵심 시연은 하나의 종단 시나리오에서 추천 결과와 검증 결과를 출력하는 데 집중한다.
16. Jira 쓰기는 후속 단계에서 적용한다.
17. 초기 운영 기준 템플릿과 기준 데이터 워크북은 사용하지 않는다. 고객별 근무·조직·권한 기준은 Policy 설정과 데이터베이스 버전으로 관리해 중복 관리와 버전 불일치를 방지한다.
18. HR 관련 물리 테이블명에는 mock을 사용하지 않고, 합성 여부는 data_origin과 dataset_version으로 구분한다.
19. 프로젝트 전체 업무 추출은 Project Knowledge Model을 기준으로 하며 RAG는 정보 통합·과거 업무·근거 검색을 보조한다.
20. Graph DB와 WorkGraph는 1차 구현의 필수 구성요소로 사용하지 않는다. 필요한 관계는 PostgreSQL의 Canonical Data Model로 관리한다.

---

## 23. 개발 추진 계획

### 0단계 — 8월 6일 핵심 시연

- 내부 People DB 합성 Seed와 People Repository를 통한 PersonSnapshot·기본 조직도 생성
- Jira 대상 프로젝트 읽기와 ExistingTaskSnapshot 생성
- 텍스트 기반 PDF 1건의 구조 보존 파싱·Project Knowledge Model·Task 추출
- PM 업무 분해 확인과 Feature Readiness
- 유효 가용용량 기준 부하율 계산
- 추천자·대안·근거·검증 결과 화면

### 1단계 — 계약과 데이터 기반

- 내부 People DB 스키마, 제약조건, 합성 Seed 데이터 확정
- Jira Discovery와 ConnectorProfile 구현
- Drive 선택 범위와 Source Registry 구현
- PostgreSQL, Vector DB, Object Storage 초기 구조
- Identity Mapping과 Canonical Model 확정

### 2단계 — 수집과 Snapshot

- 문서 구조 보존 파싱·Document Block·메타데이터 파이프라인
- Drive 증분 동기화
- Person/ExistingTask/Document Snapshot
- 조직도 생성과 충돌 검사
- 원천 검증과 Feature Readiness

### 3단계 — 지능과 검증

- Project Knowledge Model 기반 Task 추출과 보조 RAG 검색
- PM 업무 분해 확인 화면
- 업무량·가용성 계산
- 후보 생성·적합도·위험 분석
- 필수 제약조건 검증

### 4단계 — 결과 경험과 평가

- 추천·검증 화면
- 근거 문서 뷰어
- PM 수정 후 재검증
- 동기화·매핑·감사 화면
- 최소 데이터셋과 PASS/CONDITIONAL_PASS/REJECT 평가

### 5단계 — 후속 확장

- Jira 쓰기 게이트
- 실환경 Connector·보안·운영 고도화
- 다중 프로젝트 최적화

---

## 24. 제품 정의와 데모 시나리오

### 24.1 제품 정의

> “분산된 조직·업무·일정·문서 데이터를 검증 가능한 Snapshot으로 통합하고, AI와 결정론적 계산을 결합해 PM이 근거를 확인하며 최종 배정할 수 있게 하는 프로젝트 운영 코파일럿입니다.”

### 24.2 데모 시나리오

1. 기존 업무 배정이 데이터 분산과 개인 경험에 의존하는 문제를 제시한다.
2. Connector와 문서 증분 수집으로 최신 데이터를 준비하는 과정을 보여준다.
3. Feature Readiness가 누락 데이터를 숨기지 않고 실행 가능 범위를 판정한다.
4. AI가 전체 문서를 구조화한 Project Knowledge Model에서 Task를 추출하고 PM이 분해 결과를 확인한다.
5. 규칙 기반 코드가 업무량·휴가·충돌을 계산하고 Agent가 후보와 대안을 만든다.
6. 검증 Agent가 필수조건·근거·신뢰도를 검사한다.
7. PM이 추천, 대안, 위험, 원본 근거를 비교해 최종 결정한다.
8. 1차 구현 결과와 후속 Jira 쓰기·실환경 확장 계획을 구분한다.
