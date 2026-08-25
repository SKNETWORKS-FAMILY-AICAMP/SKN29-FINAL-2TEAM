# AWS 이전 매뉴얼 — 파이널 프로젝트 최소 구조

> 범위: 부트캠프 파이널 프로젝트의 통합 테스트·시연 환경  
> 기준: 수업에서 다룬 EC2 + RDS + S3 + Docker Compose 구성

## 1. 최종 AWS 구조

```text
사용자 브라우저
      │
      ▼
EC2 (Docker Compose)
├─ frontend : React 화면
└─ web      : Django API
      │                  │
      ▼                  ▼
RDS PostgreSQL       S3
+ pgvector           ├─ 프로젝트 원문 문서
                     └─ Django 정적/업로드 파일
```

| AWS 서비스 | 이번 프로젝트 역할 | 사용 이유 |
|---|---|---|
| EC2 | React·Django 컨테이너 실행 | 현재 로컬 Docker Compose 구성을 가장 적게 바꿔서 배포 가능 |
| RDS PostgreSQL | People DB, 프로젝트, Snapshot, 문서 메타데이터, 임베딩 저장 | DB를 EC2와 분리해 데이터가 서버 컨테이너와 함께 사라지지 않도록 관리 |
| S3 | Drive에서 수집한 원문 문서, Django 정적/업로드 파일 저장 | 문서 원문을 EC2 디스크와 분리하고 파일 URL/저장 키를 일관되게 관리 |

이번 범위에서는 ECS, ALB, CloudFront, SQS, 별도 Vector DB, Terraform은 사용하지 않는다.

### 배포 — `main` 에 들어오면 자동으로 나간다 (2026-08-14 추가)

처음에는 CI/CD 도 범위 밖으로 뒀는데, 서버가 열리고 나니 **손으로 `git pull` 하고
`up --build` 하는 일이 반복**돼서 붙였다. ECS 는 여전히 범위 밖이다 — 그쪽으로
가려면 ECR·task definition·클러스터·ALB 를 새로 만들고 Caddy 를 걷어내야 한다.

| 무엇 | 어디 |
|---|---|
| 트리거 | `.github/workflows/deploy.yml` — `main` push + 수동 실행 |
| 실제 로직 | **`infra/deploy.sh`** — 저장소에 둬서 리뷰되고, 서버에서 손으로도 돌아간다 |
| 접속 | 배포 전용 SSH 키. 팀원 `.pem` 과 별개라 이것만 회수할 수 있다 |

저장소 시크릿 셋이 필요하다: `EC2_HOST` · `EC2_USER` · `EC2_SSH_KEY`.

**배포하면 `web` 컨테이너가 재생성돼 몇 초 끊긴다.** 시연 중에는 `main` 에
푸시하지 않는다. 급하면 Actions 탭에서 워크플로를 잠시 비활성화한다.

`deploy.sh` 가 겪은 것을 두 개 담고 있다 — 헬스 체크에 `X-Forwarded-Proto` 를
붙이지 않으면 `SECURE_SSL_REDIRECT` 때문에 301 이 와서 앱이 죽은 것처럼 보이고,
`dev-mcp` 오버레이를 compose 파일 목록에서 빼면 그 컨테이너가 고아로 잡혀
`--remove-orphans` 한 번에 시연용 MCP 서버가 사라진다.

### 결정 — 도메인은 `halil-ai.site` (2026-08-13)

**공인 IP + HTTP 로는 막히는 것이 셋이다.** 도메인과 https 를 붙여 한 번에 푼다.

| 막히는 것 | 왜 |
|---|---|
| **Google OAuth** | 공인 IP 에 대한 `http` redirect URI 를 Google 이 받지 않는다. 2단계의 관문(1단계 §20-2)이 사실은 이것이다 |
| **MCP 서버 등록** | `services/mcp/security.py` 가 https 아닌 주소를 거절한다(SSRF 1차 방어선) |
| **쿠키·혼합 콘텐츠** | 화면이 https 인데 API 가 http 면 브라우저가 막는다 |

붙이는 방법은 셋이다.

1. **가비아(또는 산 곳) DNS + EC2 에서 TLS 종료** ← **기본으로 삼는다**
   A 레코드 하나를 탄력적 IP 로 찍고, EC2 에 Caddy 컨테이너를 얹어 Let's Encrypt
   인증서를 자동 발급·갱신한다. **탄력적 IP 가 이미 고정돼 있어서 DNS 는 A 레코드
   하나면 끝이고**, 프론트·API·MCP 를 서브도메인으로 한 번에 받는다. 요청 경로에
   남의 서비스가 끼지 않는다. 인바운드 80·443 을 연다.
2. **Cloudflare 프록시 + 이름 있는 터널** — 인증서 관리가 없고 인바운드 포트를
   안 열어도 된다. 다만 **네임서버를 Cloudflare 로 옮겨야 한다** — 이름 있는
   터널이 `<uuid>.cfargotunnel.com` 으로 가는 CNAME 을 요구하는데 그건 Cloudflare
   DNS 에서만 된다. 공인 IP 가 없거나 포트를 못 여는 환경이면 이쪽이 낫다.
3. **ACM + ALB** — AWS 답지만 §1 에서 범위 밖으로 정한 구성이다.

> 처음에는 2번을 먼저 적었다(이미 `cloudflared` 를 쓰고 있으니 배울 것이 없다는
> 이유였다). **탄력적 IP 가 고정돼 있다는 사실이 그보다 크다** — 그 경우 NS 를
> 옮길 이유가 없다(2026-08-13 정정).

`halil.site` 는 레지스트리 유보어라 못 샀고, 하이픈을 넣어 피했다. 하이픈은 DNS·TLS·
OAuth 어디서도 문제가 없고, 이름에 `ai` 가 들어가 발표에서 무엇을 하는 서비스인지
바로 읽힌다.

#### 서브도메인 계획

| 이름 | 무엇 |
|---|---|
| **`halil-ai.site` (apex)** | **프론트(React) — 본 주소다.** 발표 중 주소창에 이대로 보인다 |
| `www` · `app.halil-ai.site` | apex 로 301. 앱이 두 주소로 열리면 쿠키·CORS 를 두 벌 관리하게 된다 |
| `api.halil-ai.site` | Django API |
| `mcp.halil-ai.site` | MCP 시연 서버 — **빠른 터널의 바뀌는 주소를 여기로 고정한다** |

apex 는 CNAME 을 걸 수 없다는 제약이 있는데, **탄력적 IP 가 고정이라 A 레코드로
바로 찍으면 된다.** 이것도 §1 이 클라우드플레어 터널 대신 이 방법을 고른 이유에
들어간다.

#### 도메인이 붙으면 바꿀 것

```
ALLOWED_HOSTS=halil-ai.site,api.halil-ai.site
CORS_ALLOWED_ORIGINS=https://halil-ai.site
CSRF_TRUSTED_ORIGINS=https://halil-ai.site,https://api.halil-ai.site
FRONTEND_BASE_URL=https://halil-ai.site
VITE_API_BASE_URL=https://api.halil-ai.site/api
GOOGLE_DRIVE_REDIRECT_URI=https://api.halil-ai.site/api/connectors/google-drive/callback/
JIRA_REDIRECT_URI=https://api.halil-ai.site/api/connectors/jira/callback/
PUBLIC_BACKEND_BASE_URL=https://api.halil-ai.site
```

그리고 `SECURE_SSL_REDIRECT=True`(§4).

#### 도메인이 푸는 것이 하나 더 있다 — RunPod 터널

마지막 줄 `PUBLIC_BACKEND_BASE_URL` 은 **RunPod 워커가 원문을 받으러 오는 주소**다
(`config/settings/base.py`, `.env.example` §문서 파싱·임베딩). 지금은 여기에
`cloudflared` 빠른 터널 주소가 들어가 있고, **터널을 다시 띄울 때마다 주소가 바뀐다.**
`docs/설계 및 구현/3_중간발표 이후/Agent/Cloudflare_Tunnel_RunPod_연결_가이드.md` 는 그때마다 `.env` 와
`ALLOWED_HOSTS` 를 고치고 **컨테이너를 재생성**하라고 적어 두었다(`restart` 로는
반영되지 않는다 — 2026-08-05 에 겪은 것).

**도메인이 붙으면 이 값이 고정된다.** 파싱·임베딩은 이번 프로젝트의 와우팩터인데,
그 경로가 시연 중에 조용히 끊기는 실패 모드가 통째로 사라진다. 위 다섯 줄보다
이쪽이 덜 눈에 띄지만 값은 더 크다.

**Google·Atlassian 콘솔에 위 두 redirect URI 를 등록하는 것이 1단계 §20 이 말한
관문이다.** 도메인이 생겼으므로 이제 EC2 를 켜기 전에도 할 수 있다 — 시연 직전에
몰아서 하지 말 것.

##### 결정 — Jira 는 로컬을 포기했다 (2026-08-14)

**Google 과 Atlassian 이 다르다.** Google 은 redirect URI 를 여러 개 등록해 둘 수
있어서 localhost 와 AWS 가 공존한다. **Atlassian 3LO 는 앱마다 Callback URL 이
하나뿐이다.**

그래서 셋 중에 골라야 했다 — ① AWS 로 바꾸고 로컬을 포기 ② 앱을 하나 더 만들어
분리 ③ 시연 직전에 바꾸기. **①을 골랐다**(localhost 항목을 지우고 AWS 주소를 넣음).

| 결과 | |
|---|---|
| `JIRA_CLIENT_ID`·`SECRET` | 로컬과 AWS 가 **같은 값** — 그대로 복사하면 된다 |
| 로컬에서 Jira 연결 | **안 된다.** `redirect_uri_mismatch` 가 난다 |

**로컬에서 안 되는 것이 고장이 아니라는 걸 팀원이 알아야 한다.** 필요해지면
개발자 콘솔에 앱을 하나 더 만들어 로컬 전용으로 쓴다(②로 옮겨 가는 것).

#### 도메인을 산 뒤 실제로 남은 일 (2026-08-14 콘솔 확인)

**A 레코드에 넣을 값은 이미 정해져 있다 — `43.200.114.119`.** 탄력적 IP 라 EC2 를
껐다 켜도 안 바뀐다. 세 서브도메인을 전부 이 하나로 찍는다(Caddy 가 Host 로 가른다).

| 이름 | 유형 | 값 |
|---|---|---|
| `@` (또는 비워 둠) | A | `43.200.114.119` |
| `www` | A | `43.200.114.119` |
| `app` | A | `43.200.114.119` |
| `api` | A | `43.200.114.119` |
| `mcp` | A | `43.200.114.119` |

**다섯 줄 다 같은 IP 다.** Caddy 가 Host 헤더로 가른다 — apex 가 앱을 서빙하고
`www`·`app` 은 apex 로 넘긴다. 가비아는 apex 를 `@` 로 쓰거나 이름 칸을 비워 둔다.

**서버가 꺼져 있어도 등록은 된다.** 전파를 미리 돌려 둘 수 있으니 먼저 넣어도 손해가 없다.

⚠ **다만 EC2 보안 그룹에 80·443 이 없다.** 인바운드가 SSH 22 하나뿐이라
(`skn29-ec2-sg` / `sg-008fbec82cd5026e0`, 2026-08-14 확인) **지금 Caddy 를 올려도
Let's Encrypt 가 80 번으로 검증을 못 해 인증서 발급이 실패한다.** EC2 를 켜는
날 같이 연다 — 1단계 §17 에 반영해 뒀다.

## 2. 컨테이너 구성 변경

현재 로컬 Compose의 세 서비스 중 AWS에서는 `db` 컨테이너를 제거한다.

| 현재 로컬 | AWS 배포 | 변경 내용 |
|---|---|---|
| `frontend` | EC2의 React 컨테이너 | 유지 |
| `web` | EC2의 Django 컨테이너 | 유지. DB 주소만 RDS endpoint로 변경 |
| `db` | RDS PostgreSQL + pgvector | EC2에서 실행하지 않음 |
| (없음) | `caddy` | 80·443 에서 TLS 종료. 세 호스트를 가른다 |
| (없음) | `dev-mcp` | MCP 시연용. 기본 compose 에 없고 파일을 얹어 띄운다. **`mcp-tunnel` 은 AWS 에서 안 쓴다** |

```text
로컬 개발
frontend + web + db(Docker)

AWS 시연
EC2: caddy + frontend + web(Docker)
RDS: PostgreSQL + pgvector
S3: 원문 문서 + 정적/업로드 파일
```

### MCP 시연 서버도 함께 간다 (2026-08-13 추가)

「MCP 서버를 등록해서 실제로 쓰는」 시연을 하려면 붙일 서버가 하나 필요하다.
`infra/dev-mcp/` 의 시험용 서버를 EC2 에도 같이 올린다
(`infra/docker/docker-compose.dev-mcp.yml`). **터널은 빼고 `dev-mcp` 만** 올린다 —
Caddy 가 `mcp.halil-ai.site` 를 받아 넘긴다.

`services/mcp/security.py` 가 **https 가 아닌 주소를 거절**한다
(`security.py` 의 scheme 검사 — SSRF 1차 방어선이라 푸는 것은 답이 아니다).
그래서 붙일 주소가 반드시 https 여야 한다.

| 방법 | 주소 | 비용 |
|---|---|---|
| **가비아 DNS + EC2 Caddy** ← §1 이 정한 채택안 | **고정** (`mcp.halil-ai.site`) | 도메인 + 인바운드 80·443 개방 |
| cloudflared 빠른 터널 | 재시작마다 **바뀐다** | 없음. 시연 직전 재등록 필요 |
| cloudflared 이름 있는 터널 | 고정 | Cloudflare 계정 + 네임서버 이전 |
| 도메인 + ACM + ALB | 고정 | 이 프로젝트 범위 밖(§1) |

**빠른 터널은 임시방편이다.** 해제 조건은 도메인 구입이 아니라
**80·443 개방 + 인증서 발급 완료**다(§1 「도메인을 산 뒤 실제로 남은 일」).
그 전까지 시연한다면 **직전에 주소를 확인하고 화면에서 「수정」으로 갱신**하는
절차를 체크리스트에 넣는다. 붙은 뒤에는 이 절차 자체가 없어진다.

## 3. 보안 그룹 연결 규칙

```text
브라우저 ── 80, 443 ──▶ EC2 보안 그룹 ── (컨테이너 내부) ──▶ 8000, 5173
EC2 보안 그룹 ── 5432 ──▶ RDS 보안 그룹
```

| 대상 | 포트 | 허용 대상 |
|---|---|---|
| EC2 | 22 | 팀원 공인 IP만 허용 |
| EC2 | 80 | 전체 — Let's Encrypt HTTP-01 검증에 필요하다 |
| EC2 | 443 | 전체 |
| RDS | 5432 | EC2 보안 그룹 + 팀원(아래) |

**8000·5173 은 호스트로 열지 않는다.** Caddy 가 80·443 에서 TLS 를 끝내고
컨테이너로 넘긴다(1단계 §17).

⚠ **RDS 5432 는 지금 `0.0.0.0/0` 이다. 실수가 아니라 결정이다** — 팀원들이
무선이라 IP 가 고정되지 않아 허용목록이 현실적이지 않았다. 근거와 해제 조건은
`AWS_1단계_공유환경_구축.md` 의 「`0.0.0.0/0` 은 실수가 아니다」에 있다.

## 4. RDS 설정

| 항목 | 설정 기준 |
|---|---|
| 엔진 | PostgreSQL |
| DB 이름 | `project_copilot` |
| 접속 | EC2 보안 그룹만 허용 |
| 연결 정보 | `.env`의 `DATABASE_URL`로 주입 |
| Vector 검색 | RDS에서 `vector` 확장 사용 가능 여부 확인 후 활성화 |

RDS 생성 후 다음을 확인한다.

```sql
SELECT name, default_version, installed_version
FROM pg_available_extensions
WHERE name = 'vector';

CREATE EXTENSION IF NOT EXISTS vector;
```

EC2의 `.env` 예시는 다음과 같다. RDS endpoint와 실제 계정 정보로 교체한다.

```text
DJANGO_SETTINGS_MODULE=config.settings.production
DATABASE_URL=postgresql://<DB_USER>:<DB_PASSWORD>@<RDS_ENDPOINT>:5432/project_copilot?sslmode=require
ALLOWED_HOSTS=halil-ai.site,api.halil-ai.site
CORS_ALLOWED_ORIGINS=https://halil-ai.site
CSRF_TRUSTED_ORIGINS=https://halil-ai.site,https://api.halil-ai.site
FRONTEND_BASE_URL=https://halil-ai.site
VITE_API_BASE_URL=https://api.halil-ai.site/api
PUBLIC_BACKEND_BASE_URL=https://api.halil-ai.site
SECURE_SSL_REDIRECT=True
```

#### ⚠ 첫 줄이 제일 중요하다

`config/wsgi.py` 와 `manage.py` 는 `DJANGO_SETTINGS_MODULE` 의 기본값을
**`config.settings.local`** 로 잡는다(`setdefault`). 그리고 `.env.example` 첫 줄도
`config.settings.local` 이다. **`.env` 에서 명시적으로 바꾸지 않으면 EC2 도
local 설정으로 뜬다.**

그러면 이렇게 된다:

- `config/settings/local.py` 가 **`DEBUG = True` 를 하드코딩**한다 — `.env` 의
  `DEBUG=False` 는 무시된다. 공개 서버가 디버그 화면을 그대로 보여준다.
- `ALLOWED_HOSTS` 가 `localhost,127.0.0.1` 이라 브라우저가 도메인으로 붙으면
  **400 DisallowedHost** 가 난다.
- `SECURE_SSL_REDIRECT` 를 읽는 곳은 `config/settings/production.py` 뿐이라
  **`True` 로 바꿔도 아무 일도 일어나지 않는다.**

`curl http://localhost:8000/api/health/` 는 이 상태에서도 통과한다(§7 8단계).
**증상이 늦게 드러나므로 배포 직후 반드시 도메인으로 한 번 열어 볼 것.**

S3 값(`AWS_STORAGE_BUCKET_NAME` 등)은 일부러 뺐다 — 아직 읽는 코드가 없다.
`.env.example` 의 S3 블록 경고와 §6 을 볼 것.

RDS 생성 뒤에는 `DB/schema.sql`과 People 목업 SQL을 직접 적용한다. Django
Migration은 사용하지 않는다.

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f DB/schema.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f DB/peopleDB/peopledb_mock.sql
```

RDS PostgreSQL에서 지원하는 확장과 버전은 생성 시점에 [AWS RDS PostgreSQL 확장 목록](https://docs.aws.amazon.com/AmazonRDS/latest/PostgreSQLReleaseNotes/postgresql-extensions.html)으로 다시 확인한다.

## 5. S3 설정

**버킷은 이미 있다 — `skn29-final-2team-files-nm0p`** (1단계 Part C 에서 만들었고
`.env.example` 에 그 값이 들어 있다). 새로 만들지 말 것. 비공개·버저닝 활성화 상태다.

| 버킷 | 저장 항목 |
|---|---|
| `skn29-final-2team-files-nm0p` | Google Drive 원문 PDF/DOCX, Django 정적 파일, 향후 업로드 파일 |

**키 구조는 코드가 이미 정해 놨다.** `backend/services/storage.py` 의 `build_key()` 를
따른다 — 여기 적혀 있던 `documents/{project_id}/...` 안은 채택하지 않았다.

```text
{team_id}/{doc_id}.<확장자>      원문
avatar/{account_id}.<확장자>     프로필 사진
```

> **왜 프로젝트가 아니라 팀인가**(`storage.py` 주석, 2026-08-04): 문서는 등록
> 시점에 어느 프로젝트 것인지 모른다. 나중에 지정된다고 파일을 옮길 수는 없다.
> `DB/schema.sql` 의 `doc.proj_id` 가 NULL 을 허용하는 것도 같은 이유다.

문서 메타데이터에 지금 있는 것은 셋뿐이다 — `storage_key`, `src_file_id`(원본
Drive 파일 ID), `src_modified_at`(원본 수정 시각). **`bucket` 과 `version_id` 는
`doc` 테이블에 컬럼이 없다.** S3 로 옮기면서 버저닝 추적까지 하려면 `DB/schema.sql`
에 컬럼을 더하고 `DocumentRepository.mark_stored` 시그니처도 함께 늘려야 한다 —
§8 의 미래 항목이지 지금 있는 것이 아니다.

## 6. EC2와 S3 연결

EC2에는 IAM Role을 연결한다. Access Key를 코드나 `.env`에 직접 넣지 않는다.

| IAM Role | 최소 권한 |
|---|---|
| `skn29-final-2team-ec2-role` | 프로젝트 S3 버킷의 객체 조회·업로드·삭제에 필요한 범위 |

개발·시연 단계에서는 수업에서 사용한 방식처럼 EC2 IAM Role을 연결하고, Django에서는 `boto3`, `django-storages`를 이용한다. 단, 권한은 전체 S3가 아닌 프로젝트 버킷으로 제한한다.

```python
# config/settings/production.py에 반영할 S3 설정 방향
INSTALLED_APPS += ["storages"]

AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME")
AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="ap-northeast-2")

STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
    },
    "staticfiles": {
        "BACKEND": "storages.backends.s3.S3StaticStorage",
    },
}
```

**의존성은 이미 있다** — `requirements/production.txt` 에 `boto3` 와
`django-storages[s3]` 가 들어 있고 Dockerfile 이 그 파일로 설치한다. 아직 없는
것은 배선 둘이다: `INSTALLED_APPS` 에 `storages` 추가 + 위 `STORAGES` 설정,
그리고 `backend/services/storage.py` 의 S3 어댑터(지금은 로컬 디스크 전용).

## 7. EC2 배포 순서

**1~4 는 1단계에서 끝났다**(`AWS_1단계_공유환경_구축.md`). 5번부터가 남은 일이다.

1. ~~Ubuntu EC2 생성, Docker 설치~~ ✅
2. ~~RDS PostgreSQL 생성, 보안 그룹 연결~~ ✅
3. RDS에 `vector` 확장이 사용 가능한지 확인 — **RDS 가 꺼져 있어 아직 못 했다**
4. ~~S3 버킷 생성, Versioning 활성화~~ ✅ (`skn29-final-2team-files-nm0p`)
5. **EC2 보안 그룹에 80·443 을 연다** (§1 — 지금 22번 하나뿐이다)
6. 가비아 DNS 에 A 레코드 3개 등록 (§1)
7. EC2 IAM Role 생성 → S3 권한 부여 → 인스턴스에 연결 (**지금 IAM 역할이 없다**)
8. EC2에서 프로젝트를 내려받고 **§4 의 `.env`** 를 만든다 — 첫 줄
   `DJANGO_SETTINGS_MODULE=config.settings.production` 을 빠뜨리지 말 것
9. `infra/docker/docker-compose.aws.yml` 로 `frontend`, `web` 실행
10. **`DB/schema.sql`·People 목업 SQL 적용**(§4 의 psql 명령) → `/api/health/` 확인
11. 도메인으로 브라우저를 열어 화면이 뜨는지 확인 — `curl localhost` 만으로는
    `ALLOWED_HOSTS` 문제가 안 잡힌다

> **`python manage.py migrate` 는 실행하지 않는다.** 이 저장소는 Django ORM 을
> 쓰지 않아 `config/settings/base.py` 의 `DATABASES` 가 비어 있다 — 명령 자체가
> 실패한다. 스키마는 psql 로 직접 넣는다(§4).

EC2에서 기본 실행 명령은 아래와 같다.

```bash
git pull
docker compose -f infra/docker/docker-compose.aws.yml up --build -d
curl http://localhost:8000/api/health/
```

MCP 시연까지 하는 날은 오버레이를 하나 더 얹는다. **`dev-mcp.yml` 헤더에 적힌
예시 명령은 로컬용이라 그대로 쓰면 `db` 컨테이너까지 올라온다** — AWS 에서는
`aws.yml` 과 겹쳐야 한다.

```bash
docker compose -f infra/docker/docker-compose.aws.yml -f infra/docker/docker-compose.dev-mcp.yml up -d dev-mcp
```

**`mcp-tunnel` 은 띄우지 않는다.** Caddy 가 `mcp.halil-ai.site` 를 받아
`dev-mcp:9000` 으로 넘기므로 cloudflared 가 하던 일이 없어졌다. 주소가
재시작마다 바뀌는 문제도 여기서 끝난다.

## 8. 구현 전에 수정할 파일

| 파일/영역 | 수정 내용 |
|---|---|
| `infra/docker/docker-compose.aws.yml` | ✅ Caddy·원문 볼륨 추가 완료(2026-08-14). 남은 것은 아래 3번 |
| `.env.example` | `VITE_API_BASE_URL`, S3 버킷·리전 추가 완료 |
| `requirements/production.txt` | `boto3`, `django-storages` 추가 완료 |
| `config/settings/production.py` | S3 `STORAGES`, 실제 `ALLOWED_HOSTS`, CORS/CSRF 설정 추가 |
| `backend/services/storage.py` | S3 어댑터. **`save()` 반환값(`sha256:…`)은 바꾸지 말 것** — `doc.content_hash` 로 들어가 변경 감지에 쓰인다 |
| `DB/schema.sql` | `bucket`·`version_id` 컬럼(§5). 넣으면 `DocumentRepository.mark_stored` 시그니처도 함께 |
| 배포 스크립트 또는 매뉴얼 | SQL 스키마 적용, `collectstatic`, Health Check 순서 명시 |

### `docker-compose.aws.yml` — 2026-08-14 에 한 것과 남은 것

전에는 `web`·`frontend` 둘뿐이고 각각 8000·5173 을 호스트로 그대로 publish 했다.

1. ✅ **Caddy 서비스를 넣었다.** 80·443 을 받아 `Caddyfile` 대로 세 서브도메인을
   가른다. 인증서는 `caddy_data` 볼륨에 남는다 — **지우지 말 것**(재발급 한도).
2. ✅ **원문 저장 볼륨을 넣었다.** 없을 때는 원문이 컨테이너 쓰기 레이어에 쌓여
   `up --build` 를 다시 돌릴 때마다 Drive 원문이 사라졌다.
3. ✅ **`frontend` 를 정적 빌드로 바꿨다**(2026-08-14). `Dockerfile` 을
   멀티스테이지로 나눠 마지막 스테이지를 `dev` 로 뒀기 때문에 **로컬 개발의
   HMR 은 그대로다** — `aws.yml` 만 `target: static` 을 고른다.

8000·5173 은 **`127.0.0.1` 에만** 붙인다. 인터넷에서는 안 보이면서 서버 안에서
`curl http://localhost:8000/api/health/` 로 진단할 수 있다.

#### `production.py` 에도 한 줄이 필요했다

`SECURE_PROXY_SSL_HEADER` 가 없었다. Caddy 는 TLS 를 끝내고 **평문 HTTP** 로
넘기므로 Django 는 요청을 계속 http 로 본다. 그 상태에서 `SECURE_SSL_REDIRECT=True`
면 Django 가 https 로 되돌리고 → Caddy 가 다시 평문으로 넘기고 → **무한
리다이렉트**(`ERR_TOO_MANY_REDIRECTS`)가 된다. 추가했다.

## 9. 발표 체크리스트

- [ ] EC2에서 `frontend`, `web` 컨테이너가 실행 중이다.
- [ ] RDS에 `DB/schema.sql` 이 적용됐고 People DB 목업 데이터가 있다 (`select count(*) from mock_hr.person;` → `57`).
- [ ] `vector` 확장을 확인했다.
- [ ] S3 버킷은 비공개이며 Versioning이 활성화됐다.
- [ ] EC2 IAM Role이 프로젝트 S3 버킷에 접근할 수 있다.
- [ ] Drive/Jira/LLM 비밀값은 Git에 포함되지 않았다.
- [ ] `/api/health/`가 정상 응답한다.
- [ ] **도메인으로 브라우저를 열어 화면이 떴다** — `curl localhost` 는 `ALLOWED_HOSTS` 문제를 못 잡는다(§4).
- [ ] **`DEBUG` 가 꺼져 있다** — `.env` 첫 줄이 `config.settings.production` 인지 확인(§4).
- [ ] MCP 시연 서버와 터널이 떠 있다(`docker ps | grep mcp`).
- [ ] **빠른 터널로 시연한다면** 주소가 바뀌지 않았는지 확인했다. 바뀌었으면 설정 > MCP 에서 「수정」으로 새 주소를 넣고 「연결 확인」까지 눌렀다. `mcp.halil-ai.site` 가 붙은 뒤에는 이 항목이 없어진다.

> 「RDS 5432 는 EC2 보안 그룹 외에는 접근할 수 없다」 항목은 뺐다. **지금은
> 의도적으로 `0.0.0.0/0` 이라 통과할 수 없는 체크였다**(§3).

## 관련 수업·프로젝트 문서

- `D:\Study\08. WEB\Day_77\RDS_S3.md`
- `D:\Study\08. WEB\Day_75\ubuntu\docker_ubuntu_setup.md`
- [로컬 Docker 개발환경 설치 매뉴얼](로컬_Docker_개발환경_설치_매뉴얼.md)
- [초기 구성 상태](../../2_중간발표%20이전/초기_구성_상태.md)
