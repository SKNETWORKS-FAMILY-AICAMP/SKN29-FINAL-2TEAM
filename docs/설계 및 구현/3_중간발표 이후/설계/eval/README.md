# Agent 평가 PoC 데이터

> **V2 전환 안내(2026-08-27):** 이 디렉터리의 기존 v0/v1 데이터와 결과는 평가
> 기준을 만든 `LEGACY` 개발 증거로 보존하며 V2 공식 성적에는 포함하지 않는다.
> 새 평가의 단계·정본·완료 조건은 [`v2/README.md`](v2/README.md)에서 관리한다.

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

조회 전용 workflow의 최소 자동 실행기는 `scripts/eval_run.py`다. 데이터셋의
`allowed_tools`를 실행 시점의 도구 목록으로 고정하고, 필수·금지 도구, 전체·도구별
호출 상한, 필수 문서 ID, 도구 완료 상태, 승인 event와 최종 응답을 결정론적으로
검사한다. 실행마다 임시 채팅 세션을 만들고 종료 후 체크포인트와 함께 삭제하므로
기존 대화 상태를 재사용하지 않는다. `agent_run`과 평가 산출물은 증거로 유지한다.

Langfuse가 활성화된 실행은 SDK가 실제 `agent-run` root observation과 trace ID를
먼저 발급한다. LangChain callback은 그 root 아래 Root·Child·모델·도구 관측을
기록하며, 평가 runner는 `eval_run_id`·`case_id` metadata를 전달하고 trace ID를
case 결과와 DB에 보존한다. HITL interrupt 시 trace/root ID를 승인 카드의 내부
`trace_resume_state`에 저장하고 resume에서 새 handler를 같은 root 아래 연결한다.
handler 인스턴스 캐시는 사용하지 않는다. Langfuse 초기화·전송 장애는 Agent 실행과
로컬 평가 저장을 막지 않는다.

합성 스파이크 뒤 실제 실행도 확인했다. `WF-PROJECT-STATUS-001`의 Langfuse trace는
root `agent-run` 1개 아래 모델·도구 observation 58개를 가졌고, case 결과와 DB의
trace ID가 일치했다. 결정론적 평가 상태와 실패 assertion은 각각 CATEGORICAL·TEXT
score로 같은 trace에 연결한다.

`WF-JIRA-HITL-004A` 거절 경로는 interrupt 전·후 `LangGraph` observation이 같은
trace에 연결됐다. 승인 카드에는 `langfuse_interrupted_at`을 저장하고 resume 시
`hitl-wait` observation의 `wait_duration_ms`로 사람 대기 시간을 active 실행과
분리한다. 실제 검증에서는 Jira 도구가 `REJECTED/HITL_REJECTED`로 끝났고 KAN은
전후 0건이었다. Langfuse OTLP endpoint를 고의로 끊은 실행에서도 Agent·로컬 결과·
DB 저장과 임시 세션 정리가 완료돼 관측 장애 격리도 확인했다.

도구 실패의 제품 런타임 복구 정책은 `tool_failure_recovery_v0.md`에서 관리한다.
runner의 재시도 사후 계측에 더해, 2026-08-26부터 제품 런타임
(`services/agent_runtime/factory.py`)도 일시적인 조회 도구 오류(timeout·429·5xx)에
한해 최초 호출 포함 최대 3회 자동 재시도한다. 쓰기 도구는 분류와 무관하게 항상
1회만 실행한다. 재시도가 같은 tool_handler 호출 안에서 일어나므로 별도
tool_started/tool_completed 쌍을 만들지 않고, 따라서 runner의 `tool_reliability`
집계(모델이 같은 도구를 다시 부르는 재호출 기준)에는 이 내부 재시도가 잡히지
않는다 — 안정성 확인은 당분간 구조화 로그로 한다. 쓰기 실패 사용자 결정 카드는
재진입 안전성과 멱등성 저장이 필요하므로 별도 설계 승인 전까지 후속 단계로
남긴다.

데이터셋 v10부터 조회 중심 사례는 `tool_retry_policy`를 가진다. runner는
`tool_call_id`로 시작·완료를 연결하고, 동일 `tool_ref`와 정규화된 인자 조합이 실패한
뒤 다시 시작된 호출만 재시도로 센다. 병렬로 먼저 시작된 호출과 다른 인자의 후속
호출은 재시도가 아니다. 인자 원문이나 해시는 결과에 저장하지 않으며, 실패·재시도·
복구 횟수와 도구별 합계만 `metrics`와 `tool_reliability`에 기록한다. 현재 조회 사례의
정책은 동일 입력 재시도 최대 1회, 연속 실패 최대 2회다. Jira HITL 사례는 거절과
승인 결과를 일반 도구 실패와 구분해야 하므로 이 공통 정책에서 제외한다.

```powershell
docker compose -f infra/docker/docker-compose.yml exec -T web python scripts/eval_run.py `
  --case-id WF-PROJECT-STATUS-001 `
  --account-id UA002 `
  --project-id PJ002 `
  --environment local-docker
```

v0는 `execution_mode=read_only`만 허용한다. Judge 연결부도 존재하지만
`required_evidence_documents + optional_evidence_documents` 전체의 마스킹된 evidence
bundle이 없으면 자동으로 `UNCERTAIN`이며 호출하지 않는다. 호출하더라도
`REPORT_ONLY`라서 실패한 코드 assertion을 성공으로 바꿀 수 없다.

완료된 실행에 독립 Judge 판정을 붙이는 데는 `scripts/eval_judge.py`를 쓴다.
모델에는 최종 답변·결정적 assertion과 범위가 제한된 마스킹 근거만 전달한다. 결과는
기존 case 결과를 수정하지 않고 같은 실행 폴더의 `judge_calibration.jsonl`에
append-only로 기록한다.

2026-08-27부터 Judge 기본 모델은 평가 대상 모델과 분리한 `gpt-5.6-sol`로 고정한다.
`--judge-model`을 명시하면 비교 실험에 한해 다른 모델을 사용할 수 있지만, 결과에는
실제로 사용한 모델을 반드시 기록한다. 이 변경 전 `gpt-5.6-luna`로 생성된 Judge
결과는 과거 실행 기록으로 그대로 보존하며 새 결과와 섞어 집계하지 않는다.

`--human-verdict`는 선택 인자다. 화면(`eval_report_viewer.py`)에서 사람이 Judge의
판정과 근거를 직접 보고 판단하는 용도라면 생략해도 되며, 이 경우 Judge 단독 판정만
기록되고 `human_verdict`·`comparison`은 `null`로 남는다(화면에도 표시하지 않는다).
사람 판정과의 일치율까지 정식으로 비교(calibration)하려는 경우에만
`--human-verdict`를 넘긴다 — 사람 판정 파일은 모델 입력에 포함되지 않는다.

정식 사람 판정 파일은 `evaluator=human`, `review_status=APPROVED`, `reviewed_by`,
`reviewed_at`을 모두 가져야 한다. Codex가 준비했지만 사람이 검수하지 않은
`WF-PROJECT-STATUS-001_reference_verdict_pending_review_20260826T050101Z.json`은
판정 초안일 뿐이며 `eval_judge.py` 입력으로 사용할 수 없다.

2026-08-26 검토자는 위 초안의 5차원 판정과 종합 `FAIL`에 동의했다. 다만 팀원이
답변 출력 형식을 수정한 변경분을 먼저 병합해 영향 범위를 확인하기로 했으므로,
fixture의 `APPROVED` 전환과 정식 calibration 실행은 아직 보류한다. 이 동의는 기존
eval run `20260826T050101Z-ee604a4c`의 출력에만 적용하며 병합 후 새 출력에 재사용하지
않는다. 기존 실행은 dataset v9, Agent version `AV035`, model `gpt-5.6-luna`를
기록했지만 `git_commit=unknown`이므로 해당 한계를 그대로 보존한다.

병합된 변경이 표시 계층에만 있으면 Agent 평가 버전은 유지한다. 저장된 Agent의
system prompt·도구·모델 구성이 바뀔 때만 새 Agent version을 발행한다. 공통 런타임
프롬프트·후처리처럼 코드 배포가 `final_answer`를 바꾸는 경우에는 같은 Agent version과
별도 Git commit/runtime profile로 구분한다. 평가 사례가 바뀌지 않았다면 dataset
v10은 유지한다. 이후
`WF-PROJECT-STATUS-001` 1건을 새 eval run으로 실행해 의미·근거·도구 호출이 유지되는지
확인한 뒤 calibration을 재개한다.

실제 `origin/juneok` 병합은 충돌 없이 merge commit `dac322b`로 완료됐다. 공통
`RUNTIME_SCAFFOLD`는 제한적인 Markdown 표를 허용하고 작업 안내를 최종 답변에서
반복하지 않도록 바뀌었으며, 저장된 `AV035` 정의와 평가 사례는 바뀌지 않았다. 따라서
dataset v10·`AV035`를 유지하고 Git commit으로 런타임을 구분했다. 대표 재실행
`20260826T095913Z-8c4128af`는 표 형식 출력과 핵심 지연 표현 일부 개선을 확인했지만
도구 호출이 6회(`document_list` 1회, `document_search` 5회)로 증가해
`tool_call_limit`, `per_tool_call_limits`가 다시 실패했다. 이 결과는 DB `SYNCED`,
Langfuse trace `5fc296fcbcfe6d671f47cc4abf368d4d`에 observation 60개/root 1개와
결정론적 실패 score로 보존했다.

```powershell
# 화면 표시용 Judge 단독 판정(사람 판정 없음)
docker compose -f infra/docker/docker-compose.yml exec -T web python scripts/eval_judge.py `
  --run-dir outputs/eval-results/20260826T050101Z-ee604a4c `
  --case-id WF-PROJECT-STATUS-001 `
  --evidence "docs/설계 및 구현/3_중간발표 이후/설계/eval/fixtures/WF-PROJECT-STATUS-001_judge_evidence_v0.json" `
  --account-id UA002

# 정식 calibration(사람 판정과 일치율 비교)이 필요할 때만 추가
docker compose -f infra/docker/docker-compose.yml exec -T web python scripts/eval_judge.py `
  --run-dir outputs/eval-results/20260826T050101Z-ee604a4c `
  --case-id WF-PROJECT-STATUS-001 `
  --evidence "docs/설계 및 구현/3_중간발표 이후/설계/eval/fixtures/WF-PROJECT-STATUS-001_judge_evidence_v0.json" `
  --human-verdict "<사람이-검수-승인한-verdict.json>" `
  --account-id UA002
```

Judge 실행은 마스킹했더라도 내부 근거와 Agent 답변을 설정된 모델 엔드포인트로
전송한다. 실제 실행 전 해당 엔드포인트의 운영 주체와 데이터 외부 전송 허용 여부를
확인한다. 같은 실행·Judge 모델·프롬프트 버전의 결과는 중복 기록하지 않는다.

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
