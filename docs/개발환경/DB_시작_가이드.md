# DB 시작 가이드 (PostgreSQL + pgvector)

> 대상: git으로 이 저장소를 처음 clone한 팀원  
> 기준일: 2026-07-28  
> 범위: `db`(PostgreSQL/pgvector) 최초 기동과 확인 방법. Django/React 전체 개발환경 설치는 `로컬_Docker_개발환경_설치_매뉴얼.md`를 참고한다.

---

## 0. 이 문서가 다루는 것

이 프로젝트의 DB는 전부 PostgreSQL(pgvector) 하나에 들어있다. 벡터 검색용 인덱스(`VEC_IDX`)도 별도 Vector DB 없이 같은 인스턴스의 pgvector 테이블로 저장한다.

| 종류 | 정의 파일 | 저장 내용 |
|---|---|---|
| PostgreSQL/pgvector | `DB/schema.sql` | `doc`, `chunk`, `vec_idx` 등 `public` **49개** + HR 8개(`mock_hr` 스키마) = `CREATE TABLE` **57개**. Django ORM 테이블은 생성하지 않음 (⚠ 40+8=48 은 2026-08-11 Agent Platform 9개 추가 전 값이다 — 2026-08-12 정정) |
| PostgreSQL/pgvector (목업) | `DB/peopleDB/peopledb_mock.sql` | `schema.sql`이 만든 People DB 테이블(`mock_hr` 스키마의 `org`/`level`/`skill`/`person`/`person_skill`/`sched`/`absence`/`person_link`)에 채우는 목업 INSERT. `schema.sql`처럼 자동 실행되지 않고 수동 실행 필요(5장 참고) |
| pgvector 예시 스크립트 | `backend/services/createDB/vec_idx_setup.py` | `vec_idx` 테이블에 청크 임베딩을 저장·검색하는 예시(6장 참고) |

`infra/docker/docker-compose.yml` 에는 `db`·`web`·`frontend` 세 서비스가 있고 이 문서는 `db` 만 다룬다. git clone 후 한 번만 제대로 기동하면 이후로는 그대로 유지된다.

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

> ⚠ **「그대로 두면 된다」는 틀렸다 (2026-08-12).** AWS 이전(`3ddf9db`) 이후
> `.env.example` 의 `DATABASE_URL` 은 **빈 값**이고, `docker-compose.yml` 이
> 그것을 덮어쓰지도 않는다. 빈 문자열은 django-environ 이 기본값으로 대체하지
> 않으므로 `psycopg.connect('')` 로 죽는다.
>
> **반드시 직접 채운다** — 로컬 Postgres 컨테이너를 쓸 때:
> ```
> DATABASE_URL=postgres://project_copilot:project_copilot@db:5432/project_copilot
> ```
> 팀 공유 AWS RDS 를 쓸 때는 RDS 엔드포인트를 넣는다.
>
> 아래 §6·§7 의 **호스트 실행 명령은 인라인으로 `@localhost:5432` 를 넘기므로**
> `.env` 를 `@db:5432` 로 채워도 충돌하지 않는다 — 컨테이너 안에서는 `db`,
> 호스트에서는 `localhost` 다.

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

`user_account`, `doc`, `chunk`, `vec_idx`, `member_invite`, `user_person_link`, `sys_setting`, `sys_notice` 등 **49개**가 보이면 정상이다(2026-08-11 Agent Platform 9개 추가 전에는 40개였다). `schema.sql`의 `CREATE TABLE`은 전부 **57개**지만, HR 8개(`org`·`level`·`skill`·`person`·`person_skill`·`person_link`·`sched`·`absence`)는 `mock_hr` 스키마에 있어 `\dt`(search_path = `public`)에는 나오지 않는다 — 그 8개는 `\dt mock_hr.*`로 따로 본다(§4.3·5장 참고).

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

> **먼저 「무엇이 빠졌나」부터 묻는다 (2026-08-18 추가).**
>
> ```bash
> python DB/migrations/_apply.py --check
> ```
>
> 배포가 전제하는 테이블·컬럼 12개를 대조해 **빠진 것만** 알려 준다(읽기만 한다).
> `--url` 로 대상을 바꾼다 — 안 주면 `.env` 의 `DATABASE_URL` 이다.
> 적용도 같은 스크립트가 한다: `python DB/migrations/_apply.py <파일.sql> ...`
>
> **공유 RDS 는 서버에서 돌린다** — 로컬 `.env` 는 로컬 컨테이너를 가리킨다.
>
> ```bash
> ssh -i skn29-2team-key.pem ubuntu@43.200.114.119
> cd ~/SKN29-Final-2Team
> docker compose -f infra/docker/docker-compose.aws.yml exec -T web >   python DB/migrations/_apply.py --check
> ```
>
> ⚠ **마이그레이션이 있는 병합은 배포 전에 이걸 돌린다.** 2026-08-18 오전에
> 「코드는 새 스키마, DB 는 옛 스키마」로 배포돼 채팅이 통째로 막혔는데,
> 테스트 700건이 전부 통과한 상태였다 — 테스트가 실제 RDS 를 안 쓰기 때문이다.
> **새 마이그레이션을 더하면 `_apply.py` 의 `EXPECTED` 에 한 줄 추가한다.**


`DB/schema.sql`은 **`db` 컨테이너를 처음 만들 때만** 실행된다. 이미 볼륨이 있으면 이후 `schema.sql` 변경은 반영되지 않는다. 이 프로젝트는 마이그레이션 도구를 쓰지 않으므로(`DATABASES = {}`) 수동 `ALTER`로 공유한다.

아래를 실행하면 최신 스키마가 된다. 멱등이라 여러 번 실행해도 안전하다 — 예외는 둘이다. `exist_task.proj_source_id`의 `NOT NULL`(이 테이블이 비어 있을 때만 걸린다)과, `doc` 의 CHECK 둘(데이터가 조건을 어기면 걸린다). 둘 다 블록 바로 아래 주석이 다룬다.

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
ALTER TABLE doc ADD COLUMN IF NOT EXISTS storage_key VARCHAR(255);
ALTER TABLE doc ALTER COLUMN cur_revision TYPE VARCHAR(100);
ALTER TABLE exist_task ADD COLUMN IF NOT EXISTS proj_source_id VARCHAR(5) NOT NULL;
ALTER TABLE exist_task ADD COLUMN IF NOT EXISTS estimate NUMERIC(6,2);
ALTER TABLE exist_task ADD COLUMN IF NOT EXISTS status_category VARCHAR(20);
ALTER TABLE exist_task ADD COLUMN IF NOT EXISTS summary VARCHAR(500);
ALTER TABLE proj_source ADD COLUMN IF NOT EXISTS display_name VARCHAR(255);
ALTER TABLE proj_source ADD COLUMN IF NOT EXISTS last_sync_at TIMESTAMPTZ;
ALTER TABLE proj ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ;
ALTER TABLE proj ALTER COLUMN created_at SET DEFAULT now();
CREATE UNIQUE INDEX IF NOT EXISTS ux_exist_task_source_issue ON exist_task (proj_source_id, jira_issue_id);
ALTER TABLE user_account ADD COLUMN IF NOT EXISTS avatar_key VARCHAR(255);
ALTER TABLE team ADD COLUMN IF NOT EXISTS capacity_wk_hours NUMERIC(5,2);
ALTER TABLE team ADD COLUMN IF NOT EXISTS overload_pct INT;
ALTER TABLE team ADD COLUMN IF NOT EXISTS workload_weeks INT;
ALTER TABLE proj ADD COLUMN IF NOT EXISTS team_id VARCHAR(5);
UPDATE proj SET team_id = (SELECT ua.team_id FROM user_account ua WHERE ua.account_id = proj.owner_account_id) WHERE team_id IS NULL;
-- 프로젝트 설명(2026-08-11). 만들 때 이름+설명으로 기준 문서 후보를 찾는다.
ALTER TABLE proj ADD COLUMN IF NOT EXISTS description VARCHAR(500);
CREATE TABLE IF NOT EXISTS team_folder (
    team_folder_id      VARCHAR(5) PRIMARY KEY,
    team_id             VARCHAR(5)  NOT NULL,
    conn_id             VARCHAR(5)  NOT NULL,
    external_folder_id  VARCHAR(255) NOT NULL,
    display_name        VARCHAR(255),
    default_doc_role    VARCHAR(30),
    max_depth           INT,
    UNIQUE (team_id, external_folder_id)
);
INSERT INTO team_folder (team_folder_id, team_id, conn_id, external_folder_id, display_name, default_doc_role, max_depth)
SELECT 'TF' || lpad(((SELECT COALESCE(max(substring(team_folder_id FROM 3)::int), 0) FROM team_folder)
                     + row_number() OVER (ORDER BY ps.proj_source_id))::text, 3, '0'),
       p.team_id, ps.conn_id, ps.external_source_id, ps.display_name, ps.default_doc_role, ps.max_depth
  FROM proj_source ps JOIN proj p ON p.proj_id = ps.proj_id
 WHERE ps.source_type = 'DRIVE_FOLDER' AND p.team_id IS NOT NULL
ON CONFLICT (team_id, external_folder_id) DO NOTHING;
DELETE FROM proj_source WHERE source_type = 'DRIVE_FOLDER';
ALTER TABLE doc ADD COLUMN IF NOT EXISTS team_id VARCHAR(5);
UPDATE doc SET team_id = (SELECT p.team_id FROM proj p WHERE p.proj_id = doc.proj_id) WHERE team_id IS NULL;
ALTER TABLE doc ALTER COLUMN proj_id DROP NOT NULL;
UPDATE doc SET proj_id = NULL WHERE proj_id IS NOT NULL AND doc_role IS DISTINCT FROM 'PRIMARY';
ALTER TABLE proj_source DROP COLUMN IF EXISTS default_doc_role;
ALTER TABLE proj_source DROP COLUMN IF EXISTS max_depth;
DO \$\$
DECLARE r RECORD; new_proj_id VARCHAR(5);
BEGIN
  FOR r IN SELECT ps.proj_source_id, ps.display_name, ps.external_source_id, p.team_id, p.owner_account_id, p.tz
             FROM (SELECT proj_source_id, proj_id, display_name, external_source_id,
                          row_number() OVER (PARTITION BY proj_id ORDER BY proj_source_id) AS rn
                     FROM proj_source) ps
             JOIN proj p ON p.proj_id = ps.proj_id
            WHERE ps.rn > 1
  LOOP
    SELECT 'PJ' || lpad((COALESCE(max(substring(proj_id FROM 3)::int), 0) + 1)::text, 3, '0') INTO new_proj_id FROM proj;
    INSERT INTO proj (proj_id, name, status, tz, owner_account_id, team_id)
    VALUES (new_proj_id, COALESCE(NULLIF(r.display_name, ''), r.external_source_id), 'ACTIVE', r.tz, r.owner_account_id, r.team_id);
    UPDATE proj_source SET proj_id = new_proj_id WHERE proj_source_id = r.proj_source_id;
  END LOOP;
END \$\$;
UPDATE proj p SET name = ps.display_name FROM proj_source ps WHERE ps.proj_id = p.proj_id AND NULLIF(ps.display_name, '') IS NOT NULL;
UPDATE proj SET status = 'ACTIVE' WHERE status = 'DRAFT' AND proj_id IN (SELECT proj_id FROM proj_source);
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ux_proj_source_proj') THEN
    ALTER TABLE proj_source ADD CONSTRAINT ux_proj_source_proj UNIQUE (proj_id);
  END IF;
END \$\$;
CREATE SCHEMA IF NOT EXISTS mock_hr;
DO \$\$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['org','level','skill','person','person_skill','person_link','sched','absence'] LOOP
    IF to_regclass('public.' || t) IS NOT NULL THEN
      EXECUTE format('ALTER TABLE public.%I SET SCHEMA mock_hr', t);
    END IF;
  END LOOP;
END \$\$;
UPDATE doc SET doc_role = NULL WHERE doc_role IN ('PLAN','MEETING_NOTE','DAILY_REPORT','OTHER');
UPDATE team_folder SET default_doc_role = NULL WHERE default_doc_role IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_doc_primary_per_proj ON doc (proj_id) WHERE doc_role = 'PRIMARY' AND deleted = false;
ALTER TABLE doc_block ALTER COLUMN revision TYPE VARCHAR(100);
ALTER TABLE vec_idx   ALTER COLUMN revision TYPE VARCHAR(100);
ALTER TABLE doc_sync  ALTER COLUMN revision TYPE VARCHAR(100);
DO \$\$
DECLARE current_dim INT;
BEGIN
  SELECT atttypmod INTO current_dim FROM pg_attribute
   WHERE attrelid = 'vec_idx'::regclass AND attname = 'embedding';
  IF current_dim = 768 THEN
    RAISE NOTICE 'vec_idx.embedding 은 이미 768 차원이다. 건너뛴다.';
    RETURN;
  END IF;
  IF EXISTS (SELECT 1 FROM vec_idx) THEN
    RAISE EXCEPTION 'vec_idx 에 행이 있다. 1536 을 768 로 안전하게 바꿀 수 없으므로 중단한다.';
  END IF;
  ALTER TABLE vec_idx ALTER COLUMN embedding TYPE VECTOR(768);
END \$\$;
CREATE TABLE IF NOT EXISTS agent (
    agent_id          VARCHAR(5) PRIMARY KEY,
    team_id           VARCHAR(5)   NOT NULL,
    name              VARCHAR(100) NOT NULL,
    description       VARCHAR(500),
    instruction       TEXT         NOT NULL DEFAULT '',
    model             VARCHAR(100),
    reasoning_effort  VARCHAR(20),
    max_iterations    INT          NOT NULL DEFAULT 10,
    is_prebuilt       BOOLEAN      NOT NULL DEFAULT false,
    status            VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',
    created_by        VARCHAR(5),
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS agent_tool (
    agent_id  VARCHAR(5)   NOT NULL,
    tool_ref  VARCHAR(100) NOT NULL,
    PRIMARY KEY (agent_id, tool_ref)
);
CREATE TABLE IF NOT EXISTS mcp_server (
    mcp_server_id    VARCHAR(5) PRIMARY KEY,
    team_id          VARCHAR(5)   NOT NULL,
    name             VARCHAR(100) NOT NULL,
    endpoint_url     VARCHAR(500) NOT NULL,
    auth_token_enc   TEXT,
    status           VARCHAR(20)  NOT NULL DEFAULT 'UNCHECKED',
    last_checked_at  TIMESTAMPTZ,
    created_by       VARCHAR(5)
);
CREATE TABLE IF NOT EXISTS mcp_tool (
    mcp_tool_id    VARCHAR(5) PRIMARY KEY,
    server_id      VARCHAR(5)   NOT NULL,
    name           VARCHAR(200) NOT NULL,
    description    TEXT,
    input_schema   JSONB        NOT NULL DEFAULT '{}',
    enabled        BOOLEAN      NOT NULL DEFAULT true,
    discovered_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (server_id, name)
);
CREATE TABLE IF NOT EXISTS chat_session (
    session_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id     VARCHAR(5)   NOT NULL,
    account_id  VARCHAR(5)   NOT NULL,
    agent_id    VARCHAR(5)   NOT NULL,
    proj_id     VARCHAR(5),
    title       VARCHAR(200),
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_chat_session_account ON chat_session (account_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS chat_message (
    message_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  UUID        NOT NULL,
    role        VARCHAR(20) NOT NULL,
    content     JSONB       NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_chat_message_session ON chat_message (session_id, created_at);
CREATE TABLE IF NOT EXISTS agent_run (
    run_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id     UUID,
    agent_id       VARCHAR(5)  NOT NULL,
    parent_run_id  UUID,
    status         VARCHAR(20) NOT NULL DEFAULT 'RUNNING',
    iterations     INT         NOT NULL DEFAULT 0,
    token_in       INT,
    token_out      INT,
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at       TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_agent_run_session ON agent_run (session_id, started_at);
CREATE TABLE IF NOT EXISTS tool_call (
    tool_call_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id         UUID         NOT NULL,
    tool_ref       VARCHAR(100) NOT NULL,
    input_summary  TEXT,
    status         VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
    error_code     VARCHAR(50),
    duration_ms    INT,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_tool_call_run ON tool_call (run_id, created_at);
CREATE TABLE IF NOT EXISTS doc_meta (
    doc_id          VARCHAR(5) PRIMARY KEY,
    summary         TEXT,
    doc_type        VARCHAR(50),
    keywords        TEXT[]      NOT NULL DEFAULT '{}',
    summary_vec     VECTOR(768),
    extracted_text  TEXT,
    extract_status  VARCHAR(20) NOT NULL,
    extracted_at    TIMESTAMPTZ
);
ALTER TABLE chat_session ADD COLUMN IF NOT EXISTS agent_version_id VARCHAR(5);
ALTER TABLE agent_run ADD COLUMN IF NOT EXISTS agent_version_id VARCHAR(5);
CREATE TABLE IF NOT EXISTS agents (
    agent_id           VARCHAR(5) PRIMARY KEY,
    team_id            VARCHAR(5)   NOT NULL,
    name               VARCHAR(100) NOT NULL,
    description        VARCHAR(500),
    owner_account_id   VARCHAR(5),
    visibility         VARCHAR(20)  NOT NULL DEFAULT 'TEAM',
    status             VARCHAR(20)  NOT NULL DEFAULT 'DRAFT',
    current_version_id VARCHAR(5),
    is_prebuilt        BOOLEAN      NOT NULL DEFAULT false,
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS agent_versions (
    agent_version_id  VARCHAR(5) PRIMARY KEY,
    agent_id          VARCHAR(5)   NOT NULL,
    version           INT          NOT NULL,
    system_prompt     TEXT         NOT NULL DEFAULT '',
    model             VARCHAR(100),
    reasoning_effort  VARCHAR(20),
    max_iterations    INT          NOT NULL DEFAULT 6,
    created_by        VARCHAR(5),
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (agent_id, version)
);
CREATE INDEX IF NOT EXISTS ix_agent_versions_agent ON agent_versions (agent_id, version DESC);
CREATE TABLE IF NOT EXISTS agent_version_tools (
    agent_version_id  VARCHAR(5)   NOT NULL,
    tool_ref          VARCHAR(100) NOT NULL,
    config            JSONB        NOT NULL DEFAULT '{}',
    PRIMARY KEY (agent_version_id, tool_ref)
);
CREATE TABLE IF NOT EXISTS agent_version_subagents (
    parent_version_id       VARCHAR(5)   NOT NULL,
    child_agent_id          VARCHAR(5)   NOT NULL,
    child_version_id        VARCHAR(5)   NOT NULL,
    alias                   VARCHAR(100) NOT NULL,
    delegation_description  TEXT         NOT NULL,
    created_at              TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (parent_version_id, child_agent_id),
    UNIQUE (parent_version_id, alias)
);
-- 2026-08-14 · 실행 로그에 「그때 배포된 코드」를 남긴다
ALTER TABLE agent_run ADD COLUMN IF NOT EXISTS runtime_profile_version VARCHAR(64);
-- 2026-08-15 · 팀마다 기본 챗 에이전트 한 행
ALTER TABLE agents ADD COLUMN IF NOT EXISTS is_default_chat BOOLEAN NOT NULL DEFAULT false;
CREATE UNIQUE INDEX IF NOT EXISTS agents_one_default_chat_per_team
    ON agents (team_id) WHERE is_default_chat = true;
-- 2026-08-18 · 「내 파일」(M④) — 개인 소유 문서. 개인 문서는 team_id 가 NULL 이다
ALTER TABLE doc ADD COLUMN IF NOT EXISTS owner_account_id VARCHAR(5);
ALTER TABLE doc ADD COLUMN IF NOT EXISTS search_enabled BOOLEAN NOT NULL DEFAULT true;
CREATE INDEX IF NOT EXISTS ix_doc_owner
    ON doc (owner_account_id) WHERE owner_account_id IS NOT NULL;
ALTER TABLE doc DROP CONSTRAINT IF EXISTS doc_owner_xor_team;
ALTER TABLE doc ADD CONSTRAINT doc_owner_xor_team CHECK (
    (team_id IS NOT NULL AND owner_account_id IS NULL)
 OR (team_id IS NULL AND owner_account_id IS NOT NULL)
);
-- 2026-08-18 · 개인 문서를 팀에 공유한다(소유는 그대로 개인)
ALTER TABLE doc ADD COLUMN IF NOT EXISTS shared_team_id VARCHAR(5);
CREATE INDEX IF NOT EXISTS ix_doc_shared_team
    ON doc (shared_team_id) WHERE shared_team_id IS NOT NULL;
ALTER TABLE doc DROP CONSTRAINT IF EXISTS doc_share_is_personal_only;
ALTER TABLE doc ADD CONSTRAINT doc_share_is_personal_only CHECK (
    shared_team_id IS NULL OR owner_account_id IS NOT NULL
);
-- 2026-08-18 · 청크·임베딩 단계의 상태(요약 단계인 doc_meta.extract_status 와 다르다)
ALTER TABLE doc ADD COLUMN IF NOT EXISTS index_status VARCHAR(20);
-- 2026-08-18 · 즐겨찾기한 에이전트 (사람×에이전트)
CREATE TABLE IF NOT EXISTS agent_favorites (
    account_id  VARCHAR(5)  NOT NULL,
    agent_id    VARCHAR(5)  NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (account_id, agent_id)
);
-- 2026-08-18 · 이 대화에서만 도구를 좁혀 쓴다
ALTER TABLE chat_session ADD COLUMN IF NOT EXISTS tool_refs_override TEXT[];
"
```

> **CHECK 둘(`doc_owner_xor_team`·`doc_share_is_personal_only`)은 `DROP … IF EXISTS` 뒤에 다시 건다.** Postgres 의 `ADD CONSTRAINT` 에는 `IF NOT EXISTS` 가 없어서, 그냥 두면 두 번째 실행에서 「이미 있다」로 죽는다. 지우고 다시 거는 것이라 멱등은 유지되지만 **걸 때마다 `doc` 전체를 다시 검사한다.**
>
> ⚠ 여기서 실패한다면 컬럼이 아니라 **데이터가 조건을 어긴 것**이다 — `team_id` 와 `owner_account_id` 가 **둘 다 NULL** 인 `doc` 행이 있으면 `doc_owner_xor_team` 이 안 걸린다. `SELECT doc_id FROM doc WHERE team_id IS NULL AND owner_account_id IS NULL;` 로 찾아 팀을 채우거나 지운 뒤 다시 실행한다.

> `exist_task.proj_source_id`가 `NOT NULL`인데 기본값이 없다. **이 테이블이 비어 있어야 통과한다.** 2026-08-03 시점에는 이슈 수집이 없어 모든 팀원의 DB가 0행이었다. **2026-08-05 현재는 Jira 수집이 붙어 행이 쌓인다** — 이 마이그레이션을 아직 안 돌렸고 이미 이슈를 읽었다면 아래 대안을 쓰거나 `exist_task`를 비우고 다시 읽어야 한다. 혹시 행이 있어서 실패하면 `DB/migrations/2026-08-03_exist_task_source.sql`의 주석에 채워 넣고 `SET NOT NULL`하는 대안이 있다.

> **`UPDATE doc SET proj_id = NULL`에 `doc_role IS DISTINCT FROM 'PRIMARY'` 조건이 붙어 있다. 지우지 마세요.** 원본 마이그레이션(`DB/migrations/2026-08-04_team_scope.sql`)에는 조건이 없다 — 그때 `doc.proj_id`에 들어 있던 값은 「폴더를 고른 그 프로젝트」라는 뜻이라 근거가 없었고, 그 시점에는 `PRIMARY`가 아직 존재하지도 않았기 때문이다. 하지만 이 블록은 **여러 번 실행되는 것을 전제로 한다.** 조건 없이 두면, 이미 한 번 돌린 뒤 기준 문서를 고른 사람이 블록을 다시 실행할 때 모든 프로젝트의 기준 문서 지정이 풀린다. 게다가 아래 `doc_role` 블록은 옛 값(`PLAN` 등)만 비우므로 `doc_role = 'PRIMARY'`인데 `proj_id`는 `NULL`인 행이 남고, 부분 유니크 인덱스는 `NULL`을 서로 다르게 보기 때문에 에러도 나지 않는다 — 조용히 틀린 상태가 된다. 되돌리는 코드 경로도 없다(`set_primary_document`는 `WHERE proj_id = %s`로만 정리한다). `IS NULL`이 아니라 `IS DISTINCT FROM 'PRIMARY'`인 이유는, 옛 볼륨의 문서가 `doc_role = 'PLAN'` 같은 값을 아직 갖고 있어서 `IS NULL`로는 정리 대상에서 빠지기 때문이다.

> 마지막 블록(`mock_hr`)은 **데이터를 옮기지 않는다.** `SET SCHEMA`는 테이블을 통째로 다른 네임스페이스에 재등록만 하므로 행·인덱스·제약이 그대로 따라가고, 되돌리려면 `mock_hr` → `public`으로 같은 명령을 반대로 주면 된다. `to_regclass` 검사 때문에 이미 옮긴 DB에서 다시 실행해도 아무 일도 일어나지 않는다.

> **`doc_role` 블록은 이 컬럼의 뜻을 바꾼다.** 예전에는 문서의 **종류**(`PLAN`/`MEETING_NOTE`/`DAILY_REPORT`/`OTHER`)였는데, 폴더에 준 역할을 안의 파일이 그대로 물려받는 방식이라 「01_기획」에 든 것은 요구사항 정의서든 화면설계서든 전부 기획서가 됐다. 정작 그 값으로 분기하는 코드는 한 줄도 없었다. 이제는 **프로젝트와의 관계**를 담는다 — `NULL`(팀 문서 풀) / `PRIMARY`(기준 문서, 프로젝트당 하나) / `SUB`(근거 검색에 함께 쓰는 문서). 옛 값은 새 의미로 읽으면 거짓말이라 비운다.

> **마지막 두 블록(`revision` 폭·`vec_idx` 768차원)은 문서 파싱·임베딩 파이프라인 몫이다.** 임베딩 모델이 `google/embeddinggemma-300m`(768차원)으로 확정돼서 1536차원이던 컬럼을 바꾼다. `vec_idx`에 행이 있으면 **일부러 중단한다** — 1536차원 벡터를 768로 자르거나 0으로 채우면 값은 남지만 의미가 사라져, 검색이 조용히 엉뚱한 결과를 낸다. 2026-08-04 기준 이 테이블에 쓰는 코드는 아래 7장의 데모 스크립트뿐이라 대부분 0행이고 그냥 지나간다. 행이 있으면 `DELETE FROM vec_idx`로 비우고 다시 실행하면 된다.
>
> `revision` 세 개를 같이 넓히는 이유는 Drive의 `headRevisionId`가 실측 51자이기 때문이다. `doc.cur_revision`만 2026-07-31에 100자로 넓혀 둬서, 원문은 받아지는데 파싱 결과를 적재할 때 터지는 상태였다.

> ⚠ **`team_overrides.sql`을 쓰고 있다면 같이 고쳐야 한다.** 이 파일은 실제 이메일이 들어 있어 `.gitignore` 대상이라 **각자 로컬 사본을 직접 수정**해야 한다. 안 고치면 다음에 실행할 때 `relation "person" does not exist`가 난다.
>
> ```
> UPDATE person ...  →  UPDATE mock_hr.person ...
> UPDATE org    ...  →  UPDATE mock_hr.org    ...
> FROM person AS p   →  FROM mock_hr.person AS p
> LEFT JOIN org AS o →  LEFT JOIN mock_hr.org AS o
> ```
>
> 고친 형태는 저장소에 있는 `DB/peopleDB/team_overrides.example.sql`과 같다. 그 파일을 그대로 복사해서 이름·이메일만 다시 채워도 된다.

| 변경 | 이유 |
|---|---|
| `connector_conn.encrypted_credential_ref` → `TEXT` | Fernet 암호문이 Jira 1700자, Drive 632자다. `VARCHAR(255)`로는 토큰 하나도 안 들어간다 |
| `proj_source.default_doc_role`·`max_depth` 추가 → **삭제**(2026-08-04) | 폴더에 역할을 주고 안의 파일이 물려받게 하려던 컬럼이다. **지금은 `proj_source`에 없다** — 폴더·파일 역할 지정 기능이 제거되고 폴더 자체가 `team_folder`로 옮겨 가면서 블록 뒤쪽의 `DROP COLUMN IF EXISTS`가 지운다. 블록이 앞에서 `ADD COLUMN IF NOT EXISTS`로 붙였다가 뒤에서 지우는 것은, 옛 볼륨에 남은 폴더 행을 `team_folder`로 옮겨 실을 때 이 두 값을 읽어야 하기 때문이다. 탐색 깊이(`max_depth`)와 표시명은 `team_folder`가 그대로 물려받았다 |
| `user_account.is_admin` 추가 | 운영자 콘솔 로그인 허용 플래그. 이메일 패턴이 아니라 명시적 플래그로만 운영자를 판별한다 |
| `sys_setting`, `sys_notice` 테이블 추가 | 운영자 콘솔 전역 정책(초대 만료 기간, 시스템 공지) 저장소. `INVITE_EXPIRE_DAYS`는 기존에 코드에 하드코딩돼 있던 14일 값을 그대로 시딩한다 |
| `team`, `team_member` 테이블 + `user_account.team_id`, `member_invite.team_id` 추가 | 우리 플랫폼을 쓰는 단위는 회사 전체가 아니라 **회사 안의 그룹**이다. 조직도(`org`)에서 유도하면 팀원의 소속을 알 수 없어서, 팀장이 온보딩에서 팀명을 붙여 명시적으로 만든다. 이 `team_id`가 테넌트 경계다 — [[HR_어댑터와_테넌트_경계]] |
| `doc.storage_key` 추가 | Drive 원문을 내려받아 문서 저장소에 넣고 그 위치를 기록한다. 파일 경로가 아니라 **저장소 안의 키**라, 나중에 로컬 디스크에서 S3로 바꿔도 값이 그대로 쓰인다. 아직 안 받은 문서는 `NULL` |
| `doc.cur_revision` → `VARCHAR(100)` | Google Drive의 `headRevisionId`가 **실측 51자**라 기존 `VARCHAR(50)`에 한 글자가 모자랐다. 실제로 내려받아 보기 전에는 안 드러났다(목킹 테스트는 짧은 문자열을 썼다). Drive가 길이를 보장한다는 문서가 없어 여유를 뒀다 |
| `exist_task.proj_source_id` 추가 + `ux_exist_task_source_issue` UNIQUE (2026-08-03) | 이 이슈를 **어느 소스에서 가져왔는지** 나타내는 컬럼이 하나도 없었다. 재동기화 때 지울 범위를 특정할 수 없어 최초 1회 적재밖에 못 하는 구조였고, "임준 196h = KAN 144h + AIP 52h" 분해도 안 나온다. `proj_id`가 아니라 `proj_source_id`인 이유는 프로젝트 하나가 Jira 프로젝트를 여러 개 읽을 수 있어서(N:M) 재동기화의 실제 단위가 `proj_source`이기 때문이다. UNIQUE는 같은 이슈가 두 줄이 되어 부하가 2배로 잡히는 것을 막는 마지막 방어선이다 — [[Jira_부하계산_ToDo]] 단계 1-3 |
| `exist_task.estimate` 추가 (2026-08-03) | 최초 추정치. `exist_task_snap.estimate`가 복사해 갈 원본이 `exist_task`에 없어서 채울 곳이 없었다. Jira `timetracking.originalEstimateSeconds`를 시간으로 환산해 넣는다 |
| `proj.created_at` 추가 (2026-08-04) | 프로젝트 목록의 **"최신순" 정렬과 날짜 열**이 근거로 삼을 값이 없었다. `proj`에는 이름·상태·소유자뿐이고 `audit_log`에도 `PROJECT_CREATE`가 없어 되짚을 수도 없었다. 폴더를 고르는 행위가 프로젝트를 만드는 것이라 그 시점이 곧 생성 시각이다. **기본값을 `ADD COLUMN`에 함께 주지 않고 나중에 거는 것이 중요하다** — 같이 주면 Postgres가 기존 행까지 그 값으로 채워, 예전 프로젝트가 "오늘 만들어진 것"이 된다. 기존 행은 NULL로 두고 화면이 `-`로 보여준다 |
| `proj_source.display_name` 추가 (2026-08-03) | 화면이 Jira 프로젝트를 `KAN`·`AIP` 같은 **키로만** 보여줄 수 있었다. 실제 이름(`SKN29_Final_2Team`·`AI Platform`)이 저장돼 있지 않아서다. 매번 원본에 물어보면 대시보드가 커넥터 생존에 묶인다 — 토큰이 만료되면 저장된 부하 데이터는 멀쩡한데 이름을 못 읽어 화면이 깨진다. 고르는 시점에는 이미 이름을 알고 있으므로 그때 같이 저장한다. 기존 행은 NULL로 남고 화면이 키로 대체하며, 소스를 다시 저장하면 채워진다 |
| `exist_task.status_category` 추가 (2026-08-03) | Jira 상태 **표시 문자열은 조직·프로젝트마다 다르다.** 실측에서 같은 카테고리(`new`)인데 KAN은 `'해야 할 일'`, AIP는 `'할 일'`로 왔다. `statusCategory.name`마저 한국어로 지역화되므로 안전한 값은 `statusCategory.key`(`new`/`indeterminate`/`done`) 하나뿐이다. 이걸 `TO_DO`/`IN_PROGRESS`/`DONE`으로 바꿔 저장하고 **부하 계산은 이 컬럼만 본다.** `status`에 한글이 들어가는 건 사람이 보기 위한 것이고, 조건문에 쓰면 다른 사이트에서 조용히 매치 0건이 된다 |
| HR 8개 테이블(`org`·`level`·`skill`·`person`·`person_skill`·`person_link`·`sched`·`absence`)을 `mock_hr` 스키마로 이동 | 이 8개는 **고객사 HR 시스템의 데이터**지 우리가 소유한 데이터가 아니다. 경계는 코드(`backend/services/hr/`)로 세웠지만 DB에서는 `public`에 우리 테이블과 섞여 있어, 다음 사람이 무심코 조인하면 그만이었다. 스키마를 나누면 `mock_hr.`를 타이핑하지 않고는 건드릴 수 없다 — [[HR_어댑터와_테넌트_경계]] |
| `exist_task.summary` 추가 (2026-08-04) | 이슈 제목이 없으면 업무 목록이 `KAN-34`처럼 키만 늘어놓게 되어 무슨 일인지 알 수 없다. 값은 재동기화가 채우고 기존 행은 `NULL`이며 화면이 이슈 키로 대신 보여준다 — 없는 제목을 지어내지 않는다 |
| `proj_source.last_sync_at` 추가 (2026-08-04) | 「갱신」 버튼을 누를지 판단하려면 지금 보는 숫자가 언제 것인지 알아야 한다. `sync_status`는 `PENDING`에서 움직이지 않아 시각을 대신하지 못한다. 기본값을 걸지 않는다 — 한 번도 안 읽은 것(`NULL`)과 읽었는데 0건인 것은 다른 상태다 |
| `user_account.avatar_key` 추가 (2026-08-04) | 프로필 사진을 담을 곳이 우리에게도 HR(`mock_hr.person`)에도 없었다. 파일 경로가 아니라 **문서 저장소 안에서의 키**라, 지금은 로컬 디스크지만 S3로 바뀌어도 값이 그대로 쓰인다. 안 올렸으면 `NULL`이고 화면이 이름 첫 글자로 대신한다 |
| `team.capacity_wk_hours`·`overload_pct`·`workload_weeks` 추가 (2026-08-04) | 설정의 「팀 업무량 기준」이 화면에만 있고 저장되지 않아 계산이 그 값을 보지도 않았다. 셋 다 `NULL`이 "설정 안 함"이고 각각 HR의 사람별 값·100%·4주를 쓴다. HR 값을 복사해 두지 않는 이유는 HR이 바뀌면 우리 사본이 조용히 낡기 때문이다 |
| `proj.team_id` + `team_folder` 테이블 + `doc.team_id` + `doc.proj_id` NULL 허용 + `proj_source`에 `UNIQUE (proj_id)` (2026-08-04) | **테넌트 경계가 팀이라는 것을 스키마에 반영한 한 덩어리다.** 폴더를 고르는 행위가 프로젝트를 만드는 행위로 구현돼 있었는데, 폴더는 파일이 어디 있는지 알려주는 경로일 뿐이고 그 안의 파일이 어느 프로젝트 것인지는 열어 봐야 안다 — 그래서 폴더는 `proj_source`에서 `team_folder`(팀 소속)로, 문서는 프로젝트 필수에서 팀 필수로 옮겼다. Jira는 반대다: Jira 프로젝트 하나에 프로젝트 하나의 업무가 들어 있으므로 **1:1**로 못박았다(여러 개를 매달면 서로 다른 프로젝트의 업무가 한 진행률로 뭉개진다) — [[HR_어댑터와_테넌트_경계]] |
| `doc.doc_role` 재정의 + `ux_doc_primary_per_proj` 부분 유니크 인덱스 (2026-08-04) | 문서의 **종류**에서 **프로젝트와의 관계**로 바뀌었다(아래 `doc_role` 주석 참고). 기준 문서는 프로젝트당 하나이고, 화면이 라디오라 둘이 될 일이 없어 보여도 두 건이 되면 어느 것으로 업무를 뽑았는지 알 수 없어 조용히 틀리므로 인덱스로 강제한다 |
| `doc_block`·`vec_idx`·`doc_sync`의 `revision` → `VARCHAR(100)` (2026-08-04) | `doc.cur_revision`만 2026-07-31에 넓혀 둬서, 원문은 받아지는데 파싱 결과를 적재할 때 터지는 상태였다. Drive의 `headRevisionId`가 실측 51자다 |
| `vec_idx.embedding` → `VECTOR(768)` (2026-08-04) | 임베딩 모델이 `google/embeddinggemma-300m`(768차원)으로 확정됐다. 1536은 OpenAI `text-embedding-3-small` 전제라 맞지 않는다. 적재와 검색이 같은 모델을 써야 하므로 차원은 한 곳에서만 정해진다 |
| Agent Platform 9개 테이블 추가 — `agent`·`agent_tool`·`mcp_server`·`mcp_tool`·`chat_session`·`chat_message`·`agent_run`·`tool_call`·`doc_meta` (2026-08-11) | 8/11 팀 회의에서 Chat 기반 Agent Platform으로 확정됐다(아키텍처 §3.1). 기존 테이블은 한 줄도 안 건드리는 순수 추가라, **안 돌려도 지금 화면은 멀쩡하고 새 Chat 화면만 안 뜬다.** PK가 두 종류인 것이 눈에 걸릴 텐데 의도한 것이다 — 이 스키마의 `VARCHAR(5)`는 접두사 2자 + 숫자 3자라 **테이블당 999행이 상한**이고(`backend/db/codes.py`), 대화 한 번에 수십 줄씩 쌓이는 `chat_message`·`agent_run`·`tool_call`은 데모 도중에도 그 선을 넘는다. 그래서 로그성 테이블은 `doc_block`·`chunk`·`vec_idx`와 같은 UUID를 쓰고, 사람이 만드는 설정(`agent`·`mcp_server`·`mcp_tool`)만 기존 코드 체계를 따른다. `agent_run.session_id`가 NULL 허용인 것도 의도다 — Harness의 `run_agent`는 대화에 종속되지 않는 순수 함수라 평가 스크립트나 에이전트 간 호출에는 `chat_session`이 아예 없다 — `DB/migrations/2026-08-11_agent_platform.sql` (`71dd585`) |
| `proj.description` 추가 (2026-08-11) | 프로젝트를 만들 때 **이름과 설명으로 기준 문서 후보를 찾는다**. 이름만으로는 요약 임베딩 질의가 너무 짧아 아무 문서나 걸린다 — 「AI Platform」 같은 이름은 어떤 문서와도 비슷하고 어떤 문서와도 안 비슷하다. 찾을 때만 쓰고 버리지 않는 이유는 나중에 후보를 다시 뽑을 때 사람이 같은 문장을 또 적어야 하기 때문이다 — `POST /api/projects/primary-candidates/`, `DB/migrations/2026-08-11_proj_description.sql` (`e7369ba`) |
| `agents`·`agent_versions`·`agent_version_tools`·`agent_version_subagents` 4테이블 신설 + `chat_session`·`agent_run`에 `agent_version_id` 추가 (2026-08-13) | Deep Agent형 에이전트 빌더 개편(`docs/작업기록/Deep_Agents/2026-08-13_01_*.md`·`02_*.md`)이 "발행된 버전은 불변, 세션·서브에이전트 관계는 특정 버전에 고정"을 MVP 전제로 확정하면서 비버전 `agent`/`agent_tool`로는 이 모델을 못 담게 됐다. **기존 `agent`/`agent_tool`은 한 글자도 안 건드리는 순수 추가다** — 지금 살아있는 Chat/Agent 실행(`services/harness/`)은 여전히 옛 테이블만 쓰고, 새 4테이블은 아직 미완성인 `services/agent_runtime/`(같은 날 착수) 전용이라 지금은 아무 코드도 안 읽고 안 쓴다. `agents.agent_id`가 `agent.agent_id`와 같은 `AG` 접두사를 쓰는 건 의도된 것이다(전환 완료 시 옛 테이블을 대체할 전제) — 전환 전까지는 로그·디버깅 시 테이블명을 꼭 같이 확인할 것. ⚠ 이 전환 자체는 2026-08-11 "Harness 직접 구현" 팀 확정을 뒤집는 결정이라 별도 팀/멘토 합의가 필요하다(`docs/TO-BE/작업목록.md` "2026-08-13 착수" 절 참고) — `DB/migrations/2026-08-13_agent_versioning.sql` |
| `agent_run.runtime_profile_version` 추가 (2026-08-14) | 같은 `agent_version_id`라도 미들웨어·정책·프롬프트가 바뀌면 동작이 달라진다. 재현하려면 「어느 버전이 돌았나」뿐 아니라 **「그때 배포된 코드가 무엇이었나」**도 있어야 한다. nullable이라 기존 행에 영향이 없고, 배포 파이프라인이 `GIT_COMMIT_SHA`를 넘기기 전까지는 계속 NULL이다 — `DB/migrations/2026-08-14_agent_run_runtime_profile_version.sql` |
| `agents.is_default_chat` 추가 + `agents_one_default_chat_per_team` 부분 유니크 (2026-08-15) | 아무것도 안 고르고 말을 걸었을 때 도는 **기본 챗 에이전트** 한 행을 가리킨다. `is_prebuilt`를 재사용하지 않는 이유는 그 플래그가 이미 「우리가 시드로 넣은 것」이라는 다른 뜻이기 때문이다 — 복제용 예시 에이전트도 같은 값을 쓴다. 팀당 하나만 true이고, 삭제·비활성 금지는 DB가 아니라 Repository가 막는다 — `DB/migrations/2026-08-15_agent_default_chat.sql` |
| `doc.owner_account_id`·`search_enabled` 추가 + `doc_owner_xor_team` CHECK + `ix_doc_owner` (2026-08-18) | 「내 파일」(M④). **개인 문서는 `team_id`를 NULL로 둔다** — 팀 문서를 읽는 13곳이 전부 `WHERE d.team_id = %s`라, NULL이면 그 13곳이 한 줄도 안 바뀐 채 개인 문서를 걸러낸다. 틀리는 쪽이 안전한 방향이다(빠뜨리면 새는 게 아니라 안 보인다). `search_enabled`는 라이브러리의 toggle이고 개인 문서에서만 뜻이 있다 — `DB/migrations/2026-08-18_personal_documents.sql` |
| `doc.shared_team_id` 추가 + `doc_share_is_personal_only` CHECK + `ix_doc_shared_team` (2026-08-18) | 개인 문서를 팀에 공유한다. `team_id`와 다르다 — 이 값이 있어도 **소유는 여전히 `owner_account_id`**다. 공유는 개인 문서에만 뜻이 있어 CHECK로 막는다 — `DB/migrations/2026-08-18_document_sharing.sql` |
| `doc.index_status` 추가 (2026-08-18) | 청크 파싱·임베딩이 도는 중인지 실패했는지 **아무 데도 안 남기고 있었다** — 실패해도 화면은 「본문 읽는 중」인 채였다(PM 지적). `doc_meta.extract_status`와 다르다: 그쪽은 요약용 텍스트를 뽑는 단계고 이 칸은 그 뒤 단계다. 둘은 따로 실패한다 — `DB/migrations/2026-08-18_doc_index_status.sql` |
| `agent_favorites` 테이블 신설 (2026-08-18) | 사람이 자주 쓰는 에이전트를 위로 올린다. FK 를 걸지 않는 것은 이 스키마의 관행이다 — 계정이나 에이전트를 지울 때 즐겨찾기 한 줄 때문에 삭제가 막히면 안 된다. 복합 PK 가 같은 사람이 같은 에이전트를 두 번 담는 것을 막는다 — `DB/migrations/2026-08-18_agent_favorites.sql` |
| `chat_session.tool_refs_override` 추가 (2026-08-18) | **이 대화에서 쓸 도구를 통째로 갈아 끼운다**(Chat 의 「+」). 에이전트 버전에 박힌 목록을 고치면 그 에이전트를 쓰는 **모든** 대화가 바뀌므로 한 대화에서만 정할 자리가 없었다. ⚠ **좁히기가 아니라 교체다** — 에이전트에 없는 도구도 고를 수 있어서, 도구가 0개인 기본 챗 에이전트도 대화에서 도구를 붙여 쓴다(`tests/test_executor.py` `ToolRefsOverrideTests`). `NULL` 은 「덮어쓰지 않음」이고 빈 배열(이 대화는 도구를 전부 끔)과 다르다 — `DB/migrations/2026-08-18_chat_session_tool_override.sql` |
| `doc_meta.extract_detail` 추가 (2026-08-19) | 문서를 **왜** 못 읽었는지를 담는다. `extract_status` 로는 「실패했다」까지만 알았는데, 「암호가 걸린 PDF」(암호를 풀어 다시 올리면 된다)와 「텍스트 레이어가 없는 PDF」(다시 올려도 같다)는 사람이 할 행동이 정반대다. **추출기는 이 문구를 이미 만들고 있었고**(`extractor.py` 의 `Extraction.detail`) 담을 칸이 없어 버려지고 있었다 — 새로 계산하는 값이 아니다. 옛 행은 비어 있고, 그때는 화면이 예전처럼 뭉뚱그린 문구를 쓴다 — `DB/migrations/2026-08-19_doc_meta_extract_detail.sql` |

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
docker compose -f infra/docker/docker-compose.yml exec db psql -U project_copilot -d project_copilot -c "SELECT count(*) FROM mock_hr.person;"
```

`57`이 나오면 정상이다. 스키마명 `mock_hr.`을 빼면 `relation "person" does not exist`가 난다 — HR 테이블은 `public`에 없다(§4.3).

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
              → DB/peopleDB/demo_skills.sql
```

`demo_skills.sql`은 팀장 자리(`PX002`)의 보유 스킬을 넣는다. `peopledb_mock.sql`이 55명에게 스킬을 넣으면서 이 자리만 빠뜨려, 팀장으로 로그인하면 「내 프로필 → 보유 스킬」이 본인만 비어 보인다. 실명이 없어 저장소에 커밋돼 있고 여러 번 실행해도 안전하다.

```powershell
Get-Content -Raw DB/peopleDB/demo_skills.sql |
  docker compose -f infra/docker/docker-compose.yml exec -T db `
  psql -U project_copilot -d project_copilot -v ON_ERROR_STOP=1
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

### 6.2 기본 챗 에이전트 — 시드할 것이 없다 (2026-08-22부터)

레거시 `agent`/`agent_tool` 스키마와 그 시드 스크립트(`seed_agents.py`,
「코파일럿」)를 폐기했다. 지금은 팀을 만드는 순간
`TeamRepository.create()`가 같은 트랜잭션에서 "기본 어시스턴트"
(`agents.is_default_chat = true`)를 자동으로 만든다 — 온보딩 화면에서
팀을 만들면 그 자리에서 Chat 이 된다. 관리자가 따로 돌릴 것이 없다.

**확인 방법**: Chat 빈 대화에서 배너 없이 바로 답이 오면 정상이다. DB 로
보려면:
```sql
SELECT agent_id, name, status FROM agents WHERE is_default_chat = true;
```

**2026-08-15 이전에 만들어진 팀**(자동 생성 로직이 없던 시점)만 예외다 —
그 팀들은 `backend/services/createDB/backfill_default_chat_agents.py`로
1회성 백필한다.

```bash
DATABASE_URL="postgres://project_copilot:project_copilot@localhost:5432/project_copilot" \
  python backend/services/createDB/backfill_default_chat_agents.py --all-teams
```

멱등이다 — 이미 있는 팀은 건너뛰고(도구가 빠져 있으면 채우기만 한다), 팀이
직접 만든 에이전트는 건드리지 않는다.

옛 「코파일럿」(전체 도구 + 팀의 아무 에이전트나 위임)은 레거시 스키마
전용 개념이었다. 기본 어시스턴트는 읽기 도구만 쓰고 다른 에이전트로
위임하지 않는다 — 쓰기 도구나 위임이 필요하면 Builder에서 직접 에이전트를
만든다.

---

## 7. VEC_IDX 예시로 벡터 저장·검색해보기 (선택)

> ⚠ **2026-08-04 이후로는 이 스크립트가 실패한다.** OpenAI `text-embedding-3-small`(1536차원)로 만든 데모 코드인데, §4.3에서 `vec_idx`를 768차원으로 바꿨기 때문이다. 새 파이프라인과 호환되지 않으므로 실행하지 않는다. 실제 벡터는 문서 처리 API가 EmbeddingGemma로 적재한다. 이 장은 pgvector가 어떻게 동작하는지 읽어 보는 용도로만 남겨 둔다.

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
