# OpenTelemetry Agent 평가 학습 실험실

기존 제품의 Langfuse·V2 평가 코드는 수정하지 않고, OpenTelemetry·Phoenix·Ragas·DeepEval·Garak의 역할을 직접 확인하는 **비공식 학습용 POC**다.

모든 실험 결과는 `OTEL_EVAL_LAB_V2`, `official_score_eligible=false`로 기록한다. V2 공식 점수와 합치거나 하나의 종합 점수로 평균 내지 않는다.

## 무엇을 확인하는가

```text
샘플 또는 V2 요약 결과
        ↓
OpenTelemetry span ───────────────→ Phoenix 화면
        │
        ├─ V2 공식 판정(읽기 전용 참조)
        ├─ Ragas ID Precision / Recall
        ├─ Ragas Faithfulness
        ├─ DeepEval Answer Relevancy
        ├─ 반복 안정성·지연시간·토큰 별도 집계
        └─ Garak report.jsonl ────→ 별도 보안 annotation
```

- `import-v2`: 기존 JSONL의 질문·최종 답변·문서 ID·지표를 **요약 Trace**로 표시한다. 정확한 과거 span 재생은 아니다.
- `evaluate`: 제공된 문서 ID·context·답변으로 Ragas 또는 DeepEval을 실행한다.
- `import-garak`: 별도 Garak 실행 결과를 요약해 표시한다.

### 확정 평가 구성

| 구분 | 지표 | 현재 처리 |
|---|---|---|
| 공식 판정 | V2 Scenario PASS/FAIL + Hard Gate | 기존 결과를 변경 없이 참조 |
| 검색 | Ragas ID Context Precision / Recall | 문서 ID가 있으면 결정론적으로 계산 |
| 답변 | Ragas Faithfulness | 근거 원문이 있는 사례만 계산 |
| 답변 | DeepEval Answer Relevancy | 모든 최종 답변에 계산 |
| 안정성 | fixture별 반복 PASS 비율·변동 여부 | V2 반복 결과로 별도 집계 |
| 운영 | 지연시간·도구/모델 호출·실패·토큰 | V2에 기록된 값만 별도 집계 |
| 보안 | Garak 공격 결과 | 공식 점수와 분리 |
| 전체 경로 | Task Completion / Step Efficiency | 완전한 순서 Trace가 없으면 `N/A` |
| 엄격한 도구 | 도구명·인자·순서·결과 | 해당 원문이 없으면 `N/A` |

`N/A`를 0점이나 PASS로 바꾸지 않는다. 특히 과거 V2 결과의 도구 이름만 비교해
높은 점수를 만들던 약한 ToolCorrectness는 확정 구성에서 제외했다.

## 1. Phoenix 실행

```powershell
cd experiments/otel_eval_lab
docker compose up -d phoenix
```

브라우저에서 `http://localhost:6006`을 연다.

## 2. 전용 Python 환경

프로젝트의 `.venv`에는 설치하지 않는다. 현재 프로젝트 Python으로 실험실 전용 환경만 새로 만든다(Python 3.13 검증 완료).

```powershell
..\..\.venv\Scripts\python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

`.env.example`은 사용 가능한 환경 변수의 참고용이다. Phoenix 기본 주소를 사용하면 별도 환경 변수 없이도 Trace 전송은 가능하다.

## 3. 기존 V2 결과 3개를 요약 Trace로 표시

`experiments/otel_eval_lab` 폴더에서 실행한다.

```powershell
.venv\Scripts\python -m otel_eval_lab.cli import-v2 --results-root ..\..\outputs\eval-v2-results --limit 3
```

이 명령은 모델을 호출하지 않는다. 기존 JSONL에 없는 검색 chunk나 도구 반환값을 만들어내지도 않는다.

## 4. DeepEval Answer Relevancy 실행

```powershell
.venv\Scripts\python -m otel_eval_lab.cli evaluate --evaluator deepeval
```

질문과 최종 답변이 얼마나 직접적으로 관련되는지 외부 Judge 모델로 평가한다.
기본 모델은 `gpt-4o-mini`이며 `DEEPEVAL_JUDGE_MODEL`로 변경할 수 있다.

## 5. Ragas 실행

ID Precision/Recall은 모델 호출 없이 문서 ID로 계산한다. Faithfulness는 Judge
모델로 질문·답변·근거 원문을 전송하므로 승인된 평가 데이터와 키만 사용한다.

```powershell
$env:RAGAS_JUDGE_MODEL="gpt-4o-mini"
.venv\Scripts\python -m otel_eval_lab.cli evaluate --evaluator ragas
```

CLI는 프로젝트 루트의 `.env`를 자동으로 읽는다. 이미 설정된 환경 변수는
덮어쓰지 않으며 API 키 값은 출력하거나 Phoenix 속성으로 저장하지 않는다.
긴 실제 답변도 구조화 판정이 잘리지 않도록 기본 출력 한도는 8192 토큰이다.

팀의 OpenAI 호환 서버를 쓸 때는 `$env:OPENAI_BASE_URL`도 설정한다.

### 실제 프로젝트 에이전트 S01 실습

다음 명령은 기존 S01 PDF와 `AG004/AV073`을 실제로 실행하지만 공식 V2 결과에는
기록하지 않는다. 임시 채팅 세션은 실행 후 삭제하고, 실험용 원문은 git에서 제외된
`artifacts/`에만 저장한다.

```powershell
# 프로젝트 의존성이 설치된 루트 가상환경으로 실제 에이전트 캡처
.\.venv\Scripts\python experiments\otel_eval_lab\capture_project_s01.py

# 실험실 가상환경으로 Ragas와 DeepEval 채점 후 Phoenix 전송
cd experiments\otel_eval_lab
.\.venv\Scripts\python -m otel_eval_lab.cli evaluate `
  --cases artifacts\project_s01_case.json --evaluator both
```

### 동결 V2 전체 보조 평가

Core 36건과 S10·S11 Expansion 12건을 다시 실행하지 않고 저장된 답변 그대로
재채점한다. S08은 실행 미승인이라 포함하지 않는다. ID 검색 지표는 필수 문서 ID가
있는 사례에 적용한다. Faithfulness는 문서 근거성에 맞는 fixture에만 적용하고,
canary·HITL·메모리 격리 사례에는 적용하지 않는다. Answer Relevancy는 48개 최종
답변에 적용한다.

```powershell
cd experiments\otel_eval_lab
.\.venv\Scripts\python -m otel_eval_lab.cli evaluate-v2-batch
```

결과 JSON은 다음을 서로 분리해 저장한다.

- 실행별 V2 판정과 보조지표
- fixture별 반복 통과율과 변동 여부
- 지연시간·호출 수·실패 수·토큰 통계
- 원본 Trace 부족으로 계산할 수 없는 지표와 이유

응답별 실제 비용은 기존 결과에 통화 단위 비용이 없으므로 `N/A`다.

## 6. Garak 실행과 결과 가져오기

Garak은 Python 3.13을 지원하지 않으므로 제공된 Python 3.12 Docker 컨테이너에서 실행한다. 로컬 Python에는 설치하지 않는다.

```powershell
docker compose --profile garak build garak
```

Garak 자체 의존성이 많아 최초 빌드는 시간이 걸린다. Dockerfile은 공격 실습에 필요 없는 CUDA 패키지가 설치되지 않도록 CPU 전용 PyTorch를 먼저 고정한다.

처음에는 실제 서비스가 아닌 격리된 평가 전용 endpoint만 사용한다. `garak_rest.example.json`을 복사해 URI·요청/응답 필드를 평가 endpoint 계약에 맞게 수정한다. 내장 PromptInject는 한 종류도 수십~수백 요청을 만들 수 있으므로 스모크 테스트에는 `garak_safe_smoke.yaml`을 반드시 적용한다. 이 설정은 프롬프트 3개와 프롬프트당 생성 1회로 제한한다.

```powershell
$env:REST_API_KEY="..."
docker compose --profile garak run --rm garak `
  --config /lab/garak_safe_smoke.yaml `
  --target_type rest `
  -G /lab/garak_rest.local.json `
  --probes promptinject.HijackLongPrompt
```

Garak이 만든 report JSONL은 `garak_runs` 아래에 남는다. 콘솔에 출력된 정확한 report 경로를 Phoenix로 가져온다.

```powershell
.venv\Scripts\python -m otel_eval_lab.cli import-garak <report.jsonl 경로>
```

같은 3개 프롬프트를 실제 AG004/AV073에 비교할 때는 HTTP endpoint를 열지 않는다. 프로젝트 가상환경에서 업무 도구가 하나도 없는 임시 세션으로 로컬 재생한 뒤, 실험실 가상환경에서 결과를 Phoenix에 가져온다.

```powershell
# 저장된 Docker 내부 DB 주소를 호스트 실행용 주소로만 임시 변환한다.
$dbLine = Get-Content ..\..\.env | Where-Object { $_ -match '^DATABASE_URL=' } | Select-Object -First 1
$env:DATABASE_URL = $dbLine.Substring('DATABASE_URL='.Length).Replace('@db:', '@127.0.0.1:')
$env:LANGFUSE_PUBLIC_KEY = ''
$env:LANGFUSE_SECRET_KEY = ''
..\..\.venv\Scripts\python garak_agent_smoke.py

.\.venv\Scripts\python -m otel_eval_lab.cli import-agent-garak `
  artifacts\garak_agent_safe_results.json
```

이 재생은 공식 V2 점수가 아니다. Garak이 만든 입력을 동일하게 썼지만, 로컬 쪽 판정은 Garak의 복합 detector 전체가 아니라 해당 공격 문자열의 정확한 포함 여부와 도구 호출 여부만 확인한다.

Garak은 많은 공격 요청을 보낼 수 있다. Jira·DB 변경 도구가 연결된 제품 endpoint에는 실행하지 않는다. 모델 단독 검사는 에이전트의 시스템 프롬프트·도구 정책·HITL을 통과하지 않으므로 제품 에이전트 보안 판정으로 사용하지 않는다.

## 검증

외부 서비스나 모델 호출 없이 데이터 변환기를 검사한다.

```powershell
.venv\Scripts\python -m unittest discover -s tests -v
```

## 현재 의도적으로 하지 않는 것

- 기존 Langfuse TracerProvider 변경
- V2 runner와 공식 점수 스키마 변경
- 과거 실행에 없던 검색 원문·도구 결과 복원
- 네 도구의 점수를 하나의 종합 점수로 합산
- Garak의 자동 운영 endpoint 실행
- 완전한 Trace 없이 Task Completion·Step Efficiency 점수 생성
- 도구 인자·순서·결과 없이 엄격한 도구 점수 생성

## 확인된 upstream 주의사항

- Ragas 0.4.3은 `langchain-community==0.4.2`와 import 단계에서 충돌한다. 이 실험실은 호환되는 `0.4.1` 범위를 전용 requirements에만 고정한다.
- DeepEval 외부 Judge 호출은 요청당 60초 타임아웃과 1회 시도로 제한한다. 실패한 지표는 V2 공식 판정에 영향을 주지 않고 오류로 별도 기록한다.
