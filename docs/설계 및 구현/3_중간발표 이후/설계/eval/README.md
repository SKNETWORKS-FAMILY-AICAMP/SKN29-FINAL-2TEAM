# Agent 평가 PoC 데이터

이 디렉터리는 평가 입력과 기대 결과의 프로젝트 내부 정본이다. 제품 코드의
응답을 고정하는 하드코딩이 아니라, 같은 입력으로 모델·프롬프트 변경 전후를
비교하기 위한 버전 관리된 테스트 데이터다.

`agent_poc_v1.json`과 `agent_poc_v2.json`은 기본 기능을 확인하는 smoke 데이터다.
`agent_workflow_v1.json`은 smoke 다음 단계의 복합 업무 데이터다. 현재 실행 가능한
사례는 다중 문서 현황 종합, 문서·역량·부하·부재를 함께 보는 담당 후보 추천,
문서 근거 기반 Jira HITL 등록의 거절·승인 경로다.
상세 판정 기준은 `workflow_001_weekly_status.md`,
`workflow_002_staffing_recommendation.md`, `workflow_004_jira_hitl_registration.md`에서
관리한다. prompt injection 사례는
`workflow_003_prompt_injection.md`에 설계를 완료했지만 격리 문서 fixture가 준비되기
전까지 실행 데이터셋에는 넣지 않는다.

평가 연구 반영 범위는 `evaluation_method_adoption_v1.md`, 자동 Judge 검증 절차는
`judge_calibration_v0.md`, 결과 파일과 단계별 진행률 계약은
`result_contract_v0.md`에서 관리한다. 실제 실행 전에는 각 사례의 fixture 요구사항을
만족하는 전용 평가 세션을 준비한다.

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
