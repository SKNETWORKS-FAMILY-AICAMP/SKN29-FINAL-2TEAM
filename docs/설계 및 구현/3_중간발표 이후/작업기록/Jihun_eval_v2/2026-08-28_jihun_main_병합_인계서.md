# Jihun Agent Eval V2 — main 병합 인계서

## 1. 이 문서만 먼저 읽으면 되는 이유

이 문서는 `jihun` 브랜치를 `main`에 병합하는 사람을 위한 실행 인계서다. 설계의 상세
근거가 필요할 때만 `설계/eval/v2/` 문서를 추가로 읽는다.

한 줄 결론은 다음과 같다.

> Agent Eval V2의 Core DEV 36건 실행과 자동 평가 기반을 병합한다. S01은 해결된 것이
> 아니라 문서 전처리 고도화 전까지 보류됐고, S07 도구 설명 수정은 유지한다. Phase 9와
> HOLDOUT은 별도 승인 전까지 실행하지 않는다.

## 2. 병합 기준점과 충돌 확인

- 확인일: 2026-08-28
- 대상 브랜치: `jihun`
- 비교한 `origin/main`: `6322656`
- 비교한 `origin/jihun`: `b7db97b`. AV073 재평가와 후속 문서 커밋은 그 뒤에 추가된다.
- `git merge-tree --write-tree --messages origin/main jihun` 확인 결과: 충돌 없음
- 실제 병합 직전에는 `origin/main`을 다시 fetch하고 충돌 검사를 반복한다.

이 브랜치에는 중간 S01 실험과 그 롤백 커밋이 모두 남아 있다. 최종 tree에는 S01 실험
변경이 남아 있지 않다. PR 이력을 단순하게 유지하려면 squash merge가 이해하기 쉽지만,
일반 merge를 사용해도 최종 코드 동작은 같다. 어느 방식을 쓰든 PR 설명에
`S01 실험은 최종 상태에서 제거됨`을 반드시 적는다.

## 3. 병합되는 최종 기능

| 영역 | 최종 변경 |
|---|---|
| V2 평가 계약 | Core fixture/gold, deterministic·Hard Gate·Judge 결합 규칙 |
| V2 실행 | S01/S04/S07/S09A 전용 runner와 나머지 Core runner |
| Judge | `gpt-5.6-sol`, reasoning `medium`, strict parser |
| 결과 저장 | append-only 파일 원본과 `eval_v2_*` DB 조회 사본 |
| 결과 검증 | fixture 무결성, 자동 집계, 파일·DB checksum 대조 |
| 대시보드 | Git 밖의 V2 결과를 읽는 로컬 정적 HTML 생성기 |
| Langfuse | Agent root/child 연결, HITL resume 연결, 평가 score 기록, 장애 격리 |
| S07 | Jira 요청과 플랫폼 `task_register`의 의미를 분리한 도구 설명 |

제품 프론트엔드에는 V2 대시보드를 붙이지 않는다. 대시보드는 로컬 HTML이며 DB나 별도
서버 없이 원시 결과 파일을 읽는다.

## 4. 평가 결과의 정확한 의미

현재 공식 DEV cohort는 `AG004/AV073`과 Git
`e888d6b05729af24617509cdecd2b4d540d330aa`를 함께 고정한 36건이다. AV035 결과는
과거 기준선으로 보존한다.

| 구분 | 건수 |
|---|---:|
| 공식 Core DEV | 36 |
| PASS | 32 |
| FAIL | 4 |
| 실행 가중 통과율 | 88.9% |
| 현재 로컬 진단·실험용 | 54 |
| 현재 로컬 평가 인프라 무효 | 12 |

이 수치는 개발용 진단 결과이며 HOLDOUT 공식 성적이 아니다. LEGACY, S08, S10/S11은
Core DEV 분모에 포함하지 않는다.

### S01

- 공식 결과: 0 PASS / 3 FAIL
- 현재 상태: `KNOWN_LIMITATION`·`DEFERRED_DOCUMENT_PREPROCESSING`
- PDF의 상위 WBS 행과 하위 상세표 관계를 안정적으로 보존하지 못해 보류했다.
- S01 개선용 `AV067`~`AV071`과 실행 결과는 `DIAGNOSTIC_ONLY`다.
- 특정 답을 prompt에 넣거나 fixture·gold·Judge를 완화해 통과시키지 않는다.

### S06

- 공식 결과: 2 PASS / 1 FAIL
- 1회 REQ-F-62의 목표 요구사항을 최종 확정 범위처럼 답했다.
- 나머지 2회는 최종 범위를 확인할 수 없다고 정확히 유보했다.

### S07

- 현재 AV073 결과: 3 PASS / 0 FAIL
- 평가 fixture가 Jira와 무관한 `task_register`까지 선행 도구처럼 설명하던 문제를
  수정했다.
- 이 registry 변경은 전역 코드에 적용된다. 사용자가 Jira만 요청하면
  `jira_create_issues`만 필요하고, 플랫폼 내부 작업 등록도 명시적으로 요청한 경우에만
  `task_register`가 필요하다고 설명한다.
- 평가 환경 identity는 `EVAL_S07_TOOL_PROFILE_V2`,
  `deployment_equivalent: false`다.

### 다음 Candidate

`AG004/AV073`은 `AV072`를 덮어쓰지 않고 일반 산술 검산 규칙 한 개만 추가해 발행한
freeze 검토 Candidate다. S07 registry 수정은 코드 수준에서 적용된다. AV073으로
Phase 9를 시작하도록 승인한 것은 아니다.

## 5. Git에 포함되지 않는 것

다음은 `.gitignore` 또는 DB 상태이므로 merge만으로 다른 환경에 전달되지 않는다.

| 항목 | 현재 상태 | 병합자가 알아야 할 점 |
|---|---|---|
| `outputs/eval-v2-results/` | 로컬 실행 폴더 102개, 완료 원본 101개 | Git에 없음. 별도 원본 bundle이 없으면 과거 대시보드를 재현할 수 없음 |
| `outputs/eval-v2-dashboard/index.html` | 로컬 생성 파일 | Git에 없음. 생성기로 다시 만듦 |
| V2 DB 결과 | AV073 재평가 후 완료 원본 101/101 파일·DB 대조 | 원본 없는 실행까지 DB에 있다고 가정하면 안 됨 |
| `AG004/AV073` | 현재 사용한 DB에 발행됨 | 독립 DB에는 자동 생성되지 않음 |
| Langfuse trace/score | 설정된 Langfuse project에 저장 | Git이나 DB migration으로 복제되지 않음 |

현재는 DB에서 V2 원시 파일을 다시 내려받는 명령이 없다. 대시보드는 DB가 아니라
`outputs/eval-v2-results/`를 읽는다. 따라서 다른 컴퓨터에서 과거 실행을 봐야 하면
원본 bundle을 checksum과 함께 별도로 전달해야 한다. 원본 없이 빈 폴더에서 대시보드
생성기를 실행하면 빈 화면이 나오는 것이 정상이다.

AV073 역시 migration이나 seed가 아니다. 공유 DB를 사용하면 존재 여부를 확인하고,
독립 DB라면 임의로 같은 ID를 만들지 말고 Candidate 재현 절차를 먼저 합의한다.

## 6. DB migration

병합 후 실제 대상 DB를 먼저 읽기 전용으로 확인한다.

```text
python DB/migrations/_apply.py --check
```

다음 두 migration이 이번 평가 기능에 직접 추가됐다.

```text
python DB/migrations/_apply.py \
  DB/migrations/2026-08-26_eval_judge_result.sql \
  DB/migrations/2026-08-27_eval_v2_result_storage.sql
```

- 첫 파일: `eval_judge_result`
- 둘째 파일: `eval_v2_run`, `eval_v2_scenario_result`
- 신규 DB는 갱신된 `DB/schema.sql`에도 포함돼 있다.
- `_apply.py`는 `--url`, `DATABASE_URL`, `.env` 순으로 대상 DB를 고른다. 출력되는 대상
  주소를 확인하지 않고 적용하지 않는다.
- migration은 추가형이다. 문제가 생겼다고 운영 DB의 평가 테이블을 임의로 DROP하지
  않는다. 코드 롤백과 DB 데이터 삭제는 별도 판단이다.

Docker 환경에서는 다음처럼 실행할 수 있다.

```text
docker compose -f infra/docker/docker-compose.yml exec -T web \
  python DB/migrations/_apply.py --check
```

## 7. Langfuse 설정과 데이터 전송 주의

필요한 설정은 다음 세 개다. 값 자체는 문서나 Git에 기록하지 않는다.

```text
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://jp.cloud.langfuse.com
```

- public/secret key가 모두 없으면 Langfuse tracing은 비활성화되고 Agent 실행과 로컬·DB
  평가 저장은 계속 동작한다.
- 키가 있으면 Agent 입력·출력과 tool/LLM trace가 설정된 Langfuse project로 전송될 수
  있다. 대상 환경의 데이터 전송 승인과 project를 확인한 뒤 켠다.
- Langfuse 생성·전송 실패는 Agent 응답이나 평가 저장을 실패시키지 않도록 격리돼 있다.
- HITL resume은 저장된 trace/root ID를 사용해 같은 trace에 연결한다.

## 8. 병합 후 검증 순서

### 8.1 코드·fixture 검증

프로젝트 Python 환경이나 `web` 컨테이너 안에서 실행한다. 병합 뒤 Docker 이미지는
requirements 변경을 반영하도록 먼저 다시 빌드한다. 오래된 이미지는
`requirements/base.txt`에 선언된 `python-docx`가 없어 추적·executor·harness test가
코드 실행 전 import 단계에서 실패할 수 있다.

```text
docker compose -f infra/docker/docker-compose.yml build web
```

그다음 아래를 실행한다.

```text
python scripts/eval_v2_validate.py
python -m unittest discover -s tests -p "test_eval_v2*.py"
python -m unittest discover -s tests -p "test_evaluation_v2*.py"
python -m unittest tests.test_tracing_callbacks tests.test_executor tests.test_harness
```

2026-08-28 인계서 작성 시점의 확인 결과는 다음과 같다.

- `eval_v2_validate.py`: Core package 10개 `VALID`
- `test_eval_v2*.py`: 16/16 PASS
- `test_evaluation_v2*.py`: 20/20 PASS
- 추적·executor·harness 묶음: `web` 이미지 재빌드 후 65/65 PASS

### 8.2 기존 원본이 전달된 경우에만

```text
python scripts/eval_v2_portfolio.py
python scripts/eval_v2_record.py sync-root
python scripts/eval_v2_dashboard.py
```

- `eval_v2_portfolio.py`의 공식 기준은 `AG004/AV073`과 평가 Git commit
  `e888d6b05729af24617509cdecd2b4d540d330aa`다.
- `sync-root`는 로컬 원본을 DB에 올리고 checksum을 대조한다. 운영/공유 DB에 쓰는
  명령이므로 대상 DB를 확인한 뒤 실행한다.
- 대시보드 생성 결과는 `outputs/eval-v2-dashboard/index.html`이다.

## 9. 병합 후 금지 사항

- Phase 9/HOLDOUT을 자동으로 시작하지 않는다.
- S08 Jira 승인 경로를 실행하지 않는다.
- S10/S11을 Core 점수에 합치지 않는다.
- S01 FAIL을 숨기거나 AV067~AV071 결과를 공식 점수에 넣지 않는다.
- 진단·무효 실행을 36건 공식 cohort에 섞지 않는다.
- 원본 파일 없이 DB 숫자만 보고 파일·DB 대조가 끝났다고 쓰지 않는다.
- AV073이 모든 DB에 존재한다고 가정하지 않는다.

## 10. 문제 발생 시 되돌리는 범위

- 애플리케이션 문제: merge commit 또는 squash commit을 되돌린다.
- Langfuse 문제: 두 key를 제거해 tracing만 비활성화할 수 있다.
- 대시보드 문제: 제품 런타임과 독립적이므로 생성 파일만 사용하지 않으면 된다.
- DB migration: 평가 테이블은 추가형이므로 코드 롤백과 동시에 DROP하지 않는다.
- 이미 저장된 평가 원본·DB 행·Langfuse trace는 증거이므로 임의 삭제하지 않는다.

## 11. 연결 문서

- 현재 상태와 실행 명령: `설계/eval/v2/README.md`
- Phase 8 게이트: `설계/eval/v2/07_phase8_readiness_review.md`
- S01/S07 최종 결정: `2026-08-27_S01_보류_S07_유지_결정.md`
- 공식 DEV 결과: `2026-08-27_Core_DEV_36건_Phase8_결과.md`
- 현재 AV073 재평가 결과: `2026-08-28_AV073_Core_DEV_36건_재평가.md`
- S10/S11 팀원 범위: `2026-08-27_S10_S11_팀원_작업인계서.md`

현재 게이트: `STOP_BEFORE_PHASE_9`.
