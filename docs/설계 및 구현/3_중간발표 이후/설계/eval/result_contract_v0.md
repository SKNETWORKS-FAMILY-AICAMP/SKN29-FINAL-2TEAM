# Agent 평가 결과 계약 v0

## 목적

첫 smoke부터 비교 가능한 증거를 남기기 위한 최소 파일 계약이다. 평가 runner를
대신하지 않는다. 수동 실행 결과를 같은 모양으로 보존하고, 종료된 실행은 같은
`eval_run_id`로 프로젝트 DB의 `eval_run`·`eval_case_result`에 동기화한다. 로컬
파일은 DB 장애와 무관하게 남는 원본이며 DB는 조회·집계 사본이다.

## 저장 위치

기록기는 저장 경로를 코드에 고정하지 않는다. `--output-root`에는 팀이 승인한
접근 통제 내부 공유 위치 또는 그 위치에 마운트된 경로를 전달한다.

`outputs/eval-results`는 Git에서 제외된 로컬 계약 검증용 경로다. 실제 smoke의
유일한 원본으로 사용하지 않는다. 사용자 원문, 비밀값, 문서 전체를 Git에 넣지
않으며 외부 저장 전 마스킹·접근권한·보존기간을 확인한다.

## 실행 폴더

```text
<output-root>/<UTC시각>-<무작위 8자리>/
├─ run_manifest.json
├─ case_results.jsonl
├─ summary.json
└─ report.md
```

- 실행 폴더와 JSON/보고서는 이미 존재하면 덮어쓰지 않는다.
- `case_results.jsonl`만 실행이 끝나기 전까지 한 줄씩 추가한다.
- 중단된 실행도 `finalize --status ABORTED`로 닫아 증거를 남긴다.
- 종료된 실행에는 사례를 더 추가할 수 없다.
- 기록 중에는 실행 폴더의 `.recording.lock`으로 append와 finalize를 직렬화한다.
- `report.md`를 먼저 완성하고 `summary.json`을 마지막 완료 표식으로 생성한다.
  파일 쓰기는 같은 폴더의 임시 파일을 거쳐 원자적으로 게시한다.
- lock 안의 `owner.json`에는 기록 프로세스 PID와 잠금 획득 시각이 남는다.
  프로세스가 강제 종료돼 lock 폴더가 남았다면 이 정보를 기준으로 해당 프로세스가
  종료됐음을 확인한 뒤 `.recording.lock`만 제거하고 같은 명령을 재시도한다.

## 필수 입력

### run manifest

- `git_commit`
- `dataset_id`, `dataset_version`
- `targets`: 평가 대상 `agent_id`, `agent_version_id` 목록
- `models`
- `runtime`, `environment`, `repetitions`

장기 메모리의 영향을 통제하는 실행은 다음 확장 필드도 함께 기록한다.

- `account_id`, `team_id`
- `memory_mode`: `CLEAN`, `SEEDED`, `UNKNOWN` 중 하나
- `session_policy`
- `memory_namespace`

이 확장 필드는 기존 기록기와 DB의 manifest JSON에 그대로 보존된다. 메모리 원문은
평가 결과에 복사하지 않는다.

기록기가 `schema_version`, `eval_run_id`, `started_at`을 추가한다.

### case result

- 식별·버전: `case_id`, `agent_id`, `agent_version_id`, `model`, `runtime`
- 시간·판정: `started_at`, `finished_at`, `status`, `assertions`, `failure_reason`
- 상관관계: `agent_run_id`, `tool_call_ids`, `langfuse_trace_id`
- 계측: `metrics`
- 안전·부작용: `approval`, `side_effects`, `cleanup`
- 단계 진행(선택): `progress.milestones`
- 도구 신뢰성(선택): `tool_reliability`

`tool_reliability`는 도구 실패 뒤 Agent가 어떻게 행동했는지를 정량화한다.

- `failed_call_count`: 실패 완료된 도구 호출 수
- `retry_after_failure_count`: 실패 완료 이후 같은 도구·같은 인자로 다시 시작한 수
- `recovered_after_retry_count`: 위 재시도가 `OK`로 끝난 수
- `max_consecutive_failures_per_signature`: 같은 도구·인자 조합의 최대 연속 실패 수
- `max_retries_after_failure_per_signature`: 같은 실패 구간에서 발생한 최대 재시도 수
- `unmatched_started_call_count`: 완료 event와 연결되지 않은 시작 호출 수
- `by_tool`: 도구별 시도·실패·재시도·복구 합계

동일 호출 판정은 `tool_ref + 정규화된 arguments`의 SHA-256을 실행 중 메모리에서만
사용한다. 인자 원문과 해시는 결과 파일에 저장하지 않는다. 병렬로 실패 전에 이미
시작된 호출은 재시도가 아니며, `tool_call_id`를 사용하므로 완료 순서가 바뀌어도
호출을 정확히 연결한다.

`metrics`에는 대시보드 집계를 위한 다음 숫자도 함께 기록한다.

- `failed_tool_call_count`
- `retry_after_failure_count`
- `recovered_after_retry_count`
- `max_consecutive_tool_failures`
- `max_tool_retries_per_signature`

case에 `tool_retry_policy`가 있으면 `tool_retry_limit`과
`consecutive_tool_failure_limit` assertion을 추가한다. 정책이 없는 과거 데이터에는
새 threshold를 임의 적용하지 않고 측정값만 남긴다. `tool_calls_completed_ok`는 계속
모든 도구 완료가 `OK`인지 별도로 검사하므로, 재시도 성공이 이전 실패를 숨기지 않는다.

`progress.milestones`는 AgentBoard의 세밀한 진행률 개념을 프로젝트 업무에 맞게
축소한 선택 필드다. 각 마일스톤은 `name`과 다음 `status` 중 하나를 갖는다.

- `COMPLETED`: 해당 중간 목표와 판정 조건을 충족함
- `FAILED`: 해당 단계까지 도달했지만 판정 조건을 충족하지 못함
- `NOT_REACHED`: 앞 단계 실패·중단 등으로 해당 단계에 도달하지 못함

기록기는 입력된 마일스톤 수를 분모, `COMPLETED` 수를 분자로 진행률을 계산한다.
최종 성공을 대신하는 점수가 아니며, `FAILED` 사례가 어디까지 정상 진행됐는지를
분석하기 위한 값이다. 마일스톤 이름은 사례의 `progress_milestones`와 대응해야
하고 실행 후 결과를 보고 판정한다. 모델의 자기 보고를 그대로 기록하지 않는다.

기록기가 manifest의 `git_commit`, dataset과 `eval_run_id`를 사례마다 복사한다.
따라서 원시 JSONL 한 줄만 읽어도 실행 조건을 복원할 수 있다.
입력 JSON이 이 식별값을 포함해도 기록기가 만든 값이 우선한다. 필수 필드의
문자열·목록·객체·숫자 타입은 append 전에 검증해 잘못된 줄이 원본에 섞이지 않게
한다. `NaN`과 `Infinity` 같은 비표준 JSON 숫자도 거절한다.

`summary.json`과 `report.md`에는 상태·assertion, 실패 사례와 사유, 안전 위반,
승인 결정, cleanup 상태, token·호출 수 합계와 latency 표본 수·p50·p95를 남긴다.
마일스톤이 기록된 사례는 사례별 완료 수·전체 수·진행률·실패 마일스톤과 실행
전체의 평균 진행률도 남긴다.
latency 분위수는 표본을 정렬한 nearest-rank 방식이며 작은 smoke 표본에서는
통계적 결론이 아니라 기준선 후보로만 해석한다.

사례 상태 `SUCCESS`, `REJECTED`, `NEEDS_CLARIFICATION`은 각각 정상 완료, 의도한
거절, 의도한 추가 질문을 뜻하므로 상태만으로 실패 처리하지 않는다. 이 상태라도
`failure_reason`이 있거나 실패 assertion이 있으면 실패 사례로 집계한다. 그 밖의
상태는 실패 사유가 비어 있어도 실패 사례로 집계한다.

## 사용법

실제 값으로 예시 JSON을 복사·수정한 뒤 실행한다.

```powershell
.\.venv\Scripts\python.exe scripts\eval_record.py start `
  --output-root <내부-공유-저장경로> `
  --manifest <run-manifest.json>
```

출력된 실행 폴더에 사례를 추가한다.

```powershell
.\.venv\Scripts\python.exe scripts\eval_record.py append-case `
  --run-dir <실행-폴더> `
  --case-result <case-result.json>
```

성공·실패·중단을 숨기지 않고 종료한다.

```powershell
.\.venv\Scripts\python.exe scripts\eval_record.py finalize `
  --run-dir <실행-폴더> `
  --status COMPLETED `
  --limitation "수동 실행이라 TTFT는 수집하지 못함"
```

종료된 실행을 프로젝트 DB에 동기화한다. 먼저
`DB/migrations/2026-08-26_eval_result_storage.sql`이 대상 DB에 적용돼 있어야 한다.

```powershell
.\.venv\Scripts\python.exe scripts\eval_record.py sync-db `
  --run-dir <실행-폴더>
```

- `summary.json`이 없는 진행 중 실행은 동기화하지 않는다.
- 같은 실행을 다시 동기화해도 case가 중복 생성되지 않는다.
- 같은 `eval_run_id`에 다른 manifest·summary·case가 이미 있으면 덮어쓰지 않고
  충돌로 거부한다.
- DB 동기화가 실패해도 로컬 네 산출물은 변경하지 않는다. DB의 실행이 없거나
  `SYNC_PENDING`이면 같은 명령으로 재시도한다.

## 현재 fixture 확인

2026-08-25 main 통합 후 로컬 DB에서 다음을 확인했다.

- `AG004/AV035`: 활성, 현재 버전 7, 모델 `gpt-5.6-luna`
- `AG006/AV006`: 활성, 현재 버전 2, 모델 `gpt-5.6-luna`
- `AV006`의 `기본` 서브에이전트 연결: `AG004/AV003`
- `skill_register`: 버전 선택 목록과 별개인 `ALWAYS_ON_TOOL_REFS`

이는 평가 fixture 기록이며 제품 코드의 분기 조건이 아니다. DB가 바뀌면 평가
입력 파일만 갱신한다.
