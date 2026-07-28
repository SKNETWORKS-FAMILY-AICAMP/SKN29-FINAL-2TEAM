# SKN29 FINAL 2팀 프로젝트 기본 컨텍스트

## 프로젝트 정의

이 프로젝트는 프로젝트 문서와 조직 데이터를 분석해 업무와 담당자 후보를 제안하고, 근거와 위험 요소를 보여준 뒤 PM 또는 팀장이 최종 결정하도록 지원하는 **AI 프로젝트 운영 코파일럿**이다.

단순 챗봇이나 완전 자동 업무 배정기가 아니라 다음 원칙을 따른다.

- AI는 후보와 근거를 제안한다.
- PM은 추천을 검토·수정·승인한다.
- PM이 수정한 결과도 다시 검증한다.
- 필수 데이터가 부족하면 임의로 추론하지 않는다.
- 추천, 수정, 승인과 그 근거를 추적 가능하게 기록한다.

## 핵심 사용자 흐름

```text
PM이 프로젝트·Drive 폴더·추가 조건 선택
→ PDF/DOCX 문서 구조 보존 추출
→ 프로젝트 지식 모델과 업무 생성
→ Jira·People DB 기준 업무량·역량·부재 확인
→ 담당자 후보와 근거 제시
→ PM 수정
→ 수정 결과 재검증
→ 최종 승인·결정 기록
→ Jira 반영
```

## MVP 범위

### 입력 데이터

- Google Drive
  - 프로젝트 기획서는 필수
  - 우선 지원 형식은 PDF와 DOCX
  - 폴더 선택과 폴더 역할 지정을 통해 문서 범위를 제한
- Jira
  - 기존 업무, 일정, 상태, 잔여 공수, 계정 식별 정보
- People DB 또는 HR Mock
  - 조직, 구성원, 역할, 스킬, 근무시간, 휴가·부재, 책임 수준

Google Calendar 입력 연동은 데이터 신뢰성과 범위 문제로 MVP에서 제외하거나 후속 출력 기능으로 검토한다.

### 분석과 추천

- 문서 구조, 표, 이미지 맥락을 최대한 보존한다.
- 업무, 담당 역할, 마감일, 예상 공수, 우선순위, 제약조건을 구조화한다.
- 업무량은 Agent의 주관적 추론이 아니라 결정론적 계산 코드로 처리한다.
- 후보 추천은 역량, 경험, 업무량, 가용시간, 휴가·부재, 프로젝트 조건을 사용한다.
- Vector DB와 RAG는 문서 구조화와 근거 검색을 위한 보조 수단이다.
- 담당자 추천의 주요 판단 근거는 People DB와 Jira의 검증 가능한 데이터다.

### 검증 상태

- `SUCCESS` 또는 `PASS`: 승인 가능
- `PARTIAL_RESULT` 또는 `CONDITIONAL`: 데이터 부족이나 경고가 있지만 제한적으로 진행 가능
- `BLOCKED` 또는 `REJECT`: 필수 조건 위반 또는 필수 데이터 누락으로 진행 불가

## 전체 아키텍처

1. 사용자·입력 레이어
2. Google Drive·Jira·People DB Connector
3. 정규화·Canonical Data·Snapshot
4. Feature Readiness
5. 업무 추출·업무량 계산·후보 추천·검증
6. PM 검토·수정·승인·Jira 반영
7. 감사·실행 이력·보안·접근 통제

문서 계보의 기본 방향:

```text
Document
→ DocumentBlock / Chunk
→ KnowledgeItem
→ ProjectKnowledgeModel
→ Task
→ AnalysisSnapshot
```

인력 데이터의 기본 방향:

```text
Organization
→ Person
→ PersonSkill / PersonAbsence / WorkSchedule
→ PersonSnapshot
```

## 기술 스택

- Backend: Django, Django REST Framework
- Frontend: React, Vite, TypeScript
- Database: PostgreSQL, pgvector
- Local: Docker Compose
- AWS 시연 환경: EC2, RDS PostgreSQL, S3

## 2026-07-28 기준 구현 상태

구현됨:

- Django/DRF 프로젝트 기반
- React/Vite/TypeScript 실행 환경
- Figma 목업 기반 React 화면 14개와 기본 라우팅
- 목업 데이터 기반 프론트엔드 핵심 화면 종단 라우팅
- 목업 기반 커넥터·폴더·역할·Jira 온보딩 화면 간 라우팅
- 목업 추천 후보 수동 변경과 결과 검색·필터·페이지·재배정 상호작용
- 프론트엔드 프로젝트·People API 호출 계층과 인증·필수 데이터 부족 시 차단 UI
- PostgreSQL/pgvector Docker Compose
- 프로젝트 및 분석 실행 기본 API
- 조직 및 직원 조회 API
- Django Admin 기반 People DB
- 조직, 직원, 스킬, 휴가, 근무 기준, Identity Link 모델
- 데모 People DB seed
- People DB 합성 목업 SQL과 HR·비정형 문서 DB 설계 문서
- Health API와 최소 API 테스트
- EC2/RDS/S3 이전 매뉴얼과 AWS용 Compose

미구현 또는 스텁:

- React 인증 연동과 보호 API의 실제 데이터 표시
- AnalysisRun 연동과 서버 Readiness 상태 기반 진행 제어
- Google Drive/Jira Connector
- PDF/DOCX Parser
- DocumentBlock, Chunk, KnowledgeItem
- Project Knowledge Model
- Task와 Snapshot
- Feature Readiness 실제 판정
- 업무량 계산
- 후보 추천과 근거
- PM 수정·재검증·승인
- Jira 반영
- S3 문서 저장 어댑터

## 구현 우선순위

새로운 범용 기능을 계속 설계하기보다 아래 종단 시나리오를 먼저 완성한다.

```text
데모 프로젝트 생성
→ 기획서 1개 등록
→ 업무 3~5개 추출
→ People DB + Jira Fixture 조회
→ Readiness 판정
→ 후보 3명과 근거 제시
→ PM이 1건 수정
→ 재검증 경고
→ 최종 승인
```

## 화면과 UX 원칙

- 관리자가 이해할 수 있는 업무 언어를 사용한다.
- Vector DB, Chunk Size, Prompt 같은 내부 기술 용어를 일반 화면에 직접 노출하지 않는다.
- 무엇을 분석했는지, 왜 추천했는지, 무엇이 부족한지를 표시한다.
- 프로젝트별 추가 조건과 조직 공통 정책을 구분한다.
- `설정`은 관리자용 조직·권한·분석·배정·데이터 운영 정책을 관리한다.
- 개인 환경설정과 마이페이지는 후순위다.

## 기준 자료

- Notion: https://app.notion.com/p/SKN29-FINAL-2-bd334713f167827bb5560138c7edcd89
- Figma 목업: https://www.figma.com/design/delMK7SPWGMZjBaTIpb2VP/
- Figma 전체 흐름: https://www.figma.com/board/lJCWw2jKwewFjb5QC5SsSx/
- GitHub: https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN29-FINAL-2TEAM
- ChatGPT나 Codex에서 프로젝트 관련 나눈 대화

자료가 충돌하면 최신 회의·멘토링 결정과 실제 GitHub 구현 상태를 우선 확인하고, 충돌을 숨기지 말고 명시한다.

## 주의사항

- 서비스명은 `halil`로 확정한다. 문서 설명에서는 필요에 따라 `AI 프로젝트 운영 코파일럿`을 병기할 수 있다.
- 민감정보와 자격 증명을 문서, 코드, 커밋, 응답에 노출하지 않는다.
- Notion의 일부 공유 자료에 평문 자격 증명이 있었으므로 재사용하거나 인용하지 않는다.
- 기존 사용자 변경사항을 보존하고 관련 없는 파일을 수정하지 않는다.
