# Agent Eval V2 — HOLDOUT package 검수 체크리스트

## 검수 원칙

Reviewer는 fixture나 gold의 주장을 먼저 믿지 않고 **source부터 읽는다.** 이 검수는
Agent 답변에 사람 점수를 주는 작업이 아니라, 시험 문제와 자동 채점 정답표가 올바른지
확인하는 작업이다.

## 1. 역할·보안

- [ ] Custodian과 Reviewer가 다른 사람이다.
- [ ] Jihun은 원문·gold·개별 trace에 접근할 수 없다.
- [ ] 실제 package가 공개 Git, 채팅, 일반 Langfuse metadata에 없다.
- [ ] 개인정보·운영 credential·실제 secret이 없다.
- [ ] 공개 manifest에는 opaque commitment만 있다.

## 2. Source-first 정확성

- [ ] 실제 프로젝트 PDF 또는 승인된 격리 snapshot이다.
- [ ] source 파일 identity와 private hash가 기록돼 있다.
- [ ] 각 required fact가 지정한 페이지·snapshot에 실제로 존재한다.
- [ ] 문서 날짜와 사건 날짜를 혼동하지 않았다.
- [ ] 오래된 문서와 최신 결정의 우선순위가 명확하다.
- [ ] source만 보고 Reviewer가 같은 truth catalog를 재현할 수 있다.

## 3. DEV 독립성

- [ ] DEV의 entity 이름·날짜만 바꾼 복사본이 아니다.
- [ ] 사실 조합·교란 source·도구 조합·경계 조건 중 최소 하나가 실질적으로 다르다.
- [ ] DEV와 같은 Scenario invariant를 검사한다.
- [ ] 단순히 DEV보다 어렵게 만들기 위한 함정을 추가하지 않았다.

## 4. Fixture 실행 가능성

- [ ] 입력이 한 가지 핵심 능력을 명확히 요구한다.
- [ ] precondition을 자동 또는 독립적으로 확인할 수 있다.
- [ ] allowed/forbidden tool 경계가 시나리오 계약과 일치한다.
- [ ] required observable을 현재 수집할 수 있다.
- [ ] Jira 등 외부 상태를 바꾸지 않거나 승인된 범위만 사용한다.
- [ ] cleanup 대상이 정확한 ID로 결속돼 있다.
- [ ] cleanup 실패 시 다른 데이터에 영향을 주지 않는 중단 방법이 있다.

## 5. Gold와 판정

- [ ] 모범 문장 대신 atomic fact·관계·결론으로 작성했다.
- [ ] 모든 required conclusion에 supporting fact가 있다.
- [ ] 근거가 없는 부분은 `must_abstain_on`에 들어 있다.
- [ ] prohibited inference가 과도하게 정상 답변을 막지 않는다.
- [ ] DB·event·tool call·상태는 deterministic oracle로 판정한다.
- [ ] 의미 품질만 LLM Judge에 맡긴다.
- [ ] Judge가 deterministic 결과나 Hard Gate를 뒤집지 않는다.
- [ ] Hard Gate와 일반 Task/Reliability 실패가 구분돼 있다.

## 6. Freeze 준비

- [ ] fixture/gold version이 고정됐다.
- [ ] private package canonicalization과 HMAC 생성이 완료됐다.
- [ ] 공개 commitment와 private package가 일치한다.
- [ ] 검수 중 변경했다면 다시 commitment를 만들고 재검수했다.
- [ ] `review_status=APPROVED`이며 승인 시각이 기록됐다.
- [ ] trace가 round 종료 전 Jihun에게 노출되지 않는다.
- [ ] Phase 9 freeze manifest 승인 전 실행하지 않는다.

## 검수 결과 기록

```yaml
fixture_id: "<SXX-HOLDOUT-NNN>"
fixture_version: 1
gold_version: 1
custodian: "<PRIVATE_IDENTITY_REF>"
reviewer: "<PRIVATE_IDENTITY_REF>"
reviewed_at: "<UTC_TIMESTAMP>"
source_first_review: PASS
dev_independence_review: PASS
execution_readiness_review: PASS
gold_consistency_review: PASS
security_review: PASS
overall_status: APPROVED
rejection_reasons: []
private_package_commitment: "<OPAQUE_HMAC_ID>"
```

한 항목이라도 확인할 수 없으면 `APPROVED`를 쓰지 않는다. 이유를 남기고
`DRAFT`, `BLOCKED_FIXTURE` 또는 `BLOCKED_OBSERVABILITY`로 반환한다.

