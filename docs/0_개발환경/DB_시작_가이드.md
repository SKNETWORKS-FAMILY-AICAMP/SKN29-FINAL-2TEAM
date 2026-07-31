# DB 시작 가이드 (PostgreSQL + pgvector)

> 대상: git으로 이 저장소를 처음 clone한 팀원  
> 기준일: 2026-07-28  
> 범위: `db`(PostgreSQL/pgvector) 최초 기동과 확인 방법. Django/React 전체 개발환경 설치는 `로컬_Docker_개발환경_설치_매뉴얼.md`를 참고한다.

---

## 0. 이 문서가 다루는 것

이 프로젝트의 DB는 전부 PostgreSQL(pgvector) 하나에 들어있다. 벡터 검색용 인덱스(`VEC_IDX`)도 별도 Vector DB 없이 같은 인스턴스의 pgvector 테이블로 저장한다.

| 종류 | 정의 파일 | 저장 내용 |
|---|---|---|
| PostgreSQL/pgvector | `DB/schema.sql` | `person`, `org`, `doc`, `chunk`, `vec_idx` 등 전체 물리 스키마. Django ORM 테이블은 생성하지 않음 |
| PostgreSQL/pgvector (목업) | `DB/peopleDB/peopledb_mock.sql` | `schema.sql`이 만든 People DB 테이블(`org`/`level`/`skill`/`person`/`person_skill`/`sched`/`absence`/`person_link`)에 채우는 목업 INSERT. `schema.sql`처럼 자동 실행되지 않고 수동 실행 필요(5장 참고) |
| pgvector 예시 스크립트 | `backend/services/createDB/vec_idx_setup.py` | `vec_idx` 테이블에 청크 임베딩을 저장·검색하는 예시(6장 참고) |

`db` 서비스 하나만 `infra/docker/docker-compose.yml`에 정의되어 있고, git clone 후 한 번만 제대로 기동하면 이후로는 그대로 유지된다.

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

## 3. Postgres 기동

`docker-compose.yml`이 루트가 아니라 `infra/docker/`에 있으므로, 아래 둘 중 한 방식으로 실행한다.

```bash
# 방법 A: 루트에서 -f로 경로 지정
docker compose -f infra/docker/docker-compose.yml up -d db

# 방법 B: 디렉터리 이동 후 실행
cd infra/docker
docker compose up -d db
```

`db`는 `pgvector/pgvector:pg17` 이미지로, 처음 받는 팀원 PC에서는 이 시점에 다운로드된다(시간이 좀 걸릴 수 있음). 이 이미지는 `vector` 확장을 기본 포함하고 있어서 `VEC_IDX` 테이블을 위한 별도 설치가 필요 없다.

**중요:** `DB/schema.sql`은 `db` 컨테이너의 `/docker-entrypoint-initdb.d/01_schema.sql`로 마운트되어 있고, Postgres는 이 init 스크립트를 **데이터 볼륨이 완전히 비어있는 최초 기동 시 단 한 번만** 실행한다. 처음 clone해서 처음 `up`하는 경우에는 볼륨이 없으므로 자동으로 실행된다 — 별도 작업 불필요.

---

## 4. 정상 기동 확인

```bash
docker compose -f infra/docker/docker-compose.yml ps
```

아래처럼 `Up (healthy)`이어야 한다.

```text
NAME                     STATUS                    PORTS
skn29-final-2team-db-1   Up (healthy)   0.0.0.0:5432->5432/tcp
```

### 4.1 Postgres 테이블 확인

```bash
docker compose -f infra/docker/docker-compose.yml exec db psql -U project_copilot -d project_copilot -c "\dt"
```

`user_account`, `org`, `person`, `doc`, `chunk`, `vec_idx`, `member_invite`, `user_person_link`, `sys_setting`, `sys_notice` 등 `schema.sql` 기반 45개 테이블이 보이면 정상이다.

GUI 앱(TablePlus, DBeaver, pgAdmin 등)으로 직접 보고 싶으면 아래 정보로 접속한다.

| 항목 | 값 |
|---|---|
| Host | `localhost` |
| Port | `5432` |
| Database | `project_copilot` |
| Username | `project_copilot` |
| Password | `project_copilot` |

### 4.2 vector 확장 확인

```bash
docker compose -f infra/docker/docker-compose.yml exec db psql -U project_copilot -d project_copilot -c "\dx"
```

목록에 `vector`가 보이면 정상이다.

### 4.3 스키마 변경 반영 (이미 DB를 만들어 둔 사람)

`DB/schema.sql`은 **`db` 컨테이너를 처음 만들 때만** 실행된다. 이미 볼륨이 있으면 이후 `schema.sql` 변경은 반영되지 않는다. 이 프로젝트는 마이그레이션 도구를 쓰지 않으므로(`DATABASES = {}`) 수동 `ALTER`로 공유한다.

아래를 실행하면 최신 스키마가 된다. 모두 멱등이라 여러 번 실행해도 안전하다.

```bash
docker compose -f infra/docker/docker-compose.yml exec db \
  psql -U project_copilot -d project_copilot -c "
ALTER TABLE connector_conn ALTER COLUMN encrypted_credential_ref TYPE TEXT;
ALTER TABLE proj_source ADD COLUMN IF NOT EXISTS default_doc_role VARCHAR(30);
ALTER TABLE proj_source ADD COLUMN IF NOT EXISTS max_depth INT;
ALTER TABLE user_account ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT false;
CREATE TABLE IF NOT EXISTS sys_setting (
    setting_key    VARCHAR(50) PRIMARY KEY,
    setting_value  TEXT NOT NULL,
    updated_by     VARCHAR(5),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO sys_setting (setting_key, setting_value) VALUES ('INVITE_EXPIRE_DAYS', '14') ON CONFLICT (setting_key) DO NOTHING;
CREATE TABLE IF NOT EXISTS sys_notice (
    notice_id      VARCHAR(5) PRIMARY KEY,
    title          VARCHAR(200) NOT NULL,
    content        TEXT NOT NULL,
    status         VARCHAR(20) NOT NULL DEFAULT 'SCHEDULED',
    schedule_at    TIMESTAMPTZ NOT NULL,
    schedule_mode  VARCHAR(10) NOT NULL,
    created_by     VARCHAR(5),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS team (
    team_id           VARCHAR(5) PRIMARY KEY,
    name              VARCHAR(100) NOT NULL,
    owner_account_id  VARCHAR(5)  NOT NULL,
    src_org_id        VARCHAR(5),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS team_member (
    team_member_id  VARCHAR(5) PRIMARY KEY,
    team_id         VARCHAR(5)  NOT NULL,
    person_id       VARCHAR(5)  NOT NULL,
    added_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (team_id, person_id)
);
ALTER TABLE user_account  ADD COLUMN IF NOT EXISTS team_id VARCHAR(5);
ALTER TABLE member_invite ADD COLUMN IF NOT EXISTS team_id VARCHAR(5);
"
```

| 변경 | 이유 |
|---|---|
| `connector_conn.encrypted_credential_ref` → `TEXT` | Fernet 암호문이 Jira 1700자, Drive 632자다. `VARCHAR(255)`로는 토큰 하나도 안 들어간다 |
| `proj_source.default_doc_role` 추가 | 폴더에 역할을 주고 안의 파일이 물려받는다. `doc.doc_role`은 문서 단위라서 폴더에 파일이 추가될 때 상속 기준이 없다 |
| `proj_source.max_depth` 추가 | 폴더 탐색 깊이. `1`이면 선택한 폴더만, `NULL`이면 제한 없음. "하위 폴더 포함" 불리언을 따로 두지 않는다 — 끄는 것이 곧 `1`이고, 두 컬럼이면 어느 쪽이 이기는지 모른다 |
| `user_account.is_admin` 추가 | 운영자 콘솔 로그인 허용 플래그. 이메일 패턴이 아니라 명시적 플래그로만 운영자를 판별한다 |
| `sys_setting`, `sys_notice` 테이블 추가 | 운영자 콘솔 전역 정책(초대 만료 기간, 시스템 공지) 저장소. `INVITE_EXPIRE_DAYS`는 기존에 코드에 하드코딩돼 있던 14일 값을 그대로 시딩한다 |
| `team`, `team_member` 테이블 + `user_account.team_id`, `member_invite.team_id` 추가 | 우리 플랫폼을 쓰는 단위는 회사 전체가 아니라 **회사 안의 그룹**이다. 조직도(`org`)에서 유도하면 팀원의 소속을 알 수 없어서, 팀장이 온보딩에서 팀명을 붙여 명시적으로 만든다. 이 `team_id`가 테넌트 경계다 — [[HR_어댑터와_테넌트_경계]] |

자세한 배경은 [[Jira_Drive_커넥터_연결_설계]] §1에 있다. **새로 스키마를 바꾸면 이 표에 한 줄 추가하고 위 블록에도 넣어 주세요.**

---

## 5. People DB 목업 데이터 넣기 (`peopledb_mock.sql`)

`DB/schema.sql`은 `db` 컨테이너에 자동으로 마운트되어 최초 기동 시 실행되지만, `DB/peopleDB/peopledb_mock.sql`은 **`docker-compose.yml`에 마운트되어 있지 않아 자동 실행되지 않는다.** People DB(조직/직급/스킬/인력/근무/휴가/외부계정 연동) 목업 데이터가 필요하면 아래처럼 직접 실행한다.

```bash
cat DB/peopleDB/peopledb_mock.sql | docker compose -f infra/docker/docker-compose.yml exec -T db \
  psql -U project_copilot -d project_copilot -v ON_ERROR_STOP=1
```

정상 실행되면 `INSERT 0 9`, `INSERT 0 57` 같은 결과가 순서대로 출력된다(org 9, level 8, person 57, skill 14, person_skill 111, sched 57, absence 23, person_link 70건).

**주의:**
- 이 스크립트는 `schema.sql` 실행 이후에만 실행할 것(People DB 테이블이 먼저 있어야 함).
- INSERT가 멱등적이지 않다(`ON CONFLICT` 처리 없음). 이미 데이터가 들어있는 상태에서 다시 실행하면 PK 중복 에러(`duplicate key value violates unique constraint`)가 난다 — 한 PC당 한 번만 실행하면 된다.
- 데이터를 다시 채우고 싶으면 목업 테이블을 초기화하거나, `down -v`로 볼륨을 통째로 초기화한 뒤 `schema.sql` 자동 실행 → 이 명령 재실행 순서로 한다.

확인:

```bash
docker compose -f infra/docker/docker-compose.yml exec db psql -U project_copilot -d project_copilot -c "SELECT count(*) FROM person;"
```

`57`이 나오면 정상이다.

### 5.1 팀원 실제 이름·이메일 오버라이드

`DB/peopleDB/team_overrides.example.sql`을 복사해 Git에 올라가지 않는 `team_overrides.sql`을 만들고 실제 팀원 이름·이메일을 채운다. 이 파일은 `.gitignore` 대상이므로 팀원에게 별도로 전달해야 한다.

```powershell
Copy-Item DB/peopleDB/team_overrides.example.sql DB/peopleDB/team_overrides.sql

Get-Content -Raw DB/peopleDB/team_overrides.sql |
  docker compose -f infra/docker/docker-compose.yml exec -T db `
  psql -U project_copilot -d project_copilot -v ON_ERROR_STOP=1
```

실행 순서는 반드시 다음과 같다.

```text
DB/schema.sql → DB/peopleDB/peopledb_mock.sql → DB/peopleDB/team_overrides.sql
```

직접 가입한 팀장은 People DB 커넥터에서 가입 이메일과 `person.email`을 비교해 `SELF_EMAIL` 매핑을 만든다. 두 이메일이 다르면 HR 본인 확인과 팀원 초대가 막히므로 `team_overrides.sql`의 주소를 먼저 확인한다. 팀원 역할은 데이터의 `org.mgr_id`가 아니라 초대 코드 가입(`TEAM_INVITATION`)으로 결정된다.

---

## 6. API 서버 실행

Django는 API 계층으로만 사용하며 ORM Migration을 실행하지 않는다. 전체 스택을 올리려면:

```bash
docker compose -f infra/docker/docker-compose.yml up -d
```

API는 psycopg Repository를 통해 `schema.sql` 테이블을 직접 조회한다.

### 6.1 운영자 콘솔 운영자 계정 지정 (`grant_admin.py`)

운영자 콘솔(`/ops`)은 `user_account.is_admin = true`인 계정만 로그인할 수 있다. 이 플래그는 API로는 켤 수
없고(자기 자신·타인을 API로 운영자로 승격시키는 경로 자체가 없음), `vec_idx_setup.py`와 같은 방식으로 호스트에서
직접 실행하는 스크립트로만 켠다. 대상 이메일은 먼저 일반 회원가입으로 `user_account`에 존재해야 한다.

```bash
DATABASE_URL="postgres://project_copilot:project_copilot@localhost:5432/project_copilot" \
  python backend/services/createDB/grant_admin.py <가입된 이메일>
```

권한을 회수하려면 `--revoke`를 붙인다.

```bash
python backend/services/createDB/grant_admin.py <가입된 이메일> --revoke
```

---

## 7. VEC_IDX 예시로 벡터 저장·검색해보기 (선택)

`vec_idx_setup.py`는 컨테이너 안이 아니라 **호스트 Python**에서 실행하도록 작성되어 있다. FK 제약은 사용하지 않으며, 스크립트가 `chunk_id` 존재 여부를 검사한 뒤 벡터를 저장한다. 데모 실행 시 `proj → doc → doc_block → chunk` 체인을 먼저 만든다.

```bash
pip install "psycopg[binary]"
DATABASE_URL="postgres://project_copilot:project_copilot@localhost:5432/project_copilot" \
  python backend/services/createDB/vec_idx_setup.py
```

정상 실행되면 다음과 같이 출력된다.

```text
VEC_IDX에 저장 완료. 현재 벡터 수: 1
```

이 스크립트는 실행할 때마다 같은 `chunk_id`를 `upsert`하므로 여러 번 실행해도 행이 중복 생성되지 않는다.

---

## 8. 자주 쓰는 명령

```bash
# DB 로그
docker compose -f infra/docker/docker-compose.yml logs -f db

# 중지 (데이터 유지)
docker compose -f infra/docker/docker-compose.yml stop db

# 완전 초기화 — 주의: 로컬 DB 데이터 전부 삭제
docker compose -f infra/docker/docker-compose.yml down -v
```

`down -v` 후 복구 순서:

```text
1. docker compose ... up -d db        # schema.sql 자동 실행
2. peopledb_mock.sql 수동 실행
3. team_overrides.sql 수동 실행
4. docker compose ... up -d web frontend
```

---

## 9. 문제 해결

| 증상 | 원인·해결 |
|---|---|
| `docker compose up` 실행 시 `no configuration file provided: not found` | 프로젝트 루트가 아니라 `infra/docker/`에 compose 파일이 있음. `-f infra/docker/docker-compose.yml`을 붙이거나 `cd infra/docker` 후 실행 |
| `db`가 `healthy`가 되지 않음 | `docker compose ... logs db`로 오류 확인, 5432 포트를 로컬 Postgres가 이미 쓰고 있는지 `lsof -nP -iTCP:5432 -sTCP:LISTEN`으로 확인 |
| GUI 앱 접속 시 `role "project_copilot" does not exist` | 5432 포트를 로컬 Postgres가 먼저 점유하고 있어서 docker가 아닌 그쪽에 연결된 것. 위 1장 참고해 포트 충돌 해소 후 재접속 |
| `schema.sql`을 고쳤는데 반영이 안 됨 | init 스크립트는 볼륨이 빌 때만 실행된다. `down -v`로 `postgres_data` 볼륨 삭제 후 `up -d db`로 재기동(로컬 데이터 전부 삭제되니 주의) |
| `peopledb_mock.sql` 실행 시 `duplicate key value violates unique constraint` | 이미 목업 데이터가 들어있는 상태에서 재실행한 것. 5장 참고해 데이터 삭제 후 재실행하거나 무시(이미 들어있으면 다시 넣을 필요 없음) |
| `vec_idx_setup.py` 실행 시 `ModuleNotFoundError: No module named 'psycopg'` | `pip install "psycopg[binary]"` 먼저 실행 |
| `vec_idx_setup.py` 실행 시 `type "vector" does not exist` | `db`가 `schema.sql`의 `CREATE EXTENSION IF NOT EXISTS vector;`를 아직 안 탄 볼륨. 4.2장으로 확장 설치 여부 확인, 없으면 `down -v` 후 재기동 |
| 운영자 콘솔 로그인 시 `운영자 권한이 없는 계정입니다` | 6.1장의 `grant_admin.py`로 `is_admin`을 켜지 않은 계정. 스크립트 실행 후 재로그인 |
| `column "is_admin" does not exist` / `relation "sys_setting" does not exist` 등 스키마 반영 누락 | 기존 볼륨을 쓰고 있다면 4.3장의 ALTER/CREATE 블록을 실행 |
