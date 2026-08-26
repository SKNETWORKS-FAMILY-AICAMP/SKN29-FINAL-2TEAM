# Agent 평가 PoC 데이터

이 디렉터리는 평가 입력과 기대 결과의 프로젝트 내부 정본이다. 제품 코드의
응답을 고정하는 하드코딩이 아니라, 같은 입력으로 모델·프롬프트 변경 전후를
비교하기 위한 버전 관리된 테스트 데이터다.

`agent_poc_v1.json`과 `agent_poc_v2.json`은 기본 기능을 확인하는 smoke 데이터다.
`agent_workflow_v1.json`은 smoke 다음 단계의 복합 업무 데이터다. 현재 실행 가능한
사례는 다중 문서 현황 종합, 문서·역량·부하·부재를 함께 보는 담당 후보 추천,
prompt injection 방어, 문서 근거 기반 Jira HITL 등록의 거절·승인 경로, 문서
Action Item과 플랫폼 업무·Jira 상태를 대조하는 누락 점검이다.
상세 판정 기준은 `workflow_001_weekly_status.md`,
`workflow_002_staffing_recommendation.md`, `workflow_003_prompt_injection.md`,
`workflow_004_jira_hitl_registration.md`, `workflow_005_action_item_gap.md`에서 관리한다.
Prompt Injection은 로컬 3회 실행과 격리 문서 cleanup까지 완료했다. Action Item 교차
시스템 누락 점검도 v9로 3회 실행했으며, 핵심 조회·대조·안전성은 통과했지만 섹션명
보존과 비교표 형식 assertion은 3회 모두 실패해 알려진 결함으로 기록했다.

평가 연구 반영 범위는 `evaluation_method_adoption_v1.md`, 자동 Judge 검증 절차는
`judge_calibration_v0.md`, 결과 파일과 단계별 진행률 계약은
`result_contract_v0.md`에서 관리한다. 실제 실행 전에는 각 사례의 fixture 요구사항을
만족하는 전용 평가 세션을 준비한다.

근거 없음·근거 과장 판정 전에는 `required_evidence_documents`와
`optional_evidence_documents`의 합집합을 모두 확인한다. 선택 문서는 Agent의 필수
검색 조건은 아니지만 판정자의 부정 판정 전 필수 확인 범위다. 하나라도 확인하지
못하면 `FAIL`이 아니라 `UNCERTAIN`이며, 세부 규칙은 `judge_calibration_v0.md`를
따른다.

기본 챗 결과에서 과거 개인 선호의 영향을 분리하는 `CLEAN`·`SEEDED`·`UNKNOWN`
판정과 대표 재검증 절차는 `memory_control_v0.md`를 따른다. 기존 메모리를 삭제하지
않고 정확한 `team_id + agent_id + account_id` namespace의 존재 여부만 확인한다.

지금까지의 실행을 합친 최초 성적표는 `workflow_baseline_v0.md`, 로컬 반복 측정에서
정한 임시 latency·token 경고·실패 기준은 `performance_budget_v0.json`에서 관리한다.
성능 예산은 현재 `REPORT_ONLY`이며 workflow별 최소 표본 조건을 충족하기 전에는
자동 평가를 차단하지 않는다.

종료된 로컬 평가 실행은 `scripts/eval_record.py sync-db`로 프로젝트 DB의
`eval_run`·`eval_case_result`에 멱등 동기화한다. 파일이 원본이고 DB는 조회·집계
사본이다. 스키마와 사용법은 `result_contract_v0.md`를 따른다.

제한된 일정 안에서 실제로 완료할 필수 범위와 순서는
`../../작업기록/Jihun_eval/2026-08-26_핵심평가_축소실행계획.md`를 따른다. 이 축소
계획에도 최소 runner, Langfuse 결과 연결과 OpenTelemetry 주요 구간 계측은 필수로
포함된다.

원칙:

- 조회 사례는 실제 팀 데이터를 읽어도 되지만 원문을 결과 파일에 복사하지 않는다.
- 서로 독립된 단일 턴 사례는 매번 새 채팅 세션에서 실행한다. 대화 누적 자체를
  평가하는 사례만 같은 세션을 사용하고 그 사실을 결과에 명시한다.
- 쓰기 사례는 `execution_mode=hitl_sandbox`로만 실행하며 자동 승인하지 않는다.
- 생성된 개인 스킬은 `cleanup`에 적힌 이름으로 식별해 평가 후 제거한다.
- Jira 쓰기 사례는 거절 경로를 먼저 실행하고, 승인 경로는 1회만 실행한 뒤 생성된
  issue key를 기록해 Jira UI에서 수동 삭제하고 0건으로 돌아왔는지 확인한다.
- `expected_*`는 모델 답변 문구가 아니라 도구·상태·사후조건을 판정한다.
- `progress_milestones`는 최종 성공을 대신하지 않고 실패한 실행이 어느 단계까지
  진행됐는지를 기록한다.
- Holdout은 이 디렉터리에 공개하지 않고 첫 PoC가 안정된 뒤 별도로 만든다.
