# AWS 구성 현황 — 한 장으로 보는 지금 상태

> **이 문서의 역할 — 「지금 어떻게 되어 있나」.**
>
> 나머지 AWS 문서는 절차서다. 이 문서는 **결과**만 적는다.
>
> | 문서 | 무엇 |
> |---|---|
> | [[AWS_1단계_공유환경_구축]] | RDS·S3·EC2 를 처음 만드는 작업 지시서 |
> | [[AWS_이전_매뉴얼]] | 로컬에서 EC2 로 옮기는 절차 |
> | [[2026-08-14_AWS_배포_후_팀_공지]] | 배포 후 팀원이 알아야 할 변화 |
> | **이 문서** | **현재 구성값** |
>
> 기준일 2026-08-14 · 리전 `ap-northeast-2`(서울) · 실서버 응답으로 대조 완료

---

## 1. 전체 그림

```text
                  브라우저
                     │ HTTPS
                     ▼
   ┌──────────────────────────────────────────────┐
   │ EC2  skn29-2team-app   t3.micro   gp3 30GiB  │
   │ 탄력적 IP 43.200.114.119                      │
   │                                               │
   │  Caddy (80·443)  ── TLS 종단 · Host 로 분기    │
   │    ├─ halil-ai.site      → frontend:5173      │
   │    ├─ www / app          → apex 로 301         │
   │    ├─ api.halil-ai.site  → web:8000           │
   │    └─ mcp.halil-ai.site  → dev-mcp:9000       │
   │                                               │
   │  web       Django 5.2 + DRF   127.0.0.1:8000  │
   │  frontend  React 정적 빌드     127.0.0.1:5173  │
   │  dev-mcp   시연용 MCP (오버레이로 별도 기동)     │
   │                                               │
   │  volume  document_storage → /var/lib/halil/documents
   │  volume  caddy_data       → 발급받은 인증서
   └───────────┬───────────────────────┬───────────┘
               │ 5432                  │ HTTPS
               ▼                       ▼
   RDS PostgreSQL 18.3          S3  skn29-final-2team-files-nm0p
   db.t4g.micro · gp3 20GiB     (버저닝 켬)
   + pgvector
```

**인터넷에 열려 있는 것은 Caddy 의 80·443 뿐이다.** `web` 과 `frontend` 는
`127.0.0.1` 에만 묶여 있어, 서버 안에서 `curl localhost:8000` 으로 진단은
되지만 밖에서는 보이지 않는다.

---

## 2. 도메인

다섯 이름이 **전부 같은 IP** 를 가리킨다. 가르는 것은 DNS 가 아니라 Caddy 의
Host 헤더다.

| 이름 | 응답 | 향하는 곳 |
|---|---|---|
| `halil-ai.site` | 200 | frontend — **여기가 본 주소다** |
| `www.halil-ai.site` | 301 | → `halil-ai.site` |
| `app.halil-ai.site` | 301 | → `halil-ai.site` |
| `api.halil-ai.site` | 200 | web (Django) |
| `mcp.halil-ai.site` | dev-mcp | 오버레이를 안 띄웠으면 502 — 고장 아님 |

**apex 를 본 주소로 정한 이유**(2026-08-14): 발표 중 주소창에 `halil-ai.site`
가 그대로 보여야 한다. apex 는 CNAME 을 못 걸지만 탄력적 IP 가 고정이라 A
레코드로 바로 찍으면 된다. `www`·`app` 을 리디렉트로 보낸 것은 앱이 두 주소로
열리면 쿠키·CORS 를 두 벌 관리하게 되기 때문이다.

인증서는 Let's Encrypt 자동 발급·갱신이다. 전제가 둘이다 — **A 레코드가 이 IP
를 가리킬 것**, **보안 그룹에 80 과 443 이 둘 다 열려 있을 것**(80 은 HTTP-01
검증용이라 닫히면 발급 자체가 실패한다).

---

## 3. 자원별 값

### EC2

| | |
|---|---|
| 이름 / 인스턴스 | `skn29-2team-app` / `i-0ebfec705a8745351` |
| 유형 | t3.micro (프리 티어) |
| 디스크 | gp3 **30 GiB** — 기본 8GiB 로 두면 Docker 이미지로 금방 찬다 |
| 탄력적 IP | `43.200.114.119` |
| 키 페어 | `skn29-2team-key` (rsa) |
| 접속 | `ssh -i skn29-2team-key.pem ubuntu@43.200.114.119` |
| 저장소 경로 | `~/SKN29-Final-2Team` |

**메모리가 909MB + swap 2G 다.** 그래서 배포 스크립트가
`COMPOSE_PARALLEL_LIMIT=1` 로 순차 빌드한다 — 병렬로 돌리면 버겁다.

### RDS

| | |
|---|---|
| 식별자 | `skn29-final-2team` |
| 엔진 | **PostgreSQL 18.3** + pgvector |
| 인스턴스 | db.t4g.micro · gp3 **20 GiB** · 자동 조정 끔 · 단일 AZ |
| DB 이름 | `project_copilot` |
| 마스터 사용자 | `project_copilot` — 로컬과 같게 뒀다. `DATABASE_URL` 만 갈아끼우면 된다 |
| 접속 허용 | EC2 보안 그룹 + 팀원 |

로컬 `db` 컨테이너는 `pgvector:pg17` 이라 메이저가 다르다. 이 프로젝트가 쓰는
기능 범위에서는 문제되지 않아 맞추지 않기로 했다.

### S3

| | |
|---|---|
| 버킷 | `skn29-final-2team-files-nm0p` |
| 버저닝 | 켬 |
| 용도 | Drive 에서 받은 원문 문서 |

⚠ **다만 EC2 의 원문 저장은 지금 S3 가 아니라 도커 볼륨이다**
(`document_storage` → `/var/lib/halil/documents`). 이 줄과 볼륨이 없으면 원문이
컨테이너 쓰기 레이어에 쌓여 `up --build` 때마다 사라진다.

### 보안 그룹

```text
브라우저 ── 80, 443 ──▶ EC2 SG ── (컨테이너 내부) ──▶ 8000, 5173
EC2 SG   ── 5432     ──▶ RDS SG
```

| 대상 | 포트 | 허용 |
|---|---|---|
| EC2 | 22 | 팀원 |
| EC2 | 80, 443 | 전체 (인증서 발급·서비스) |
| RDS | 5432 | EC2 보안 그룹 + 팀원 |

---

## 4. 배포

`main` 에 커밋이 들어오면 **자동으로 시연 서버에 나간다.**

```text
push → GitHub Actions(.github/workflows/deploy.yml)
     → SSH → infra/deploy.sh
       1. git fetch + merge --ff-only origin/main
       2. COMPOSE_PARALLEL_LIMIT=1 up -d --build web frontend caddy
       3. dev-mcp 가 떠 있으면 재생성
       4. 헬스 체크 (X-Forwarded-Proto: https 를 붙여서)
       5. dangling 이미지 정리
     → 도메인으로 다시 확인 (api /health, apex 200)
```

**필요한 저장소 시크릿** — Settings > Secrets and variables > Actions

| 이름 | 값 |
|---|---|
| `EC2_HOST` | `43.200.114.119` |
| `EC2_USER` | `ubuntu` |
| `EC2_SSH_KEY` | 배포 전용 개인키 전문 |

⚠ 팀원 접속용 `.pem` 을 그대로 넣지 않는다. 배포 전용 키를 따로 두면 나중에 그
키만 서버의 `authorized_keys` 에서 지워 회수할 수 있다.

⚠ **배포하면 `web` 컨테이너가 재생성돼 몇 초 끊긴다. 시연·발표 중에는 `main` 에
푸시하지 말 것.**

---

## 5. 밟기 쉬운 자리

여기 적힌 것은 전부 실제로 한 번씩 겪은 것이다.

| 증상 | 원인 | 처치 |
|---|---|---|
| 컨테이너가 재시작만 반복 | Caddyfile 의 전역 `email` 에 빈 환경변수가 들어가 **인자 없는 `email` 로 전개돼 파싱 실패**. web·frontend 는 200 이라 안쪽만 보면 정상으로 보인다 | 전역 블록을 두지 않는다. 상태는 안쪽 응답이 아니라 **재시작 횟수**로 본다 |
| `ERR_TOO_MANY_REDIRECTS` | Caddy 가 TLS 를 끝내고 평문으로 넘기는데 Django 가 http 로 보고 다시 https 로 되돌린다 | `SECURE_PROXY_SSL_HEADER` (production.py 에 들어 있다) |
| 헬스 체크가 301 | `SECURE_SSL_REDIRECT` 가 켜져 있어 헤더 없이 http 로 부르면 301 | `-H 'X-Forwarded-Proto: https'` 를 붙인다 |
| API 주소를 바꿨는데 화면이 옛 주소를 봄 | Vite 가 `VITE_API_BASE_URL` 을 **빌드 시점에 굽는다.** 런타임 environment 로는 안 바뀐다 | `up --build` 로 다시 빌드 |
| 배포 후 MCP 서버가 사라짐 | 오버레이를 빼고 compose 를 돌리면 `skn29-dev-mcp` 가 고아로 보이고, 그 경고를 보고 `--remove-orphans` 를 붙이면 지워진다 | `deploy.sh` 가 떠 있는지 보고 파일 목록에 넣는다 |
| CI 가 10초 만에 인증 실패 | Windows 클립보드를 거친 키가 CRLF 가 됐다. OpenSSH 가 «invalid format» 으로 거절한다 | 워크플로가 `tr -d '\r'` 로 걷어낸다 |
| `database ... does not exist` | RDS 생성 때 **초기 데이터베이스 이름**을 비워 뒀다 | `psql .../postgres` 로 붙어 `CREATE DATABASE project_copilot;` |
| 로컬에서 테스트가 42건 503 | `DATABASE_URL` 호스트가 컨테이너 이름 `db` 라 호스트에서 안 풀린다 | 컨테이너 안에서 돌리거나 `localhost` 로 바꿔 돌린다 |

---

## 6. 상태 확인 명령

```bash
# 밖에서
curl -s https://api.halil-ai.site/api/health/
curl -s -o /dev/null -w '%{http_code}\n' https://halil-ai.site

# 서버에서
ssh -i skn29-2team-key.pem ubuntu@43.200.114.119
cd ~/SKN29-Final-2Team
docker compose -f infra/docker/docker-compose.aws.yml ps
docker compose -f infra/docker/docker-compose.aws.yml logs --tail 50 caddy
```

정상이면 헬스 응답이 이렇다.

```json
{"status":"ok","service":"ai-project-operation-copilot",
 "database":{"status":"ok","people":"ready","vector":"ready"}}
```
