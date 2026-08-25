# 로컬 Django와 RunPod Serverless 연결

> **이 문서는 로컬 개발용이다.** 노트북에는 공인 https 주소가 없어서 터널이
> 필요하다.
>
> **AWS 시연 환경은 이 절차를 쓰지 않는다**(2026-08-14~). Django 가
> `https://api.halil-ai.site` 에 떠 있어 RunPod 이 바로 닿는다 —
> `PUBLIC_BACKEND_BASE_URL` 이 고정이고 터널도, 주소를 다시 넣는 일도 없다.
> `docs/설계 및 구현/3_중간발표 이후/개발환경/AWS_이전_매뉴얼.md` §1 참고.

## 경계

- Django, React, PostgreSQL, 문서 원문 저장소는 로컬에서 실행한다.
- Docling, 구조 보존 청킹, EmbeddingGemma는 RunPod CUDA Worker에서 실행한다.
- RunPod에는 로컬 경로나 DB 자격증명을 전달하지 않는다.
- Cloudflare Tunnel은 만료되는 서명 문서 다운로드 URL에만 사용한다.

## 1. 로컬 서버

```powershell
docker compose -f infra/docker/docker-compose.yml up --build
```

RunPod가 접근할 주소의 Django `ALLOWED_HOSTS`에 Cloudflare hostname을 추가한다.

## 2. Quick Tunnel

노트북에서 개발할 때는 Cloudflare `cloudflared`를 설치한 뒤:

```powershell
cloudflared tunnel --url http://localhost:8000
```

출력된 `https://<random>.trycloudflare.com` 주소를 `.env`에 넣는다.

```dotenv
PUBLIC_BACKEND_BASE_URL=https://<random>.trycloudflare.com
```

Quick Tunnel 주소는 실행할 때마다 바뀐다. 바뀌면 `.env`의 `PUBLIC_BACKEND_BASE_URL`과 `ALLOWED_HOSTS`를 고친 뒤 **컨테이너를 재생성**한다.

```bash
docker compose -f infra/docker/docker-compose.yml up -d --force-recreate web
```

> ⚠ **2026-08-05 정정 — `restart`로는 반영되지 않는다.** 이 줄은 "주소를 바꾼 후 Django를 다시 시작한다"였다. `docker compose restart`는 컨테이너를 그대로 두고 프로세스만 다시 띄우기 때문에 `env_file`을 다시 읽지 않는다. 바뀐 주소가 반영되지 않은 채 RunPod이 옛 주소로 원문을 받으러 가고, 시연 중에 원인을 찾기 어려운 실패가 된다.

## 3. RunPod 설정

로컬 Django `.env`:

```dotenv
RUNPOD_API_KEY=
RUNPOD_ENDPOINT_ID=
PUBLIC_BACKEND_BASE_URL=
RUNPOD_JOB_TTL_MS=3600000
RUNPOD_EXECUTION_TIMEOUT_MS=1800000
DOCUMENT_DOWNLOAD_TOKEN_MAX_AGE_SECONDS=900
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.6-sol
# 검색어 생성 전용. 같은 일에 Sol 은 Luna 의 수백 배가 든다(실측)
OPENAI_PLAN_MODEL=gpt-5.6-luna
OPENAI_REASONING_EFFORT=xhigh
EMBEDDING_MODEL=google/embeddinggemma-300m
EMBEDDING_DEVICE=cuda
CHUNKING_MAX_TOKENS=512
CHUNKING_MERGE_PEERS=true
```

RunPod Worker 환경변수:

```dotenv
HF_TOKEN=
EMBEDDING_MODEL=google/embeddinggemma-300m
EMBEDDING_DEVICE=cuda
```

`HF_TOKEN`은 Google EmbeddingGemma 사용 약관에 동의한 Hugging Face 계정의
토큰이어야 한다. 토큰·RunPod key·OpenAI key를 Git에 저장하지 않는다.

## 4. 비동기 계약

1. Django가 `/run`에 작업을 제출하고 job id를 반환한다.
2. 클라이언트가 Django 상태 API를 polling한다.
3. Django가 RunPod `/status/{job_id}`를 조회한다.
4. `COMPLETED`일 때만 결과 전체를 하나의 DB 트랜잭션으로 적재한다.
5. Block, Chunk, 768차원 Vector 중 하나라도 잘못되면 전체 적재를 rollback한다.

RunPod 비동기 결과는 제한된 시간만 보관되므로 완료 결과는 즉시 조회한다.
