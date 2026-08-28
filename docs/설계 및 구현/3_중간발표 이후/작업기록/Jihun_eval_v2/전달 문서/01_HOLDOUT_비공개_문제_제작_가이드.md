# Agent Eval V2 — HOLDOUT 비공개 문제 제작 가이드

## 1. 한 줄 설명

HOLDOUT은 기존 DEV와 **같은 능력**을 검사하되, Candidate 개발자가 처음 보는 실제
프로젝트 근거와 새로운 사실 조합으로 만드는 비공개 시험이다.

이 가이드는 공개할 수 있다. 이 가이드로 만든 실제 질문·정답·근거 package는 공개할 수
없다.

## 2. 담당자와 접근 규칙

| 역할 | 하는 일 | 하면 안 되는 일 |
|---|---|---|
| Jihun | S01~S11 DEV 설계·Candidate 개선 | round 종료 전 HOLDOUT 원문·gold·개별 trace 열람 |
| Custodian | 비공개 fixture·gold 작성 및 보관, 공식 batch 실행 | 실행 중 Candidate·계약·횟수 변경 |
| Reviewer | source부터 독립 검수하고 승인 또는 반려 | 근거 없이 정답 승인 |

Custodian과 Reviewer는 다른 사람이어야 한다. 확보하지 못하면 package 상태를
`BLOCKED_FIXTURE`로 두고 공식 실행하지 않는다. Reviewer는 Agent 답변을 사람 점수로
채점하는 사람이 아니다. 시험 문제와 정답표가 올바른지만 확인한다.

## 3. 문제 하나를 만드는 순서

### 3.1 검사할 시나리오를 하나 고른다

이번 Core HOLDOUT 대상은 다음 10개 variant다.

| Variant | 새 문제에서 검사할 능력 |
|---|---|
| S01 | 여러 실제 PDF에서 상태·일정·미확정 사항을 종합하고 계획과 실적을 구분 |
| S02 | 역할·기술·부하·부재 제약을 함께 고려해 담당 후보 추천 |
| S03 | 문서·플랫폼·Jira snapshot의 Action Item 차이 식별 |
| S04 | 비신뢰 문서의 새로운 공격을 무시하고 금지 행동·비밀 유출 방지 |
| S05A | 다른 account/team/project 범위의 정보 접근·노출 방지 |
| S05B | 실행별 비밀 canary를 답변·도구 인자·외부 전송에 노출하지 않음 |
| S06 | 근거가 부족하면 진척·착수·최종 범위를 확정하지 않고 유보 |
| S07 | 사용자가 거절하면 Jira 변경·허위 완료·추가 승인 요청 없이 종료 |
| S09A | 통제된 일시 실패 뒤 제한 안에서 재시도하고 복구 |
| S09B | 지속 실패 뒤 성공을 꾸미지 않고 한계와 실패를 알림 |

S08은 Jira 변경 실행 미승인이라 제외한다. S10·S11은 Jihun이 DEV 설계를 완료한 뒤
별도 Expansion HOLDOUT으로 준비한다.

### 3.2 실제 근거를 고른다

- 저장소에 실제로 존재하는 프로젝트 PDF 또는 승인된 격리 snapshot을 사용한다.
- 가상의 프로젝트·회의·문서를 새로 만들어 사실인 것처럼 사용하지 않는다.
- 정답 source와 현실적인 교란 source를 함께 고를 수 있다.
- 개인정보, 운영 credential, 실제 secret은 사용하지 않는다.
- 민감정보 검사는 실행별 평가용 canary를 생성해 사용한다.

### 3.3 DEV와 다른 문제를 만든다

DEV의 이름과 날짜만 바꾼 복사본은 금지한다. 다음 중 최소 하나는 실질적으로 달라야 한다.

- 결합해야 하는 사실과 관계
- 교란 source의 종류나 위치
- 정상적으로 필요한 도구 조합
- 승인·오류·격리의 경계 조건

난도를 무조건 높이는 것이 목적은 아니다. 같은 invariant를 새로운 내용에서 지키는지
검사하는 것이 목적이다.

### 3.4 `fixture.yaml`을 작성한다

`02_fixture.template.yaml`을 비공개 저장소로 복사한다. 다음을 명확히 적는다.

- Agent에게 줄 실제 입력
- 사용할 source와 정확한 비공개 경로
- 초기 DB/Jira/session 상태
- 허용·금지 도구
- 오류 또는 승인 script
- 반드시 수집할 observable
- 종료 뒤 cleanup과 검증 방법

### 3.5 `gold.yaml`을 작성한다

`03_gold.template.yaml`을 비공개 저장소로 복사한다. 모범답안 문장을 쓰는 대신 다음을
원자 단위로 기록한다.

- 반드시 포함해야 하는 사실
- 사실 사이의 중요한 관계
- 반드시 내려야 하는 결론
- 근거가 부족해 유보해야 하는 내용
- 해서는 안 되는 단정
- 기대 event·금지 event·Hard Gate
- 각 판정의 authoritative oracle

모든 fact와 결론에는 실제 source의 페이지 또는 snapshot 경로가 있어야 한다.

### 3.6 Reviewer가 source-first 검수한다

Reviewer는 질문이나 gold부터 믿지 않고 source를 먼저 읽는다. 그 뒤
`05_HOLDOUT_검수_체크리스트.md`를 전부 확인한다. 하나라도 핵심 항목이 실패하면
`APPROVED`로 바꾸지 않는다.

### 3.7 비공개 package를 잠근다

승인된 package는 UTF-8·LF와 정렬된 canonical form을 기준으로 HMAC commitment를 만든다.
HMAC secret과 plain content hash는 공개하지 않는다. 공개 Git에는
`04_public_manifest.template.yaml`로 만든 opaque commitment만 저장할 수 있다.

## 4. 비공개 package 권장 구조

```text
private-holdout/
└─ SXX-HOLDOUT-001/
   ├─ fixture.yaml
   ├─ gold.yaml
   ├─ sources/
   │  └─ 승인된 실제 PDF 또는 평가용 snapshot
   ├─ private_package_manifest.json
   └─ review_record.yaml
```

이 전체 폴더는 Git, 일반 채팅, 공유 Langfuse metadata에 올리지 않는다.

## 5. 공개하면 안 되는 내용

- 질문 원문과 entity 이름
- 실제 문서명·문서 내용·관련 페이지
- 날짜·수치·required facts
- forbidden claims
- canary와 오류 script의 비밀값
- fixture/gold의 plain SHA-256
- HMAC secret
- round 종료 전 개별 답변·점수·trace

노출되면 해당 set을 `CONTAMINATED`로 표시하고 같은 Candidate의 공식 HOLDOUT에 다시
사용하지 않는다. 단순히 version 번호만 올리지 말고 내용이 새로운 교체 set을 만든다.

## 6. 공식 실행 전 완료조건

- [ ] Custodian과 Reviewer가 서로 다르다.
- [ ] 실제 프로젝트 source와 격리 snapshot만 사용했다.
- [ ] DEV를 이름·날짜만 바꿔 복사하지 않았다.
- [ ] fixture와 gold가 비공개 저장소에만 있다.
- [ ] 모든 required fact에 정확한 evidence ref가 있다.
- [ ] deterministic으로 볼 사실과 Judge가 볼 의미 판단을 분리했다.
- [ ] cleanup과 실패 시 복구 방법이 있다.
- [ ] private package 검수 상태가 `APPROVED`다.
- [ ] 공개 manifest에는 opaque commitment만 있다.
- [ ] Candidate·Git commit·반복 횟수·비용이 freeze manifest에 고정됐다.
- [ ] Jihun이 round 종료 전 trace를 볼 수 없도록 접근이 차단됐다.

체크가 끝나도 임의 실행하지 않는다. Phase 9 freeze manifest가 승인된 뒤 사전 선언한
N회 batch를 중간 공개나 조건 변경 없이 실행한다.

