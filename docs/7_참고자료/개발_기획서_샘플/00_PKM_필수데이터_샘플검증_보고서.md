# Project Knowledge Model 필수 데이터 샘플 검증 보고서

> 검토일: 2026-07-27  
> 목적: 공개 개발 기획·요구사항 문서를 기준으로 현재 `ProjectKnowledgeModel` 의미 유형과 필수성 분류를 검증한다.  
> 범위: 영문 PRD·SRS 5건과 국내 요구사항 문서 가이드·개발방법론·정보시스템 구축 제안요청서 5건을 비교했다. 공개 자료를 이용한 초기 스키마 검증이므로 실제 팀 프로젝트의 다문서 조합 검증은 별도로 수행한다.

## 1. 검토 자료

| ID | 문서 | 유형 | 원본 |
|---|---|---|---|
| S1 | `01_SRS_표준_템플릿.md` | IEEE 830·ISO/IEC/IEEE 29148 기반 SRS 템플릿 | <https://github.com/jam01/SRS-Template> |
| S2 | `02_The_Urlist_PRD.md` | 실제 웹 제품 PRD | <https://gist.github.com/burkeholland/f3b987881007641ecaa92090c35232bc> |
| S3 | `03_Weight_Tracking_PRD.md` | 일정·아키텍처를 포함한 MVP PRD | <https://gist.github.com/unix14/4bbcad4122c25d5df72688ecedb428df> |
| S4 | `04_EU_Age_Verification_Spec.md` | 대규모 운영·보안·제품·아키텍처 명세 | <https://github.com/eu-digital-identity-wallet/av-doc-technical-specification> |
| S5 | `05_eBug_Tracker_SRS.pdf` | 실제 애플리케이션 SRS PDF | <https://github.com/amira921/e-Bug-Tracker-System-SRS> |
| S6 | `06_KR_요구사항관리_문서가이드.pdf` | 국내 SW 요구사항 정의·분석·변경관리 작성 가이드 | <https://www.swbank.kr/html/pdf/sample/requirements.pdf> |
| S7 | `07_KR_SW개발방법론.pdf` | 국내 공공 SW 개발방법론·표준 산출물·추적성 지침 | <https://new.kpx.or.kr/boardDownload.es?bid=0045&list_no=70219&seq=1> |
| S8 | `08_KR_정보시스템구축_RFP.pdf` | 국내 정보시스템 운영·유지관리 제안요청서 | <https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/downloadFile.do?bidPbancNo=R26BK01348164&bidPbancOrd=000&fileSeq=3&fileType=&prcmBsneSeCd=03> |
| S9 | `09_KR_블록체인온라인투표_RFP.pdf` | 국내 블록체인 기반 온라인 투표시스템 구축 제안요청서 | <https://www.kisa.or.kr/403/form?lang_type=KO&page=&postSeq=9050> |
| S10 | `10_KR_모두의AI실험실_플랫폼고도화_RFP.hwp` | 국내 AI 플랫폼 고도화 제안요청서 | <https://www.nia.or.kr/site/nia_kor/ex/bbs/View.do?bcIdx=29662&cbIdx=78336> |

S1은 필드 후보를 확인하는 템플릿이므로 “실제 값 출현율” 계산에서는 제외하고 구조 비교에만 사용했다. S5~S9는 텍스트 추출과 대표 페이지 렌더링을 확인했다. S10은 게시물의 파일명이 HWPX로 안내되지만 실제 다운로드 파일 시그니처가 OLE 기반 구형 HWP여서 현재 파서로 본문을 분석하지 못했다. 이 사례는 확장자가 아니라 실제 파일 시그니처와 MIME을 검사해야 한다는 원천 검증 근거로 사용했다.

### 1.1 수집 파일 고정 정보

수집일은 2026-07-27이며, 이후 원본이 변경되어도 이번 판정을 재현할 수 있도록 내려받은 파일의 SHA-256을 기록한다.

| 파일 | 바이트 | SHA-256 |
|---|---:|---|
| `01_SRS_표준_템플릿.md` | 24,339 | `6389DC1326249881ED765736E74872A73703E0A2BF5BA7148A94A52574C4A6C6` |
| `02_The_Urlist_PRD.md` | 16,445 | `58E611BFC5DC835914428E11227996944EA7A4434FBCBBDFABB4381D31623134` |
| `03_Weight_Tracking_PRD.md` | 31,293 | `2A9E1A4E212F9595C46F4572F239277A1428195763E3963724DB5321776289DE` |
| `04_EU_Age_Verification_Spec.md` | 70,630 | `532A3E7182CDED00C4858DF916D7DDC72595AED44AB63B3BBD58DFD37EBF96E7` |
| `05_eBug_Tracker_SRS.pdf` | 4,559,171 | `BEC711A782520B40CFE36D1F3CDF7DCF614E08B56F968004627F48973434E7BD` |
| `06_KR_요구사항관리_문서가이드.pdf` | 488,336 | `7CF1C04ABA33A271C2B0B319712B15AD45D1F2829EE94646DEB4E2E9B00651A9` |
| `07_KR_SW개발방법론.pdf` | 1,961,675 | `404D9EA79E6C42AA9E27D534E6168AE3531E7CC0F76A76C7FA2370703BDE2516` |
| `08_KR_정보시스템구축_RFP.pdf` | 1,826,957 | `75029FF0965BF82C5349C071476E15713244CEBDE380AF26D15F6FADE49110B1` |
| `09_KR_블록체인온라인투표_RFP.pdf` | 1,380,832 | `A7963731C769540679EC3ECC876D08B8B55B9BDBEDF7DD7C63A385FA414F50E5` |
| `10_KR_모두의AI실험실_플랫폼고도화_RFP.hwp` | 1,540,096 | `BB3161D5C611F59B87015DEAE4522A40F4471BB7D90C240DFF6BC6606BB2672A` |

## 2. 판정 기준

- `O`: 명시적으로 존재하며 원문에서 직접 추출 가능
- `△`: 간접 표현·분산 표현으로 존재하여 해석 또는 통합 필요
- `X`: 문서에서 확인되지 않음
- `T`: 템플릿 항목만 존재하고 실제 값은 없음

## 3. 문서별 PKM 항목 비교

| 후보 항목 | S1 | S2 | S3 | S4 | S5 | 판단 |
|---|:---:|:---:|:---:|:---:|:---:|---|
| 문서 ID·버전·출처 | T | △ | O | O | O | 원문 계보에 필수 |
| 프로젝트 목적·목표 | T | O | O | O | O | PKM 필수 |
| 포함 범위 | T | △ | O | O | O | PKM 필수, 기능 목록으로 보완 가능 |
| 제외 범위 | T | O | O | O | X | 조건부, 없으면 PM 확인 |
| 사용자·이해관계자 | T | O | O | O | O | 의미 유형 추가 필요 |
| 기능·기능 요구사항 | T | O | O | O | O | PKM 필수 |
| 비기능 요구사항 | T | △ | O | O | O | `requirement_kind`로 구분 필요 |
| 결정사항 | X | △ | △ | O | X | 선택, 존재하면 반드시 적용 |
| 제약조건 | T | △ | O | O | O | 조건부 필수 |
| 가정 | T | X | O | O | O | 의미 유형 추가 필요 |
| 일정·마일스톤 | T | X | O | X | X | 문서 필수로 둘 수 없음 |
| 의존관계 | T | △ | O | O | O | 조건부 필수 |
| 리스크 | △ | X | O | O | X | 선택, 위험 분석 보조 |
| 완료·검수 조건 | T | △ | O | △ | O | 업무 확정 전 보완 필요 |
| 성공지표 | X | O | O | △ | X | 의미 유형 추가 필요 |
| 담당 역할·책임 | △ | X | △ | O | O | 사용자 역할과 수행 책임을 분리해야 함 |
| 미결 질문 | X | O | X | △ | X | 의미 유형 추가 필요 |
| Task별 우선순위 | X | X | △ | X | X | 문서 추출값이 아니라 PM 보완값 |
| Task별 예상 공수 | X | X | X | X | X | 문서 추출값이 아니라 PM 보완값 |
| Task별 시작·마감일 | X | X | △ | X | △ | 마일스톤과 구분하고 PM 확인 필요 |

### 3.1 국내 자료 추가 비교

| 후보 항목 | S6 | S7 | S8 | S9 | S10 | 국내 자료 판정 |
|---|:---:|:---:|:---:|:---:|:---:|---|
| 문서 ID·버전·출처 | O | O | O | O | △ | 원문 계보와 활성 버전 판정에 필수 |
| 프로젝트 목적·배경 | O | O | O | O | 미분석 | PKM 필수 |
| 사업 범위·기능 | O | O | O | O | 미분석 | PKM 필수 |
| 요구사항 고유 ID | O | O | O | O | 미분석 | 국내 RFP 추적성 보존에 필요 |
| 요구사항 분류코드 | △ | O | O | O | 미분석 | 원천 코드와 정규화 유형을 함께 보존 |
| 성능·연계·데이터·보안·품질 요구 | O | O | O | O | 미분석 | 네 종류 고정 열거형으로는 부족 |
| 제약조건 | O | O | O | O | 미분석 | 조건부 필수 |
| 일정·단계·마일스톤 | O | O | O | O | 미분석 | 전역 일정과 Task 기간을 구분 |
| 수행 조직·역할·책임 | O | O | O | O | 미분석 | `role_or_ownership`으로 구조화 |
| 요구사항별 산출물 | O | O | O | O | 미분석 | `deliverable` 의미 유형 추가 필요 |
| 시험·검수·인수 기준 | O | O | O | O | 미분석 | 완료 조건과 검증방법을 함께 보존 |
| 요구사항 추적성 | O | O | O | O | 미분석 | 요구사항↔산출물↔Task↔검증 관계 필요 |
| 예산 | X | △ | O | O | 미분석 | 프로젝트 메타데이터 또는 제약으로 보존 |
| Task별 예상 공수 | X | X | △ | △ | 미분석 | 여전히 PM 보완이 필요한 경우가 많음 |

`미분석`은 내용이 없다는 뜻이 아니라 현재 도구가 구형 HWP 본문을 안정적으로 파싱하지 못했다는 뜻이다. 원천 존재 여부와 파싱 성공 여부를 분리해 기록해야 한다.

## 4. 핵심 발견

### 4.1 현재 PKM의 핵심 구조는 유지한다

목표·범위·요구사항·제약·의존관계·원문 근거는 서로 다른 문서 유형에서도 반복적으로 확인됐다. 따라서 `KnowledgeItem → FeatureCluster → ProjectKnowledgeModel` 구조는 유지한다.

### 4.2 의미 유형을 다섯 가지 보완한다

현재 허용값에 다음 유형을 추가한다.

- `stakeholder_or_user`: 사용자, 이해관계자, 시스템 행위자
- `assumption`: 사실로 확정되지 않은 전제
- `success_metric`: 목표 달성 여부를 판단하는 정량·정성 지표
- `open_question`: 아직 결정되지 않아 PM 확인이 필요한 질문
- `deliverable`: 요구사항·단계·Task가 만들어야 하는 산출물

기능·비기능 요구사항은 테이블을 분리하지 않고 `requirement`의 하위 유형으로 구분한다. 다만 국내 RFP의 분류를 보존하기 위해 고정 네 종류가 아니라 다음 확장 가능한 표준 분류를 사용한다.

`FUNCTIONAL`, `OPERATION_MAINTENANCE`, `PERFORMANCE`, `INTERFACE`, `DATA`, `TEST`, `SECURITY`, `QUALITY`, `CONSTRAINT`, `PROJECT_MANAGEMENT`, `PROJECT_SUPPORT`, `COMPLIANCE`, `OTHER`

원문에 있는 요구사항 번호와 분류는 각각 `source_requirement_id`, `source_category_code`에 그대로 보존한다. `requirement_kind`는 시스템 내부의 정규화 분류이므로 원천 분류를 덮어쓰지 않는다.

포함·제외 범위는 `scope`의 `scope_type=IN_SCOPE/OUT_OF_SCOPE`로 구분한다.

요구사항의 의무 여부와 확인 방식을 위해 `mandatory`, `verification_method`를 선택 필드로 둔다. 검수·인수 조건은 `acceptance_criteria`, 결과물은 `deliverable`로 분리하고 관계로 연결한다.

### 4.3 PKM 필수와 업무 확정 필수를 분리한다

#### PKM 생성 필수

- 프로젝트 식별자
- 활성 문서와 revision
- 최소 하나의 목적·목표
- 최소 하나의 포함 범위 또는 기능
- 최소 하나의 요구사항
- 모든 추출 항목의 원문 근거

위 항목이 없으면 프로젝트 전체를 기준으로 업무를 추출할 수 없으므로 `BLOCKED`다.

#### PKM 조건부·선택

- 제외 범위, 결정사항, 제약조건, 가정, 마일스톤, 의존관계, 리스크, 완료 조건, 성공지표, 담당 책임
- 요구사항 또는 단계에 명시된 산출물
- 문서에 해당 개념이 선언되어 있는데 값·근거를 해석할 수 없으면 관련 기능만 `PARTIAL_RESULT` 또는 `BLOCKED`
- 문서 자체에 개념이 없으면 “없음”과 “추출 실패”를 구분하고 PM 확인 대상으로 보낸다.

#### NewTaskSnapshot 확정 필수

- Task명
- 설명·범위
- 요구 역할
- 예상 공수
- 수행 기간 또는 마감일
- 우선순위
- 출처 유형과 근거

공수·세부 일정·우선순위·실제 담당자는 공개 샘플에서 거의 문서화되지 않았다. 따라서 이 값을 기획서 추출의 절대 필수로 두지 않고 `NewTaskDraft 누락 표시 → PM 보완 → NewTaskSnapshot 확정`으로 처리한다.

## 5. 추출 규칙 조정안

| 상황 | 처리 |
|---|---|
| 문서에 명시된 값 | `EXTRACTED`, Citation 필수 |
| 여러 문서에 같은 의미가 반복 | FeatureCluster로 통합, 모든 근거 유지 |
| 최신 회의 결정과 기존 명세가 상충 | 자동 삭제하지 않고 conflict로 표시, 최신성 규칙 적용 후 PM 확인 |
| 목표가 개요에서 간접적으로만 표현 | `EXTRACTED` 가능, 근거와 낮은 신뢰도 표시 |
| 일정·공수·우선순위가 없음 | 생성 사실로 채우지 않고 PM 보완 필드로 표시 |
| 완료 조건을 시스템 동작에서 유도 | `GENERATED`, 상위 요구 근거와 생성 이유 표시 |
| 문서에 없는 필수 구현 업무 제안 | `AI_SUGGESTED_MISSING_TASK`, PM 승인 전 미확정 |
| Open Question 발견 | Task로 바로 변환하지 않고 `open_question`으로 저장 |
| 원문 요구사항 코드가 존재 | 원문 ID·분류코드를 보존하고 내부 표준 유형을 별도 매핑 |
| 요구사항별 산출물·검수방법이 존재 | `deliverable`, `acceptance_criteria`, `verification_method`로 분리 후 요구사항과 연결 |
| 파일 확장자와 실제 시그니처가 불일치 | 확장자를 신뢰해 파싱하지 않고 감지 형식으로 Parser 선택, 불일치를 원천 검증 결과에 기록 |
| 필수 문서가 지원하지 않는 구형 HWP | 다른 핵심 문서가 없으면 `BLOCKED`, 보조 문서이면 `PARTIAL_RESULT` |

## 6. 중간 시연 권장 입력

S3 `Weight Tracking PRD`를 구조화 시연의 1차 기준 문서로 권장한다. 목표, 기능 요구사항, 비기능 요구사항, 역할, 제약, 일정, 마일스톤, 성공 조건과 리스크가 한 문서에 있어 PKM 전체 흐름을 보여주기 쉽다.

S2 `The Urlist PRD`는 공수·일정·담당 책임이 없는 문서의 누락 처리와 PM 보완 흐름 검증에 적합하다.

S5 `eBug Tracker SRS`는 PDF 표 구조, 기능별 입력·행동·출력·사전조건·사후조건·예외 경로의 구조 보존 파싱 검증에 적합하다.

S8·S9 국내 RFP는 요구사항 ID·유형·상세내용·산출물·검수 및 프로젝트 관리 항목을 함께 포함하므로 국내 요구사항 정의서 구조화 시연의 기준 문서로 적합하다.

## 7. 후속 검증

1. 동일 프로젝트의 기획서·회의록·기술 명세처럼 다문서 조합 1세트 추가
2. 팀이 실제 사용할 내부 기획서·요구사항 정의서의 비식별 샘플 1~3건 추가
3. 각 의미 유형별 정답 KnowledgeItem을 사람이 작성
4. LLM 추출 결과와 정답을 비교해 누락률·오분류율 측정
5. 공수·일정·우선순위 PM 보완 화면 검증
6. HWPX와 구형 HWP의 지원 범위·변환 경로를 구현 단계에서 확정
