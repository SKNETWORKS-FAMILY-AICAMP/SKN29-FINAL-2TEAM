# 로컬 Docker 개발환경 설치 매뉴얼

> 대상: AI 프로젝트 운영 코파일럿 백엔드 작업자  
> 기준일: 2026-07-28  
> 범위: Django + PostgreSQL/pgvector + React/Vite 로컬 공통 환경. React 화면 구현은 Figma/프론트엔드 팀 작업 범위다.

---

## 1. 이 매뉴얼을 사용하는 이유

팀원마다 Python·PostgreSQL을 직접 설치하면 버전과 데이터가 달라진다. 이 프로젝트는 Docker Compose로 다음 서비스를 같은 방식으로 실행한다.

```text
Docker Desktop
├─ db       : PostgreSQL 17 + pgvector, VEC_IDX 벡터 검색 포함 (호스트 포트 5432)
├─ web      : Django + DRF 개발 서버 (호스트 포트 8000)
└─ frontend : React + Vite 개발 서버 (호스트 포트 5173)
```

Docker Compose 프로젝트 이름은 `skn29-final-2team`으로 고정된다. 따라서 컨테이너는 `skn29-final-2team-db-1`, `skn29-final-2team-web-1`처럼 표시된다.

각 팀원의 DB는 서로 독립적이다. 테이블 구조는 Migration(Django)과 `DB/schema.sql`(원본 도메인 스키마)로, 공통 기본 데이터는 Seed 명령으로 동일하게 맞춘다.

---

## 2. 사전 준비

1. Git으로 이 프로젝트를 내려받는다.
2. Docker Desktop을 설치하고 실행한다.
3. PowerShell에서 아래 명령이 정상 응답하는지 확인한다.

```powershell
docker --version
docker compose version
docker info
```

`docker info`에서 Docker daemon 연결 오류가 나면 Docker Desktop을 먼저 실행한다.

Python 가상환경은 Docker 방식으로만 개발할 때 필수가 아니다. 문서 파싱·AI 모듈을 컨테이너 밖에서 개별 실험할 때, 그리고 아래 7장의 `vec_idx_setup.py` 실행 시에만 별도로 구성한다.

---

## 3. 최초 1회 설정

프로젝트 루트에서 실행한다.

```powershell
Copy-Item .env.example .env
```

`.env`는 로컬 전용 설정이며 Git에 올리지 않는다. 팀원이 변경할 수 있는 값은 다음이다.

| 항목 | 기본값 | 변경 시점 |
|---|---|---|
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173` | React 개발 서버 포트·주소 변경 시 |
| `ANALYSIS_EXECUTION_MODE` | `stub` | 실제 분석 Worker 연결 시 |
| `OBJECT_STORAGE_PROVIDER` | `local` | S3 또는 MinIO 연결 시 |
| `SECRET_KEY` | 개발용 값 | 공유·배포 환경 구성 시 |

`DATABASE_URL`은 호스트에서 Django를 직접 실행할 때의 주소다. Docker `web` 컨테이너 안에서는 Compose가 서비스명 `db` 주소로 자동 교체하므로 수정하지 않는다.

**주의:** `docker compose` 명령은 항상 아래 두 방식 중 하나로 실행한다. `docker-compose.yml`이 프로젝트 루트가 아니라 `infra/docker/`에 있기 때문에, 그냥 루트에서 `docker compose up`만 치면 `no configuration file provided: not found` 오류가 난다.

```powershell
# 방법 A: 루트에서 -f로 경로 지정 (이 문서의 예시는 전부 이 방식)
docker compose -f infra/docker/docker-compose.yml up -d

# 방법 B: 디렉터리 이동 후 실행
cd infra/docker
docker compose up -d
```

---

## 4. 실행

### 4.1 처음 실행 또는 Dockerfile 변경 후

```powershell
docker compose -f infra/docker/docker-compose.yml up --build
```

터미널을 유지한 채 로그를 확인할 수 있다. 종료는 `Ctrl + C`다.

### 4.2 백그라운드 실행

```powershell
docker compose -f infra/docker/docker-compose.yml up -d --build
docker compose -f infra/docker/docker-compose.yml ps
```

정상 상태 예시:

```text
db       Up (healthy)   0.0.0.0:5432->5432/tcp
web      Up             0.0.0.0:8000->8000/tcp
frontend Up             0.0.0.0:5173->5173/tcp
```

### 4.3 상태 확인

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/health/
```

예상 응답:

```json
{"status":"ok","service":"ai-project-operation-copilot"}
```

---

## 5. DB 스키마 자동 생성 확인 (`DB/schema.sql`)

`DB/schema.sql`은 `db` 컨테이너의 `/docker-entrypoint-initdb.d/01_schema.sql`로 마운트되어 있다. Postgres의 init 스크립트는 **데이터 디렉터리가 완전히 빈 상태, 즉 `postgres_data` 볼륨을 최초로 생성할 때 단 한 번만** 실행된다.

- 저장소를 처음 clone하고 처음 `up`하는 경우: 볼륨이 없으므로 자동 실행된다. 별도 작업 불필요.
- 이미 한 번이라도 `db`를 띄운 적 있는 PC에서 `schema.sql`을 수정한 경우: 자동으로 재실행되지 않는다.

**테이블이 만들어졌는지 확인:**

```powershell
docker compose -f infra/docker/docker-compose.yml exec db psql -U project_copilot -d project_copilot -c "\dt"
```

`user_account`, `org`, `person`, `doc`, `chunk`, `vec_idx` 등 41개 테이블이 보이면 정상이다. GUI(TablePlus, DBeaver 등)로 보고 싶으면 `localhost:5432`, DB `project_copilot`, 계정/비번 `project_copilot`/`project_copilot`으로 접속한다.

**`schema.sql`을 고친 뒤 다시 반영하고 싶을 때** (주의: 로컬 DB 데이터가 전부 삭제된다):

```powershell
docker compose -f infra/docker/docker-compose.yml down
docker volume rm skn29-final-2team_postgres_data
docker compose -f infra/docker/docker-compose.yml up -d db
```

---

## 6. 최초 데이터 준비 (Django)

웹 컨테이너 안에서 Migration과 합성 People DB 데이터를 준비한다.

```powershell
docker compose -f infra/docker/docker-compose.yml exec web python manage.py migrate
docker compose -f infra/docker/docker-compose.yml exec web python manage.py createsuperuser
docker compose -f infra/docker/docker-compose.yml exec web python manage.py seed_demo_people
```

`seed_demo_people`는 다음 합성 데이터를 반복 실행해도 중복 없이 생성·갱신한다.

- 조직 2개: AI Platform, Delivery
- 직원 3명
- Skill 4개: Python, Django, React, Jira
- 직원별 Skill·숙련도 및 주 40시간 근무 일정

관리 데이터는 아래 주소에서 확인한다.

```text
http://127.0.0.1:8000/admin/
```

---

## 7. VEC_IDX(pgvector) 설정 (`vec_idx_setup.py`)

벡터 검색은 별도 서비스 없이 `db`의 `vec_idx` 테이블(pgvector)로 처리한다. `pgvector/pgvector:pg17` 이미지가 `vector` 확장을 이미 포함하고 있어서, `schema.sql`의 `CREATE EXTENSION IF NOT EXISTS vector;`만으로 준비가 끝난다.

`vec_idx_setup.py`는 컨테이너 안이 아니라 **호스트 Python**에서 실행하도록 작성되어 있다. `vec_idx.chunk_id`에는 `chunk`를 가리키는 실FK가 걸려 있으므로, 스크립트가 데모용 `proj → doc → doc_block → chunk` 체인을 먼저 만든 뒤 그 청크에 벡터를 저장한다.

```powershell
pip install "psycopg[binary]"
$env:DATABASE_URL = "postgres://project_copilot:project_copilot@localhost:5432/project_copilot"
python backend/services/createDB/vec_idx_setup.py
```

정상 실행되면 다음과 같이 출력된다.

```text
VEC_IDX에 저장 완료. 현재 벡터 수: 1
```

**`vector` 확장이 설치돼 있는지 확인:**

```powershell
docker compose -f infra/docker/docker-compose.yml exec db psql -U project_copilot -d project_copilot -c "\dx"
```

---

## 8. React 팀 연동 기준

React + Vite 실행 환경은 이 저장소의 `frontend/`에 포함되어 있다. 화면 HTML/CSS와 Figma 디자인의 React 컴포넌트 변환은 프론트 팀이 진행한다. `src/App.tsx`는 의도적으로 빈 상태다.

프론트 팀은 아래 백엔드 주소를 환경변수로 사용한다.

```text
VITE_API_BASE_URL=http://127.0.0.1:8000/api
```

Docker 환경에서는 `http://localhost:5173/`에서 React 개발 서버를 확인한다. 화면 구현 전에는 빈 화면이 표시되는 것이 정상이다.

현재 제공 API:

| Method | URL | 설명 | 인증 |
|---|---|---|---|
| GET | `/api/health/` | 서버 상태 | 불필요 |
| GET, POST | `/api/projects/` | 프로젝트 목록·생성 | 필요 |
| GET | `/api/projects/{projectId}/` | 프로젝트 상세 | 필요 |
| POST | `/api/projects/{projectId}/analysis-runs/` | 분석 실행 생성 | 필요 |
| GET | `/api/analysis-runs/{runId}/` | 분석 실행 상태 | 필요 |
| GET | `/api/organizations/` | 조직 목록 | 필요 |
| GET | `/api/people/` | 직원 목록 | 필요 |

현재는 React용 로그인 API가 아직 없다. 보호 API의 인증 방식은 화면 개발 착수 전 `세션 인증` 또는 `JWT` 중 하나로 팀에서 확정한다. 그 전에는 Health API와 Mock 응답으로 화면 연동을 진행한다.

---

## 9. 개발 중 자주 쓰는 명령

```powershell
# 실행 중인 서비스 상태
docker compose -f infra/docker/docker-compose.yml ps

# Django 웹 로그
docker compose -f infra/docker/docker-compose.yml logs -f web

# PostgreSQL 로그
docker compose -f infra/docker/docker-compose.yml logs -f db

# 모델 변경 후 Migration 생성·적용
docker compose -f infra/docker/docker-compose.yml exec web python manage.py makemigrations
docker compose -f infra/docker/docker-compose.yml exec web python manage.py migrate

# 자동 테스트
docker compose -f infra/docker/docker-compose.yml exec web python manage.py test tests

# 서비스만 중지 (DB 데이터 유지)
docker compose -f infra/docker/docker-compose.yml stop

# 서비스와 네트워크 제거 (DB Volume 유지)
docker compose -f infra/docker/docker-compose.yml down

# DB까지 완전 초기화 — 주의: 로컬 데이터 전부 삭제
docker compose -f infra/docker/docker-compose.yml down -v
```

`down -v` 후에는 다시 `up`, `migrate`, `createsuperuser`, `seed_demo_people`, `vec_idx_setup.py`를 실행해야 한다.

---

## 10. 문제 해결

| 증상 | 원인·해결 |
|---|---|
| `docker compose up` 실행 시 `no configuration file provided: not found` | 프로젝트 루트가 아니라 `infra/docker/`에 compose 파일이 있음. `-f infra/docker/docker-compose.yml`을 붙이거나 `cd infra/docker` 후 실행 |
| Docker daemon 연결 실패 | Docker Desktop을 실행한 뒤 재시도 |
| `db`가 `healthy`가 되지 않음 | `docker compose ... logs db`로 오류 확인 후 포트 5432 충돌 여부 확인 |
| 웹 컨테이너가 DB에 연결하지 못함 | `.env`의 `DATABASE_URL`을 임의로 `db`로 바꾸지 말고 Compose 환경변수 설정 유지 |
| 8000 포트 충돌 | `"8000:8000"`을 `"8001:8000"`으로 변경하고 React API 주소도 함께 변경 |
| `schema.sql`을 고쳤는데 반영이 안 됨 | init 스크립트는 볼륨이 빌 때만 실행된다. 5장을 참고해 `postgres_data` 볼륨 삭제 후 재기동 |
| `vec_idx_setup.py` 실행 시 `type "vector" does not exist` | `db`가 `vector` 확장을 아직 안 탄 볼륨. 7장으로 확장 설치 여부 확인, 없으면 `down -v` 후 재기동 |
| 모델 변경이 반영되지 않음 | `makemigrations` 후 `migrate` 실행 |
| 데이터가 꼬임 | 필요한 경우 `down -v`로 로컬 DB 초기화 후 Seed·`vec_idx_setup.py` 재실행 |

---

## 11. 현재 구현 범위 확인

이 환경은 백엔드 기반과 데이터 관리용이다. 아래 기능은 아직 미구현이므로 실행 결과가 나오지 않는 것이 정상이다.

- Google Drive·Jira Connector
- PDF/DOCX 파싱과 DocumentBlock
- Project Knowledge Model
- AnalysisSnapshot·Feature Readiness
- 업무량 계산·추천·검증 Agent
- React 로그인·권한 연동

구체적인 상태와 다음 수정 위치는 `초기_구성_상태.md`를 함께 확인한다.
