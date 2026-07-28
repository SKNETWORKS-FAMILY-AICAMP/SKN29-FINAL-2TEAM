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

이번 범위에서는 ECS, ALB, CloudFront, SQS, 별도 Vector DB, Terraform, CI/CD는 사용하지 않는다.

## 2. 컨테이너 구성 변경

현재 로컬 Compose의 세 서비스 중 AWS에서는 `db` 컨테이너를 제거한다.

| 현재 로컬 | AWS 배포 | 변경 내용 |
|---|---|---|
| `frontend` | EC2의 React 컨테이너 | 유지 |
| `web` | EC2의 Django 컨테이너 | 유지. DB 주소만 RDS endpoint로 변경 |
| `db` | RDS PostgreSQL + pgvector | EC2에서 실행하지 않음 |

```text
로컬 개발
frontend + web + db(Docker)

AWS 시연
EC2: frontend + web(Docker)
RDS: PostgreSQL + pgvector
S3: 원문 문서 + 정적/업로드 파일
```

## 3. 보안 그룹 연결 규칙

```text
브라우저 ── 5173, 8000 ──▶ EC2 보안 그룹
EC2 보안 그룹 ── 5432 ──▶ RDS 보안 그룹
```

| 대상 | 포트 | 허용 대상 |
|---|---|---|
| EC2 | 22 | 팀원 공인 IP만 허용 |
| EC2 | 5173 | 시연 중 필요한 사용자만 허용 |
| EC2 | 8000 | 시연 중 필요한 사용자만 허용 |
| RDS | 5432 | **EC2 보안 그룹만 허용** |

RDS는 Public access를 사용하지 않고, RDS 보안 그룹의 인바운드 규칙에서 소스로 EC2 보안 그룹을 지정한다. `5432`를 인터넷에 열지 않는다.

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
USE_SQLITE=False
DATABASE_URL=postgresql://<DB_USER>:<DB_PASSWORD>@<RDS_ENDPOINT>:5432/project_copilot?sslmode=require
AWS_STORAGE_BUCKET_NAME=skn29-final-2team-files-<고유값>
AWS_S3_REGION_NAME=ap-northeast-2
VITE_API_BASE_URL=http://<EC2_PUBLIC_IP>:8000/api
SECURE_SSL_REDIRECT=False
```

현재 시연 구조는 HTTPS 도메인 없이 EC2 공인 IP와 HTTP를 사용하므로 `SECURE_SSL_REDIRECT=False`로 둔다. 도메인과 HTTPS를 적용하는 시점에는 `True`로 바꾼다.

RDS 생성 뒤에는 EC2의 Django 컨테이너에서 migration과 seed를 실행한다.

```bash
docker compose -f infra/docker/docker-compose.yml exec web python manage.py migrate
docker compose -f infra/docker/docker-compose.yml exec web python manage.py seed_demo_people
```

RDS PostgreSQL에서 지원하는 확장과 버전은 생성 시점에 [AWS RDS PostgreSQL 확장 목록](https://docs.aws.amazon.com/AmazonRDS/latest/PostgreSQLReleaseNotes/postgresql-extensions.html)으로 다시 확인한다.

## 5. S3 설정

S3 버킷은 하나로 시작한다.

| 버킷 예시 | 저장 항목 |
|---|---|
| `skn29-final-2team-files-<고유값>` | Google Drive 원문 PDF/DOCX, Django 정적 파일, 향후 업로드 파일 |

S3 경로는 역할로 구분한다.

```text
documents/{project_id}/{source_file_id}/{version}/original.pdf
static/
media/
```

문서 메타데이터에는 S3 URL 전체 대신 아래 값을 저장한다.

- `bucket`
- `storage_key`
- `version_id`
- 원본 Drive 파일 ID
- 원본 수정 시각

이 값은 Document → ContentBlock → Chunk → Citation의 원문 근거 추적에 사용한다. 버킷은 비공개로 만들고, 문서 변경 이력을 위해 Versioning을 활성화한다.

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

위 코드는 이전 전 구현할 항목이다. 현재 코드에는 `django-storages`와 S3 저장 어댑터가 아직 포함되지 않았다.

## 7. EC2 배포 순서

1. Ubuntu EC2 생성, Security Group 설정, Docker와 Docker Compose 설치
2. RDS PostgreSQL 생성, RDS 보안 그룹에서 EC2 보안 그룹의 5432 접근만 허용
3. RDS에 `vector` 확장이 사용 가능한지 확인
4. S3 버킷 생성, Versioning 활성화
5. EC2 IAM Role에 프로젝트 S3 버킷 권한 부여 후 EC2에 연결
6. EC2에서 프로젝트를 내려받고 `.env`에 RDS endpoint·S3 버킷 정보를 설정
7. `infra/docker/docker-compose.aws.yml`로 `frontend`, `web`만 실행
8. Django migration, seed, `/api/health/` 확인
9. S3 업로드와 Drive 문서 원문 저장 키 기록을 확인

EC2에서 기본 실행 명령은 아래와 같다.

```bash
git pull
docker compose -f infra/docker/docker-compose.aws.yml up --build -d
docker compose -f infra/docker/docker-compose.aws.yml exec web python manage.py migrate
curl http://localhost:8000/api/health/
```

## 8. 구현 전에 수정할 파일

| 파일/영역 | 수정 내용 |
|---|---|
| `infra/docker/docker-compose.aws.yml` | AWS용 Compose. `db` 컨테이너 없이 `frontend`, `web`만 실행 |
| `.env.example` | `VITE_API_BASE_URL`, S3 버킷·리전, HTTPS 전환 설정값 추가 완료 |
| `requirements/production.txt` | `boto3`, `django-storages` 추가 완료 |
| `config/settings/production.py` | S3 `STORAGES`, 실제 `ALLOWED_HOSTS`, CORS/CSRF 설정 추가 |
| 문서 저장 서비스 | S3 업로드 후 `bucket`, `storage_key`, `version_id` 기록 |
| 배포 스크립트 또는 매뉴얼 | `migrate`, `collectstatic`, Health Check 순서 명시 |

## 9. 발표 체크리스트

- [ ] EC2에서 `frontend`, `web` 컨테이너가 실행 중이다.
- [ ] RDS에 migration이 적용됐고 People DB 목업 데이터가 있다.
- [ ] RDS 5432는 EC2 보안 그룹 외에는 접근할 수 없다.
- [ ] `vector` 확장을 확인했다.
- [ ] S3 버킷은 비공개이며 Versioning이 활성화됐다.
- [ ] EC2 IAM Role이 프로젝트 S3 버킷에 접근할 수 있다.
- [ ] Drive/Jira/LLM 비밀값은 Git에 포함되지 않았다.
- [ ] `/api/health/`가 정상 응답한다.

## 관련 수업·프로젝트 문서

- `D:\Study\08. WEB\Day_77\RDS_S3.md`
- `D:\Study\08. WEB\Day_75\ubuntu\docker_ubuntu_setup.md`
- [로컬 Docker 개발환경 설치 매뉴얼](로컬_Docker_개발환경_설치_매뉴얼.md)
- [초기 구성 상태](초기_구성_상태.md)
