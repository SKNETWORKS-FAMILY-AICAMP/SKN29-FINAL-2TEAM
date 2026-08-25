# RunPod Serverless 배포 및 연동 인수인계

## 1. 문서 목적

이 문서는 `SKN29-FINAL-2TEAM`의 문서 파싱·구조 보존 청킹·임베딩 Worker를
RunPod Serverless에 배포한 실제 과정과 현재 상태를 백엔드·프론트엔드 담당자에게
인계하기 위한 문서다.

- 작성 및 실환경 확인일: 2026-08-04
- Django 통합 작업본: `C:\final_project\choi_local`
- Worker 배포 저장소: `https://github.com/choiwon10/SKN29-RUNPOD-WORKER`
- RunPod Endpoint ID: `ugczgulvpawbyv`
- RunPod 콘솔: `https://console.runpod.io/serverless/user/endpoint/ugczgulvpawbyv`
- 임베딩 모델: `google/embeddinggemma-300m`
- 임베딩 차원: 768
- 실행 장치: CUDA 전용

이 문서에는 API key, Hugging Face token, OpenAI key의 실제 값을 기록하지 않는다.
비밀값은 저장소나 메신저 평문이 아닌 별도의 안전한 경로로 전달해야 한다.

> **이 문서가 적고 있던 Endpoint ID `wmsdhbftpejzjw` 는 틀렸다 (2026-08-25 정정).**
> 그 Endpoint 도, 한때 재생성했던 `ekysa59yf3ni6t` 도 지금은 **404 — 지워졌다.**
> 2026-08-24 에 Endpoint 를 다시 만들었고, 살아 있는 것은 `ugczgulvpawbyv`
> 하나뿐이다(`embed_queries` 실호출로 확인: `google/embeddinggemma-300m`, 768차원).
> 5.3 도 콘솔과 대조해 고쳤다. **배포 방식이 바뀌었다** — GitHub 저장소
> (`choiwon10/SKN29-RUNPOD-WORKER`, `codex/install-triton-compiler`) 에서
> 빌드하던 것이 아니라, 미리 구운 이미지
> `somber7/skn29-runpod-worker:2026-08-24` 를 가리킨다. 워커 코드를 고쳐도
> **그 이미지를 다시 굽고 태그를 올리기 전에는 아무 일도 일어나지 않는다.**

## 2. 현재 결론

RunPod Worker의 이미지 빌드, Endpoint 배포, CUDA 모델 로딩 및 질의 임베딩 실요청은
완료됐다. 2026-08-04 기준 실요청 결과는 다음과 같다.

| 항목 | 확인 결과 |
|---|---|
| RunPod 상태 | `COMPLETED` |
| Worker action | `embed_queries` |
| 모델 | `google/embeddinggemma-300m` |
| 출력 차원 | 768 |
| 실제 첫 Vector 길이 | 768 |
| 대기 시간 | 11,280ms |
| 실행 시간 | 17,673ms |
| 성공 job ID | `7fe074b2-4990-4d05-8740-492a6ab5affa-e1` |

현재 Endpoint는 `main`이 아니라 `codex/install-triton-compiler` 브랜치를 배포한다.
`main`에는 아래 7장의 C compiler 수정이 아직 없으므로, 브랜치 병합 전 Endpoint를
`main`으로 되돌리면 같은 오류가 재발할 수 있다.

## 3. 시스템 경계

```text
React
  -> 로컬 Django API
       -> 로컬 PostgreSQL + pgvector
       -> 로컬 문서 저장소
       -> RunPod /run 요청
            -> Cloudflare HTTPS 서명 URL로 원문 다운로드
            -> Docling 파싱
            -> 구조 보존 청킹
            -> EmbeddingGemma 문서 임베딩(768)
       <- 브라우저가 Django 상태 API polling
       -> 완료 결과를 doc_block/chunk/vec_idx에 단일 트랜잭션 적재

업무 추출 시:
React -> Django Query Agent
      -> RunPod /runsync로 질의 임베딩
      -> pgvector 검색
      -> OpenAI Extraction Agent
```

책임 경계는 다음과 같다.

- RunPod Worker는 PDF/DOCX 파싱, 청킹, 임베딩만 수행한다.
- Worker에는 로컬 경로, DB 자격증명, OAuth token을 전달하지 않는다.
- Django가 서명된 원문 URL을 만들고 결과를 검증·적재한다.
- RunPod는 **공개된 만료형 HTTPS URL**로만 원문을 받는다. 그 https 를 어디서 얻느냐가 환경마다 다르다 — **로컬은 Cloudflare Quick Tunnel**, **AWS 는 `https://api.halil-ai.site` 고정**이라 터널이 필요 없다(2026-08-14~).
- 문서 임베딩과 검색 질의 임베딩은 같은 모델과 768차원 계약을 사용한다.

## 4. 배포 저장소 구성

기존 프로젝트의 `runpod_worker`만 독립 배포할 수 있도록 별도 비공개 저장소의
루트로 옮겼다.

```text
SKN29-RUNPOD-WORKER/
├─ Dockerfile
├─ handler.py
├─ pipeline.py
├─ requirements.txt
└─ README.md
```

| 브랜치/커밋 | 내용 | 현재 용도 |
|---|---|---|
| `main` / `38d654a` | 최초 Worker 배포 코드 | compiler 수정 전 상태 |
| `codex/install-triton-compiler` / `0b362a6` | Triton 실행용 compiler 의존성 추가 | 현재 RunPod 배포 브랜치 |

원본 통합 프로젝트의 `C:\final_project\choi_local\runpod_worker`에도 같은 Dockerfile
수정이 반영되어 있다.

## 5. 실제 배포 과정

### 5.1 Worker 저장소 생성 및 업로드

1. GitHub에 `SKN29-RUNPOD-WORKER` 비공개 저장소를 만들었다.
2. 통합 프로젝트의 `runpod_worker` 파일 5개를 저장소 루트에 배치했다.
3. 최초 Worker 코드를 `main`에 올렸다.
4. RunPod가 저장소를 읽을 수 있도록 GitHub 연결을 승인했다.

RunPod 빌드 컨텍스트는 저장소 루트이며 Dockerfile 경로도 루트의 `Dockerfile`이다.

### 5.2 RunPod Secret 생성

RunPod 콘솔의 Secret에서 Hugging Face token을 다음 이름으로 등록했다.

```text
Secret name: HF_TOKEN
Secret value: 실제 Hugging Face token (문서에 기록 금지)
```

Endpoint 환경변수에서는 Secret을 다음과 같이 참조한다.

```text
HF_TOKEN={{ RUNPOD_SECRET_HF_TOKEN }}
```

EmbeddingGemma 모델 페이지의 사용 조건에 동의한 Hugging Face 계정의 token이어야
한다. token을 Docker image, Git, RunPod job payload에 직접 넣지 않는다.

### 5.3 Endpoint 생성 및 설정

현재 Endpoint 설정은 다음과 같다.

| 항목 | 값 |
|---|---|
| Endpoint 이름 | `SKN29-RUNPOD-WORKER-IMG` |
| Endpoint ID | `ugczgulvpawbyv` |
| 생성일 | 2026-08-24 |
| 배포 방식 | **미리 구운 Docker 이미지** (GitHub build 아님) |
| 이미지 | `somber7/skn29-runpod-worker:2026-08-24` |
| GPU Worker | Serverless GPU, 24 GB · 24 GB Pro · 48 GB (count 1) |
| 최소 CUDA | 12.8 |
| 최소 Worker | 0 |
| 최대 Worker | 1 |
| Idle timeout | 300초 |
| Execution timeout | 1,800초 |
| FlashBoot | Standard |
| Cached model | **없음** — 아래 주의 참고 |

> ⚠ **2026-08-05 정정 — 모델은 캐시되어 있지 않다.** 이 표는 `google/embeddinggemma-300m`이
> Cached model이라고 적고 있었다. Dockerfile이 모델을 이미지에 굽지 않고 RunPod의 Cached
> model에도 없어서, **최소 워커 0이면 워커가 새로 뜰 때마다 수 GB를 다시 받는다**
> (`runpod_worker/pipeline.py:126-128`의 주석이 같은 내용을 적고 있다. Idle timeout 300초).
>
> 이 표를 믿으면 **시연 전 예열을 건너뛰게 된다.** 시연 전에는 문서 하나를 미리 처리해
> 워커를 깨워 둘 것. 콜드 스타트를 줄이려면 Network Volume에 HF 캐시를 두거나 이미지에
> 구워야 한다.

Endpoint 환경변수는 다음과 같다.

```dotenv
HF_TOKEN={{ RUNPOD_SECRET_HF_TOKEN }}
EMBEDDING_MODEL=google/embeddinggemma-300m
EMBEDDING_DEVICE=cuda
```

최소 Worker가 0이므로 요청이 없으면 비용이 들지 않지만 첫 요청에는 콜드 스타트가
발생할 수 있다. 최대 Worker가 1이므로 동시에 여러 작업을 보내면 나머지는 큐에서
대기한다.

### 5.4 Docker 이미지 구성

현재 Dockerfile의 핵심은 다음과 같다.

```dockerfile
FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-dev python3-pip build-essential libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /worker
COPY requirements.txt .
RUN python3 -m pip install -r requirements.txt
COPY . .

CMD ["python3", "handler.py"]
```

주요 Python 의존성은 `runpod`, `docling==2.117.0`, `transformers`,
`sentence-transformers`, `torch`, `requests`, `python-dotenv`다.

### 5.5 Worker action

`handler.py`는 `job.input.action`을 기준으로 두 작업만 허용한다.

| action | 용도 | 호출 방식 |
|---|---|---|
| `process_document` | PDF/DOCX 파싱·청킹·문서 임베딩 | Django가 `/run` 비동기 호출 |
| `embed_queries` | pgvector 검색용 질의 임베딩 | Django가 `/runsync` 호출 |

지원하지 않는 action, CUDA 미설정, 잘못된 모델, 잘못된 차원은 대체값으로 넘어가지
않고 명시적으로 실패한다.

## 6. 첫 배포 실패와 수정 이력

최초 이미지의 Endpoint 배포 자체는 성공했지만 첫 `embed_queries` 실행은 다음
오류로 실패했다.

```text
RuntimeError: Failed to find C compiler.
Please specify via CC environment variable or set triton.knobs.build.impl.
```

- 실패 job ID: `e5481835-51c0-488e-ba81-b279fbff9d31-e2`
- CUDA 인식, HF 인증, 모델 다운로드·로딩까지는 정상 완료됐다.
- 실제 encode 단계에서 Torch/Triton이 사용할 C compiler가 image에 없어 실패했다.

해결을 위해 Dockerfile의 apt package에 다음을 추가했다.

```text
python3-dev
build-essential
```

수정 커밋은 `0b362a6 fix: install Triton compiler dependencies`다. 이 수정 후 이미지를
다시 빌드·배포하고 동일한 입력으로 재시험하여 768차원 결과를 확인했다.

RunPod 대시보드에 실패 요청 1건이 남아 있는 것은 이 최초 검증 이력이며 현재 배포의
지속적인 오류를 의미하지 않는다.

## 7. Django 백엔드 연동 계약

### 7.1 필요한 로컬 환경변수

`C:\final_project\choi_local\.env`에서 다음 항목이 필요하다.

```dotenv
RUNPOD_API_KEY=<별도 안전한 경로로 전달>
RUNPOD_ENDPOINT_ID=ugczgulvpawbyv
PUBLIC_BACKEND_BASE_URL=https://<현재 Quick Tunnel 호스트>
RUNPOD_JOB_TTL_MS=3600000
RUNPOD_EXECUTION_TIMEOUT_MS=1800000
DOCUMENT_DOWNLOAD_TOKEN_MAX_AGE_SECONDS=900

OPENAI_API_KEY=<업무 추출까지 시험할 때 필요>
# ⚠ OPENAI_MODEL·OPENAI_PLAN_MODEL·OPENAI_REASONING_EFFORT 는 2026-08-12 부터
#   .env 에서 읽지 않는다. 모델은 호출하는 에이전트가 들고 오고, 지원 밖 모델이면
#   오류 대신 코드 기본값(gpt-5.6-sol/xhigh, gpt-5.6-luna/low)으로 조용히 대체하고
#   결과의 model_fallback_from 에 남긴다. .env 에는 키만 둔다.
EMBEDDING_MODEL=google/embeddinggemma-300m
EMBEDDING_DEVICE=cuda
CHUNKING_MAX_TOKENS=512
CHUNKING_MERGE_PEERS=true
```

`RUNPOD_API_KEY`는 프론트로 전달하면 안 된다. 브라우저는 항상 Django API만 호출한다.
`PUBLIC_BACKEND_BASE_URL`은 반드시 HTTPS여야 하며 Quick Tunnel을 다시 시작해 주소가
바뀌면 `.env`를 바꾼 후 **컨테이너를 재생성**한다(`up -d --force-recreate web`).
`docker compose restart`는 `env_file`을 다시 읽지 않는다(2026-08-05 정정).

Cloudflare 호스트는 Django `ALLOWED_HOSTS`에도 추가한다.

```dotenv
ALLOWED_HOSTS=localhost,127.0.0.1,<random>.trycloudflare.com
```

### 7.2 문서 처리 시작

> ⚠ **아래 HTTP 경로 셋은 2026-08-18 에 걷었다.** `pipeline-documents/` 와
> `processing-runs/`(POST·GET)는 **사람이 파싱을 시작하던** 시절의 입구다 —
> 2026-08-15 에 「이 문서를 파싱/임베딩 하겠다를 사람이 정하지 않는다」로
> 정하면서 그 화면(`/files/new`)이 없어졌고, 부르는 쪽이 사라졌다.
>
> **워커와 주고받는 payload·상태값은 그대로 유효하다** — 지금은
> `services/document_intake.promote_to_searchable()` 이 같은 내용으로
> `submit_document_job()` 을 부르고 `job_status()` 로 기다린다. 원문을 받아 가는
> `GET /api/internal/runpod/documents/{doc_id}/` 도 그대로다.


```http
POST /api/team/documents/{doc_id}/processing-runs/
Authorization: Bearer <Django session token>
```

정상 응답은 HTTP 202다.

```json
{
  "job_id": "RunPod job id",
  "status": "IN_QUEUE"
}
```

Django는 다음 조건을 먼저 확인한다.

- 요청 사용자가 **그 팀 소속인가**(`_require_team`)
- 문서가 **해당 팀에 속하는가**(`doc.team_id`)
- 문서가 삭제 또는 접근 철회 상태가 아닌가
- `storage_key`와 `cur_revision`이 존재하는가

> ⚠ **2026-08-05 정정 — 프로젝트 소유자·프로젝트 소속 검사가 아니라 팀 검사다.**
> 앞의 두 줄은 "요청 사용자가 프로젝트 소유자인가 / 문서가 해당 프로젝트에 속하는가"였다.
> 문서는 등록 시점에 `proj_id`가 `NULL`이므로 **적힌 대로 구현하면 처리 가능한 문서가
> 항상 0건**이 된다. 폴더·문서는 팀에 매달리고, 소유자 검사를 걸면 팀장이 등록한 문서를
> 팀원이 처리할 수 없다.
- 로컬 문서 저장소에 실제 원문이 존재하는가
- Cloudflare 기반 HTTPS 서명 URL을 만들 수 있는가

통과하면 RunPod `/run`에 `process_document` action을 제출한다.

### 7.3 상태 조회와 DB 적재

```http
GET /api/team/documents/{doc_id}/processing-runs/{job_id}/
Authorization: Bearer <Django session token>
```

진행 중 응답 예시:

```json
{
  "job_id": "RunPod job id",
  "status": "IN_PROGRESS"
}
```

완료 응답 예시:

```json
{
  "job_id": "RunPod job id",
  "status": "COMPLETED",
  "ingested": {
    "blocks": 10,
    "chunks": 25,
    "vectors": 25
  }
}
```

Terminal status는 `COMPLETED`, `FAILED`, `CANCELLED`, `TIMED_OUT`이다. 완료 상태를
조회한 시점에 Django가 RunPod output을 검증하고 `doc_block`, `chunk`, `vec_idx`를
하나의 DB transaction으로 적재한다. 같은 완료 job을 다시 polling해도 기존 적재 수를
반환하도록 멱등성 보호가 구현되어 있다.

다음 중 하나라도 불일치하면 전체 적재를 rollback한다.

- `doc_id`, revision, content hash
- `embedding_model=google/embeddinggemma-300m`
- `embedding_dimension=768`
- Worker validation 결과
- Block/Chunk 연결 및 sequence
- Chunk 수와 Vector 수

### 7.4 RunPod 원문 다운로드

Worker가 호출하는 내부 URL은 다음 형태다.

```http
GET /api/internal/runpod/documents/{doc_id}/?token=<만료형 Django 서명>
```

이 URL만 인증 예외이며 token에 문서 ID, 프로젝트 ID, revision이 서명되어 있다.
기본 만료시간은 900초다. 서명 오류, 만료, revision 변경, 파일 부재는 각각 오류를
반환한다.

### 7.5 업무 추출

문서 처리와 Vector 적재가 끝난 뒤 다음 API를 호출한다.

```http
POST /api/projects/{project_id}/task-extraction-runs/
Authorization: Bearer <Django session token>
Content-Type: application/json

{
  "primary_document_id": "DC001"
}
```

이 단계는 RunPod 질의 임베딩뿐 아니라 OpenAI Query/Extraction Agent를 사용하므로
`OPENAI_API_KEY`가 별도로 필요하다. `search_ready=false`인 문서에는 HTTP 409를
반환하며 임의 결과를 만들지 않는다.

## 8. 프론트엔드 인수인계

### 8.1 이미 구현된 부분

`frontend/src/api/projects.ts`에는 다음 함수와 타입이 있다.

- `startDocumentProcessing(token, projId, docId)`
- `fetchDocumentProcessing(token, projId, docId, jobId)`
- `DocumentProcessingRun`
- `startTaskExtraction(token, projId, primaryDocumentId)`
- 문서의 `downloaded`, `search_ready` 상태

> ⚠ **`PrimaryDocumentSelectPage` 는 2026-08-11 에 삭제됐다.** 기능이 셋으로
> 나뉘었다 — 등록 즉시 자동 처리는 `NewFilesPage`, 기준 문서 선택은
> `ProjectDetailPage` 의 `PrimaryDocumentCard`, 추출 결과 열람은 Chat 근거 카드.
> API 함수 이름도 바뀌었다: `startDocumentProcessing(token, docId)` ·
> `streamTaskExtraction(token, projectId, primaryDocumentId)`.

### 8.2 프론트 연결 — 완료됨

> ⚠ **2026-08-05 정정.** 이 절은 "아직 연결되지 않은 부분"이었고, 프론트 담당자에게
> **「문서 처리」 버튼을 추가하라**고 지시하고 있었다. 그 버튼은 만들지 않기로 확정됐다 —
> **등록 한 번이 원문 수신 → 파싱 → 청킹 → 임베딩까지 간다.** 나누면 「등록은 됐는데 못
> 쓰는 문서」가 남고 그것을 사용자가 따로 관리해야 하기 때문이다. 그래서 문서 관리
> 화면에 처리할 문서를 고르는 칸이 **없다.** 아래 2~7번은 그 흐름 안에서 이미 구현됐다.

화면이 문서마다 순차로 진행하며 상태를 보여주고, 한 건이 실패해도 나머지는 계속한다.
구현된 동작은 다음과 같다.

1. 등록과 동시에 처리가 시작된다 — 사용자가 누를 별도 버튼은 없다.
2. `startDocumentProcessing`을 문서당 한 번만 호출하고 `job_id`를 보관한다.
3. `fetchDocumentProcessing`으로 상태를 polling한다.
4. `COMPLETED`이면 문서 목록을 다시 조회해 `search_ready=true`를 반영한다.
5. `FAILED`, `CANCELLED`, `TIMED_OUT`이면 서버의 `error`를 화면에 표시하고 polling을
   중단한다.
6. 컴포넌트 unmount 또는 문서 변경 시 timer와 미완료 요청을 정리한다.
7. 처리 중 중복 제출 버튼을 비활성화한다.

브라우저가 RunPod API 또는 RunPod API key를 직접 사용해서는 안 된다. 진행률을
가짜 숫자로 만들지 말고 서버가 주는 status만 표시한다.

## 9. 로컬 실행 전 현재 미완료 환경

2026-08-04 점검 당시 작업 PC 상태는 다음과 같다.

| 항목 | 현재 상태 | 영향 |
|---|---|---|
| RunPod Worker | 배포 및 임베딩 실요청 성공 | Worker 단독 사용 가능 |
| Django `.env`의 RunPod key/Endpoint ID | 설정됨 | 값 공유 금지 |
| Docker Desktop/CLI | 미설치 | 로컬 PostgreSQL·Django·React compose 실행 불가 |
| `cloudflared` | 미설치 | RunPod가 로컬 원문을 받을 수 없음 |
| `PUBLIC_BACKEND_BASE_URL` | 미설정 | 문서 처리 시작 API가 명시적 설정 오류 반환 |
| `OPENAI_API_KEY` | 미설정 | 멀티에이전트 업무 추출 실행 불가 |
| 프론트 처리/polling UI | 미연결 | 수동 API 호출 없이는 문서 Vector 적재 시작 불가 |

즉, RunPod Worker만 놓고 보면 준비됐지만 로컬 Django부터 PGVector까지의 문서 E2E는
아직 단순 실행만으로 시험할 수 없다.

## 10. 로컬 E2E 실행 순서

### 10.1 사전 준비

1. Docker Desktop을 설치하고 실행한다.
2. `cloudflared`를 설치한다.
3. 프로젝트 `.env`에 RunPod 설정을 넣는다.
4. 업무 추출까지 시험한다면 OpenAI key도 넣는다.

### 10.2 로컬 서비스 시작

프로젝트 루트에서 실행한다.

```powershell
docker compose -f infra/docker/docker-compose.yml up --build
```

확인 URL:

- Django health: `http://127.0.0.1:8000/api/health/`
- React: `http://127.0.0.1:5173/`

### 10.3 Cloudflare Quick Tunnel 시작

별도 PowerShell 창에서 실행한다.

```powershell
cloudflared tunnel --url http://localhost:8000
```

출력된 `https://<random>.trycloudflare.com`을 `.env`의
`PUBLIC_BACKEND_BASE_URL`과 `ALLOWED_HOSTS`에 반영한 뒤 Django 컨테이너를
**재생성**한다 — `docker compose -f infra/docker/docker-compose.yml up -d --force-recreate web`.
`restart`로는 `env_file`을 다시 읽지 않아 바뀐 주소가 반영되지 않는다(2026-08-05 정정).

Quick Tunnel URL은 프로세스를 다시 시작하면 바뀔 수 있다. 이전 URL을 그대로 쓰면
RunPod의 원문 다운로드가 실패한다.

### 10.4 기능 시험 순서

1. 로그인한다.
2. 프로젝트와 Drive 문서를 연결하고 원문 다운로드를 완료한다.
3. 문서 처리 시작 API를 호출한다.
4. 반환된 `job_id`로 상태 API를 polling한다.
5. `COMPLETED`와 blocks/chunks/vectors 수를 확인한다.
6. 문서 목록의 `search_ready=true`를 확인한다.
7. 기준 문서를 선택해 업무 추출 API를 호출한다.
8. 결과의 근거 Chunk와 pgvector 검색 결과가 실제 문서에 존재하는지 확인한다.

## 11. Worker 단독 smoke test

Endpoint 배포만 검증하려면 로컬 `.env`에서 key와 Endpoint ID를 읽어 아래처럼
비동기 요청을 보낼 수 있다. key 자체는 출력하지 않는다.

```powershell
$envPath = 'C:\final_project\choi_local\.env'
$apiKey = ((Get-Content $envPath | Where-Object { $_ -like 'RUNPOD_API_KEY=*' })).Substring('RUNPOD_API_KEY='.Length)
$endpointId = ((Get-Content $envPath | Where-Object { $_ -like 'RUNPOD_ENDPOINT_ID=*' })).Substring('RUNPOD_ENDPOINT_ID='.Length)
$headers = @{ Authorization = "Bearer $apiKey" }
$body = @{ input = @{ action = 'embed_queries'; texts = @('연결 테스트') } } | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method Post `
  -Uri "https://api.runpod.ai/v2/$endpointId/run" `
  -Headers $headers `
  -ContentType 'application/json' `
  -Body $body
```

반환된 ID를 사용해 상태를 조회한다.

```powershell
Invoke-RestMethod -Method Get `
  -Uri "https://api.runpod.ai/v2/$endpointId/status/<job_id>" `
  -Headers $headers
```

합격 조건은 다음과 같다.

- `status == COMPLETED`
- `output.embedding_model == google/embeddinggemma-300m`
- `output.embedding_dimension == 768`
- `output.embeddings[0].Count == 768`

Vector 전체를 콘솔이나 로그에 출력할 필요는 없다.

## 12. 재배포 절차

Worker 코드를 수정할 때는 다음 순서를 사용한다.

1. 비밀값이 포함되지 않았는지 확인한다.
2. 기능 브랜치에 변경을 commit/push한다.
3. RunPod Endpoint가 감시하는 브랜치를 확인한다.
4. 새 build가 `Succeeded`인지 확인한다.
5. Endpoint 상태가 `Ready`가 될 때까지 기다린다.
6. `embed_queries` smoke test로 CUDA·모델·768차원을 확인한다.
7. PDF 또는 DOCX의 `process_document` E2E를 별도로 확인한다.
8. 실패하면 Build log와 Worker log를 구분해서 확인한다.

현재는 feature branch 배포 상태이므로 팀 합의 후 다음 중 하나를 선택해야 한다.

- 수정 브랜치를 `main`에 병합하고 RunPod 배포 브랜치를 `main`으로 변경한다.
- 당분간 수정 브랜치를 배포 기준으로 유지한다.

이 선택은 아직 수행하지 않았다.

## 13. 장애 확인표

| 증상 | 우선 확인 |
|---|---|
| `Failed to find C compiler` | 배포 commit이 `0b362a6` 이상인지, `build-essential`이 image에 있는지 |
| HF 401/403 또는 모델 접근 실패 | RunPod `HF_TOKEN` Secret 참조와 모델 약관 동의 여부 |
| CUDA 관련 시작 실패 | `EMBEDDING_DEVICE=cuda`, GPU Worker와 CUDA 12.8 image 확인 |
| Django에서 `PUBLIC_BACKEND_BASE_URL` 오류 | Quick Tunnel 실행 여부와 HTTPS URL 설정 |
| RunPod 원문 다운로드 403 | 서명 만료, 컨테이너 재생성 누락(`.env` 미반영), 서버 시간, token 변조 확인 |
| RunPod 원문 다운로드 404 | storage key, revision, connector 다운로드 상태 확인 |
| DB 적재 rollback | model/dimension/hash/revision/Chunk sequence 불일치 확인 |
| 문서가 계속 `처리 필요` | 프론트가 processing API를 호출했는지, 완료 poll에서 ingest가 실행됐는지 확인 |
| 업무 추출 409 | 문서의 `search_ready` 확인 |
| 업무 추출 설정 오류 | `OPENAI_API_KEY`, 모델 `gpt-5.6-sol`, reasoning `xhigh` 확인 |

## 14. 담당별 체크리스트

### 백엔드 담당

- [ ] Docker Desktop 기반 PostgreSQL/pgvector와 Django 실행 확인
- [ ] `.env`의 RunPod key/Endpoint ID 주입
- [ ] `PUBLIC_BACKEND_BASE_URL` 설정 — **로컬만** Cloudflare Quick Tunnel 이 필요하고,
      AWS 는 `https://api.halil-ai.site` 로 이미 고정돼 있다
- [ ] (로컬만) Cloudflare hostname을 `ALLOWED_HOSTS`에 추가
- [ ] PDF/DOCX 처리 시작·polling·DB 적재 E2E 확인
- [ ] `vec_idx.embedding`이 `VECTOR(768)`인지 확인
- [ ] 업무 추출용 OpenAI key를 별도 주입
- [ ] RunPod feature branch를 `main`에 병합할지 팀에서 결정

### 프론트엔드 담당

- [ ] 문서별 처리 시작 버튼 연결
- [ ] `job_id` 보관과 상태 polling 구현
- [ ] terminal status에서 polling 중단
- [ ] 중복 제출 방지
- [ ] 완료 후 문서 목록 갱신 및 `search_ready` 반영
- [ ] 실패 원문을 사용자에게 표시
- [ ] RunPod key를 브라우저 코드나 환경변수에 넣지 않음

### 공통 인수 기준

- [ ] 실제 PDF 1건과 DOCX 1건 처리 성공
- [ ] 표가 있는 문서에서 표 구조 metadata 확인
- [ ] Block 수, Chunk 수, Vector 수 정합성 확인
- [ ] 모든 Vector가 768차원인지 확인
- [ ] 같은 완료 job 재조회 시 중복 적재되지 않는지 확인
- [ ] 검색 질의 임베딩과 문서 임베딩 모델이 동일한지 확인
- [ ] 실패 시 임의 fallback 없이 명시적 오류가 표시되는지 확인

## 15. 관련 파일

| 범위 | 파일 |
|---|---|
| Worker | `runpod_worker/Dockerfile` |
| Worker dispatcher | `runpod_worker/handler.py` |
| Worker 핵심 파이프라인 | `runpod_worker/pipeline.py` |
| Django RunPod client | `services/document_pipeline/runpod_client.py` |
| Django 서명 URL | `services/document_pipeline/signing.py` |
| Django API | `apps/projects/api_views.py`, `apps/projects/api_urls.py` |
| DB 적재·검색 | `backend/db/document_pipeline.py` |
| Frontend API | `frontend/src/api/projects.ts` |
| 최소 선택 화면 | `frontend/src/pages/PrimaryDocumentSelectPage/PrimaryDocumentSelectPage.tsx` |
| 전체 구현 변경 명세 | `docs/설계 및 구현/3_중간발표 이후/Agent/RunPod_구조보존청킹_멀티에이전트_병합_구현명세.md` |
| Cloudflare 실행 안내 | `docs/설계 및 구현/3_중간발표 이후/Agent/Cloudflare_Tunnel_RunPod_연결_가이드.md` |
