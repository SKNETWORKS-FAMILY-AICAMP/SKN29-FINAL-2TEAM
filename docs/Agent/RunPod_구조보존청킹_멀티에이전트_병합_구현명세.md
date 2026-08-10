# RunPod 구조 보존 청킹·pgvector·멀티에이전트 병합 구현 명세

## 1. 문서 목적과 기준

이 문서는 기존 `SKN29-FINAL-2TEAM` 프로젝트를 그대로 복사한
`C:\final_project\choi_local`에 구조 보존 청킹, EmbeddingGemma 임베딩,
pgvector 검색, 업무 근거 멀티에이전트, RunPod Serverless 연동 및 최소 화면을
병합하면서 변경한 부분과 새로 추가한 부분을 기록한다.

- 작성 기준일: 2026-08-04
- 로컬 작업본: `C:\Users\Playdata\OneDrive\문서\파이널프로젝트\choi_local`
- 최종 반영 위치: `C:\final_project\choi_local`
- 원본 프로젝트 구조는 보존하고 루트에 `runpod_worker`만 형제 디렉터리로 추가했다.
- 이 문서의 "구현 완료"는 코드와 로컬 정적 검증이 끝났다는 뜻이다.
- 실제 RunPod Endpoint, Cloudflare Tunnel, Hugging Face, OpenAI까지 연결한 실환경
  E2E는 필요한 비밀값과 CUDA Endpoint가 준비된 뒤 별도로 확인해야 한다.

### 1.1 병합에 사용한 입력 자료

다음 원본 코드와 명세를 대조했다.

1. 기존 전체 프로젝트: `C:\final_project\final_git\SKN29-FINAL-2TEAM`
2. 표 구조 보존 청킹 명세:
   `C:\Users\Playdata\Downloads\chunking\표구조보존_청킹_프로젝트_병합_구현명세.md`
3. 표 구조 청킹 코드:
   `C:\Users\Playdata\Downloads\chunking\chunking\06_chunk_tables_structured.py`
4. 안정 Chunk 생성 코드:
   `C:\Users\Playdata\Downloads\chunking\chunking\07_build_stable_chunks.py`
5. 멀티에이전트 병합 명세:
   `C:\final_project\parser\docs\업무근거_멀티에이전트_프로젝트_병합_구현명세.md`
6. 쿼리 생성 노트북:
   `C:\final_project\parser\agent\업무근거_쿼리생성_멀티에이전트.ipynb`
7. Docling 파서 노트북:
   `C:\final_project\parser\base\docling_base_parser.ipynb`

## 2. 대화에서 확정한 요구사항

| 항목 | 확정 내용 | 코드 반영 |
|---|---|---|
| 병합 위치 | 원본 프로젝트를 `choi_local`에 복사한 뒤 그 구조에서 병합 | 기존 루트 구조 유지 |
| Worker 위치 | 같은 저장소 루트에 Django backend와 별개인 `runpod_worker` 추가 | `runpod_worker/` 신설 |
| 서버 위치 | Django, React, PostgreSQL, 원문 저장소는 로컬 실행 | Worker에 DB 접속정보를 전달하지 않음 |
| 외부 연결 | 중간발표는 AWS 없이 Cloudflare Tunnel 사용 | HTTPS 서명 다운로드 URL 구현 |
| RunPod 방식 | RunPod Serverless Endpoint | Django `/run`, `/status`, `/runsync` client 구현 |
| 처리 방식 | 문서 처리는 비동기 요청 후 polling | 시작 API와 상태 API 분리 |
| Worker 장치 | RunPod CUDA만 사용 | CPU fallback 없이 CUDA 미사용 시 오류 |
| 임베딩 모델 | 적재와 검색 모두 `google/embeddinggemma-300m` | 문서 `encode_document`, 질의 `encode_query` |
| 토큰 기준 | 청킹 토큰화도 EmbeddingGemma tokenizer로 통일 | MiniLM tokenizer 제거 |
| 임베딩 차원 | 768 | DB, Worker, 적재, 검색에서 검증 |
| Vector 단위 | Chunk 하나당 `vec_idx` 하나 | Chunk UUID와 Vector PK를 1:1로 적재 |
| 비밀값 | `.env`를 통해 읽고 사용자가 HF token 등을 주입 | key/token 하드코딩 없음 |
| Agent 모델 | 검색어 생성 `gpt-5.6-luna`(effort `low`), 최종 정리 `gpt-5.6-sol`(effort `xhigh`) | 아는 모델이 아니면 명시적 설정 오류 (2026-08-05 분리) |
| 미처리 문서 | 아직 준비되지 않았으면 화면에 오류만 표시 | 409 응답 및 선택 화면 오류 표시 |
| 화면 범위 | 기준 문서 선택 → 추출 → 1차 확인까지 연결 | 진행 스트리밍·근거 열람·JSON 복사 포함 (2026-08-05) |
| 실패 정책 | 하드코딩된 대체값으로 억지 실행 금지 | 누락·불일치·초과 시 명시적 오류 |

### 2.1 MiniLM 관련 확인 결과

기존 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`는 파싱 모델이
아니었다. 기존 청킹 단계에서 `HybridChunker`의 크기를 재기 위한 tokenizer로만
사용됐으며, 제공된 `06`/`07` 코드에도 실제 임베딩 생성이나 pgvector 적재는
없었다. 이번 병합에서는 해당 경로를 확장한 것이 아니라 다음처럼 교체했다.

- 파싱: Docling
- 청킹 토큰 계산: EmbeddingGemma tokenizer
- 문서 임베딩: EmbeddingGemma `encode_document`
- 검색 질의 임베딩: EmbeddingGemma `encode_query`
- 저장 및 검색: PostgreSQL pgvector 768차원

따라서 파싱 모델과 임베딩 모델을 혼동하지 않으며, MiniLM은 새 파이프라인에서
사용하지 않는다.

## 3. 병합 전후 아키텍처

### 3.1 기존 흐름

기존 프로젝트에는 Drive 연결, 로컬/S3 추상화 저장소, 문서 메타데이터,
`doc_block`/`chunk`/`vec_idx` 테이블 골격, Django/React 화면이 있었다. 그러나
다음 연결은 완성되어 있지 않았다.

- 제공된 표 청킹 코드는 파일 단위 산출물을 만들 뿐 Django/DB에 연결되지 않았다.
- 기존 안정 청킹은 `embedding_text`를 만들었지만 임베딩을 생성하지 않았다.
- `vec_idx`는 1536차원을 전제로 했고 EmbeddingGemma와 맞지 않았다.
- RunPod에 로컬 원문을 안전하게 전달하는 경로가 없었다.
- 업무 근거 Query Agent와 실제 pgvector 검색/추출 Agent가 Django API에 없었다.
- 프로젝트 화면은 빈 상수 배열을 사용하고 실제 프로젝트 API와 연결되지 않았다.

### 3.2 현재 흐름

```text
Google Drive
  -> 기존 Django 다운로드 API
  -> 로컬 문서 저장소 + doc.storage_key/content_hash/cur_revision
  -> Django가 만료형 서명 URL 생성
  -> Cloudflare Tunnel HTTPS
  -> RunPod Serverless CUDA Worker
       -> Docling PDF/DOCX 파싱
       -> 본문 HybridChunker
       -> 표 구조 보존 청킹
       -> EmbeddingGemma document embedding(768)
  -> 브라우저가 Django 상태 API polling
  -> Django가 완료 output 검증
  -> doc_block + chunk + vec_idx 원자적 적재
  -> Query Agent가 단계별 검색어 생성
  -> RunPod EmbeddingGemma query embedding(768)
  -> pgvector cosine 검색
  -> Extraction Agent가 근거 기반 업무 반환
```

로컬 파일 경로나 OAuth token은 RunPod로 보내지 않는다. RunPod는 서명된 HTTPS
URL로 원문만 읽고, Django만 PostgreSQL 자격증명과 적재 권한을 가진다.

## 4. 디렉터리 구조 변경

원본 최상위 디렉터리는 이름과 위치를 그대로 유지했다. 추가된 주요 구조는
다음과 같다.

```text
choi_local/
├─ apps/projects/                    # 기존 Django API 확장
├─ backend/db/
│  └─ document_pipeline.py           # 신규 적재·검색 repository
├─ DB/
│  └─ migrations/
│     └─ 2026-08-04_embeddinggemma_768.sql
├─ services/
│  ├─ document_pipeline/             # 서명 URL 및 RunPod client 확장
│  └─ task_extraction/               # 신규 Query/Extraction Agent
├─ runpod_worker/                    # 신규 독립 Worker 빌드 컨텍스트
│  ├─ Dockerfile
│  ├─ handler.py
│  ├─ pipeline.py
│  ├─ requirements.txt
│  └─ README.md
├─ frontend/src/pages/
│  └─ PrimaryDocumentSelectPage/     # 신규 최소 선택 화면
├─ tests/
│  └─ test_document_pipeline.py
└─ docs/
   └─ Agent/                       # 이 기능 문서는 한자리에 모아 둔다
      ├─ Cloudflare_Tunnel_RunPod_연결_가이드.md
      ├─ RunPod_Serverless_배포_인수인계.md
      └─ RunPod_구조보존청킹_멀티에이전트_병합_구현명세.md
```

`backend`와 `runpod_worker`를 별도 저장소처럼 독립 배포할 수 있도록 Worker는
자체 `Dockerfile`과 `requirements.txt`를 가진다. 현재는 사용자 요청대로 한
루트에 함께 두었지만 RunPod 빌드 컨텍스트는 `runpod_worker`만 지정할 수 있다.

## 5. 기존 파일 수정 명세

### 5.1 backend 및 설정

| 파일 | 기존 상태 | 변경 내용 |
|---|---|---|
| `.env.example` | RunPod/Embedding/OpenAI 설정 없음 | RunPod Endpoint/key/TTL/timeout, 외부 backend URL, 서명 만료, HF/OpenAI, 모델, CUDA, 청킹 설정 예시 추가 |
| `config/settings/base.py` | 기존 django-environ 설정만 존재 | RunPod, Cloudflare 공개 URL, OpenAI, Embedding, 청킹 설정을 `env`로 읽도록 추가. 비밀값과 외부 주소의 실사용 기본값은 빈 문자열 |
| `requirements/base.txt` | OpenAI Structured Output용 패키지 없음 | `openai`, `pydantic` 추가 |
| `DB/schema.sql` | `vec_idx.embedding VECTOR(1536)` | `VECTOR(768)`로 변경 |
| `backend/db/repositories.py` | 삭제 여부만 보고 문서 목록 반환 | `access_revoked=false` 조건 추가, 현재 revision에 활성 Block/Chunk/Vector가 존재하는지 `search_ready`로 계산 |
| `apps/projects/serializers.py` | 문서 readiness와 task extraction 입력 없음 | `TaskExtractionCreateSerializer`와 문서 응답의 `search_ready` 추가 |
| `apps/projects/api_urls.py` | 기존 프로젝트/문서/배정 API만 존재 | 문서 처리 시작·상태, RunPod 내부 다운로드, 업무 추출 API route 추가 |
| `apps/projects/api_views.py` | RunPod/업무 추출 endpoint 없음 | 소유권/준비상태 검증, 서명 URL 생성, `/run` 요청, `/status` polling, 완료 결과 적재, 서명 원문 전송, 업무 추출 실행 View 추가 |
| `services/document_pipeline/README.md` | 향후 단계와 Vector를 보조 검색으로 설명 | 실제 구현된 Local Django→RunPod→pgvector→Agent 경계와 명시적 오류 정책으로 갱신 |

### 5.2 frontend

| 파일 | 기존 상태 | 변경 내용 |
|---|---|---|
| `frontend/src/api/projects.ts` | 프로젝트/문서 기본 API만 제공 | `downloaded`, `search_ready`, 문서 처리 시작/상태 type과 함수, 업무 추출 결과 type과 실행 함수 추가 |
| `frontend/src/pages/ProjectListPage/ProjectListPage.tsx` | `ACTIVE_PROJECTS`/`COMPLETED_PROJECTS`가 빈 하드코딩 배열, CTA가 다른 화면으로 이동 | `listMyProjects` 실제 호출, 검색/분류/선택, 선택 프로젝트의 기준 문서 화면으로 이동하도록 수정 |
| `frontend/src/App.tsx` | 기준 문서 선택 route 없음 | 새 페이지 lazy import와 인증 route 추가 |
| `frontend/src/routes.ts` | route 상수 없음 | `/tasks/distribution/documents` 상수 추가 (2026-08-05 정정 — `/projects/:projectId/select-source-document`로 적혀 있었으나 실제 경로는 이쪽이다. 기준 문서를 고르는 시점에는 아직 프로젝트가 없다) |
| `frontend/src/api/opsAudit.ts` | 실제 응답에 선택적으로 존재할 수 있는 시간/업무명 type 누락 | `started_at`, `created_at`, `task_name` optional field 추가 |
| `frontend/src/pages/OpsAuditPage/OpsAuditPage.tsx` | 두 timestamp가 모두 없으면 `timeAgo(undefined)` 가능 | 둘 다 없을 때 `-`를 표시하도록 guard 추가 |

마지막 두 Ops Audit 변경은 새 파이프라인 기능 변경이 아니라, 전체 frontend
production build에서 드러난 기존 타입 불일치를 안전하게 보완한 것이다.

## 6. 새 파일 구현 명세

| 새 파일 | 역할 |
|---|---|
| `DB/migrations/2026-08-04_embeddinggemma_768.sql` | 기존 pgvector 컬럼을 768차원으로 바꾸는 보호 migration |
| `backend/db/document_pipeline.py` | 처리 문서 조회, 서명 다운로드 검증, 결과 원자 적재, pgvector 검색 |
| `services/document_pipeline/errors.py` | 설정/RunPod/결과/준비상태 오류 계층 |
| `services/document_pipeline/runpod_client.py` | RunPod `/run`, `/status/{id}`, `/runsync` HTTP client |
| `services/document_pipeline/signing.py` | Cloudflare HTTPS 기반 Django 서명 URL 발급·검증 |
| `services/task_extraction/__init__.py` | `extract_tasks` 공개 export |
| `services/task_extraction/service.py` | 4단계 Query Agent, pgvector 검색, 최종 Extraction Agent |
| `runpod_worker/Dockerfile` | CUDA runtime 기반 독립 Worker 이미지 |
| `runpod_worker/requirements.txt` | RunPod, Docling, Transformers, SentenceTransformers, Torch 등 Worker 의존성 |
| `runpod_worker/handler.py` | RunPod action dispatcher와 시작 시 CUDA 설정 검증 |
| `runpod_worker/pipeline.py` | 다운로드, 파싱, 구조 청킹, 임베딩, 결과 검증 핵심 구현 |
| `runpod_worker/README.md` | Worker 입력 경계와 필수 환경변수 |
| `frontend/src/pages/PrimaryDocumentSelectPage/PrimaryDocumentSelectPage.tsx` | 프로젝트 문서 조회, 기준 문서 radio 선택, readiness 오류, 업무 추출 호출 |
| `frontend/src/pages/PrimaryDocumentSelectPage/PrimaryDocumentSelectPage.module.css` | 최소 화면 스타일과 모바일 배치 |
| `docs/Agent/Cloudflare_Tunnel_RunPod_연결_가이드.md` | AWS 없이 로컬 Django를 RunPod에 연결하는 발표용 실행 절차 |
| `tests/test_document_pipeline.py` | 표 청킹, 서명 URL, RunPod payload, 미처리 문서 오류 회귀 테스트 |
| `docs/Agent/RunPod_구조보존청킹_멀티에이전트_병합_구현명세.md` | 현재 병합의 전체 변경 및 신규 기능 명세 |

## 7. 환경변수와 오류 정책

### 7.1 로컬 Django `.env`

| 변수 | 용도 | 누락/오류 시 동작 |
|---|---|---|
| `RUNPOD_API_KEY` | RunPod API 인증 | 문서 처리/질의 임베딩 시 503 설정 오류 |
| `RUNPOD_ENDPOINT_ID` | Serverless Endpoint 식별자 | 문서 처리/질의 임베딩 시 503 설정 오류 |
| `PUBLIC_BACKEND_BASE_URL` | Cloudflare Tunnel의 Django HTTPS root | HTTPS가 아니거나 비어 있으면 서명 URL 생성 오류 |
| `RUNPOD_JOB_TTL_MS` | 비동기 작업 보관 TTL | 기본 3,600,000ms |
| `RUNPOD_EXECUTION_TIMEOUT_MS` | Worker 실행 제한 | 기본 1,800,000ms |
| `DOCUMENT_DOWNLOAD_TOKEN_MAX_AGE_SECONDS` | 원문 URL 서명 유효시간 | 기본 900초 |
| `OPENAI_API_KEY` | Query/Extraction Agent 호출 | 업무 추출 시 503 설정 오류 |
| `OPENAI_MODEL` | 최종 정리 Agent 모델 | `gpt-5.6-sol` · `gpt-5.6-terra` · `gpt-5.6-luna` 중 하나가 아니면 오류 (`service.py:90-97, :106`) |
| `OPENAI_PLAN_MODEL` | 검색어 생성 Agent 모델 | 같은 3개 중 하나. 실제 설정은 `gpt-5.6-luna`(effort `low`) |
| `OPENAI_SERVICE_TIER` | OpenAI 처리 등급 | 기본 `auto`. `priority`는 **요금이 2배**다 |
| `OPENAI_REASONING_EFFORT` | Agent reasoning 수준 | 정확히 `xhigh`가 아니면 오류 |
| `EMBEDDING_MODEL` | Django 결과/검색 계약 | `google/embeddinggemma-300m` 사용 |
| `EMBEDDING_DEVICE` | 구성 표시 및 Worker 계약 | Worker에서는 정확히 `cuda` 필요 |
| `CHUNKING_MAX_TOKENS` | Chunk 최대 tokenizer token | 기본 512, Worker 허용 범위 1~2048 |
| `CHUNKING_MERGE_PEERS` | HybridChunker peer 병합 | boolean만 허용 |

### 7.2 RunPod Worker 환경변수

| 변수 | 필수값/의미 |
|---|---|
| `HF_TOKEN` | EmbeddingGemma 이용 약관에 동의한 Hugging Face token |
| `EMBEDDING_MODEL` | `google/embeddinggemma-300m` |
| `EMBEDDING_DEVICE` | `cuda` |

Worker는 `python-dotenv.load_dotenv()`로 환경변수를 읽는다. Django는 기존
`django-environ`의 `read_env` 흐름을 유지한다. 비밀값은 코드나 RunPod job
payload에 기록하지 않는다.

### 7.3 하드코딩 금지와 명시적 실패

이 병합에서 설정이 없거나 데이터가 불완전할 때 임의의 모델, CPU, 예제 데이터,
빈 Vector, 추정 업무로 대체하지 않는다.

- CUDA를 사용할 수 없으면 Worker 시작/모델 로드 오류
- HF token 또는 모델 설정이 없으면 모델 로드 오류
- 원문 URL이 HTTPS가 아니면 다운로드 거부
- 지원하지 않는 MIME type이면 오류
- source reference, 표 셀 구조, Chunk 본문이 없으면 오류
- 원자 표 행/제품 Chunk가 token 상한을 넘으면 자르지 않고 오류
- 임베딩 수나 차원이 다르면 적재하지 않고 오류
- job output의 문서 ID/revision/hash/model이 요청과 다르면 rollback
- OpenAI 모델 설정이 확정값과 다르면 오류
- Query Agent가 중복이 아닌 새 질의를 못 만들면 오류
- Extraction Agent가 검색하지 않은 Chunk ID를 인용하면 오류
- 미처리 문서는 업무 추출을 실행하지 않고 409와 화면 오류 표시

상수로 고정된 `768`, `google/embeddinggemma-300m`, `gpt-5.6-sol`, `xhigh`는
편의를 위한 fallback이 아니라 사용자와 확정한 교차 시스템 계약을 검증하기 위한
불변조건이다. 환경변수에 다른 값이 들어오면 조용히 바꾸어 실행하지 않고 실패한다.

## 8. RunPod Worker 상세

### 8.1 Handler 계약

`handler.py`는 `job.input` 객체의 `action`만 dispatch한다.

- `process_document`: 원문 파싱·청킹·문서 임베딩
- `embed_queries`: 검색 질의 임베딩
- 그 외 action: 지원하지 않는 action 오류

### 8.2 문서 입력 계약

```json
{
  "input": {
    "action": "process_document",
    "doc_id": "DC001",
    "revision": "source revision",
    "mime_type": "application/pdf",
    "source_url": "https://<cloudflare>/api/internal/runpod/documents/DC001/?token=...",
    "max_tokens": 512,
    "merge_peers": true
  },
  "policy": {
    "ttl": 3600000,
    "executionTimeout": 1800000
  }
}
```

`storage_key`, Windows 경로, DB 접속정보, OAuth token, 원문 base64는 보내지 않는다.
원문을 job payload에 넣지 않으므로 RunPod 요청 payload 한도와 로컬 경로 접근
불가능 문제를 피한다.

### 8.3 파싱

지원 MIME은 PDF와 DOCX다. 제공된 Docling base notebook 설정을 Worker용으로
옮겼다.

- PDF: **텍스트 레이어가 있으면 OCR 을 돌리지 않는다**(2026-08-05). 압축 스트림의
  `Tj`/`TJ` 연산자를 세어 판정한다 — 스캔본은 0에 가깝고 프로그램으로 만든 문서는
  수천이다. OCR 이 멀쩡한 본문을 자모 단위로 덮어써 「중도탈락을」이 「중도달락올」로
  적재되던 것을 고쳤다. `force_backend_text=True` 로는 막히지 않았다
- 스캔본: EasyOCR `ko`, `en` / OCR mode `LAYOUT_REGIONS` / full-page OCR 강제하지 않음
- backend text 강제 사용
- heading hierarchy 활성화
- picture classification/description 활성화
- chart extraction 활성화
- PDF와 DOCX 각각 맞는 format option 사용
- Converter와 임베딩 모델은 `lru_cache(maxsize=1)`로 Worker 프로세스에서 재사용

### 8.4 본문 청킹

1. Docling 문서를 JSON-compatible dict로 변환한다.
2. 문서 body/group reference를 순회하여 원문 순서를 만든다.
3. 원본 그대로 청킹하고, **표만으로 이뤄진 청크를 뒤에서 걸러낸다**(2026-08-05 정정 — 아래 주석 참고).
4. EmbeddingGemma tokenizer를 `HuggingFaceTokenizer`에 주입한다.
5. Docling `HybridChunker`로 본문을 청킹한다.
6. contextualized text, raw text, source refs, page, headings/meta를 보존한다.
7. 표 Chunk와 합친 뒤 문서 순서로 다시 정렬한다.

> ⚠ **2026-08-05 정정 — 「표를 먼저 제거하고 청킹한다」는 2026-08-04에 뒤집혔다.**
>
> 원래 의도는 본문 HybridChunker가 표 내용을 다시 포함해 같은 정보가 중복되는 것을 막는
> 것이었다. 그런데 표를 먼저 빼면 **표와 본문이 섞인 청크에서 본문까지 사라진다.** 실제
> 문서에서 그 손실이 표가 한 번 더 들어가는 것보다 컸다.
>
> 그래서 지금은 원본 그대로 청킹하고, 만들어진 청크 중 **모든 source ref가 표인 것만**
> 버린다(`runpod_worker/pipeline.py:398-401`). 표와 본문이 혼합된 청크는 **일부러
> 남긴다** — 중복을 감수하는 쪽을 택했다.

### 8.5 표 구조 보존 청킹

표 셀 좌표의 `start/end row/col offset`, `column_header`, `row_header`, 병합 셀
범위를 사용한다.

제품 열 구조로 처리하는 조건은 첫 행에 `Model`인 column header가 정확히 하나
있고 그 오른쪽에 비어 있지 않은 제품 header가 있는 경우다. 이 조건을 만족하면:

- 제품 열 하나를 하나의 원자 Chunk로 만든다.
- 왼쪽 descriptor 셀을 `속성명`, 제품 열 셀을 `값`으로 결합한다.
- 원본 제품 열 순서를 유지한다.
- `product`, `source_product_col`, `source_row_index`, `cell_ref`, 병합 셀 공유 여부를
  metadata에 남긴다.

조건을 만족하지 않는 표는 버리거나 제품표로 추측하지 않고 generic row 전략을
사용한다.

- 첫 행의 column header를 label로 사용한다.
- 데이터 행 하나를 원자 Chunk로 만든다.
- `header: value` 쌍과 원본 row/column 정보를 보존한다.
- 셀 구조가 없거나 값 행을 만들 수 없으면 오류다.

제품 열/일반 행은 원자 단위다. 512 token을 넘는 원자 Chunk를 일부 잘라 구조를
훼손하지 않는다.

> ⚠ **2026-08-05 정정 — 상한 초과가 항상 오류는 아니다.** 초과한 청크에 **표가 걸렸으면
> 그 청크만 빼고 문서는 살린다.** 무엇을 뺐는지는 결과의 `validation.dropped_chunks`에
> 남는다(`runpod_worker/pipeline.py:499-507`). 표 한 줄 때문에 본문 수백 블록을 잃는 쪽이
> 손실이 크기 때문이다. 표가 안 걸렸는데 넘쳤으면 우리 청킹 문제라 그때는 문서를
> 실패시킨다. §8.8 출력 계약에도 `dropped_chunks`를 넣어야 한다.

### 8.6 결과 정렬·Block 연결

- 본문과 표 Chunk를 원문 reference 순서로 정렬한다.
- 같은 위치에서는 본문, 표 순서를 사용한다.
- 표는 table index, row index, product column 순서를 사용한다.
- 정렬 뒤 `sequence=0..N-1`을 부여한다.
- Worker 내부 연결용 `local_block_key`, 진단용 `local_chunk_key`를 만든다.
- DB의 실제 `block_id`, `chunk_id`는 Django가 UUID로 생성한다.

Docling의 `source_ref`, page/provenance, 표 원본 구조는 Block/Vector metadata에
보존한다. `stable-chunk-*` 문자열을 DB UUID로 강제 변환하지 않는다.

### 8.7 임베딩

- 문서 Chunk: `SentenceTransformer.encode_document`
- 검색 질의: `SentenceTransformer.encode_query`
- 모델: `google/embeddinggemma-300m`
- 장치: CUDA
- 정규화: `normalize_embeddings=True`
- 출력: Chunk/질의마다 정확히 768개의 float

문서와 질의에 서로 맞는 전용 encode 경로를 사용하되 모델과 차원은 동일하다.

### 8.8 Worker 출력 계약

```text
schema_version
doc_id / revision / content_hash
parser_status
embedding_model / embedding_dimension
chunker_version
blocks[]
chunks[] + 각 chunk.embedding[768]
validation.passed
validation.table_diagnostics[]
```

`table_diagnostics`에는 표마다 `structured_product_columns` 또는
`generic_table_rows` 전략과 생성 record 수가 남는다.

## 9. Django–Cloudflare–RunPod 연동

### 9.1 서명 원문 URL

`signed_download_url`은 `doc_id`와 `revision`을 Django signing으로 서명한다.
URL에는 원문 저장 경로나 DB 정보가 없다.

> ⚠ **2026-08-05 정정 — 서명에 `project_id`는 들어가지 않는다**(`apps/projects/api_views.py:948-950`).
> 문서는 등록 시점에 `proj_id`가 `NULL`이라 서명할 값이 없다. 권한 검사도 프로젝트
> 소유권이 아니라 `_require_team`(팀 검사)이다 — 이 문서 §5.1·§14의 「프로젝트 소유자·
> 프로젝트 소속 검사」 서술도 같은 이유로 틀렸다. 소유자 기준으로 걸면 팀장이 등록한
> 문서를 팀원이 처리할 수 없게 된다.

- salt: `halil.runpod.document-download.v1`
- 공개 base URL: `PUBLIC_BACKEND_BASE_URL`
- HTTPS만 허용
- 기본 만료: 900초
- download 요청 시 path의 `doc_id`와 token의 `doc_id` 일치 검증
- 현재 DB revision과 token revision 일치 검증
- 삭제/접근철회/원문 미존재 검증

Quick Tunnel URL은 실행할 때마다 바뀌므로 바뀐 값을 `.env`에 넣고 **컨테이너를
재생성**해야 한다(`up -d --force-recreate web`) — `restart`는 `env_file`을 다시 읽지
않는다(2026-08-05 정정). `localhost`는 RunPod에서 접근할 수 없으므로 전달하지 않는다.

### 9.2 비동기 문서 처리

1. frontend 또는 API client가 Django 문서 처리 시작 API를 호출한다.
2. Django가 문서 소유권, 프로젝트, 삭제/접근철회, storage/revision을 확인한다.
3. Django가 서명 URL을 만들고 RunPod `/run`에 제출한다.
4. Django는 `202`와 job ID를 즉시 반환한다.
5. client가 Django 상태 API를 polling한다.
6. Django가 RunPod `/status/{job_id}`를 조회한다.
7. 상태가 `COMPLETED`일 때만 output을 DB에 적재한다.
8. 실패 terminal 상태는 RunPod 오류를 전달하고 적재하지 않는다.

### 9.3 질의 임베딩

업무 추출 중 검색 질의는 짧은 동기 작업이므로 RunPod `/runsync`를 사용한다.
응답이 `COMPLETED`가 아니거나 질의 수와 Vector 수가 다르거나 768차원이 아니면
검색하지 않는다.

## 10. DB 변경과 적재

### 10.1 pgvector 차원

`DB/schema.sql`의 신규 DB 스키마는 `VECTOR(768)`을 생성한다. 기존 DB에는
`DB/migrations/2026-08-04_embeddinggemma_768.sql`을 적용한다.

Migration은 `vec_idx`에 한 행이라도 있으면 예외를 내고 중단한다. 서로 다른
모델의 1536차원 Vector를 768차원으로 안전하게 변환할 수 없기 때문이다. 기존
Vector를 임의 절단하거나 0으로 채우지 않는다. 개발 데이터의 재임베딩/삭제를
운영자가 명시적으로 결정한 후 빈 테이블에서 migration해야 한다.

### 10.2 적재 전 검증

다음을 모두 통과해야 트랜잭션을 시작/완료한다.

- output `doc_id`가 요청 문서와 일치
- output `revision`이 요청 및 잠근 현재 문서 revision과 일치
- 원문 `content_hash`가 로컬 DB 값과 일치
- `embedding_dimension == 768`
- `embedding_model == google/embeddinggemma-300m`
- `validation.passed == true`
- blocks/chunks가 비어 있지 않음
- block local key가 비어 있지 않고 중복 없음
- Chunk sequence가 0부터 연속
- Chunk마다 768차원 Vector
- Chunk가 존재하는 local block key만 참조

### 10.3 원자적 적재 순서

1. `doc` 행을 `FOR UPDATE`로 잠근다.
2. 같은 revision/hash/model/dimension의 완료 결과가 이미 모두 있으면 기존 개수를
   반환한다. 반복된 완료 polling이 UUID를 다시 만들지 않게 하는 idempotency다.
3. 재처리가 필요하면 해당 문서의 기존 `vec_idx`를 먼저 삭제한다.
4. 이어서 기존 `chunk`, `doc_block`을 삭제한다.
5. `doc_block`을 새 UUID로 삽입한다.
6. `chunk`를 새 UUID로 삽입한다.
7. 같은 Chunk UUID를 PK로 `vec_idx`를 1:1 삽입한다.
8. 어느 단계라도 실패하면 전체 트랜잭션을 rollback한다.

### 10.4 필드 매핑

| Worker 결과 | DB 위치 |
|---|---|
| Block type/page/content/sequence | `doc_block` 기본 열 |
| heading path | **`chunk.heading_path`** — `doc_block.heading_path`는 Worker가 `[]`를 하드코딩해 항상 비어 있다(`runpod_worker/pipeline.py:542`, 2026-08-05 정정) |
| source ref/provenance | `doc_block.src_locator` |
| 원본 표 구조 | `doc_block.struct_content` |
| Chunk embedding text | `chunk.search_text` |
| Chunk sequence | `chunk.chunk_idx` |
| tokenizer token count | `chunk.token_cnt` |
| `stable-structured-1.0` | `chunk.chunker_ver` |
| Vector 768 float | `vec_idx.embedding` |
| doc/source refs/pages/type/table meta | `vec_idx.metadata` |
| EmbeddingGemma model | `vec_idx.embed_model`, `embed_ver` |
| 768 | `vec_idx.embed_dim` |
| 원문 hash/revision | `vec_idx.content_hash`, `revision` |

### 10.5 검색 조건

pgvector cosine distance `<=>`를 사용하고 점수는 `1 - distance`로 반환한다.
검색은 아래를 모두 만족하는 행만 대상으로 한다.

- 요청 팀 안의 서버 검증 document ID (2026-08-04 프로젝트 → 팀)
- 삭제되지 않고 접근 철회되지 않은 문서
- 활성 Chunk와 활성 Vector
- `embed_model=google/embeddinggemma-300m`
- `embed_dim=768`
- Agent가 정한 `top_k` 범위 1~20 (기본 10)

## 11. 멀티에이전트 업무 추출

### 11.1 Agent 모델 계약

Query Agent와 최종 Extraction Agent 모두 OpenAI Responses API의 Structured
Output을 사용한다. **단계마다 모델이 다르다**(2026-08-05).

| 단계 | 모델 | effort | 왜 |
|---|---|---|---|
| 검색어 생성 1~4 | `gpt-5.6-luna` (`OPENAI_PLAN_MODEL`) | `low` | 한국어 질의 1~3개를 뽑는 일이다 |
| 최종 정리 | `gpt-5.6-sol` (`OPENAI_MODEL`) | `xhigh` | 근거를 읽고 업무를 판단한다 |

같은 프롬프트로 잰 결과다 — luna 2.8초/192토큰, terra 2.9초/135토큰,
sol 53.3초/4,883토큰. Sol 은 느리고 비쌀 뿐 아니라 질의 하나가 여러 문장이
이어 붙은 덩어리로 나와 임베딩 검색에 더 나빴다. `OPENAI_SERVICE_TIER`로
처리 대기열을 고를 수 있고 기본은 `auto`다 — `priority`는 요금이 2배다.

### 11.2 Query Agent 단계

| 순서 | intent | 찾는 정보 | 검색 문서 범위 |
|---|---|---|---|
| 1 | `TASK_DISCOVERY` | 발주자가 만들라고 요구한 결과물과 그 과업 | 사용자가 선택한 기준 문서만 |
| 2 | `TASK_CORE` | 요구사항, 산출물, 완료 기준 | 검색 준비된 **팀 문서 전체** |
| 3 | `ASSIGNMENT_REQUIREMENT` | 담당 역할, 필수 기술/경험 | 〃 |
| 4 | `EXECUTION_CONDITION` | 공수, 일정, 우선순위, 의존성, 제약, 위험 | 〃 |

범위가 프로젝트에서 **팀**으로 바뀌었다(2026-08-04). 사람은 기준 문서 하나만
고르고 근거는 에이전트가 찾는데, 프로젝트로 좁히면 방금 만든 DRAFT에 묶인
문서가 기준 문서 하나뿐이라 2~4단계가 1단계와 같아진다. 두 번째 자물쇠도
`proj_id`가 아니라 `team_id`로 건다.

각 단계는 새 한국어 질의 1~3개와 `top_k`를 Structured Output으로 만든다. 이미
사용한 질의를 다시 만들 수 없고, 새 질의가 하나도 없으면 오류다. 질의는
EmbeddingGemma Worker에서 임베딩한 후 pgvector를 검색한다.

질의 생성에는 **기준 문서의 첫머리**(앞 12청크, 1,500자)를 함께 준다. 파일명만
주면 모델이 주제를 모른 채 「사업 수행 범위에 포함된 업무 영역」 같은 일반
문장을 만들고, 그런 벡터는 실제 과업이 아니라 사업관리 보일러플레이트와 가장
가깝다. 실제로 실행 과업이 한 건도 안 잡힌 적이 있다(2026-08-05).

프롬프트는 **문서 제목·파일명·날짜를 질의에 넣는 것을 금지**한다. 검색 대상이
그 문서인데 제목을 넣으면 변별력이 0이고 목차·표지가 대신 검색된다 — 근거
1·2위가 목차 줄과 제안서 양식 표였던 적이 있다.

### 11.3 근거 통합과 추출

- 검색 결과는 Chunk ID로 중복 제거한다.
- retrieval score 내림차순으로 20개를 최종 Agent에 전달하되, **기준 문서가 아닌
  문서는 최대 6자리까지만** 차지한다. 팀 문서 전체를 뒤지므로 관련 없는 문서가
  근거를 잠식할 수 있다 — 다른 사업의 감리 과업지시서가 20자리 중 8자리를
  가져가 기준 문서의 과업 Chunk를 밀어낸 적이 있다(2026-08-05).
- 근거에는 `chunk_id`·`doc_id`·`heading_path`·`text`·`intent`·`query`·유사도만
  싣는다. `vec_idx.metadata`(bbox 좌표·binary_hash·임시 파일명)는 평균 927자로
  프롬프트의 대부분을 채우면서 모델도 화면도 쓰지 않았다.
- 각 evidence에 어느 intent와 질의로 찾았는지 기록한다.
- 최종 Agent는 업무 title/description, 역할/기술, 공수/일정/우선순위,
  dependencies/constraints/risks, 완료기준/산출물, 누락 필드, 근거 Chunk ID를
  구조화한다.
- 근거가 없는 역할, 기술, 공수, 날짜는 추정하지 않고 null/빈 배열 및
  `missing_fields`로 남긴다.
- 근거 인용은 UUID가 아니라 `E1`~`E20` 짧은 번호로 받고 서버가 `chunk_id`로
  되돌린다. 36자 UUID를 옮겨 적게 했더니 하나가 어긋나 추출 전체가 실패했다.
- 모르는 번호는 **그 업무에서만** 떨어뜨리고 `warnings`에 남긴다. 근거가 하나도
  확인되지 않은 업무는 제외한다 — 근거 없는 업무를 만들지 않는다는 원칙이다.

응답에는 `tasks`, `warnings`, `evidence`, 단계별 검색 건수 `trace`, `model`,
`reasoning_effort`가 포함된다.

## 12. API 명세

모든 프로젝트 작업 API는 기존 Bearer 인증을 사용한다. RunPod 원문 다운로드만
짧게 만료되는 서명 token을 사용하므로 session 인증을 요구하지 않는다.

### 12.1 문서 목록

`GET /api/team/pipeline-documents/`

기존 응답에 다음을 추가했다.

```json
{
  "downloaded": true,
  "search_ready": true
}
```

`search_ready`는 현재 `doc.cur_revision`의 활성 Block, Chunk, Vector가 실제로
연결되어 있을 때만 true다.

### 12.2 문서 처리 시작

`POST /api/team/documents/{doc_id}/processing-runs/`

성공 `202`:

```json
{"job_id": "runpod-job-id", "status": "IN_QUEUE"}
```

원문/revision 미준비, 로컬 파일 미존재는 409다. RunPod 설정 누락은 503,
RunPod HTTP 실패는 502다.

### 12.3 문서 처리 polling

`GET /api/team/documents/{doc_id}/processing-runs/{job_id}/`

진행 중:

```json
{"job_id": "...", "status": "IN_PROGRESS"}
```

완료 및 적재:

```json
{
  "job_id": "...",
  "status": "COMPLETED",
  "ingested": {"blocks": 10, "chunks": 24, "vectors": 24}
}
```

실패 terminal 상태에는 `error`가 포함된다. 완료 polling이 반복되어도 이미 같은
결과가 적재된 경우 기존 개수를 반환한다.

### 12.4 RunPod 원문 다운로드

`GET /api/internal/runpod/documents/{doc_id}/?token={signed_token}`

- 유효 서명: 원문 stream
- 만료/위조/URL ID 불일치: 403
- 삭제/접근철회/revision 불일치/원문 없음: 외부에는 404

내부 원인을 과도하게 노출하지 않도록 없는 문서 계열은 같은 응답으로 처리한다.

### 12.5 업무 추출

`POST /api/projects/{project_id}/task-extraction-runs/`

```json
{"primary_document_id": "DC001"}
```

- 기준 문서를 팀 문서에서 찾을 수 없음: 404
- 파싱·청킹·임베딩 미완료: 409

성공하면 **`application/x-ndjson` 스트림**으로 응답한다(2026-08-05). 한 줄이 한
사건이다 — `stage`(단계 시작, 화면용 `label` 포함), `queries`(에이전트가 만든
검색어), `stage_done`(누적 근거 수), 마지막에 `result`. 몇 분이 걸리는 일이라
끝나고 한 번에 주면 진행을 보여줄 수 없다.

응답이 시작된 뒤에는 상태 코드를 바꿀 수 없으므로, 도중 실패는 마지막 줄의
`error`로 알린다. 위의 404·409 검사는 스트림을 열기 전에 끝낸다.
- 외부 설정 누락: 503
- RunPod 호출 실패: 502
- 성공: `200`과 NDJSON 스트림(마지막 줄이 구조화 업무/근거/trace)

현재 이 API는 추출 결과를 응답으로 반환하며 `task`, `task_source`, `assign_run`에
영구 저장하지 않는다. 영속화는 현재 범위에 포함되지 않았다.

## 13. frontend 변경과 현재 화면 범위

### 13.1 프로젝트 목록

빈 하드코딩 배열을 제거하고 실제 `listMyProjects` 응답을 사용한다. 「업무 분배
시작」은 **신규 프로젝트 업무 추출** 화면으로 간다 — 목록의 프로젝트는 Jira에서
온 진행 중인 것이고, 그것은 팀원 부하를 재는 재료지 업무를 새로 뽑을 대상이
아니다(2026-08-04).

프로젝트 상세에 **삭제**가 있다. 무엇이 사라지고 무엇이 남는지 모달에서 보여준
뒤 지운다 — Jira 업무는 함께 지우고, 기준 문서는 지우지 않고 팀 문서 풀로
돌려보낸다.

### 13.2 문서 관리

등록된 문서와 준비 상태를 보여준다. **등록이 검색 가능한 상태까지 간다** —
`doc` 행을 만들고, 원문을 받고, 파싱·청킹·임베딩까지 끝낸다(2026-08-05).
여기서 멈추면 「등록은 됐는데 못 쓰는 문서」가 남고 그것을 사용자가 따로
관리해야 한다. 그래서 처리할 문서를 고르는 칸이 없다.

문서마다 순차로 처리하며 진행을 보여준다. 한 건이 실패해도 나머지는 계속하고,
남은 것은 「N건 다시 처리」로 복구한다.

### 13.3 신규 프로젝트 업무 추출

사람이 고르는 것은 **기준 문서 하나**다. 근거 문서 선택은 없앴다(2026-08-04) —
무엇이 어디 적혀 있는지 미리 알아야 고를 수 있는데, 그걸 대신 찾아 주는 것이
이 기능의 목적이라 순서가 거꾸로였다.

- 프로젝트 이름(기준 문서를 고르면 파일명이 들어온다)
- radio 단일 선택 · `검색 준비 완료` / `준비 안 됨`
- 진행 모달 — 5단계 진행률, **에이전트가 만든 검색어**, 단계별 경과 시간

준비되지 않은 문서는 고를 수 없다. 임의 처리나 fake 결과를 만들지 않는다.
실행하면 DRAFT 프로젝트를 만들고 기준 문서를 묶은 뒤 추출 스트림을 받는다.

### 13.4 추출된 업무 확인

중간발표의 완료 지점이다. 업무마다 **근거가 된 원문 Chunk**를 펼쳐 볼 수 있고,
어느 문서의 어느 질의로 찾았는지가 함께 붙는다. 근거 없이 비운 필드는
`missing_fields`로 드러낸다.

결과가 아직 저장되지 않아 새로고침하면 사라진다. 그때까지의 임시 통로로
「JSON 복사」를 뒀다.

### 13.5 현재 화면에서 하지 않는 것

- 추출 결과의 `task`·`task_source` 영속화
- 업무 수정·확정 UX
- 업무 분배·추천·배정(`TaskDistributionPage` 이후는 정적 화면 그대로)

공수·담당 역할은 제안요청서에 원래 없어 `missing_fields`로 남는다. 이를 채우는
방법(팀의 Jira 이력 기반 추정 등)은 업무 분배 단계의 설계 사안이며 중간발표
범위 밖이다.

## 14. 보안 및 데이터 경계

- Google OAuth token은 기존 Django connector에서만 사용한다.
- RunPod에는 OAuth token, DB password, local storage key/path를 보내지 않는다.
- 원문 URL은 HTTPS이고 문서/revision을 묶은 만료형 서명이다.
- RunPod API key, OpenAI key, HF token은 환경변수로만 주입한다.
- RunPod Worker는 DB에 직접 쓰지 않는다.
- Django가 소유권, 프로젝트 포함관계, 삭제, 접근철회, revision을 재검증한다.
- job output도 신뢰하지 않고 ID/revision/hash/model/dimension을 검증한다.
- RunPod 다운로드 endpoint는 유효하지 않은 문서 세부 상태를 외부에 노출하지 않는다.
- `.env`와 token/key는 Git에 커밋하지 않는다.

Cloudflare Quick Tunnel은 중간발표용 연결 수단이다. 고정 도메인, Access 정책,
rate limit, WAF가 필요한 운영 배포는 별도 설계가 필요하다.

## 15. 테스트 및 검증 결과

병합 당시 다음을 확인했다.

| 검증 | 결과 |
|---|---|
| 전체 Django test suite | 141 passed |
| `manage.py check` | 통과 |
| Python `compileall` | 통과 |
| frontend `npm run build` | 통과 |
| 제품 열 표의 원본 제품 순서/값 보존 | 신규 단위 테스트 통과 |
| 비제품 표 generic row fallback | 신규 단위 테스트 통과 |
| 서명 URL 발급/검증 round trip | 신규 단위 테스트 통과 |
| HTTP 공개 URL 거부 | 신규 단위 테스트 통과 |
| RunPod payload에 storage path 미포함 | 신규 API 테스트 통과 |
| 미처리 기준 문서 409 | 신규 API 테스트 통과 |

`npm audit`은 기존 lockfile에 high severity 2건을 보고했다. 이 병합에서는
breaking dependency 변경 가능성이 있는 `npm audit fix --force`를 실행하지 않았다.

실제 외부 E2E가 미검증인 이유는 다음 값/환경이 현재 제공되지 않았기 때문이다.

- 실제 Cloudflare Tunnel URL
- 실제 RunPod Serverless Endpoint ID/API key
- CUDA가 있는 배포 Worker
- 약관 동의된 Hugging Face token
- OpenAI API key

## 16. 로컬 발표 실행 순서

1. PostgreSQL의 `vec_idx`가 비어 있는지 확인하고 768 migration을 적용한다.
2. 로컬 Django `.env`에 DB/기존 connector 설정과 RunPod/OpenAI/Cloudflare 설정을
   넣는다.
3. `cloudflared tunnel --url http://localhost:8000`을 실행한다.
4. 출력된 `https://<random>.trycloudflare.com`을 `PUBLIC_BACKEND_BASE_URL`과
   `ALLOWED_HOSTS`에 넣고 컨테이너를 **재생성**한다(`up -d --force-recreate web`).
5. RunPod Endpoint는 `runpod_worker`를 빌드 컨텍스트로 배포한다.
6. Worker 환경에 `HF_TOKEN`, `EMBEDDING_MODEL`, `EMBEDDING_DEVICE`를 넣는다.
7. Drive connector로 문서를 등록하고 기존 다운로드 API로 로컬 저장소에 받는다.
8. 문서 처리 시작 API를 호출하고 상태 API를 terminal 상태까지 polling한다.
9. `COMPLETED`와 적재 개수를 확인한 뒤 문서 목록의 `search_ready=true`를 확인한다.
10. frontend에서 프로젝트와 기준 문서를 선택하여 업무 추출을 실행한다.

상세 명령과 `.env` 예시는
`docs/Agent/Cloudflare_Tunnel_RunPod_연결_가이드.md`에 분리해 두었다.

## 17. 현재 제약과 후속 구현 필요사항

다음은 숨기지 않고 현재 상태로 명시하는 항목이다.

1. ~~**Frontend 문서 처리/polling 미연결**: 함수와 backend API는 있으나 버튼과
   progress UI가 없다.~~
   > ⚠ **2026-08-05 — 이 서술은 틀렸다.** 같은 문서 §13.2와 정면으로 충돌하고 있었다.
   > **등록 한 번이 원문 수신 → 파싱 → 청킹 → 임베딩까지 간다.** 화면이 문서마다 순차로
   > 진행하며 상태를 보여주고, 한 건이 실패해도 나머지는 계속한다. 그래서 문서 관리
   > 화면에 "처리할 문서를 고르는 칸"이 **없다** — 나누면 「등록은 됐는데 못 쓰는 문서」를
   > 사용자가 따로 관리해야 하기 때문에 의도적으로 합쳤다.
2. **업무 추출 API는 동기**: 내부에서 4단계 Query Agent, RunPod `/runsync`, 최종
   Agent를 한 HTTP 요청에서 수행한다. 시간이 길어지면 별도 job 모델이 필요하다.
3. **추출 결과 미영속화**: 현재 `task`, `task_source`, `assign_run`에 저장하지 않는다.
4. **업무 분배 화면 미연결**: 기존 정적 `TaskDistributionPage`가 실제 결과를
   렌더링하지 않는다.
5. **RunPod 결과 크기**: 문서 job output에 모든 Block/Chunk/768 Vector를 담아
   `/status`로 받는다. 큰 문서에서는 RunPod 결과 보관 제한과 응답 크기를 고려해
   외부 결과 저장소, callback 또는 batch ingest가 필요할 수 있다.
6. **RunPod 완료 결과 보관시간**: 완료 output은 제한된 시간만 조회 가능하므로
   polling 간격과 즉시 적재가 중요하다.
7. **Cloudflare Quick Tunnel 주소 변동**: 재실행할 때 URL이 바뀌므로 환경변수 수정과
   **컨테이너 재생성**이 필요하다(`restart`는 `env_file`을 다시 읽지 않는다).
8. **실환경 E2E 미완료**: 비밀값/CUDA Endpoint가 준비되어야 최종 연결 검증 가능하다.
9. **기존 demo Vector script 주의**:
   `backend/services/createDB/vec_idx_setup.py`에는 병합 전 1536차원
   `text-embedding-3-small` demo 데이터 생성 코드가 남아 있다. 신규
   EmbeddingGemma 파이프라인과 호환되지 않으므로 실행하지 말아야 하며, 운영 DB는
   schema/migration과 문서 처리 API를 사용해야 한다.
10. ~~**revision 열 길이**: `doc_block.revision`과 `vec_idx.revision`이 `VARCHAR(50)`이라
    길이 통일 migration이 필요하다.~~ **해결됨(2026-08-05 확인)** — `doc.cur_revision`
    (`DB/schema.sql:367`) · `doc_block.revision`(`:433`) · `doc_sync.revision`(`:448`) ·
    `vec_idx.revision`(`:520`) 전부 `VARCHAR(100)`이다. Drive의 `headRevisionId`가 실측
    51자라 50으로는 한 글자가 모자랐던 것을 2026-08-04에 넓혔다.
11. **표 인식 규칙**: 제품형 표는 명세대로 정확히 하나의 `Model` header를
    식별조건으로 사용한다. 다른 언어/동의어를 임의 추측하지 않고 generic row로
    처리한다. 새로운 제품표 형식 지원은 명시적 규칙 합의 후 추가해야 한다.
12. **원자 Chunk 초과**: 큰 셀/행은 자동 분해하지 않는다. 오류를 보고 표 단위
    분할 정책을 별도 합의해야 한다.
13. **운영 보안**: Quick Tunnel은 중간발표용이다. 운영은 고정 tunnel/domain,
    Access/rate limit/관측성 정책이 필요하다.
14. **의존성 취약점**: 기존 frontend lockfile audit high 2건은 별도 dependency
    upgrade 작업으로 처리해야 한다.

위 항목은 작동하는 것처럼 보이게 만드는 임시 hardcoding으로 숨기지 않았다.

## 18. 인수 확인 체크리스트

- [x] 원본 루트 구조 보존
- [x] `runpod_worker` 형제 디렉터리 추가
- [x] Django는 로컬 실행, Worker는 RunPod Serverless CUDA
- [x] Cloudflare HTTPS 서명 원문 URL
- [x] 문서 처리 async submit/polling backend API
- [x] PDF/DOCX Docling 파싱
- [x] 본문/표 중복 방지
- [x] 제품 열 표 구조 및 원본 순서 보존
- [x] 일반 표 generic row 보존
- [x] EmbeddingGemma tokenizer/문서/질의 임베딩 통일
- [x] pgvector 768차원 schema/migration
- [x] Chunk당 Vector 1개 원자 적재
- [x] revision/hash/model/dimension 검증 및 transaction rollback
- [x] 4단계 Query Agent와 pgvector 근거 검색
- [x] `gpt-5.6-sol`, reasoning `xhigh`
- [x] 미처리 문서 명시적 오류
- [x] 최소 기준 문서 선택 화면
- [x] 변경/신규 구현 문서화
- [ ] 실제 RunPod/Cloudflare/HF/OpenAI E2E
- [ ] frontend 문서 처리 polling UI
- [ ] 실제 업무 분배 화면 연동
- [ ] 추출 결과 DB 영속화
- [ ] 운영용 Tunnel/결과 저장/관측성 설계

## 19. 최종 변경 파일 목록

### 19.1 기존 파일 수정

```text
.env.example
DB/schema.sql
apps/projects/api_urls.py
apps/projects/api_views.py
apps/projects/serializers.py
backend/db/repositories.py
config/settings/base.py
frontend/src/App.tsx
frontend/src/api/opsAudit.ts
frontend/src/api/projects.ts
frontend/src/pages/OpsAuditPage/OpsAuditPage.tsx
frontend/src/pages/ProjectListPage/ProjectListPage.tsx
frontend/src/routes.ts
requirements/base.txt
services/document_pipeline/README.md
```

### 19.2 새 파일 추가

```text
DB/migrations/2026-08-04_embeddinggemma_768.sql
backend/db/document_pipeline.py
docs/Agent/Cloudflare_Tunnel_RunPod_연결_가이드.md
docs/Agent/RunPod_구조보존청킹_멀티에이전트_병합_구현명세.md
frontend/src/pages/PrimaryDocumentSelectPage/PrimaryDocumentSelectPage.module.css
frontend/src/pages/PrimaryDocumentSelectPage/PrimaryDocumentSelectPage.tsx
runpod_worker/Dockerfile
runpod_worker/README.md
runpod_worker/handler.py
runpod_worker/pipeline.py
runpod_worker/requirements.txt
services/document_pipeline/errors.py
services/document_pipeline/runpod_client.py
services/document_pipeline/signing.py
services/task_extraction/__init__.py
services/task_extraction/service.py
tests/test_document_pipeline.py
```

`services/document_pipeline/__init__.py`는 기존 구조에 있던 파일이며 이번 병합에서
내용을 변경하지 않았다. 최종 파일 목록은 기존 프로젝트 대비 실제 생성/수정
범위를 구분한 것이다.
