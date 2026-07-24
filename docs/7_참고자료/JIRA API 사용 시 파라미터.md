# JIRA API 사용 시 파라미터

생성일: 2026년 7월 20일 오전 10:22

## **1. 자료 설명**

---

- Google Docs
회의록(회의 제목, 프로젝트 명, 참석자, 날짜, 내용, Action Item)
기획서(프로젝트 명, 요구사항, 기능 목록)
- Google Calendar
일정(시작/종료), 회의 일정, 휴가, 외근
- Jira
Task : 업무의 제목
Description (업무 설명)
Assignee (담당자)
Reporter (업무 생성자)
Priority (우선순위) : 업무가 얼마나 급한지
Status (현재 상태) : Task가 어디까지 진행되었는지
Sprint (스프린트)
Story Point : 업무 난이도 또는 예상 작업량
Due Date (마감일)
Project (프로젝트) : 어떤 프로젝트인지
Issue Type (업무 종류)
: story(새로운 기능 개발), bug, task(일반 업무), epic(큰 기능 묶음)
Label (라벨) : 사용자가 붙이는 태그
Component (컴포넌트) : 시스템 구조 기준으로 backend, frontend

사람 정보(어떻게?)
내 생각 : 이정도 정보는 첫 회원가입시에 받자
이름, 이메일
직무(Role)
소속 팀(Department)
경력 수준(Level)
skill(?)
프로젝트 경험(?)
최근 완료한 Task

⇒ 이거 workday API로 대체될 듯

## **2. 자료 첨부**

---

# 1. Data Connector Layer (유지)

### 기존

```
Google Docs
Google Calendar
Jira
Slack
```

### 수정

```
Google Docs
Google Calendar
Jira
Slack (확장 기능)
```

### 이유

- Slack은 현재 핵심 의사결정 데이터가 거의 없음
- 알림(Notification) 용도로 충분
- MVP에서는 우선순위를 낮춘다.

**변경 없음 (Slack만 Optional 표시)**

---

# 2. Data Integration Layer → Harness Layer로 확장

## 기존

```
OAuth / API

Webhook

OCR

Data Normalize

Vector DB
```

---

## 수정

```
OAuth / API

Webhook

Data Normalize

*Context Memory*

Vector DB

*Permission*

*Logging*

*Tool Registry*
```

---

## 추가 이유

### Context Memory

**근거**

Harness Engineering

기존에는

```
필요할 때마다

Google Docs

Jira

Calendar

조회
```

하지만 Agent는

현재 상황(Context)을 계속 유지해야 한다.

예를 들어

```
현재 Sprint

현재 프로젝트

현재 담당자

회의 일정
```

을 기억한다.

---

### Logging

**근거**

Explainable AI

Harness

Agent Engineering

AI가

왜 추천했는지

남겨야 한다.

예를 들어

```
추천

↓

김철수

↓

Reason

Story Point 18

회의 2시간

Backend
```

로그 저장

---

### Tool Registry

**근거**

Harness

Agent는

Tool을 선택해서 사용한다.

예를 들어

```
회의 일정 확인

↓

Calendar API
```

---

# 3. Supervisor Agent 수정

현재 구조

```
Context Builder
↓
Task Extractor
↓
Role + Skill Match
↓
Workload Analyzer
↓
Assignment Planner
```

---

## 수정

```
Workflow Router
↓
Context Builder
↓
Task Extractor
↓
Adaptive Retrieval
↓
Role / Context Matcher
↓
Workload Analyzer
↓
Assignment Planner
↓
Reviewer Agent
```

---

# Workflow Router

---

Workflow Router

---

### 이유

논문에서는 Planner지만 우리 프로젝트는 Workflow Routing 정도만 해도 충분

예를 들어

```
회의록
↓
Task 생성
↓
Assignment 필요?
↓
Assignment Planner 호출
```

---

# Context Builder

유지

---

### 이유

현재 프로젝트 Context

현재 Sprint

현재 일정

현재 Task

통합

---

# Task Extractor

유지

---

### 이유

Google Docs

↓

Task 추출

↓

Action Item 추출

---

# Adaptive Retrieval

```
Task 추출
↓
담당자 없음?
↓
Jira 조회
↓
마감일 없음?
↓
Calendar 조회
추천
```

---

---

### 이유

Adaptive RAG 논문의 철학은 유지

하지만

무한 Loop는 구현하지 않음

필요한 Connector만

추가 조회

---

# Role + Skill Match → Role / Context Matcher

---

### 수정

```
Role
Project History
Jira History
Task History
```

---

---

예를 들어

```
최근

Backend

Task

15개

↓

Backend 적합
```

---

# Workload Analyzer

유지

---

### 분석

Story Point

Priority

Due Date

Task 개수

Calendar 일정

---

# Assignment Planner

유지

---

### 역할

추천 생성

---

# Reviewer Agent (추가)

### 새로 추가

---

### 역할

추천 검증

예를 들어

```
추천

↓

김철수

↓

Reviewer

- 과부하?

- 휴가?

- 마감 임박?

- Role 적합?

↓

추천 승인
```

---

### 이유

Reflection

Self Verification

최근 Multi-Agent 논문

---

# Human in the Loop

유지

---

PM 승인

---

# Execution Layer

유지

---

```
Jira

Calendar

Google Docs

Slack
```

---

# Monitoring Layer 수정

현재

```
진행상황
↓
결과분석
↓
정책반영
```

---

## 수정

```
Progress Tracking
↓
Bottleneck Detection
↓
Feedback Log
↓
Recommendation History
↓
Prompt Context
```

---

---

### 이유

실제로 AI가 학습하는 것은 구현하지 않음

---

대신 PM

피드백 저장

---

예를 들어

```
추천
↓
거절
↓
이유 저장
↓
다음 Prompt
참고
```

---

이건

실제로 구현 가능

---

# 논문 인용 수정

---

### Harness

```
최근 Agent Engineering / Harness Engineering에서 제안하는 실행 환경 구조
```

---

### HERA

발표 전

원문 확인

---

안 맞으면

대체

Reflexion

또는

Generative Agents

---

# 최종 구조

```
Connector Layer

↓

Harness Layer
- Normalize
- Context Memory
- Logging
- Tool Registry

↓

Supervisor

① Workflow Router

↓

② Context Builder

↓

③ Task Extractor

↓

④ Adaptive Retrieval

↓

⑤ Role / Context Matcher

↓

⑥ Workload Analyzer

↓

⑦ Assignment Planner

↓

⑧ Reviewer Agent

↓

Recommendation

↓

Human Approval

↓

Execution

↓

Monitoring

- Progress Tracking

- Bottleneck Detection

- Feedback Log

- Recommendation History

- Prompt Context
```

---

# 최종 변경사항 요약

| 구분 | 변경 내용 | 변경 이유 |
| --- | --- | --- |
| Data Layer | Context Memory 추가 | 현재 업무 맥락 유지(Harness) |
| Data Layer | Logging 추가 | 추천 근거 저장 및 설명 가능성 확보 |
| Data Layer | Tool Registry 추가 | 필요한 커넥터를 선택적으로 사용 |
| Planner | Workflow Router로 축소 | MVP 범위에 맞게 역할 단순화 |
| Adaptive Retrieval | 무한 탐색 → 조건부 2단계 조회 | 구현 가능성과 비용 고려 |
| Skill Match | Role / Context Matcher로 변경 | Skill DB 없이 Jira 이력 기반 추론 |
| Reviewer Agent | 추가 | 추천 결과 검증(Reflection) |
| Monitoring | Experience Memory → Feedback Log + Recommendation History | 학습 대신 피드백 기반 재활용으로 현실화 |
| 논문 인용 | HERA 원문 확인, Harness 표현 수정 | 발표 시 인용 정확성 확보 |

이 버전이 **현재 구현 가능성(MVP), 논문 근거, 발표 방어**를 가장 균형 있게 만족하는 최종 아키텍처라고 생각합니다.

### 시스템 필드 (모든 Jira 사이트 공통, 39개)

| 그룹 | 필드 (id → 한글명) |
| --- | --- |
| 기본 정보 | `summary`(요약), `description`(설명), `issuetype`(이슈 유형), `issuekey`(키), `project`(프로젝트) |
| 상태/흐름 | `status`(상태), `statusCategory`(상태 범주), `resolution`(해결), `resolutiondate`(해결됨) |
| 사람 | `creator`(작성자), `reporter`(보고자), `assignee`(담당자) |
| 시간 | `created`(만듦), `updated`(업데이트), `duedate`(기한), `lastViewed`(최근에 봄) |
| 계층/연결 | `parent`(상위 항목), `subtasks`(하위 작업), `issuelinks`(연결된 이슈) |
| 협업 | `comment`(댓글), `attachment`(첨부 파일), `watches`(지켜보는 사람), `votes`(투표) |
| 작업추적 | `timetracking`, `timeoriginalestimate`, `timeestimate`, `timespent`, `worklog`(로그 작업), `progress`/`aggregateprogress` |
| 분류 | `priority`(우선순위), `labels`(레이블), `components`(컴포넌트), `fixVersions`(수정 버전), `versions`(영향을 받는 버전) |
| 기타 | `environment`(환경), `security`(보안 등급), `issuerestriction`(제한) |

### 커스텀 필드 (이 사이트 KAN 프로젝트 전용, 6개)

| id | 이름 | 타입 | 의미 |
| --- | --- | --- | --- |
| `customfield_10015` | 시작 날짜 (Start date) | date | 이슈 시작일 |
| `customfield_10017` | 이슈 색상 (Issue color) | string | 칸반보드 카드 색상 |
| `customfield_10019` | 순위 (Rank) | lexo-rank | 보드/백로그 내 정렬 순서 (Jira Software 전용 내부 필드) |
| `customfield_10021` | Flagged | 체크박스 배열 | "플래그" 표시 여부 |
| `customfield_10000` | development | any | PR/커밋/브랜치 연동 정보 (Bitbucket, GitHub 연동 시 채워짐) |
| `customfield_10001` | Team | team | 담당 팀 |

이 커스텀 필드 6개는 **사이트마다 다릅니다** — 다른 회사 Jira는 스토리 포인트, 승인자, 고객사 같은 완전히 다른 커스텀 필드를 쓸 수 있어요. 그래서 실제 커넥터를 만들 땐 연동 대상 사이트마다 이 `/rest/api/3/field` 호출을 한 번씩 해서 필드 매핑을 자동으로 구성하는 게 안전합니다.

### 참고: 이건 "이슈" 필드만입니다

지금까지 테스트한 건 이슈 레벨 데이터예요. 아래는 **아직 안 가져와본** 다른 데이터 유형이고, 이슈 필드와는 별도 엔드포인트가 필요해요:

- 프로젝트 메타(컴포넌트/버전/권한 스킴) → `/project/{key}`
- 보드/스프린트 → `/rest/agile/1.0/board`, `/sprint`
- 사용자 목록 → `/users/search`
- 워크플로우 전이 가능 목록 → `/issue/{key}/transitions`

---

## 2. 테스트 사이트 기본 정보

| 항목 | 값 |
| --- | --- |
| 프로젝트 | KAN (SKN29_Final_2Team), SAM1 (예제) |
| 프로젝트 방식 | Team-managed (`simplified: true`, `style: next-gen`) |
| 이슈 타입 (7개) | 에픽, 스토리, 작업, 하위 작업, 기능, 요청, 버그 |
| 보드 | KAN board (id=2, **칸반형/simple** → 스프린트 미지원) |
| 상태 흐름 (4단계) | 해야 할 일 → 진행 중 → 검토 중 → 완료 |

---

## 3. 읽기(Read)로 확인된 엔드포인트

| 목적 | 엔드포인트 | 비고 |
| --- | --- | --- |
| 내 계정 확인 | `GET /rest/api/3/myself` | 인증 테스트용 |
| 프로젝트 목록 | `GET /rest/api/3/project/search` |  |
| 프로젝트 상세 | `GET /rest/api/3/project/{key}` | 이슈타입, 리드, 역할, 컴포넌트/버전 |
| 이슈 검색 (JQL) | `GET /rest/api/3/search/jql?jql=...&fields=...` | **구 `/rest/api/3/search`는 폐지됨.** `fields` 생략 시 `id`만 반환. 페이지네이션은 `nextPageToken` 방식 |
| 이슈 상세 | `GET /rest/api/3/issue/{key}?expand=names` | `names`로 커스텀필드 사람이 읽는 이름 매핑 가능 |
| 전체 필드 카탈로그 | `GET /rest/api/3/field` | 이 사이트의 시스템+커스텀 필드 전체 목록 |
| 보드 목록 | `GET /rest/agile/1.0/board?projectKeyOrId={key}` |  |
| 스프린트 목록 | `GET /rest/agile/1.0/board/{id}/sprint` | 칸반 보드면 `400` 에러 ("보드는 스프린트를 지원하지 않습니다") — 정상 |
| 사용자 목록 | `GET /rest/api/3/users/search` | `accountType: atlassian`(사람) vs `app`(봇) 구분 필요 |
| 사용자 검색 | `GET /rest/api/3/user/search?query=...` | 특정 사용자의 accountId 조회 |
| 전이 가능 상태 | `GET /rest/api/3/issue/{key}/transitions` | 상태 변경 전 필수 조회 (transition id 확인용) |

### 3-1. 이슈 필드 — 시스템 필드 (39개, 공통)

| 그룹 | 필드 |
| --- | --- |
| 기본 정보 | summary, description, issuetype, issuekey, project |
| 상태/흐름 | status, statusCategory, resolution, resolutiondate |
| 사람 | creator, reporter, assignee |
| 시간 | created, updated, duedate, lastViewed |
| 계층/연결 | parent, subtasks, issuelinks |
| 협업 | comment, attachment, watches, votes |
| 작업추적 | timetracking, timeoriginalestimate, timeestimate, timespent, worklog, progress |
| 분류 | priority, labels, components, fixVersions, versions |
| 기타 | environment, security, issuerestriction |

### 3-2. 이슈 필드 — 커스텀 필드 (6개, **이 사이트 전용** — 사이트마다 다름)

| id | 이름 | 타입 | 의미 |
| --- | --- | --- | --- |
| customfield_10015 | 시작 날짜 (Start date) | date | 이슈 시작일 |
| customfield_10017 | 이슈 색상 (Issue color) | string | 칸반보드 카드 색상 |
| customfield_10019 | 순위 (Rank) | lexo-rank | 보드/백로그 정렬 순서 |
| customfield_10021 | Flagged | checkbox[] | 플래그 표시 여부 |
| customfield_10000 | development | any | PR/커밋/브랜치 연동 정보 |
| customfield_10001 | Team | team | 담당 팀 |

> 커넥터를 만들 땐 연동 대상 Jira 사이트마다 `/rest/api/3/field`를 호출해서 필드 매핑을 자동 구성해야 함.
> 

---

## 4. 쓰기(Write)로 확인된 엔드포인트

| 목적 | 메서드/엔드포인트 | 확인 결과 |
| --- | --- | --- |
| 이슈 생성 | `POST /rest/api/3/issue` | 성공 (`project.key`, `summary`, `issuetype.name` 세 필드만으로 생성됨 — team-managed라서 필수 필드가 단순함) |
| 담당자 지정 (생성 시) | 생성 body에 `assignee.accountId` 포함 | 성공 — 생성과 동시에 담당자 지정됨 |
| 담당자 지정 (기존 이슈) | `PUT /rest/api/3/issue/{key}` (body: `fields.assignee`) | 미실행 — 204 응답 예상 |
| 상태 변경 | `POST /rest/api/3/issue/{key}/transitions` (body: `transition.id`) | 미실행 — transition id는 3장 표 참고 |

### 실제 생성된 테스트 데이터

- KAN-6 등 여러 개, 최종적으로 **KAN-33** (담당자: 최원빈으로 지정 성공)

---

## 5. 테스트 중 확인된 주의사항

- **`/rest/api/3/search` 완전 폐지** → `/rest/api/3/search/jql`로 마이그레이션 필수, 페이지네이션도 `startAt` → `nextPageToken`으로 변경됨
- **team-managed vs company-managed** 프로젝트에 따라 이슈 생성 시 필수 필드 개수가 다름 (KAN은 team-managed라 단순)
- **사용자 목록에 봇 계정이 섞여 있음** — `accountType: app`인 Slack, Automation for Jira 등은 실제 담당자 후보에서 제외해야 함
- **칸반 보드는 스프린트 API가 애초에 동작 안 함** — 에러가 아니라 정상적인 "지원 안 됨" 신호로 처리해야 함
- **cmd(Windows)에서 curl 사용 시** JSON body의 큰따옴표를 `\"`로 이스케이프해야 함 (bash와 문법 다름)
- **API 토큰은 절대 채팅/커밋/로그에 노출 금지** — 노출되면 즉시 폐기(revoke) 후 재발급