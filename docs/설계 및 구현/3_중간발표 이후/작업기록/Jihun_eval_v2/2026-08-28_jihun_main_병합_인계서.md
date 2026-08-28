# Jihun Agent Eval V2 — main 병합 인계서

## 1. 이 문서만 먼저 읽으면 되는 이유

이 문서는 `jihun` 브랜치를 `main`에 병합하는 사람을 위한 실행 인계서다. 설계의 상세
근거가 필요할 때만 `설계/eval/v2/` 문서를 추가로 읽는다.

한 줄 결론은 다음과 같다.

> Agent Eval V2의 Core DEV 36건과 S10·S11 Expansion DEV 12건 평가 기반을 병합한다.
> S01은 해결된 것이 아니라 문서 전처리 고도화 전까지 보류됐고, S07 도구 설명 수정은
> 유지한다. Phase 9 비공개 HOLDOUT은 이번 V2 마감 범위에서 연기한다. 별도
> `experiments/otel_eval_lab/`은 OTel·Phoenix·Ragas·DeepEval·Garak 학습용 POC이며
> V2 공식 점수와 제품 runtime을 변경하지 않는다.

## 2. 병합 기준점과 충돌 확인

- 확인일: 2026-08-28
- 대상 브랜치: `jihun`
- 비교한 `origin/main`: `4b1b470455b7f2693a32e4d29c24de8fefd1b30c`
- 확인 시점의 로컬 `jihun` HEAD: `a243b09`(이 인계서 보강 전)
- push 전 로컬 `jihun` 주요 최신 커밋: `f8f8b57`(S10·S11 구현),
  `63cbd01`(동결 결과), `811b94d`(대시보드 Expansion 분리)
- 최신 main과의 commit 차이: main 고유 12개, jihun 고유 37개
- `git merge-tree --write-tree --messages origin/main HEAD` 재확인 결과: 충돌 없음
- main 고유 변경은 `.gitignore`와 Landing page 2개 파일이며, 이번 미커밋 평가
  실험실·대시보드 파일과 경로가 겹치지 않는다.
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
| S10 | account/team/agent memory namespace와 session checkpoint 격리 runner |
| S11 | 단일 Root/Child 위임 결속·도구 경계·Jira 우회 차단 runner |
| 대시보드 | Core·S10/S11 Expansion·진단·무효 결과를 분리하는 로컬 정적 HTML 생성기 |
| 통합 보조지표 | 대시보드에 Ragas·DeepEval·Garak을 공식 V2와 분리해 표시 |
| OTel 평가 실험실 | `experiments/otel_eval_lab/` 별도 프로세스에 Phoenix·Ragas·DeepEval·Garak POC 추가 |
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
| S10·S11 Expansion DEV | 12 |
| Expansion PASS / FAIL | 12 / 0 |
| 현재 로컬 진단·실험용 | 82 |
| 현재 로컬 평가 인프라 무효 | 18 |

이 수치는 개발용 진단 결과이며 HOLDOUT 공식 성적이 아니다. LEGACY, S08, S10/S11은
Core DEV 분모에 포함하지 않는다. S10/S11은 별도 Expansion 결과로만 표시한다.

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

### S10·S11 Expansion

- 동결 기준: Candidate `AG004/AV073`, Git
  `f8f8b57f9847b594d978703b0139f44a7b4db046`, Judge prompt `eval-v2-judge-v3`
- S10 메모리·세션 격리: 6 VALID / 6 PASS
- S11 단일 Child 위임 안전·결과: 6 VALID / 6 PASS
- 최종 S11 보조 검색 효율도 6/6 PASS지만, 동결 전 진단 실행에서 4회 검색 변동성이
  관측됐으므로 장기 안정성을 증명한 것으로 확대 해석하지 않는다.
- S11 Jira 도구는 connector 없는 평가용 trap만 사용했으며 실제 Jira 변경은 0건이다.
- S10/S11 결과를 Core 36건의 분자·분모에 합치지 않는다.

### 다음 Candidate

`AG004/AV073`은 `AV072`를 덮어쓰지 않고 일반 산술 검산 규칙 한 개만 추가해 발행한
freeze 검토 Candidate다. S07 registry 수정은 코드 수준에서 적용된다. AV073으로
Phase 9를 시작하도록 승인한 것은 아니다.

## 5. Git에 포함되지 않는 것

다음은 `.gitignore` 또는 DB 상태이므로 merge만으로 다른 환경에 전달되지 않는다.

| 항목 | 현재 상태 | 병합자가 알아야 할 점 |
|---|---|---|
| `outputs/eval-v2-results/` | 로컬 실행 폴더·manifest·result 각 148개 | Git에 없음. 별도 원본 bundle이 없으면 과거 대시보드를 재현할 수 없음 |
| `outputs/eval-v2-dashboard/index.html` | 로컬 생성 파일 | Git에 없음. 생성기로 다시 만듦 |
| V2 DB 결과 | Core 기존 대조 기록 보존, 최종 S10/S11 12건은 실행별 `db_matched=true` | 전체 148건을 새로 일괄 대조했다고 확대 해석하지 않음 |
| `AG004/AV073` | 현재 사용한 DB에 발행됨 | 독립 DB에는 자동 생성되지 않음 |
| Langfuse trace/score | 설정된 Langfuse project에 저장 | Git이나 DB migration으로 복제되지 않음 |
| Phoenix Trace/annotation | Docker named volume `phoenix_data` | Git에 없으며 다른 PC에서 자동 복원되지 않음 |
| Ragas·DeepEval 전체 결과 | `experiments/otel_eval_lab/artifacts/` | `.gitignore` 대상. 없으면 대시보드에 `N/A` 표시 |
| Garak raw report·격리 재생 결과 | `experiments/otel_eval_lab/garak_runs/`, `artifacts/` | `.gitignore` 대상. 민감 값은 없지만 대량 실행 증거라 Git에 포함하지 않음 |

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

### 7.1 OTel·Phoenix 보조 평가 실험실 주의

- `experiments/otel_eval_lab/` 의 requirements와 Docker image는 제품 배포 의존성에 합치지
  않는다. Python 3.13 제품 환경과 Garak Python 3.12 Docker를 분리한다.
- Phoenix는 로컬 `6006`/`4317` 포트와 `phoenix_data` volume을 사용한다.
- Ragas Faithfulness·DeepEval Answer Relevancy·모델 단독 Garak은 설정된
  OpenAI API로 프롬프트·답변이 전송될 수 있으므로 실행 전 승인과 비용을 확인한다.
- Garak 기본 PromptInject는 수십·수백 건을 생성할 수 있다. 스모크는
  `garak_safe_smoke.yaml`로 3건을 강제한다.
- `garak_agent_smoke.py`는 AG004/AV073에 업무 도구를 0개 노출하고 임시 세션을
  생성·삭제한다. 공식 V2 recorder나 점수를 쓰지 않는다.
- 현재 3건 결과는 모델 단독 `0/3 PASS`, 격리 에이전트 `3/3 PASS`지만
  모델·보호 계층이 다르고 표본이 작아 공식 보안 성적으로 사용하지 않는다.

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
python manage.py test tests.test_eval_v2_isolation tests.test_eval_v2_delegation tests.test_eval_v2_dashboard tests.test_evaluation_v2_fixtures tests.test_evaluation_v2_judge tests.test_events tests.test_factory tests.test_loader
python manage.py test tests.test_tracing_callbacks tests.test_executor tests.test_harness
```

2026-08-28 인계서 작성 시점의 확인 결과는 다음과 같다.

- `eval_v2_validate.py`: Core 10개와 Expansion 4개, 총 14개 package `VALID`
- S10/S11·대시보드·fixture·Judge·runtime 관련 묶음: 189/189 PASS
- 추적·executor·harness 묶음: `web` 이미지 재빌드 후 65/65 PASS
- 통합 V2 대시보드: 9/9 PASS
- OTel 평가 실험실: 7/7 PASS

실험실과 대시보드만 다시 확인할 때는 다음을 실행한다.

```text
python -m unittest tests.test_eval_v2_dashboard -v
cd experiments/otel_eval_lab
.venv/Scripts/python -m unittest discover -s tests -v
```

새 S10/S11 테스트는 Django 설정을 사용하므로 `python -m unittest discover` 대신
`python manage.py test`로 실행한다. 로컬 `.env`가 Docker hostname `db`를 가리키는
상태에서 전체 통합 테스트를 호스트 Python으로 돌리면 DB 이름 해석에 실패할 수 있다.
그 경우 Docker `web` 컨테이너를 사용하거나 확인된 localhost DB URL을 명시한다.

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
- 대시보드 상단은 Core 36건과 동결 S10/S11 Expansion 12건을 별도 종합으로 표시한다.

## 9. 병합 후 금지 사항

- Phase 9/HOLDOUT을 자동으로 시작하지 않는다.
- S08 Jira 승인 경로를 실행하지 않는다.
- S10/S11을 Core 점수에 합치지 않는다.
- S01 FAIL을 숨기거나 AV067~AV071 결과를 공식 점수에 넣지 않는다.
- 진단·무효 실행을 36건 공식 cohort에 섞지 않는다.
- 원본 파일 없이 DB 숫자만 보고 파일·DB 대조가 끝났다고 쓰지 않는다.
- AV073이 모든 DB에 존재한다고 가정하지 않는다.
- Ragas·DeepEval·Garak 점수를 V2 공식 PASS/FAIL에 합산하지 않는다.
- Garak을 실제 Jira·DB·Skill·Task 변경 도구가 연결된 endpoint에 실행하지 않는다.
- `garak_safe_smoke.yaml` 없이 외부 모델 PromptInject를 실행하지 않는다.

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
- S10/S11 Jihun 작업계획: `2026-08-27_S10_S11_Jihun_작업계획.md`
- S10/S11 최종 구현 결과: `2026-08-28_S10_S11_DEV_구현결과.md`
- HOLDOUT 팀원 전달 자료: `전달 문서/README.md`
- 보조 평가 지표·실행 결과: `2026-08-28_V2_Ragas_DeepEval_평가지표.md`
- OTel·Phoenix·Ragas·DeepEval·Garak 실행법: `experiments/otel_eval_lab/README.md`

Jihun은 S01~S11 DEV 설계·개선과 S10/S11 트랙을 맡는다. 이전의 S10/S11 팀원 이관
결정은 철회됐다. Phase 9 비공개 HOLDOUT은 연기됐으므로 현재 custodian/reviewer나 공식
batch 담당자를 확정된 것처럼 쓰지 않는다. 향후 HOLDOUT을 재개한다면 비공개 정답 접근
통제와 담당 역할을 다시 승인해야 한다.

현재 게이트: `PHASE9_DEFERRED`. 별도 재개 결정과 freeze manifest 승인 전 HOLDOUT 실행 금지.
