# AI 프로젝트 운영 코파일럿 중간발표 To-Do

> 기준일: 2026-07-28  
> 실행 환경: 로컬 Docker Compose  
> 목표: Google Drive 기획서를 분석해 업무를 추출하고, 로컬 People DB와 Jira 업무량을 기준으로 담당자를 추천·검증하여 PM 화면에 출력한다.

## 1. 중간발표 완료 기준

아래 종단 흐름이 하나의 시연 시나리오에서 끝까지 실행되어야 한다.

```text
기획서
→ 구조화
→ Task 확인
→ 인력·업무량 조회
→ 추천
→ 검증
→ PM 결과 확인
```

기능 개수를 늘리는 것보다 동일한 입력과 데이터 버전에서 결과를 재현하고, 추천 근거와 원문 출처를 설명할 수 있는 상태를 우선한다.

### 중간발표 실행 환경

```text
사용자 브라우저
      │
      ▼
로컬 Docker Compose
├─ frontend : React 화면
├─ web      : Django API
└─ db       : PostgreSQL + pgvector
                    │
                    └─ 로컬 문서 저장소
```

- AWS 계정 지급 여부는 중간발표 구현의 선행조건으로 두지 않는다.
- DB는 로컬 Docker의 PostgreSQL + pgvector를 사용한다.
- Drive에서 내려받은 원문은 로컬 문서 저장소에 보관한다.
- AWS 계정을 받은 후 환경변수와 저장소 구현체를 교체해 RDS·S3로 전환한다.

---

## P0. 시연 기준 확정

- [ ] 모든 팀원이 로컬 Docker Compose를 실행할 수 있는지 확인
- [ ] 중간발표 종단 시나리오 1개 확정
- [ ] 시연용 프로젝트 기획서 1~2개 선정
- [ ] 시연용 직원 8~10명 구성
- [ ] 시연용 Jira 프로젝트와 이슈 준비
- [ ] 최종 출력할 Task 수 결정
- [ ] 정상 추천 시나리오 1개 준비
- [ ] `PARTIAL_RESULT` 또는 `CONDITIONAL_PASS` 시나리오 1개 준비
- [ ] 화면과 백엔드 API 요청·응답 스키마 확정

완료 기준: 어떤 데이터를 입력하고 어떤 결과를 보여줄지 팀원이 동일하게 설명할 수 있어야 한다.

---

## P1. People DB 최소 데이터 완성

현재 기본 모델이 구현되어 있으므로 시연 데이터를 보강한다.

- [ ] 조직과 상하위 조직 데이터 입력
- [ ] 직원·직무·재직 상태 입력
- [ ] Skill·숙련도 입력
- [ ] 책임수준 입력
- [ ] 주간 기준 근무시간/FTE 입력
- [ ] 휴가·부재 데이터 입력
- [ ] Jira `accountId` 매핑 데이터 입력
- [ ] 조직도 조회 API 보완
- [ ] 직원 상세·Skill·가용성 조회 API 작성

완료 기준: 직원별 역할, Skill, 책임수준, 가용시간을 API에서 조회할 수 있어야 한다.

---

## P2. Google Drive 문서 처리

- [ ] Google Drive Connector 인증 구성 및 지정 폴더 읽기 연결
- [ ] 선택 폴더의 파일 목록 조회
- [ ] PDF·DOCX 파일 다운로드
- [ ] 원문 파일 로컬 문서 저장소에 저장
- [ ] 문서 메타데이터 로컬 PostgreSQL에 저장
- [ ] 원문 파일의 `storage_key`·해시·버전·수정 시각 저장
- [ ] PDF·DOCX 텍스트 파싱
- [ ] ContentBlock 생성
- [ ] Chunk 생성
- [ ] 문서·페이지·청크·원문 위치 연결
- [ ] Embedding 생성
- [ ] pgvector 저장
- [ ] Citation 조회 가능 여부 확인

완료 기준:

```text
Drive 파일
→ 로컬 원문 저장소
→ 문서 메타데이터
→ ContentBlock
→ Chunk
→ Embedding
→ Citation
```

위 흐름이 하나의 문서에서 정상적으로 실행되어야 한다.

---

## P3. ProjectKnowledgeModel과 Task 추출

- [ ] 프로젝트 목표 추출
- [ ] 포함·제외 범위 추출
- [ ] 요구사항 추출
- [ ] 결정·제약조건 추출
- [ ] 일정·마일스톤 추출
- [ ] 리스크 추출
- [ ] 완료 조건 추출
- [ ] 역할·담당 영역 추출
- [ ] 중복 항목 통합
- [ ] 원문 Citation 연결
- [ ] ProjectKnowledgeModel 저장
- [ ] NewTaskDraft 생성
- [ ] Task명·역할·Skill·공수·기간·우선순위 생성
- [ ] `EXTRACTED`, `GENERATED`, `AI_SUGGESTED`, `USER_ADDED` 출처 구분
- [ ] PM 승인·수정·반려 API 작성

완료 기준: 기획서에서 추출된 Task가 원문 근거와 함께 화면에 표시되어야 한다.

---

## P4. Jira 읽기 및 업무량 계산

- [ ] Jira 연결 설정
- [ ] `/field` Discovery
- [ ] 프로젝트 조회
- [ ] 사용자 조회
- [ ] Board·Sprint 조회
- [ ] 이슈·담당자·상태·우선순위 조회
- [ ] 예상·잔여·사용 공수 수집
- [ ] 시작일·마감일 수집
- [ ] Story Point 수집
- [ ] ExistingTaskSnapshot 생성
- [ ] Jira `accountId`와 Person 매핑
- [ ] 매핑 실패 시 `PARTIAL_RESULT` 처리
- [ ] 유효 가용용량 계산
- [ ] 현재 할당량 계산
- [ ] 잔여 가용시간 계산
- [ ] 예상 부하율 계산
- [ ] 일정 중복 계산

완료 기준: 직원별 기존 업무량과 신규 업무 배정 가능 시간을 계산할 수 있어야 한다.

---

## P5. Feature Readiness Check

- [ ] 기능별 필수 데이터 목록 작성
- [ ] 조건부 필수 데이터 규칙 작성
- [ ] 선택 데이터 규칙 작성
- [ ] Connector 연결 상태 검사
- [ ] 원천 필드 존재 여부 검사
- [ ] 값 형식 검사
- [ ] 데이터 최신성 검사
- [ ] Identity Mapping 상태 검사
- [ ] Snapshot 생성 가능 여부 검사
- [ ] `SUCCESS` 판정
- [ ] `PARTIAL_RESULT` 판정
- [ ] `BLOCKED` 판정
- [ ] 누락 데이터·제한사항·가정·신뢰도 출력

완료 기준: 추천 실행 가능 여부와 불가능한 이유가 화면에 표시되어야 한다.

---

## P6. Snapshot 생성

- [ ] 분석 실행 시점의 PersonSnapshot 생성
- [ ] ExistingTaskSnapshot 생성
- [ ] NewTaskSnapshot 생성
- [ ] 분석 실행 ID 연결
- [ ] 원천 데이터 버전·갱신 시각 저장
- [ ] Snapshot 생성 시각 저장
- [ ] 동일 실행 중 Snapshot 고정
- [ ] 재실행 시 새로운 Snapshot 생성
- [ ] RecommendationResult와 Snapshot 연결

완료 기준: 같은 분석 실행에서는 데이터가 변해도 동일한 입력 기준을 사용해야 한다.

---

## P7. 추천·검증 로직

### 추천

- [ ] 필수 역할 기준 후보 생성
- [ ] 필수 Skill 기준 후보 생성
- [ ] 책임수준 기준 후보 생성
- [ ] 조직 제한 적용
- [ ] 업무 적합도 계산
- [ ] 가용시간·부하율 반영
- [ ] 휴가·일정 충돌 반영
- [ ] 업무 집중·병목 위험 계산
- [ ] 추천 담당자 선정
- [ ] 최소 1명의 대안 후보 선정
- [ ] 추천 근거 생성
- [ ] 위험 요소 생성
- [ ] 신뢰도 계산

### 검증 Agent

- [ ] 역할 검사
- [ ] 필수 Skill 검사
- [ ] 책임수준 검사
- [ ] 조직 제한 검사
- [ ] 권한 검사
- [ ] 휴가·휴직 중복 검사
- [ ] 일정 충돌 검사
- [ ] 추천 근거 존재 여부 검사
- [ ] 누락 데이터 검사
- [ ] Skill 누락 시 `UNKNOWN` 처리
- [ ] `PASS` 판정
- [ ] `CONDITIONAL_PASS` 판정
- [ ] `REJECT` 판정

완료 기준: 추천 담당자, 대안 후보, 근거, 부하율, 위험, 검증 결과가 하나의 결과로 출력되어야 한다.

---

## P8. 프론트와 백엔드 연결

현재 프론트는 정적 목업이므로 중간발표 핵심 화면만 우선 연결한다.

- [ ] 프로젝트 선택·생성 화면
- [ ] Connector 상태 화면
- [ ] Drive 폴더·문서 선택 화면
- [ ] Feature Readiness 결과 화면
- [ ] Task 추출 결과 확인 화면
- [ ] PM Task 수정·승인 화면
- [ ] 추천 실행 화면
- [ ] 추천·대안 후보 결과 화면
- [ ] 검증 결과 화면
- [ ] 로딩·오류·`BLOCKED` 상태 처리

회원가입·비밀번호 찾기처럼 핵심 시연과 무관한 화면은 실제 기능 연결을 뒤로 미룬다.

---

## P9. 통합 테스트와 발표 준비

- [ ] 새 PC에서 `.env` 복사 후 Docker Compose 실행 확인
- [ ] `frontend`, `web`, `db` 컨테이너 상태 확인
- [ ] 로컬 PostgreSQL Migration 실행 확인
- [ ] People DB와 프로젝트 시연 데이터 Seed 확인
- [ ] 로컬 문서 저장 디렉터리 생성·쓰기 권한 확인
- [ ] 전체 종단 시나리오 1회 실행
- [ ] `SUCCESS` 시나리오 테스트
- [ ] `PARTIAL_RESULT` 시나리오 테스트
- [ ] `BLOCKED` 시나리오 테스트
- [ ] `CONDITIONAL_PASS` 시나리오 테스트
- [ ] Jira 매핑 실패 테스트
- [ ] Skill `UNKNOWN` 테스트
- [ ] 추천 결과의 원문 Citation 확인
- [ ] 데이터 초기화·재생성 명령 작성
- [ ] 시연 실패 대비 Seed 데이터 준비
- [ ] Docker 재시작 후 데이터와 문서가 유지되는지 확인
- [ ] 발표 순서와 담당자 확정
- [ ] 시연 영상 또는 화면 캡처 백업
- [ ] 5~7분 분량 시연 스크립트 작성

---

## 중간발표 제외 범위

- OCR
- HWP·PPTX 파싱
- Drive Changes API 기반 증분 동기화
- Calendar 실제 연동
- Jira 쓰기
- PM 승인 후 Jira 반영
- 복잡한 최적화 알고리즘
- KPI 대시보드
- SSO
- 운영용 권한 체계
- EC2 배포
- RDS 생성·이전
- S3 버킷 생성·이전
- SQS Worker
- ECS·ALB·CloudFront
- Terraform·CI/CD
- AWS 계정이 필요한 모든 실제 리소스 작업

---

## AWS 계정 지급 전 유지할 전환 기준

AWS 작업은 중간발표 완료 조건에서 제외하지만 이후 이전을 위해 다음 구조는 유지한다.

- DB 연결값은 `DATABASE_URL`로 관리한다.
- 문서 저장 위치를 코드에 절대경로로 고정하지 않는다.
- 문서는 `storage_key`를 기준으로 조회한다.
- 저장소 호출은 `DocumentStorage` 인터페이스를 통해 수행한다.
- 문서 메타데이터에 `bucket`, `storage_key`, `version_id`를 수용할 수 있는 구조를 유지한다.
- 비밀값과 Connector Token은 `.env`에 두고 Git에 포함하지 않는다.
- AWS 계정 지급 후 로컬 PostgreSQL을 RDS로, 로컬 문서 저장소를 S3로 교체한다.

---

## 실행 우선순위

1. 종단 시나리오와 API 스키마 확정
2. People DB 시연 데이터 완성
3. Drive 문서 1개 파싱·저장
4. ProjectKnowledgeModel과 Task 추출
5. Jira 읽기와 업무량 계산
6. Feature Readiness와 Snapshot
7. 추천·검증 로직
8. 핵심 화면 API 연결
9. 통합 테스트와 발표 준비
