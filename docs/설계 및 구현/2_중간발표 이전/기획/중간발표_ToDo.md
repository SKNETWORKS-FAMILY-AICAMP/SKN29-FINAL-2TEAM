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

### 진행 현황 (2026-07-30 점검)

로컬 DB와 코드를 직접 확인한 결과다. **`[x]`는 확인된 것만** 표시했고, 일부만 된 항목은 `[ ]`로 두고 뒤에 `— 부분:`으로 무엇이 남았는지 적었다. 팀원 판단이 필요한 항목은 `— 확인 필요`로 남겼다.

| 단계 | 상태 |
|---|---|
| P0 시연 기준 확정 | 데이터는 준비됨, 시나리오·스키마 확정은 팀 논의 필요 |
| P1 People DB | **데이터 입력 완료.** Skill·부재 조회 API만 남음 |
| P2 Drive 문서 처리 | **완료**(2026-08-05). 등록이 원문 수신 → 파싱 → 청킹 → 임베딩까지 이어진다. RunPod Serverless Worker 가 처리하고 Django 가 적재한다 |
| P3 PKM·Task 추출 | **Task 추출 완료**(2026-08-05). 4단계 검색 + 정리로 업무를 근거와 함께 뽑고 1차 확인 화면까지 연결됐다. **PKM(`know_item`)과 결과 영속화(`task`)는 미착수** — 추출 결과는 응답으로만 존재한다 |
| P4 Jira | **연결·프로젝트 조회·이슈·공수 수집·부하 계산 완료(2026-08-05).** `exist_task` 59건. 분석 시점 Snapshot 고정만 남음 |
| P5 Feature Readiness | 미착수 |
| P6 Snapshot | 미착수 |
| P7 추천·검증 | 미착수 |
| P8 프론트 연결 | 커넥터·폴더·문서 선택 + 대시보드·문서 관리·프로젝트·업무 추출 화면 + 운영자 콘솔 8화면 완료. 업무 분배 이후 화면만 목업 |
| P9 통합 테스트 | 환경 확인 일부 완료 |

**2026-07-31 추가 — 테넌트 경계 확정.** 위 표에 없는 작업이지만 P3 이후 전체에 영향이 있어 적어 둔다. 우리 플랫폼을 쓰는 단위가 **회사가 아니라 회사 안의 팀**으로 확정됐고(팀장이 온보딩에서 팀명을 적어 직접 만든다), HR 목업(`org`/`person`)은 어댑터 한 곳으로만 읽도록 분리했다. 업무 추출·분배가 "누구에게 배정할 수 있는가"를 이 경계로 결정하므로 P3 착수 전에 필요한 작업이었다. 배경과 판단 근거는 [[HR_어댑터와_테넌트_경계]], 경과는 [[2026-07-31_HR_어댑터_테넌트_경계_작업기록]].

점검 근거가 된 DB 행 수:

```
org 9 · level 8 · skill 14 · person 57 · person_skill 111
person_link 70 · sched 57 · absence 23
exist_task 0 · doc 0 · doc_block 0 · chunk 0 · vec_idx 0 · know_item 0 · task 0
```

**2026-08-05 갱신.** 파싱 산출물이 채워졌다 — 문서 3건에서 `doc_block` 935 · `chunk` 456 · `vec_idx` 456. Jira 동기화도 붙어 `exist_task` 59건이 있다. 여전히 0인 것은 `know_item`(PKM 미착수)과 `task`(추출 결과 영속화 미착수)다.

2026-07-31 재확인. 회원가입으로 만든 테스트 계정을 전부 지우고 온보딩을 처음부터 한 번 태운 결과다.

```
team 1 · team_member 5 · user_account 2 · member_invite 4 · connector_conn 3
doc 17   ← 위 표의 doc 0에서 채워졌다 (Drive 폴더 선택 → 메타데이터 저장 경로)
doc_block 935 · chunk 456 · vec_idx 456   ← 2026-08-05. 등록이 임베딩까지 간다
```

2026-08-03 재확인. 로컬 Docker DB를 직접 조회한 값이다.

```
mock_hr  org 9 · level 8 · skill 14 · person 57 · person_skill 111
         person_link 73 · sched 57 · absence 23
public   team 1 · team_member 5 · user_account 2 · member_invite 4 · connector_conn 3
         proj 1 · proj_source 6 · doc 9
         doc_block 0 · chunk 0 · vec_idx 0 · exist_task 0 · know_item 0 · task 0
```

- `doc` 9건이 **시연 대상 문서 세트**다(기획서·요구사항 정의서·화면설계서·WBS·회의록 4건·수집 데이터 보고서). 07-31 블록의 17건은 교체 전 선택분이라 지금과 무관하다
- Drive 폴더는 `team_folder` 4건(01_기획·02_회의록·03_일일보고·04_참고자료)으로 **팀에 매단다**(2026-08-04 이동, 역할 값은 없앴다). `proj_source`는 Jira 전용이다 — 부하 분해 시연("KAN만 90% → 합산 122%")의 전제다

> 이 표는 점검 시점 기록이다. 항목을 완료하면 체크박스와 함께 위 표도 갱신할 것.

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

- [ ] 모든 팀원이 로컬 Docker Compose를 실행할 수 있는지 확인 — 확인 필요. [[DB_시작_가이드]] §4.3의 `ALTER` 블록을 각자 실행해야 한다(전체가 멱등이라 통째로 다시 실행하면 된다). **2026-08-03에 `exist_task` 변경이 추가됐으니 07-31에 이미 돌린 사람도 한 번 더 돌려야 한다**
- [ ] 중간발표 종단 시나리오 1개 확정 — 확인 필요
- [ ] 시연용 프로젝트 기획서 1~2개 선정 — 확인 필요. Drive `SKN29/산출물`에 5건 있고 `[기획] 프로젝트 기획서_2Team.docx` 포함. 등록 경로는 검증됨
- [x] 시연용 직원 8~10명 구성 — `person` 57명(활성 56), 개발팀 5명 + 초대 범위 18명
- [ ] 시연용 Jira 프로젝트와 이슈 준비 — 부분: 프로젝트 **KAN·AIP 2개**를 골라 `proj_source`에 저장했고, 목업 이슈 37건(KAN 25 + AIP 12, 라벨 `mock-workload`)을 Jira에 만들어 뒀다. **수집도 붙었다**(2026-08-05) — `exist_task` 59건. 프로젝트 상세의 「갱신」과 대시보드가 쓴다. 추정치 재조정은 남았다([[Jira_부하계산_ToDo]] 단계 4)
  > **2026-08-03 정정.** 이 항목은 "프로젝트 `KAN SKN29_Final_2Team` 확인. 이슈는 조회 코드가 없어 확인 못 함"이었다. 프로젝트는 2개가 됐고 이슈도 준비됐다 — 남은 것은 조회 코드뿐이다.
- [ ] 최종 출력할 Task 수 결정 — 확인 필요
- [ ] 정상 추천 시나리오 1개 준비
- [ ] `PARTIAL_RESULT` 또는 `CONDITIONAL_PASS` 시나리오 1개 준비
- [ ] 화면과 백엔드 API 요청·응답 스키마 확정 — 부분: 인증·초대·커넥터·프로젝트 소스·문서는 확정([[초기_구성_상태]] §3). 추천·검증 계열 미확정

완료 기준: 어떤 데이터를 입력하고 어떤 결과를 보여줄지 팀원이 동일하게 설명할 수 있어야 한다.

---

## P1. People DB 최소 데이터 완성

현재 기본 모델이 구현되어 있으므로 시연 데이터를 보강한다.

- [x] 조직과 상하위 조직 데이터 입력 — `org` 9건, `up_org_id` 계층 구성됨
- [x] 직원·직무·재직 상태 입력 — `person` 57건(`job_role`, `emp_status`)
- [x] Skill·숙련도 입력 — `skill` 14건, `person_skill` 111건
- [x] 책임수준 입력 — `level` 8건, `person.level_id` 연결
- [x] 주간 기준 근무시간/FTE 입력 — `sched` 57건(`fte`, `wk_hours`, `def_wk_hours`)
- [x] 휴가·부재 데이터 입력 — `absence` 23건
- [x] Jira `accountId` 매핑 데이터 입력 — `person_link` 70건
- [x] 조직도 조회 API 보완 — `GET /api/organizations/` (활성 조직 + `up_org_id`·`mgr_id`)
- [ ] 직원 상세·Skill·가용성 조회 API 작성 — 부분: `GET /api/people/`가 역할·책임수준·가용시간(`fte`/`weekly_hours`/`tz`)은 주지만 **Skill과 부재는 응답에 없다.** `person_skill`·`absence`에 데이터는 있으니 쿼리·직렬화만 추가하면 된다
  > **2026-07-31 변경 — 작업 전 확인.** 이 엔드포인트는 이제 **로그인이 필요하고 본인 팀 소속만** 반환한다(전에는 인증 없이 전 직원). `PersonRepository`는 제거됐으니 `backend/services/hr/mock_db.py`의 `list_persons()`에 필드를 추가하면 된다 — HR 조회는 전부 이 어댑터를 거친다. 배경은 [[HR_어댑터와_테넌트_경계]]

완료 기준: 직원별 역할, Skill, 책임수준, 가용시간을 API에서 조회할 수 있어야 한다.
→ Skill만 남았다. 데이터는 다 들어가 있고 조회 경로가 없다.

---

## P2. Google Drive 문서 처리

- [x] Google Drive Connector 인증 구성 및 지정 폴더 읽기 연결 — OAuth 인가 흐름 + 토큰 갱신. 읽을 폴더를 골라 `team_folder`에 저장(2026-08-04 이동. `proj_source`는 Jira 전용이다)
- [x] 선택 폴더의 파일 목록 조회 — `max_depth`만큼 하위 폴더까지. 파싱 가능 형식은 `supported`로 구분
- [x] PDF·DOCX 파일 다운로드 — `POST /api/team/documents/download/`. 실계정 9건(md·docx·xlsx·pdf, 최대 21MB) 성공. Google 문서는 Office 형식으로 내보내 받는다
- [x] 원문 파일 로컬 문서 저장소에 저장 — `backend/services/storage.py`. 컨테이너 볼륨 `document_storage`에 `{proj_id}/{doc_id}.{ext}`로 저장
- [x] 문서 메타데이터 로컬 PostgreSQL에 저장 — `doc`에 `file_name`·`mime_type`·`source_type` 저장. `doc_role`은 기준 문서로 뽑힐 때 `PRIMARY`가 된다(2026-08-04 의미 변경. 폴더 역할 상속은 없앴다)
- [x] 원문 파일의 `storage_key`·해시·버전·수정 시각 저장 — `storage_key` 컬럼을 추가하고 `content_hash`(sha256)·`cur_revision`(Drive headRevisionId)까지 채운다. 9건 전부 해시가 파일과 일치
- [x] PDF·DOCX 텍스트 파싱 — RunPod Worker 가 Docling 으로 처리한다. **텍스트 레이어가 있는 PDF 는 OCR 을 건너뛴다**(2026-08-05) — OCR 이 멀쩡한 본문을 자모 단위로 망가뜨리고 있었다. 스캔본은 EasyOCR 로 읽는다
- [x] ContentBlock 생성 — `doc_block` 935건
- [x] Chunk 생성 — `chunk` 456건. 구조 보존 청킹(표는 행/제품 단위로 다시 만든다)
- [x] 문서·페이지·청크·원문 위치 연결 — `heading_path`·`pages`·`source_refs`
- [x] Embedding 생성 — `google/embeddinggemma-300m`, 768차원
- [x] pgvector 저장 — `vec_idx` 456건
- [x] Citation 조회 가능 여부 확인 — 추출 결과의 업무마다 근거 Chunk 원문·문서·질의가 함께 나온다

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

> **2026-08-05 — Task 추출이 동작한다.** 4단계 검색(업무 후보 → 요구사항·산출물 →
> 역할·기술 → 공수·일정·제약) 뒤 근거를 모아 정리한다. 아래 항목 중 상당수가 이
> 한 흐름 안에서 함께 나온다. 다만 **`ProjectKnowledgeModel`(`know_item`)로 저장하는
> 구조는 만들지 않았다** — 추출 결과는 응답으로만 존재하고 `task`·`know_item`은 0행이다.

- [x] 요구사항 추출 — 업무별 `acceptance_criteria`
- [x] 결정·제약조건 추출 — `constraints`
- [x] 리스크 추출 — `risks`(근거 있을 때만)
- [x] 완료 조건 추출 — `acceptance_criteria`
- [x] 산출물 추출 — `deliverables`
- [x] 업무 간 의존 관계 — `dependencies`가 다른 업무를 가리킨다
- [x] 원문 Citation 연결 — 업무마다 근거 Chunk 원문·문서·질의
- [x] Task명·역할·Skill 생성 — `title`·`required_role`·`required_skills`
- [ ] 공수·기간·우선순위 생성 — **제안요청서에 없어 `missing_fields`로 남는다.**
      지어내지 않는다. 채우는 방법은 업무 분배 단계의 설계 사안이다
- [ ] 프로젝트 목표·포함/제외 범위 추출 — 업무 단위로만 뽑고 프로젝트 수준 요약은 없다
- [ ] 일정·마일스톤 추출 — 문서의 추진일정 표가 병합 머리글이라 월 대응이 사라진다
- [ ] 중복 항목 통합
- [ ] ProjectKnowledgeModel 저장 — `know_item` 0행
- [ ] NewTaskDraft 생성 · 출처 구분(`EXTRACTED`/`GENERATED`/…) — `task` 0행
- [ ] PM 승인·수정·반려 API 작성

완료 기준: 기획서에서 추출된 Task가 원문 근거와 함께 화면에 표시되어야 한다.
→ **충족.** 「추출된 업무 확인」 화면에서 업무마다 근거를 펼쳐 볼 수 있다.

---

## P4. Jira 읽기 및 업무량 계산

- [x] Jira 연결 설정 — OAuth 2.0 (3LO) + `cloud_id` 조회. 읽을 프로젝트를 골라 `proj_source`에 저장
- [ ] `/field` Discovery
- [x] 프로젝트 조회 — `GET /api/connectors/jira/projects/`. `description`·`lead`는 `expand`가 필요하다
- [ ] 사용자 조회 — `read:jira-user` 범위는 받아 뒀고 호출 코드가 없다
- [ ] Board·Sprint 조회 — **범위가 부족하다.** Agile API는 `read:board-scope:jira-software`가 필요한데 현재 요청 범위에 없어 콘솔 설정부터 고쳐야 한다
  > **2026-08-03 — 중간발표 경로에서는 빠졌다.** 부하 계산에 Board·Sprint가 필요 없다는 것이 확인됐다. 이슈 수집은 `read:jira-work`만으로 되고([[Jira_부하계산_ToDo]] 단계 1-1), 기간 창은 스프린트가 아니라 `[기준일, 기준일+4주)`로 잡는다(D1). 콘솔 권한 추가는 **막고 있는 것이 아니라 중간발표 이후 과제다.**
- [x] 이슈·담당자·상태·우선순위 조회 — `exist_task` 59건. 프로젝트 상세의 「갱신」과 대시보드가 쓴다
- [x] 예상·잔여·사용 공수 수집 — `exist_task.estimate`·`remaining`·`spent`에 적재(`ExistTaskRepository.replace_for_source`)
- [x] 시작일·마감일 수집 — `exist_task.start_at`·`due_at`
- [ ] Story Point 수집
- [ ] ExistingTaskSnapshot 생성
- [x] Jira `accountId`와 Person 매핑 — 담당자 이메일을 `person_link`로 묶는다(`lookup_person_ids_by_external_email`). 실패분은 버리지 않고 `unmapped_assignees`로 센다
- [ ] 매핑 실패 시 `PARTIAL_RESULT` 처리
- [x] 유효 가용용량 계산 — `services/workload/calculator.py`의 `effective_capacity`(창으로 자른 부재를 차감)
- [x] 현재 할당량 계산 — `current_allocation`(창 안에 마감이 있는 일의 `Σ remaining`)
- [x] 잔여 가용시간 계산 — `remaining_capacity`
- [x] 예상 부하율 계산 — `load_rate`. `GET /api/team/workload/`가 사람별·프로젝트별로 돌려준다
- [ ] 일정 중복 계산

> **2026-08-03 추가 — 계산식은 확정됐다.** 유효 가용용량·현재 할당량·잔여 가용시간·예상 부하율의 수식이 조사·확정됐다([[업무량계산_조사]] Q4-2, 출처는 [[업무량계산_출처]]). 우리 스키마(`exist_task`·`mock_hr.sched`·`mock_hr.absence`)의 컬럼에 직접 대입해 검증한 것이고, NULL 대체 정책도 Q3-3에 정해져 있다. **2026-08-05 — 구현까지 끝났다.** 이슈 수집이 붙어 `exist_task` 59건이 있고, `services/workload/calculator.py`가 위 수식을 그대로 구현한다.

완료 기준: 직원별 기존 업무량과 신규 업무 배정 가능 시간을 계산할 수 있어야 한다.
→ **충족.** 대시보드가 사람별 유효 가용용량·현재 할당량·잔여 가용시간·부하율을 보여준다.

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

- [x] 프로젝트 선택·생성 화면 — **별도 생성 화면을 두지 않기로 했다.** 폴더를 고르는 행위가 `DRAFT` 프로젝트를 만든다([[Jira_Drive_커넥터_연결_설계]] §4). `ProjectListPage`는 실데이터에 붙었다 — 진행/완료 구분과 「업무 분배 시작」이 추출로 간다
- [x] Connector 상태 화면 — 서버의 `connector_conn`이 원본. 연결·재연결·다음 단계 이동
- [x] Drive 폴더·문서 선택 화면 — 트리 탐색·파일 미리보기. 저장 후 새로고침해도 유지됨(폴더·파일 역할 지정은 2026-08-04에 제거됐다)
- [x] Jira 프로젝트 선택 화면 — 목록에 없던 항목. 저장된 선택이 체크로 되살아난다
- [ ] Feature Readiness 결과 화면
- [x] Task 추출 결과 확인 화면 — `/tasks/extraction` 「추출된 업무 확인」. 업무마다 근거를 펼쳐 본다. **중간발표 완료 지점**
- [ ] PM Task 수정·승인 화면
- [ ] 추천 실행 화면
- [ ] 추천·대안 후보 결과 화면
- [ ] 검증 결과 화면
- [ ] 로딩·오류·`BLOCKED` 상태 처리 — 부분: 연결한 화면들은 로딩·오류·미연결(404)·재연결 필요(502)를 처리한다. `BLOCKED`은 P5가 없어 해당 없음

회원가입·비밀번호 찾기처럼 핵심 시연과 무관한 화면은 실제 기능 연결을 뒤로 미룬다.

> **이 방침은 바뀌었다.** 인증(회원가입·로그인·비밀번호 재설정)과 팀원 초대는 실제로 구현했다. 커넥터 연결이 계정 단위이고 팀장만 HR을 연동할 수 있어서, 로그인·역할 판정이 없으면 커넥터 화면 자체가 성립하지 않았다.

**온보딩 완료 이후는 의도적으로 데모다.** 하단 `커넥터 설정 완료` 버튼은 커넥터 연결만 확인하고 `/dashboard`(목업)로 보낸다. 완료 시점에 문서·Jira를 읽어 프로젝트 현재 상태를 초기 설정하는 것이 원래 설계지만, 그 부분은 P2~P7 결과 형태에 의존하므로 결과가 나온 뒤에 만든다. 자세한 내용은 [[2026-07-30_커넥터_소스선택_저장_작업기록]] §7.

---

## P9. 통합 테스트와 발표 준비

- [ ] 새 PC에서 `.env` 복사 후 Docker Compose 실행 확인 — 확인 필요. `.env`에 Drive·Jira 자격증명이 있어야 하고, 바꾼 뒤에는 재시작이 아니라 **재생성**해야 반영된다
- [x] `frontend`, `web`, `db` 컨테이너 상태 확인 — 3개 모두 정상. `db`는 healthy
- [ ] ~~로컬 PostgreSQL Migration 실행 확인~~ — **해당 없음.** 이 프로젝트는 `DATABASES = {}`로 Django Migration을 쓰지 않는다. 대신 `DB/schema.sql`과 수동 `ALTER`로 관리한다([[DB_시작_가이드]] §4.3). §4.3이 미적용인 팀원이 있으면 폴더 저장에서 에러가 나고, 08-03 `exist_task` 변경이 빠지면 이슈 수집을 붙이는 순간 깨진다
- [x] People DB와 프로젝트 시연 데이터 Seed 확인 — People DB 전 테이블 입력됨(P1). 프로젝트 데이터는 온보딩으로 생성되며 경로 검증됨
- [x] 로컬 문서 저장 디렉터리 생성·쓰기 권한 확인 — 명명 볼륨 `document_storage`에 실계정 9건 저장·해시 일치 확인
  > **2026-08-03 정정.** 이 항목은 "원문 다운로드(P2)가 없어 아직 저장소를 쓰지 않는다"로 적혀 있었으나 **틀렸다.** 2026-07-31에 다운로드가 구현되면서(`backend/services/storage.py`) 저장소를 실제로 쓰고 있다.
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
- [x] Docker 재시작 후 데이터와 문서가 유지되는지 확인 — 명명 볼륨 `postgres_data`라 컨테이너를 재생성해도 데이터가 남는다(확인함). 단 **Google 테스트 모드의 `refresh_token`은 7일 후 만료된다** — 시연 직전 재연결이 필요할 수 있다
- [ ] 발표 순서와 담당자 확정
- [ ] 시연 영상 또는 화면 캡처 백업
- [ ] 5~7분 분량 시연 스크립트 작성

---

## 중간발표 제외 범위

- 텍스트 레이어가 있는 PDF에 대한 OCR (스캔본은 EasyOCR `ko`·`en` 으로 읽는다)
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

1. 종단 시나리오와 API 스키마 확정 — 수집·저장 계열은 확정, 추천 계열 미확정
2. People DB 시연 데이터 완성 — 데이터 완료, Skill 조회 API만 남음
3. Drive 문서 1개 파싱·저장 — **완료(2026-08-05).** 등록이 원문 수신 → 파싱 → 청킹 → 임베딩까지 이어진다
4. ProjectKnowledgeModel과 Task 추출
5. Jira 읽기와 업무량 계산 — **완료(2026-08-05).** 이슈 수집(`exist_task` 59건)과 부하 계산(`services/workload/`)이 대시보드에 붙었다
6. Feature Readiness와 Snapshot
7. 추천·검증 로직
8. 핵심 화면 API 연결 — 커넥터·폴더·문서·Jira 선택과 대시보드·문서 관리·프로젝트·업무 추출 화면 완료
9. 통합 테스트와 발표 준비

### 지금 남은 것

> **2026-08-05 정정.** 이 절이 병목으로 지목하던 둘(문서 파싱 연결·Jira 이슈 수집)은 **둘 다 해결됐다.** 아래는 그 이후 기준으로 다시 쓴 것이다.

**문서 파이프라인은 뚫렸다.** Django가 `doc.storage_key`의 원문을 만료형 서명 URL로 RunPod Worker에 넘기고, 결과를 `doc_block`·`chunk`·`vec_idx`로 적재한다(`backend/db/document_pipeline.py`, `services/document_pipeline/runpod_client.py`). 문서 3건에서 `doc_block` 935 · `chunk` 456 · `vec_idx` 456.

```
완료   Drive 폴더 선택 → doc 등록 → 원문 다운로드 → 로컬 저장 → content_hash
완료   RunPod Worker 파싱·구조보존 청킹·임베딩 → doc_block 935 · chunk 456 · vec_idx 456
완료   위 둘을 잇는 경로 — Django가 doc.storage_key로 원문을 넘기고 결과를 적재
남음   know_item(PKM) · task(추출 결과 영속화) — 둘 다 0행
```

남은 것은 추출 결과를 `task`·`know_item`으로 저장하는 것뿐이다. 파싱 쪽 상세 상태는 [[PROJECT_PROGRESS]] §7·§10.

**Jira 쪽도 뚫렸다.** 이슈 수집(`ExistTaskRepository.replace_for_source`)이 붙어 `exist_task` 59건이 있고, 부하 계산(`services/workload/calculator.py`)이 팀 부하 API(`GET /api/team/workload/`)와 대시보드에 연결됐다. 남은 것은 추정치 재조정과 분석 시점 Snapshot 고정이다([[Jira_부하계산_ToDo]] 단계 4).

> **2026-08-03 정정.** 이 자리에는 "Board·Sprint 조회가 콘솔 설정부터 막혀 있다"가 병목으로 적혀 있었으나, 부하 계산에 Board·Sprint가 필요 없는 것으로 확인돼 중간발표 경로에서 빠졌다. 콘솔 권한 추가는 중간발표 이후 과제다.
