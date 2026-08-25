# WORKDAY API

생성일: 2026년 7월 20일 오후 12:32

## 핵심 정리

> **결론:** Workday 공개 문서만으로 실제 고객사의 HR 데이터를 가져올 수는 없지만, 공식 API 구조와 예시 응답을 참고해 **Workday-compatible Mock API + Connector Adapter**를 구현하는 것은 가능하다. 다만 이 기능은 핵심 HR 데이터 소스라기보다, 향후 실제 Workday 연동으로 교체 가능한 구조를 검증하는 후순위 기술 데모로 보는 것이 적절하다.
> 

| 구분 | 확인 결과 | 프로젝트 적용 |
| --- | --- | --- |
| 구성원 기본정보 | `id`, `descriptor`, `primaryWorkEmail`, `businessTitle` 확인 | 구성원 식별·표시·계정 연결 |
| 조직·보고 관계 | `primarySupervisoryOrganization`, `isManager`, 조직의 `manager`, `directReports` 확인 | 소속 팀·관리자·직접 보고 관계 구성 |
| 근무 위치 | Worker 상세의 `location` 확인 | 근무지·지역 기반 조건에 활용 |
| 휴가·부재 | `timeOffSummary`로 잔여량 확인, 실제 일정은 Time Off Entries 추가 확인 필요 | 실제 가용시간 판단에는 휴가 일정 데이터가 필요 |
| 재직 상태·FTE·표준 근무시간 | 공개 Legacy Workers 문서에서는 명확히 확인되지 않음 | Staffing·SOAP·RaaS 추가 검증 전 공식 필드로 사용하지 않음 |
| Worker Skills | 직원 보유 역량 데이터 후보. Skills Cloud는 기술명 표준화·추론·격차 분석용 | 담당자 추천의 업무 적합도 근거로 활용 |

### 우리 프로젝트에서 필요한 데이터

- **Workday·HR:** 구성원 ID, 이메일, 직함, 조직, 관리자 관계, 위치, 역량
- **Google Calendar:** 회의, 일정, 출장, 휴가 등 실제 가용시간
- **Google Drive:** 이력서, 경력, 기술, 프로젝트 문서와 산출물
- **Jira:** 현재 태스크, 담당자, 상태, 우선순위, 마감일

각 시스템의 원본 응답은 그대로 사용하지 않고 다음 흐름으로 처리한다.

```
외부 API
→ Connector
→ 정제·표준화 Adapter
→ 내부 Person / Organization / Skill 모델
→ Google·Jira 데이터와 사용자 매핑
→ 업무량·가용시간·업무 적합도 분석
```

### Worker Skills의 의미

`Worker Skills`는 **특정 구성원이 보유한 기술·역량**을 의미한다. 예를 들어 Python, FastAPI, 프로젝트 관리 등의 역량을 구성원과 연결해 담당자 추천 근거로 사용할 수 있다.

다만 다음 두 개념은 구분해야 한다.

- **Worker Skills:** 특정 직원이 보유한 역량
- **Skills Cloud API:** `파이썬`, `Python Programming`처럼 제각각인 기술명을 표준 기술로 정규화하거나, 직함·자격증에서 기술을 추론하고 기술 격차를 분석하는 기능

직원별 보유 역량을 직접 조회하는 정확한 엔드포인트와 숙련도·검증 상태 스키마는 Talent Management API Explorer 또는 실제 테넌트 명세에서 추가 확인해야 한다.

### 1차 Mock 구현 범위

공개 문서에서 직접 확인된 항목만 우선 구현한다.

- `GET /workers`
- `GET /workers/{id}`
- `GET /workers/{id}/directReports`
- `GET /supervisoryOrganizations`
- `GET /supervisoryOrganizations/{id}`
- `id`, `descriptor`, `primaryWorkEmail`, `businessTitle`
- `isManager`, `primarySupervisoryOrganization`, `location`, 조직의 `manager`
- `limit`·`offset` 페이지네이션
- 인증·권한 오류와 `429` 재시도

재직 상태, FTE, 표준 근무시간, 실제 Time Off Entries, 직원별 Skills 상세는 명세 확인 후 2차 범위로 둔다.

### 최종 판단

> Workday Mock은 실제 인사 데이터를 만드는 목적이 아니라, **외부 HR API의 계약을 해석하고 내부 공통 모델로 변환하는 커넥터 구조**를 검증하는 데 의미가 있다. 핵심 MVP는 Google Drive·Calendar·Jira의 실제 데이터 흐름을 먼저 완성하고, Workday는 시간이 허용될 때 확장성 시연으로 추가한다.
> 

---

## 출처 포함된 표 개정제시안

| 항목 | 값·필드명 | 가져오는 방법 | 확인 근거 (이번 세션) | 최종 판단 |
| --- | --- | --- | --- | --- |
| Workday 내부 식별자 | `id` | `GET /workers`, `/workers/{id}` | Workato, BlinkOps, Ballerina `workday.common` 스키마 3중 확인 | **확인됨** |
| 사번·직원번호 | Employee_ID Reference | `GET /workers/Employee_ID={사번}` | SOAP `Worker_Reference`가 `type="Employee_ID"` 사용 확인, Ballerina의 `opportunityReferenceID` 필드 설명("Reference ID로 조회")이 동일 관례를 뒷받침 | **확인됨 (격상).** 다만 REST 정확한 URL 문법 자체는 원문 100% 대조는 아님 |
| 표시명 | `descriptor` | `GET /workers`, `/workers/{id}` | 3개 소스 일치 | **확인됨** |
| 이메일 | `primaryWorkEmail` | 동일 | 3개 소스 일치 | **확인됨** |
| 전화번호 | `primaryWorkPhone` | 동일 | 3개 소스 일치 | **확인됨** |
| 업무상 직함 | `businessTitle` | 동일 | Ballerina: "포지션에 업무 타이틀 없으면 포지션 타이틀 반환"까지 세부 확인 | **확인됨** |
| 소속 팀·주 감독 조직 | `primarySupervisoryOrganization` | 동일 | 3개 소스 일치 | **확인됨** |
| 관리자 여부 | `isManager` | 동일 | 3개 소스 일치 | **확인됨** |
| 직속 상사 | `SupervisoryOrganizationSummary.manager` | 조직 조회 후 `manager` 필드 확인 | Ballerina 스키마에 `manager [Manager]` 필드 명시적 존재 확인 | **확인됨 (격상)** |
| 직접 보고자·팀원 목록 | Direct Reports | `getWorkerReports(id)` 계열 엔드포인트 | Ballerina에 `getWorkerReports`/`getReportForWorker` 함수 존재 확인 | **확인됨 (격상).** 단 정확한 REST 경로/필드명은 함수명 기반 추정 |
| 조직 소속 구성원 | `SupervisoryOrganizationSummary.workers` | 조직 조회 후 `workers` 필드 | Ballerina 스키마에 `workers` 필드 + `getWorkersOfSupervisoryOrg` 함수 확인 | **확인됨 (격상)** |
| 부서 | Organization type 필터 | `GET /organizations?organizationType={typeID}` | Ballerina에 `getOrganizationTypes`/`getOrgTypeInstance` 별도 룩업 엔드포인트 존재 확인 → 타입은 문자열이 아니라 ID로 조회하는 구조가 맞음 | **확인됨 (격상)** |
| 회사 | Organization type 필터 | 동일 | 동일 근거 | **확인됨** |
| 비용센터 | Organization type 필터 | 동일 | 동일 근거. 별도 `/companies`, `/costCenters` 리소스명은 스키마에 없음 확인 → **하나의 Organizations 리소스를 타입으로 필터링하는 구조**임을 확인 | **확인됨. 별도 리소스 아님이 확정됨** |
| 근무지 | `location` | `GET /workers`, `/workers/{id}` | Ballerina Worker 스키마에 `location [Location]` 필드 확인, Workato는 목록(Search)·상세(Get) 응답 모두에 포함 확인 | **확인됨.** "상세조회 전용" 제약은 근거 없어 삭제 |
| 휴가 잔여량 | `timeOffSummary` 계열 | `?view=timeOffSummary` | 이번 세션 소스로도 못 찾음 | **미확인 (변동 없음)** |
| 휴가 상세 일정 | Time Off Entry | `getTimeOffEntriesForWorker`/`getTimeOffEntryForWorker` | Ballerina 함수 존재 확인 + StackOne "List Time Off Details"/"List Worker Time Off Entries" 별도 액션 확인 → 이전 턴 상충(피드백은 POST만 있다고 주장) 해소 | **확인됨 (재격상).** 다중 독립 소스로 GET 상세조회 엔드포인트 실존 쪽에 무게 |
| 장기 휴직 | Leave of Absence | Absence Management REST/SOAP | StackOne "List Leaves Of Absence" REST 액션 확인 | **조건부 확인 (격상).** REST 액션 존재는 확인, 응답 필드는 미확인 |
| 직무 프로필 | Job Profile | SOAP `Get_Job_Profiles` | StackOne: "job family, level, management details 포함" 설명 확인 | **개념·SOAP 경로 확인됨.** REST 경로는 미확인 |
| 직군 | Job Family | Get_Job_Profiles 응답 내 포함 | 위와 동일 | **SOAP 내 존재 확인됨.** 별도 REST 리소스 여부 미확인 |
| 직급·레벨 | Job Level·Grade | Get_Job_Profiles 응답 내 포함 | 위와 동일 | **SOAP 내 존재 확인됨.** REST 미확인 |
| 포지션 | Position | SOAP `List Positions`/`Create Position` | StackOne 액션 목록 확인 | **SOAP 확인됨.** REST 경로 미확인 |
| 고용 형태 | `workerTypes` | Graph API/WQL | 지난 턴 확인 유지 | **확인됨** |
| 표준 근무시간 | Scheduled Weekly Hours | — | 동일 스키마에서도 미발견 | Workday 안에는 있지만 REST API에는 없음 |
| FTE | FTE(Full Time Equivalent) | — | Workday 공식 개념 정의: "Scheduled Weekly Hours ÷ Default Weekly Hours로 산출"이라는 계산식만 확인 | Workday 안에는 있지만 REST API에는 없음 |
| 구성원 보유 역량 | Worker Skill/Explicit Skill | List/Get Worker Skills 등 | 지난 턴 확정 유지 | **확인됨** |
| 근속연수 | `yearsOfService` | `GET /workers`, `/workers/{id}` | Workato ("Years of service, integer") + Ballerina 스키마(`yearsOfService [int]`, "The years of service for the worker") 이중 확인 | **확인됨.** 계산값 아니라 실제 반환 필드 |
- v1.0
    
    
    | 항목 | 값(필드명) | 가져오는 방법 |
    | --- | --- | --- |
    | 식별자 | `id` | `GET /workers` |
    | 표시명 | `descriptor` | `GET /workers/{id}` |
    | 이메일 | `primaryWorkEmail` | `GET /workers/{id}` (또는 Person API `GET /person/v4/workers/{id}/workEmails`) |
    | 전화번호 | Work Phone | Person API `GET /person/v4/workers/{id}/workPhones` |
    | 직책 | `businessTitle` | `GET /workers/{id}` |
    | 소속 조직·팀 | `primarySupervisoryOrganization` | `GET /workers/{id}` |
    | 관리자 여부 | `isManager` | `GET /workers/{id}` |
    | 상사 | 조직의 `manager` | `GET /supervisoryOrganizations/{id}` |
    | 팀원 목록 | `directReports` | `GET /workers/{id}/directReports` |
    | 부서 | Organization(type=Department) | Common API `GET /common/v1/organizations?type=Department` |
    | 회사 | Organization(type=Company) | Common API `GET /common/v1/organizations?type=Company` |
    | 비용센터 | Organization(type=Cost_Center) | Common API `GET /common/v1/organizations?type=Cost_Center` |
    | 근무지 | `location` | `GET /workers/{id}` |
    | 휴가 잔여(요약) | `timeOffSummary` | `GET /workers/{id}` |
    | 휴가 상세 일정 | date · type · quantity · status | Absence Management v4 `GET /absenceManagement/v4/workers/{id}/timeOffDetails` |
    | 장기 휴직 | Leave of Absence | Absence Management API (List Leaves Of Absence) |
    | 직급 | Job Profile | HR SOAP `Get_Job_Profiles` |
    | 직무 | Position | Recruiting SOAP `List Positions` |
    | 고용 형태 | Worker Type(Employee/Contingent) | HR SOAP `Get_Workers` 응답 내 필드 |

- 고봉밥
    
    # Workday 공개 문서 기반 HR 데이터 활용 가능성 검토
    
    > 검토 기준일: 2026년 7월 20일
    > 
    > 
    > 목적: Workday 공개 문서를 참고하여 자체 Workday-compatible Mock API와 HR Connector Adapter를 구현할 수 있는지 확인
    > 
    > 주의: 공개 문서와 예시 데이터는 확인할 수 있지만, 실제 Workday 테넌트와 고객 데이터에는 접근할 수 없음
    > 
    
    ---
    
    # 1. 조사에 사용한 공식 문서
    
    | 구분 | 공식 문서명 | 링크 주소 | 이번 조사에서 확인한 내용 |
    | --- | --- | --- | --- |
    | 기본 구조 | Workday REST API Fundamentals | `https://developer.workday.com/documentation/GUID-85810465-bcfb-4fdf-a26d-55eaff3968a8-enHYPHENus/` | API 주소 구조, JSON 응답, ID, `data[]`, `total`, 페이지네이션, 하위 리소스 |
    | 구성원 | Reference: Workers | `https://developer.workday.com/documentation/dan1370797991225` | ID, 이름, 이메일, 직함, 관리자 여부, 소속 조직, 위치, 휴가 잔여량 |
    | 조직 | Reference: Supervisory Organizations | `https://developer.workday.com/documentation/dan1370797989680/ReferenceSupervisoryOrganizations` | 조직 ID·이름, 관리자, 조직 소속 직원 조회 경로 |
    | 일반 조직 | Reference: Organizations | `https://developer.workday.com/documentation/jas1400704341610/ReferenceOrganizations` | 조직 유형별 조회, 일반 조직과 감독 조직의 관계 |
    | 보안 | Concept: Workday REST API Security | `https://developer.workday.com/documentation/dan1370797986071/ConceptWorkdayRESTAPISecurity` | 사용자 보안 프로필, 도메인 권한, 하위 리소스 접근조건 |
    | SOAP 직원 조회 | Get Workers | `https://developer.workday.com/documentation/GUID-1f289b82-801e-434e-9e5a-aef66bc35179/GetWorkers` | 대량 직원 조회, 선택적 데이터 섹션, 변경 감지 |
    | 조회 대안 | Concept: Workday Query Language | `https://developer.workday.com/documentation/GUID-6546152a-bcf0-447d-8d64-230f9e2ac291-enHYPHENus` | Workday 데이터 소스와 필드를 SQL 유사 방식으로 조회 |
    | 보고서 API | Concept: Reports-as-a-Service | `https://developer.workday.com/documentation/hto1529968349582` | 사용자 정의 보고서를 JSON·CSV·XML API로 노출 |
    | 날짜 처리 | Workday REST API Date, Time, and Time Zone Handling | `https://developer.workday.com/documentation/jas1392746623599/ConceptWorkdayRESTAPIDateTimeandTimeZoneHandling` | 날짜·시간·시간대 형식 |
    | 문서 포털 | Workday Documentation | `https://doc.workday.com/` | Workday 공식 문서 진입점 |
    | 개발자 포털 | Workday Developers | `https://developer.workday.com/` | REST·SOAP·Graph API 및 개발 문서 |
    
    ---
    
    # 2. 결론부터 확인
    
    우리 프로젝트가 필요로 하는 데이터 중 다음 항목은 **공개된 Workday REST 문서와 JSON 예시에서 직접 확인됐다.**
    
    - 구성원 Workday ID
    - 구성원 표시 이름
    - 업무 이메일
    - 직함
    - 주 소속 조직
    - 관리자 여부
    - 조직 관리자
    - 직접 보고자 조회 구조
    - 근무 위치
    - 휴가 잔여량
    
    반면 다음 항목은 공개된 `Common (Legacy HCM) > Workers` 문서에서는 직접 확인되지 않았다.
    
    - 재직 상태
    - 표준 근무시간
    - FTE
    - 실제 휴가 시작일·종료일의 정확한 응답 스키마
    
    이 항목들은 Staffing REST API Explorer, SOAP `Get_Workers`, WQL 또는 고객사가 구성한 RaaS 보고서를 통해 확보할 가능성은 있지만, **현재 확인한 공개 문서만으로 특정 REST 필드명을 확정할 수는 없다.**
    
    ---
    
    # 3. 데이터별 확인 결과 요약
    
    | 필요한 데이터 | 공개 문서 확인 결과 | 주요 문서 | 구현 판단 |
    | --- | --- | --- | --- |
    | 구성원 ID | 확인 | Reference: Workers | 1차 Mock 구현 가능 |
    | 이름 | 확인 | Reference: Workers의 `descriptor` | 표시명으로 사용 가능 |
    | 이메일 | 확인 | `primaryWorkEmail` | 1차 구현 가능 |
    | 직함 | 확인 | `businessTitle` | 1차 구현 가능 |
    | 소속 조직 | 확인 | `primarySupervisoryOrganization` | 1차 구현 가능 |
    | 관리자 여부 | 확인 | `isManager` | 1차 구현 가능 |
    | 관리자·보고 관계 | 확인 | Supervisory Organizations, Direct Reports | 여러 API 조합 필요 |
    | 근무 위치 | 확인 | Worker 상세의 `location` | 상세 조회 필요 |
    | 재직 상태 | Legacy Workers에서는 미확인 | Staffing·SOAP 추가 확인 필요 | 공식 필드 확정 전 보류 |
    | 표준 근무시간 | Legacy Workers에서는 미확인 | Staffing·SOAP·RaaS 후보 | 공식 필드 확정 전 보류 |
    | FTE | Legacy Workers에서는 미확인 | Staffing·SOAP·RaaS 후보 | 공식 필드 확정 전 보류 |
    | 휴가 잔여량 | 확인 | Workers `timeOffSummary` | 1차 구현 가능 |
    | 실제 휴가 일정 | 관련 하위 리소스 존재 확인 | Workers/Time off Entries | 정확한 응답 필드 추가 확인 필요 |
    
    ---
    
    # 4. 구성원 ID와 이름
    
    ## 확인한 문서
    
    **문서명:** Reference: Workers
    
    **주소:**
    
    `https://developer.workday.com/documentation/dan1370797991225`
    
    ## 문서에서 확인한 내용
    
    Workday의 직원 컬렉션과 개별 직원 조회 경로는 다음과 같다.
    
    ```
    GET /workers
    GET /workers/{id}
    ```
    
    직원 객체에는 기본적으로 다음 필드가 포함된다.
    
    ```
    {
      "descriptor": "Abby Brennan [C]",
      "id": "6dcb8106e8b74b5aabb1fc3ab8ef2b92",
      "href": "https://{endpoint}/workers/6dcb..."
    }
    ```
    
    - `id`: Workday 객체의 고유 ID
    - `descriptor`: 사람이 읽을 수 있는 객체 표시명
    - `href`: 해당 객체의 상세 조회 주소
    
    Workday REST API의 모든 비즈니스 객체는 일반적으로 `id`, `descriptor`, `href`를 포함한다.
    
    ## 프로젝트 적용
    
    ```
    {
      "external_worker_id": "6dcb8106e8b74b5aabb1fc3ab8ef2b92",
      "display_name": "Abby Brennan [C]",
      "source_system": "WORKDAY"
    }
    ```
    
    ## 주의사항
    
    `descriptor`는 설정에 따라 다음 중 하나일 수 있다.
    
    - 법적 이름
    - 선호 이름
    - 법적 이름과 선호 이름의 조합
    
    따라서 내부 필드명을 `legal_name`으로 정하면 안 되고, 우선은 `display_name`으로 사용하는 것이 안전하다.
    
    ---
    
    # 5. 이메일
    
    ## 확인한 문서
    
    **문서명:** Reference: Workers
    
    **주소:**
    
    `https://developer.workday.com/documentation/dan1370797991225`
    
    ## 확인한 필드
    
    ```
    primaryWorkEmail
    ```
    
    이 필드는 직원 목록인 `workerSummary`와 직원 상세인 `workerProfile` 양쪽에서 확인된다. 공식 예시 응답에도 업무 이메일이 포함된다.
    
    ## 예시 구조
    
    ```
    {
      "id": "worker-id",
      "descriptor": "Emma Hobson",
      "primaryWorkEmail": "ehobson@workday.net"
    }
    ```
    
    ## 프로젝트 적용
    
    이메일은 Google Calendar, Google Drive, Jira 사용자와 Workday 직원을 연결할 때 가장 중요한 공통 키 후보다.
    
    ```
    Workday.primaryWorkEmail
            ↓
    Google 사용자 이메일
            ↓
    Jira 등록 이메일 또는 사용자 매핑
            ↓
    내부 Person ID
    ```
    
    다만 이메일이 변경되거나 누락될 수 있으므로, 이메일만 영구 식별자로 쓰는 것은 위험하다.
    
    권장 구조:
    
    ```
    {
      "person_id": "P-001",
      "identities": {
        "workday_worker_id": "wd-001",
        "work_email": "worker@example.com",
        "jira_account_id": "jira-account-001"
      }
    }
    ```
    
    ---
    
    # 6. 직함
    
    ## 확인한 문서
    
    **문서명:** Reference: Workers
    
    **주소:**
    
    `https://developer.workday.com/documentation/dan1370797991225`
    
    ## 확인한 필드
    
    ```
    businessTitle
    ```
    
    이 필드는 직원 목록과 상세 조회 모두에 포함될 수 있다.
    
    ## 예시
    
    ```
    {
      "businessTitle": "Customer Service Representative"
    }
    ```
    
    ## 프로젝트 적용
    
    ```
    {
      "business_title": "Backend Developer"
    }
    ```
    
    ## 주의사항
    
    `businessTitle`은 업무상 표시 직함이며, 다음 개념과 항상 동일하다고 볼 수 없다.
    
    - Job Profile
    - Position
    - Job Family
    - Grade
    - Role
    - 사내 직급
    
    예를 들어 “선임”, “과장”, “백엔드 개발자”가 기업마다 서로 다른 필드에 저장될 수 있다.
    
    따라서 업무 추천에 사용할 때는 다음처럼 분리하는 것이 좋다.
    
    ```
    {
      "business_title": "Backend Developer",
      "job_level": null,
      "job_family": null,
      "role": null
    }
    ```
    
    공개 Workers REST에서 확인된 것은 우선 `businessTitle`이다.
    
    ---
    
    # 7. 소속 조직
    
    ## 확인한 문서
    
    ### 직원의 주 소속 조직
    
    **문서명:** Reference: Workers
    
    **주소:**
    
    `https://developer.workday.com/documentation/dan1370797991225`
    
    확인 필드:
    
    ```
    primarySupervisoryOrganization
    ```
    
    ### 조직 자체 정보
    
    **문서명:** Reference: Supervisory Organizations
    
    **주소:**
    
    `https://developer.workday.com/documentation/dan1370797989680/ReferenceSupervisoryOrganizations`
    
    ## 직원 응답 구조
    
    ```
    {
      "primarySupervisoryOrganization": {
        "descriptor": "Global Support - UK & Ireland Group",
        "id": "7159687c81c24f91b0769772c4a6ac90",
        "href": "https://{endpoint}/supervisoryOrganizations/715..."
      }
    }
    ```
    
    ## 조직 응답 구조
    
    ```
    {
      "descriptor": "Accounts Payable Department",
      "id": "97c57c8cc22f43ccbb77bdb5a19ab49d",
      "name": "Accounts Payable",
      "workers": "https://{endpoint}/supervisoryOrganizations/{id}/workers",
      "manager": {
        "descriptor": "James Walker",
        "id": "bba6d8ec44e9476aab2902478f2d1a66",
        "href": "https://{endpoint}/workers/bba6..."
      }
    }
    ```
    
    Supervisory Organization 문서에서는 조직 ID, 이름, 관리자와 소속 직원 조회 주소가 실제 JSON 예시로 제공된다.
    
    ## 프로젝트 적용
    
    ```
    {
      "organization": {
        "external_id": "org-001",
        "name": "플랫폼개발팀"
      }
    }
    ```
    
    ---
    
    관리자 관계는 하나의 필드만으로 처리하기보다, 여러 리소스를 조합해야 한다.
    
    ## 8.1 관리자 여부
    
    ### 확인 문서
    
    **문서명:** Reference: Workers
    
    **주소:**
    
    `https://developer.workday.com/documentation/dan1370797991225`
    
    확인 필드:
    
    ```
    isManager
    ```
    
    예시:
    
    ```
    {
      "isManager": true
    }
    ```
    
    이 값은 해당 직원이 관리자인지를 나타내는 Boolean 값이다.
    
    ## 8.2 해당 조직의 관리자
    
    ### 확인 문서
    
    **문서명:** Reference: Supervisory Organizations
    
    **주소:**
    
    `https://developer.workday.com/documentation/dan1370797989680/ReferenceSupervisoryOrganizations`
    
    확인 필드:
    
    ```
    manager
    ```
    
    예시:
    
    ```
    {
      "manager": {
        "descriptor": "Maria Cardoza",
        "id": "cc7fb31eecd544e9ae8e03653c63bfab",
        "href": "https://{endpoint}/workers/cc7..."
      }
    }
    ```
    
    ## 8.3 직접 보고자
    
    ### 확인 문서
    
    **문서명:** Workday REST API Fundamentals
    
    **주소:**
    
    `https://developer.workday.com/documentation/GUID-85810465-bcfb-4fdf-a26d-55eaff3968a8-enHYPHENus/`
    
    공식 Fundamentals 문서는 하위 리소스의 예로 다음 경로를 직접 제시한다.
    
    ```
    GET /workers/{id}/directReports
    ```
    
    이 경로는 특정 관리자에게 직접 보고하는 직원 컬렉션을 조회한다.
    
    ## 프로젝트에서 보고 관계를 만드는 방법
    
    ```
    직원의 primarySupervisoryOrganization.id
            ↓
    Supervisory Organization 조회
            ↓
    organization.manager.id
            ↓
    직원의 manager_id로 변환
    ```
    
    또는:
    
    ```
    관리자 Worker ID
            ↓
    GET /workers/{id}/directReports
            ↓
    직접 보고자 목록
    ```
    
    ## 내부 모델
    
    ```
    {
      "person_id": "P-001",
      "is_manager": false,
      "manager_person_id": "P-010",
      "organization_id": "ORG-001"
    }
    ```
    
    ---
    
    # 9. 근무 위치
    
    ## 확인한 문서
    
    **문서명:** Reference: Workers
    
    **주소:**
    
    `https://developer.workday.com/documentation/dan1370797991225`
    
    ## 확인 필드
    
    ```
    location
    ```
    
    `location`은 직원 목록용 `workerSummary`에는 나타나지 않고, 일반적으로 개별 직원 상세인 `workerProfile`에서 제공된다.
    
    ## 조회 방식
    
    ```
    GET /workers/{id}
    ```
    
    ## 예시 구조
    
    ```
    {
      "location": {
        "descriptor": "San Francisco",
        "id": "6cb76d060ed24d0993b64558ed8ce550"
      }
    }
    ```
    
    ## 프로젝트 적용
    
    ```
    {
      "work_location": {
        "external_id": "location-001",
        "name": "서울"
      }
    }
    ```
    
    ## 주의사항
    
    `location`은 근무지 객체를 나타내지만 다음 정보가 항상 한 번에 포함된다고 보장할 수 없다.
    
    - 상세 주소
    - 국가
    - 시간대
    - 재택·원격 여부
    - 근무 형태
    
    우리 프로젝트에서 지역 또는 시간대가 필요하다면 별도 위치 상세 API나 고객사 데이터 구성이 필요할 수 있다.
    
    ---
    
    # 10. 재직 상태
    
    ## 확인 결과
    
    공개된 `Common (Legacy HCM) > Reference: Workers` 필드 목록에서는 다음과 같은 직접적인 재직 상태 필드를 확인하지 못했다.
    
    ```
    employmentStatus
    active
    workerStatus
    terminationStatus
    ```
    
    Workers 문서에서 확인되는 주요 필드는 다음과 같다.
    
    - `descriptor`
    - `id`
    - `businessTitle`
    - `isManager`
    - `location`
    - `primarySupervisoryOrganization`
    - `primaryWorkEmail`
    - `yearsOfService`
    
    재직 상태 필드는 해당 Legacy Workers 문서에 명시돼 있지 않다.
    
    ## 추가 확인 후보
    
    ### Staffing REST API Explorer
    
    **진입 주소:**
    
    `https://developer.workday.com/`
    
    이후:
    
    ```
    APIs
    → REST API Explorer
    → Production Services
    → Staffing
    → 최신 운영 버전
    → workers 또는 worker 관련 Schema
    ```
    
    Workday REST Fundamentals는 Staffing 서비스 예시 주소로 다음을 제시한다.
    
    ```
    https://{tenantHostname}/api/staffing/v7/{tenant}/workers
    ```
    
    ### SOAP Get Workers
    
    **문서명:** Get Workers
    
    **주소:**
    
    `https://developer.workday.com/documentation/GUID-1f289b82-801e-434e-9e5a-aef66bc35179/GetWorkers`
    
    SOAP `Get_Workers`는 여러 데이터 섹션을 선택해 직원 상세 정보를 반환한다. 공개 가이드는 `Include_Personal_Information` 같은 Boolean 옵션으로 응답 섹션을 선택할 수 있음을 설명한다.
    
    다만 공개 가이드 본문만으로 재직 상태의 정확한 XML 요소명까지는 확인되지 않았다.
    
    ## 판단
    
    ```
    재직 상태 자체가 Workday에 존재할 가능성: 높음
    공개 Legacy Workers REST 필드로 확인됨: 아니오
    현재 Mock에서 공식 Workday 필드로 사용 가능: 보류
    ```
    
    Mock에서 임시로 넣는다면 공식 필드와 구분해야 한다.
    
    ```
    {
      "workday_fields": {
        "id": "worker-001",
        "descriptor": "김지훈"
      },
      "platform_extension": {
        "employment_status": "ACTIVE"
      }
    }
    ```
    
    ---
    
    # 11. 표준 근무시간과 FTE
    
    ## 확인 결과
    
    현재 확인한 공개 `Reference: Workers` 문서에는 다음 이름의 필드가 없다.
    
    ```
    standardWeeklyHours
    scheduledWeeklyHours
    defaultWeeklyHours
    fte
    fullTimeEquivalent
    ```
    
    따라서 Legacy Workers REST 예시만 보고 표준 근무시간과 FTE를 구현할 수는 없다.
    
    ## 확보 가능성이 있는 경로
    
    ### 11.1 Staffing REST API Explorer
    
    **진입 주소:**
    
    `https://developer.workday.com/`
    
    검색 대상:
    
    ```
    Staffing
    workers
    jobs
    positions
    worker job data
    time type
    full time equivalent
    scheduled weekly hours
    default weekly hours
    ```
    
    REST API Explorer는 서비스별 OpenAPI 명세를 확인하고, 실제 테넌트와 연결돼 있으면 테스트할 수 있는 공식 도구다. Workday 문서도 전체 REST 서비스 명세를 확인하려면 REST API Explorer를 사용하라고 안내한다.
    
    ### 11.2 SOAP Get Workers
    
    **문서명:** Get Workers
    
    **주소:**
    
    `https://developer.workday.com/documentation/GUID-1f289b82-801e-434e-9e5a-aef66bc35179/GetWorkers`
    
    대량의 직원 상세 데이터를 여러 응답 섹션으로 받을 수 있기 때문에, 근무시간과 FTE는 직원의 고용·직무·포지션 관련 데이터 섹션에 포함될 가능성이 있다.
    
    하지만 정확한 XML 필드명을 확인하려면 WSDL 또는 Web Service Directory의 스키마를 봐야 한다.
    
    ### 11.3 RaaS
    
    **문서명:** Concept: Reports-as-a-Service
    
    **주소:**
    
    `https://developer.workday.com/documentation/hto1529968349582`
    
    RaaS는 Workday 보고서를 웹 서비스로 노출해 다음 형식으로 받을 수 있다.
    
    - JSON
    - CSV
    - XML
    - Workday XML
    
    고객사 Workday 안에서 FTE와 표준 근무시간을 포함하는 사용자 정의 보고서를 만든다면, 우리 커넥터는 그 보고서를 API처럼 조회할 수 있다.
    
    ## 판단
    
    FTE와 표준 근무시간은 다음처럼 다루는 것이 안전하다.
    
    ```
    현재 공개 Legacy Workers REST에서 확인: 실패
    실제 Workday에서 확보 가능성: 있음
    정확한 공통 필드명 보장: 어려움
    실제 기업 적용 시 현실적인 방법: Staffing·SOAP 또는 RaaS
    ```
    
    ---
    
    # 12. 휴가와 부재 정보
    
    휴가 데이터는 두 종류로 나눠야 한다.
    
    ## 12.1 휴가 잔여량
    
    ### 확인 문서
    
    **문서명:** Reference: Workers
    
    **주소:**
    
    `https://developer.workday.com/documentation/dan1370797991225`
    
    Workers API는 다음 View를 지원한다.
    
    ```
    timeOffSummary
    ```
    
    조회 예시:
    
    ```
    GET /workers/{id}?view=timeOffSummary
    ```
    
    또는 전체 직원:
    
    ```
    GET /workers?view=timeOffSummary
    ```
    
    반환 데이터에는 다음 필드가 포함된다.
    
    ```
    {
      "descriptor": "Logan McNeil",
      "id": "66faa65677834f0a9b586dd5645e9004",
      "totalHourlyBalance": "184"
    }
    ```
    
    일 단위 휴가제도라면 일 단위 잔여량도 별도로 반환될 수 있다고 문서가 설명한다.
    
    ## 활용 가능성
    
    휴가 잔여량은 다음 질문에는 답할 수 있다.
    
    - 이 직원이 사용할 수 있는 휴가가 얼마나 남았는가?
    
    하지만 다음 질문에는 답할 수 없다.
    
    - 이번 주에 언제 휴가를 가는가?
    - 특정 날짜에 업무 배정이 가능한가?
    
    업무 배정에는 잔여량보다 실제 휴가 일정이 더 중요하다.
    
    ---
    
    ## 12.2 실제 휴가·부재 일정
    
    Workday 공식 문서 목록에는 다음 하위 리소스가 존재한다.
    
    ```
    Reference: Workers/Time off Entries
    Reference: Workers/Time Off Plans
    ```
    
    공식 개발자 문서의 Common Legacy HCM 목록에서 해당 문서명이 확인된다.
    
    또한 REST 보안 문서는 휴가 요청 하위 리소스의 예로 다음 경로를 명시한다.
    
    ```
    POST /workers/employee_123/requestTimeOff
    ```
    
    이 하위 리소스에 접근하려면 부모 Worker에 대한 접근 권한도 필요하다.
    
    ## 현재 확인 한계
    
    공개 검색 결과에서는 `Workers/Time off Entries` 문서의 정확한 고유 URL과 전체 응답 JSON 스키마까지 안정적으로 확인하지 못했다.
    
    따라서 현재 확정 가능한 것은 다음이다.
    
    ```
    Time off Entries 하위 리소스 존재: 확인
    휴가 잔여량 View 존재: 확인
    휴가 요청 API 존재: 확인
    Time off Entries의 정확한 필드명: 추가 확인 필요
    ```
    
    ## 우리 내부 모델 예시
    
    아래는 Workday 공식 필드가 아니라, 우리 플랫폼의 표준 모델 예시다.
    
    ```
    {
      "person_id": "P-001",
      "absence_type": "PAID_LEAVE",
      "start_date": "2026-07-27",
      "end_date": "2026-07-28",
      "status": "APPROVED",
      "source_system": "WORKDAY"
    }
    ```
    
    Workday Mock의 외부 응답에는 공식 문서에서 확인된 실제 필드만 사용하고, 위와 같은 구조는 Adapter 뒤의 내부 표준 모델로 두는 것이 안전하다.
    
    ---
    
    # 13. 날짜·시간 처리
    
    ## 확인 문서
    
    **문서명:** Concept: Workday REST API Date, Time, and Time Zone Handling
    
    **주소:**
    
    `https://developer.workday.com/documentation/jas1392746623599/ConceptWorkdayRESTAPIDateTimeandTimeZoneHandling`
    
    ## 확인 내용
    
    Workday REST API는 다음 형식을 사용한다.
    
    ### 날짜
    
    ```
    yyyy-mm-dd
    ```
    
    ### 날짜와 시간
    
    ISO 8601 형식:
    
    ```
    {
      "dateTime": "2023-07-25T23:43:15.000Z"
    }
    ```
    
    시간대가 필요한 경우 `dateTimeZone` 구조를 사용할 수 있다.
    
    ## 프로젝트 적용
    
    휴가·부재와 근무 일정 데이터를 가져올 경우 반드시 다음 작업이 필요하다.
    
    - Workday 시간 형식 파싱
    - UTC 또는 원본 시간대 보존
    - Asia/Seoul로 표시 시 변환
    - 종일 휴가와 시간 단위 휴가 분리
    - 시작일·종료일 경계 처리
    
    ---
    
    # 14. 실제 API 응답에서 고려해야 할 사항
    
    ## 14.1 빈 필드는 응답에서 빠질 수 있음
    
    Workday REST Fundamentals는 필드 값이 비어 있으면 해당 이름과 값의 쌍 자체가 응답에서 빠진다고 설명한다.
    
    예를 들어 이메일이 없는 직원은 다음처럼 올 수 있다.
    
    ```
    {
      "id": "worker-001",
      "descriptor": "김지훈",
      "businessTitle": "Backend Developer"
    }
    ```
    
    `primaryWorkEmail: null`이 아니라 필드가 아예 없을 수 있다.
    
    따라서 Connector는 필드 누락을 처리해야 한다.
    
    ## 14.2 필드 순서를 신뢰하면 안 됨
    
    응답의 JSON 필드 순서는 바뀔 수 있다.
    
    ## 14.3 서비스 업데이트로 필드가 추가될 수 있음
    
    Workday는 릴리스나 패치를 통해 추가 필드를 반환할 수 있다.
    
    따라서 엄격하게 정의되지 않은 추가 필드 때문에 파싱이 실패하면 안 된다.
    
    ## 14.4 상세 조회와 목록 조회가 다름
    
    예를 들어 `location`은 상세 `workerProfile`에만 나타날 수 있다.
    
    따라서 다음 흐름이 필요하다.
    
    ```
    GET /workers
    → 기본 구성원 목록
    
    GET /workers/{id}
    → 위치 등 상세정보 보강
    ```
    
    ---
    
    # 15. 우리 프로젝트의 권장 수집 구조
    
    ## 15.1 1차 구성원 목록 수집
    
    ```
    GET /workers?limit=100&offset=0
    ```
    
    수집 데이터:
    
    - ID
    - 이름
    - 이메일
    - 직함
    - 관리자 여부
    - 주 소속 조직
    
    ## 15.2 직원별 상세정보 보강
    
    ```
    GET /workers/{id}
    ```
    
    추가 데이터:
    
    - 위치
    - 관리하는 조직
    - 상세 연락처
    - 기타 프로필 정보
    
    ## 15.3 조직 정보 수집
    
    ```
    GET /supervisoryOrganizations
    GET /supervisoryOrganizations/{id}
    ```
    
    수집 데이터:
    
    - 조직 ID
    - 조직명
    - 관리자
    - 소속 직원 조회 주소
    
    ## 15.4 직접 보고 관계 수집
    
    ```
    GET /workers/{id}/directReports
    ```
    
    ## 15.5 휴가 잔여량
    
    ```
    GET /workers/{id}?view=timeOffSummary
    ```
    
    ## 15.6 실제 휴가 일정
    
    ```
    Workers/Time off Entries 문서의 정확한 명세 확인 후 추가
    ```
    
    ---
    
    # 16. Workday-compatible Mock 1차 스키마
    
    공개 문서에서 직접 확인된 필드만 사용한 예시다.
    
    ```
    {
      "total": 1,
      "data": [
        {
          "descriptor": "김지훈",
          "id": "19f7dabb79994d29931cd139df6272ed",
          "href": "/workers/19f7dabb79994d29931cd139df6272ed",
          "businessTitle": "Backend Developer",
          "primaryWorkEmail": "jihoon@example.com",
          "isManager": false,
          "primarySupervisoryOrganization": {
            "descriptor": "플랫폼개발팀",
            "id": "7159687c81c24f91b0769772c4a6ac90",
            "href": "/supervisoryOrganizations/7159687c81c24f91b0769772c4a6ac90"
          }
        }
      ]
    }
    ```
    
    직원 상세:
    
    ```
    {
      "descriptor": "김지훈",
      "id": "19f7dabb79994d29931cd139df6272ed",
      "businessTitle": "Backend Developer",
      "primaryWorkEmail": "jihoon@example.com",
      "isManager": false,
      "location": {
        "descriptor": "서울",
        "id": "location-001"
      },
      "primarySupervisoryOrganization": {
        "descriptor": "플랫폼개발팀",
        "id": "org-001"
      }
    }
    ```
    
    조직:
    
    ```
    {
      "descriptor": "플랫폼개발팀",
      "id": "org-001",
      "name": "Platform Development",
      "workers": "/supervisoryOrganizations/org-001/workers",
      "manager": {
        "descriptor": "박민수",
        "id": "worker-010",
        "href": "/workers/worker-010"
      }
    }
    ```
    
    ---
    
    # 17. 내부 공통 Person 모델
    
    Workday 응답을 우리 서비스에서 직접 사용하지 않고 다음처럼 표준화한다.
    
    ```
    {
      "person_id": "P-001",
      "external_ids": {
        "workday_worker_id": "19f7dabb79994d29931cd139df6272ed"
      },
      "display_name": "김지훈",
      "work_email": "jihoon@example.com",
      "business_title": "Backend Developer",
      "organization_id": "ORG-001",
      "manager_person_id": "P-010",
      "is_manager": false,
      "work_location": "서울",
      "employment_status": null,
      "standard_weekly_hours": null,
      "fte": null,
      "source": {
        "system": "WORKDAY",
        "endpoint": "/workers/19f7...",
        "synced_at": "2026-07-20T10:00:00Z"
      }
    }
    ```
    
    확인되지 않은 값은 임의로 만들지 않고 `null`로 유지하거나 다른 데이터 소스에서 보완한다.
    
    ---
    
    # 18. Google·Jira와 결합하는 방식
    
    ```
    Workday
    - 구성원 ID
    - 이메일
    - 조직
    - 직함
    - 관리자 관계
    - 위치
    
    Google Calendar
    - 회의
    - 일정
    - 출장
    - 실제 휴가 일정 보완 가능
    
    Google Drive
    - 이력서
    - 경력
    - 기술
    - 프로젝트 산출물
    
    Jira
    - 현재 태스크
    - 담당자
    - 우선순위
    - 마감일
    - 진행 상태
    ```
    
    이메일을 중심으로 연결하되 외부 ID를 별도로 유지한다.
    
    ```
    Workday primaryWorkEmail
            ↓
    Identity Mapping
            ↓
    Google email / Jira account
            ↓
    Internal Person ID
    ```
    
    ---
    
    # 19. 최종 데이터 채택안
    
    ## 19.1 공식 명세 기반으로 바로 구현
    
    - `id`
    - `descriptor`
    - `primaryWorkEmail`
    - `businessTitle`
    - `isManager`
    - `primarySupervisoryOrganization`
    - `location`
    - Supervisory Organization의 `manager`
    - `directReports`
    - `timeOffSummary`
    
    ## 19.2 추가 명세 확인 후 구현
    
    - 재직 상태
    - 표준 근무시간
    - FTE
    - Time Off Entries의 실제 필드
    - 상세 근무 형태
    - Position·Job Profile·Job Family
    
    ## 19.3 프로젝트 확장 필드로 구분
    
    공식 Workday 명세에서 확인되지 않은 값을 Mock 응답에 넣을 경우 별도 네임스페이스로 분리한다.
    
    ```
    {
      "workday": {
        "id": "worker-001",
        "descriptor": "김지훈"
      },
      "platformExtension": {
        "employmentStatus": "ACTIVE",
        "standardWeeklyHours": 40,
        "fte": 1.0
      }
    }
    ```
    
    하지만 더 바람직한 방법은 확장 필드를 외부 Mock 응답이 아니라 Adapter 이후의 내부 모델에서만 사용하는 것이다.
    
    ---
    
    # 20. 최종 결론
    
    Workday 공개 문서에는 실제 필드 표와 JSON 응답 예시가 있으며, 다음 정보는 공식 자료를 기준으로 Workday-compatible Mock API에 반영할 수 있다.
    
    - 구성원 ID와 이름
    - 이메일
    - 직함
    - 소속 조직
    - 관리자 여부
    - 조직 관리자와 보고 관계
    - 근무 위치
    - 휴가 잔여량
    
    다만 다음 정보는 현재 확인한 `Reference: Workers` 문서에 직접 명시되지 않았다.
    
    - 재직 상태
    - 표준 근무시간
    - FTE
    - 실제 휴가 일정의 정확한 응답 필드
    
    따라서 1차 Mock은 공식 공개 필드만으로 구현하고, FTE·근무시간·재직 상태는 Staffing API Explorer, SOAP `Get_Workers`, WQL 또는 RaaS에서 추가 검증한 뒤 반영해야 한다.
    
    우리 프로젝트에서 가장 안전한 구현 원칙은 다음과 같다.
    
    > 공개 Workday 문서에서 확인된 필드는 Workday-compatible Mock에 구현하고, 확인되지 않은 항목은 Workday 공식 필드처럼 만들지 않는다. 부족한 데이터는 Google Calendar, Drive, Jira 또는 내부 표준 모델에서 보완하며, 실제 Workday 테넌트를 확보하면 Adapter만 실제 구현체로 교체한다.
    > 

jIRA에서 프로젝트로 그룹화해서 사람별로 그룹화

프로젝트 하나당 필드가 39개 인데, 한 사람당 프로젝트가 하나가 아니라 여러 개일 수 있는데, 하나의 프로젝트를 생성할 때 한 사람이 아닌 30명 이라면 30 * 개인의 프로젝트 개수 * 39 가 되는데, 이러면 너무 느려지는 거 같아.