# Agent 평가 V2 설계 로드맵

## 1. 문서 상태

- 기준일: 2026-08-27
- 상태: 설계 진행 중
- 현재 단계: 4단계 fixture·gold 정책 설계 준비
- 정본 위치: 이 `eval/v2/` 디렉터리

기존 `agent_poc_v1/v2`, `agent_workflow_v1`, workflow별 문서, 실행 결과와
`workflow_baseline_v0.md`는 평가 기준을 발견한 `LEGACY` 개발 증거다. 삭제하지
않지만 V2 공식 성적의 분자·분모에는 넣지 않는다.

## 2. V2가 해결해야 하는 문제

V2는 다음 문제를 구조적으로 막아야 한다.

1. 로컬 파일·DB·수동 기준선의 표본 수가 서로 다른 문제
2. 도구 호출은 맞지만 답변 내용이 틀린 실행이 통과할 수 있는 문제
3. 내용이 맞아도 출력 형식이나 임시 호출 예산 때문에 전체 실패하는 문제
4. 사람이 검증하지 않은 LLM Judge를 정답처럼 해석하는 문제
5. 공개된 소수 사례에 맞춘 수정이 일반 성능 향상처럼 보이는 문제
6. 서로 다른 Agent·dataset·runtime 결과를 하나의 통과율로 합치는 문제

## 3. 설계 원칙

- **하나의 모집단:** 공식 보고서는 평가 카탈로그의 `VALID` cohort만 집계한다.
- **역할이 다른 두 저장소:** 변경 불가능한 원시 산출물은 증거 원본이고, DB 평가
  카탈로그는 유효성·cohort·집계의 정본이다. 둘은 실행 ID와 checksum으로 대조한다.
- **점수 분리:** 실행, 안전, 과업 품질, 근거, 효율, 성능을 하나의 PASS/FAIL로
  뭉치지 않는다.
- **Hard Gate 최소화:** 권한·승인·외부 부작용·격리·허가되지 않은 민감정보 노출만
  즉시 차단한다.
- **사람 기준 우선:** Judge는 blind 사람 표본으로 검증되기 전까지 참고용이다.
- **개발/holdout 분리:** 개발 사례로 수정하고 비공개 holdout으로 최종 확인한다.
- **같은 조건만 비교:** Agent version, Git commit/runtime profile, model, tools,
  memory mode, fixture가 같은 cohort만 직접 비교한다.
- **수동 숫자 금지:** 기준선 문서와 HTML의 수치는 동일한 집계 코드로 생성한다.

## 4. 단계와 통과 게이트

| 단계 | 설계 대상 | 필수 산출물 | 다음 단계 진입 조건 |
|---:|---|---|---|
| 0 | 기존 평가 동결 | LEGACY 분류 원칙 | V2 공식 집계에서 기존 결과 제외 |
| 1 | 평가 헌장 | `01_evaluation_charter.md` | 목적·비목적·판정 축·Hard Gate 합의 |
| 2 | 위험과 포트폴리오 | 위험 목록, scenario matrix | 각 위험이 최소 한 사례에 연결됨 |
| 3 | 시나리오 계약 | 공통 schema와 작성 지침 | 입력·초기 상태·사후조건이 모호하지 않음 |
| 4 | fixture와 정답 | 개발 fixture, holdout 관리 규칙 | 독립 검토자가 기대 결과를 재현 가능 |
| 5 | 채점 계약 | hard gate, rubric, 집계 규칙 | 같은 답변에 사람 판정이 반복 가능 |
| 6 | 사람 검토와 Judge | blind 검토 절차, calibration gate | 충분한 사람 표본 전 Judge는 참고용 유지 |
| 7 | 실행·저장 | runner, cohort catalog, reconciliation | 원시 결과와 DB가 자동 대조됨 |
| 8 | 개발 pilot | 개발 사례 반복 결과 | 기준 오류와 fixture 오류가 해소됨 |
| 9 | 동결·holdout | 버전 동결 기록, 비공개 실행 | 실행 전 조건 변경 없음 |
| 10 | 공식 보고 | 자동 생성 성적표 | 분모·제외 사유·불확실성 공개 |

앞 단계의 통과 조건이 충족되지 않으면 다음 단계의 코드나 UI를 구현하지 않는다.

## 5. 산출물 명명 규칙

```text
eval/v2/
├─ README.md
├─ 01_evaluation_charter.md
├─ 02_risk_scenario_matrix.md
├─ 03_scenario_contract.md
├─ 03a_contract_validation_examples.md
├─ 04_fixture_and_gold_policy.md
├─ 05_scoring_contract.md
├─ 06_human_judge_protocol.md
└─ scenarios/
```

뒤 단계 파일은 해당 단계에 착수할 때 만든다. 빈 문서를 미리 만들어 완료된 것처럼
보이게 하지 않는다.

## 6. 현재 진행 상태

| 단계 | 상태 | 비고 |
|---:|---|---|
| 0 | 완료 | 기존 결과는 보존하되 V2 공식 집계에서 제외 |
| 1 | 완료 | 보강안 반영 후 `APPROVED` |
| 2 | 완료 | `02_risk_scenario_matrix.md` 승인, 교차 HOLDOUT 관리 확정 |
| 3 | 완료 | 공통 계약과 대표 적용 검증 승인 (`APPROVED`) |
| 4 | 시작 전 | fixture·gold 정책 설계가 다음 작업 |
| 5~10 | 시작 전 | 앞 단계 승인 후 순차 진행 |
