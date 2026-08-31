# PLATFORM_BEHAVIOR_V3 실행 준비

이 디렉터리는 현재 Candidate에서 V2 계약을 다시 실행하고, 신규 문서 전처리·검색
변경 variant를 추가하는 V3 정본이다.

## 공식 구성

- V2 Core 재실행: 12 variant × 3회 = 36회
- V2 Expansion 재실행: 4 variant × 3회 = 12회
- 신규 검색 변경: 6 variant × 3회 = 18회
- 합계: 22 variant, 66회

과거 V2 실행 48회는 비교 기준선이며 V3 66회에 포함하지 않는다. 기존 계약도 현재
Candidate와 현재 Git commit에서 새로 실행한다.

## 실행 순서

프로젝트 루트에서 실행한다.

실제 문서 provision 전에는 PostgreSQL/pgvector DB, `RUNPOD_API_KEY`,
`RUNPOD_ENDPOINT_ID`, 외부 worker가 접근 가능한 `PUBLIC_BACKEND_BASE_URL`이 필요하다.
필수 설정이 비어 있으면 `provision-delta`는 문서 행을 만들기 전에 차단된다.

```powershell
# 외부 호출 없는 정적 검증
.\.venv\Scripts\python.exe scripts\eval_v3.py validate

# 66회 실행 계획 확인
.\.venv\Scripts\python.exe scripts\eval_v3.py plan `
  --agent-id AG004 --agent-version-id AV073

# 101개 corpus 색인(평가 DB·스토리지·RunPod 사용, 중단 후 같은 명령으로 재개 가능)
.\.venv\Scripts\python.exe scripts\eval_v3.py provision-corpus `
  --account-id UA002

# 색인된 corpus를 D01~D06 fixture에 결속
.\.venv\Scripts\python.exe scripts\eval_v3.py bind-delta `
  --account-id UA002

# 한 variant smoke: 실제 Agent/Judge 호출
.\.venv\Scripts\python.exe scripts\eval_v3.py run `
  --variant D01 --repeats 1 --allow-dirty `
  --account-id UA002 --agent-id AG004 --agent-version-id AV073

# 평가 관련 변경을 커밋한 뒤 Candidate·commit·index·binding 동결
.\.venv\Scripts\python.exe scripts\eval_v3.py freeze `
  --account-id UA002 --team-id TM001 `
  --agent-id AG004 --agent-version-id AV073

# 전체 66회: 실제 Agent/Judge 호출
.\.venv\Scripts\python.exe scripts\eval_v3.py run `
  --cohort all --repeats 3 `
  --account-id UA002 --agent-id AG004 --agent-version-id AV073
```

`provision-corpus`, `provision-delta`, `bind-delta`, `run`은 자동으로 호출되지 않는다.
Candidate, commit, 모델, 인덱스가 동결된 뒤 명시적으로 실행한다. 신규 문서 binding은
`outputs/eval-v3-fixture-bindings/`, 결과는 `outputs/eval-v3-results/`에 분리한다.
동결 manifest는 `outputs/eval-v3-freeze/`에 append-only로 생성한다. 미추적 발표 문서처럼
런타임에 영향을 주지 않는 파일은 허용하지만 tracked 변경이 있으면 동결과 공식 실행을
차단한다.

공식 실행은 UA002의 메모리·TITK·DB 상태와 지연시간을 공유하므로 단일 orchestrator가
suite 순서대로 직렬 실행한다. 여러 서브에이전트는 Core·Expansion·Delta 산출물의 누락,
Hard Gate, 중복 호출 및 trace 정합성을 병렬 검증하는 데 사용한다. 동일 계정에서 실제
run을 병렬화한 결과는 운영 효율 공식 수치로 사용하지 않는다.

`provision-corpus --limit 1`로 한 문서만 먼저 색인할 수 있다. 전체 corpus가 이미 다른
절차로 색인된 환경에서는 `provision-corpus`를 생략하고 `bind-delta`만 실행한다.
`provision-delta`는 D01~D06 문서만 별도로 올리는 호환 경로이며, 101개 전체 환경을
만들지는 않는다.

## 보조평가

Phoenix·Ragas·DeepEval은 현재 V2 전용 batch에 고정되어 있으므로 V3 실행과 동시에
자동 기록되지 않는다. V3 결과 adapter가 준비되기 전에는 공식 66회 판정과 분리한다.
Garak은 실제 업무 쓰기 도구가 없는 격리 환경에서 별도로 실행하고 report를 import한다.
