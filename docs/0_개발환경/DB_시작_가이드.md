# DB 시작 가이드 (PostgreSQL + ChromaDB)

> 대상: git으로 이 저장소를 처음 clone한 팀원  
> 기준일: 2026-07-28  
> 범위: `db`(PostgreSQL/pgvector) + `chroma`(ChromaDB) 최초 기동과 확인 방법. Django/React 전체 개발환경 설치는 `로컬_Docker_개발환경_설치_매뉴얼.md`를 참고한다.

---

## 0. 이 문서가 다루는 것

이 프로젝트는 DB가 두 종류다.

| 종류 | 정의 파일 | 저장 내용 |
|---|---|---|
| PostgreSQL/pgvector | `DB/schema.sql` | `person`, `org`, `doc`, `chunk` 등 도메인 스키마(Figma 설계 기준) + Django ORM 테이블(`accounts_*`, `people_*`, `projects_*`, `auth_*` 등) |
| ChromaDB | `backend/services/createDB/chroma_setup.py` | 청크 임베딩 벡터 컬렉션(`chunks_{embed_ver}`) |

둘 다 `infra/docker/docker-compose.yml`에 서비스로 정의되어 있고, git clone 후 한 번만 제대로 기동하면 이후로는 그대로 유지된다.

---

## 1. 사전 준비

1. Docker Desktop 설치 후 실행.
2. 로컬에 다른 PostgreSQL이 5432 포트를 쓰고 있지 않은지 확인한다.

```bash
lsof -nP -iTCP:5432 -sTCP:LISTEN
```

---

## 2. 최초 1회: 환경 변수 설정

프로젝트 루트에서:

```bash
cp .env.example .env
```

`.env`는 Git에 올라가지 않는 로컬 전용 설정이다. DB 관련 기본값은 그대로 두면 된다.

---

## 3. Postgres + Chroma 기동

`docker-compose.yml`이 루트가 아니라 `infra/docker/`에 있으므로, 아래 둘 중 한 방식으로 실행한다.

```bash
# 방법 A: 루트에서 -f로 경로 지정
docker compose -f infra/docker/docker-compose.yml up -d db chroma

# 방법 B: 디렉터리 이동 후 실행
cd infra/docker
docker compose up -d db chroma
```

`db`는 `pgvector/pgvector:pg17` 이미지로, `chroma`는 `chromadb/chroma:latest` 이미지로 처음 받는 팀원 PC에서는 이 시점에 다운로드된다(시간이 좀 걸릴 수 있음).

**중요:** `DB/schema.sql`은 `db` 컨테이너의 `/docker-entrypoint-initdb.d/01_schema.sql`로 마운트되어 있고, Postgres는 이 init 스크립트를 **데이터 볼륨이 완전히 비어있는 최초 기동 시 단 한 번만** 실행한다. 처음 clone해서 처음 `up`하는 경우에는 볼륨이 없으므로 자동으로 실행된다 — 별도 작업 불필요.

---

## 4. 정상 기동 확인

```bash
docker compose -f infra/docker/docker-compose.yml ps
```

아래처럼 두 서비스 모두 `Up`(가능하면 `healthy`)이어야 한다.

```text
NAME                          STATUS
skn29-final-2team-db-1        Up (healthy)   0.0.0.0:5432->5432/tcp
skn29-final-2team-chroma-1    Up             0.0.0.0:8001->8000/tcp
```

### 4.1 Postgres 테이블 확인

```bash
docker compose -f infra/docker/docker-compose.yml exec db psql -U project_copilot -d project_copilot -c "\dt"
```

`user_account`, `org`, `person`, `doc`, `chunk` 등 `schema.sql` 기반 테이블이 보이면 정상이다(Django `migrate`를 아직 안 돌렸다면 `accounts_*`, `people_*` 등은 이후 5장에서 생긴다).

GUI 앱(TablePlus, DBeaver, pgAdmin 등)으로 직접 보고 싶으면 아래 정보로 접속한다.

| 항목 | 값 |
|---|---|
| Host | `localhost` |
| Port | `5432` |
| Database | `project_copilot` |
| Username | `project_copilot` |
| Password | `project_copilot` |

### 4.2 Chroma 상태 확인

```bash
curl http://127.0.0.1:8001/api/v1/heartbeat
```

응답이 오면 정상이다.

---

## 5. Django 쪽 테이블도 필요하면

Django ORM 테이블(`accounts_*`, `people_*`, `projects_*`, `auth_*`)은 `web` 컨테이너를 기동하면 자동으로 `migrate`가 실행되면서 생성된다. `web`까지 포함해서 전체 스택을 올리려면:

```bash
docker compose -f infra/docker/docker-compose.yml up -d
```

자세한 내용(관리자 계정 생성, People 데모 데이터 시드, API 목록 등)은 `로컬_Docker_개발환경_설치_매뉴얼.md`의 5장 이후를 참고한다.

---

## 6. ChromaDB 예시 컬렉션 만들어보기 (선택)

`chroma_setup.py`는 컨테이너 안이 아니라 **호스트 Python**에서 실행하도록 작성되어 있다.

```bash
pip install chromadb --break-system-packages
python backend/services/createDB/chroma_setup.py
```

정상 실행되면 다음과 같이 출력된다.

```text
컬렉션 'chunks_embed-1.0'에 저장 완료. 현재 문서 수: 1
```

이 스크립트는 실행할 때마다 같은 `vec_id`(`V-018`)를 `upsert`하므로 여러 번 실행해도 컬렉션이 중복 생성되지 않는다.

---

## 7. 자주 쓰는 명령

```bash
# DB/Chroma 로그
docker compose -f infra/docker/docker-compose.yml logs -f db
docker compose -f infra/docker/docker-compose.yml logs -f chroma

# 중지 (데이터 유지)
docker compose -f infra/docker/docker-compose.yml stop db chroma

# 완전 초기화 — 주의: schema.sql/Chroma 데이터 전부 삭제, 다음 up 때 schema.sql이 다시 자동 실행됨
docker compose -f infra/docker/docker-compose.yml down -v
```

---

## 8. 문제 해결

| 증상 | 원인·해결 |
|---|---|
| `docker compose up` 실행 시 `no configuration file provided: not found` | 프로젝트 루트가 아니라 `infra/docker/`에 compose 파일이 있음. `-f infra/docker/docker-compose.yml`을 붙이거나 `cd infra/docker` 후 실행 |
| `db`가 `healthy`가 되지 않음 | `docker compose ... logs db`로 오류 확인, 5432 포트를 로컬 Postgres가 이미 쓰고 있는지 `lsof -nP -iTCP:5432 -sTCP:LISTEN`으로 확인 |
| GUI 앱 접속 시 `role "project_copilot" does not exist` | 5432 포트를 로컬 Postgres가 먼저 점유하고 있어서 docker가 아닌 그쪽에 연결된 것. 위 1장 참고해 포트 충돌 해소 후 재접속 |
| `schema.sql`을 고쳤는데 반영이 안 됨 | init 스크립트는 볼륨이 빌 때만 실행된다. `down -v`로 `postgres_data` 볼륨 삭제 후 `up -d db`로 재기동(로컬 데이터 전부 삭제되니 주의) |
| `localhost:8001`(Chroma) 접속 실패 | `docker compose ps`로 `chroma` 컨테이너 상태 확인, 8001 포트를 다른 프로세스가 점유하고 있는지 확인 |
| `chroma_setup.py` 실행 시 `ModuleNotFoundError: No module named 'chromadb'` | `pip install chromadb --break-system-packages` 먼저 실행 |
