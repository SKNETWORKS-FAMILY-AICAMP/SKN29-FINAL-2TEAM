# AWS 1단계 — 공유 환경 구축 (RDS · S3 · EC2 준비)

> **이 문서를 받은 사람이 혼자 끝까지 갈 수 있게 쓴 작업 지시서다.**
> 모르는 값이 나오면 추측하지 말고 §23 문제 해결을 먼저 볼 것.
>
> 작성 2026-08-11 · 계정 = 수업·부트캠프 제공 · 리전 = `ap-northeast-2`(서울)

---

## 0. 이 작업이 무엇이고 왜 하는가

지금 팀원마다 **자기 노트북에 Postgres 를 띄워서** 개발한다. 그래서
① 스키마를 바꾸면 각자 수동 `ALTER` 를 돌려야 하고(안 돌린 사람은 에러),
② A가 등록·색인한 문서를 B는 못 본다. **"각자 한 걸 종합하기 힘들다"** 가 이것이다.

이 작업은 **DB 와 문서 원본만 AWS 로 올린다.** 개발은 계속 각자 로컬에서 한다.
EC2 배포는 2단계(`AWS_이전_매뉴얼.md`)이고 **지금 하지 않는다.**

### 0.1 왜 RDS 만으로는 안 되는가

RDS 만 공유하면 **절반만 풀린다.**

문서 메타·청크·임베딩은 DB 에 있으니 합쳐진다. 그런데 **원문 파일은 각자 로컬
디스크에 남는다**(`backend/services/storage.py` → `/var/lib/halil/documents`).
DB 에 `doc.storage_key` 는 있는데 내 디스크에 그 파일이 없는 상태가 된다.

| 기능 | RDS 만 | RDS + S3 |
|---|---|---|
| 검색·업무 추출 | ✅ 청크·임베딩이 DB 에 있음 | ✅ |
| 원문 근거 열람(다운로드) | ❌ 남이 넣은 문서는 파일이 없음 | ✅ |
| 재파싱 | ❌ 〃 | ✅ |
| 스키마 드리프트 | ✅ 해소 | ✅ |

**A(RDS)까지만 끝내고 팀에 뿌려도 된다.** 원문 열람이 안 되는 건 남지만
스키마 드리프트와 데이터 분산은 그 시점에 해소된다.

### 0.2 전체 순서와 소요

| | 작업 | 소요 | 누가 |
|---|---|---|---|
| **A** | RDS 생성 → 스키마·시드 적용 | 2~3시간 (생성 대기 20분 포함) | **이 문서를 받은 사람** |
| **B** | 팀원 `.env` 배포 | 30분 | 〃 |
| **C** | S3 버킷 + IAM 사용자 | 1시간 | 〃 |
| **D** | **EC2 — 만들어만 둔다** (인스턴스·Docker·SSH) | 1~1.5시간 | 〃 |
| **E** | `storage.py` S3 백엔드 + 기존 문서 업로드 | 반나절 | **개발 담당(코드)** |

**A → B 를 먼저 완주할 것.** 그것만으로 스키마 드리프트와 데이터 분산이 해소된다.

**D(EC2)는 앱 배포가 아니다.** 인스턴스를 만들고 Docker 를 깔고 SSH 가 되는
데까지다 — 손 많이 가는 구간을 미리 끝내 두는 것이고, OAuth 결정과 무관하다.
실제 배포는 2단계(`AWS_이전_매뉴얼.md`)이며 그 전에 OAuth 방향이 정해져야 한다(§13).

**E 는 코드라 다른 사람 몫이다.** C 는 E 가 없으면 버킷만 놀고 있으므로 시점을
맞출 것.

### 0.3 준비물

- [ ] AWS 콘솔 로그인 (수업 제공 계정)
- [ ] 이 저장소를 로컬에 클론해 둔 상태
- [ ] Docker Desktop 실행 중 — **psql 을 따로 설치하지 않아도 된다**(§4.1 참고)
- [ ] 팀원 전원의 공인 IP (§1.1 에서 수집)
- [ ] 팀원에게 값을 전달할 채널(카톡·노션 등). **비밀번호를 Git 에 올리지 말 것**

---

# A. RDS PostgreSQL

## 1. 사전 수집

### 1.1 팀원 공인 IP 모으기

**5432 포트를 인터넷 전체(`0.0.0.0/0`)에 열면 안 된다.** 팀원 IP 만 연다.
각자 아래를 실행해서 나온 숫자를 알려달라고 한다.

```bash
# macOS / Linux / Git Bash
curl ifconfig.me
```

```powershell
# Windows PowerShell
(Invoke-WebRequest -Uri "https://ifconfig.me/ip").Content
```

받아서 이렇게 정리해 둔다. 나중에 보안 그룹에 하나씩 넣는다.

| 팀원 | 공인 IP | CIDR 로 적을 값 |
|---|---|---|
| (예) 준 | `123.45.67.89` | `123.45.67.89/32` |
| … | | |

> 집·카페 IP 는 바뀐다. 팀원이 "갑자기 접속이 안 된다"고 하면 십중팔구 IP 가
> 바뀐 것이다 — §23 참고.

### 1.2 마스터 비밀번호 정하기

- **20자 이상.** 퍼블릭 액세스를 켤 것이므로 이게 사실상 유일한 방어선이다.
- `@ : / ?` 는 **쓰지 말 것.** `DATABASE_URL` 에 그대로 들어가서 URL 파싱을 깬다.
- 영문 대소문자 + 숫자 + `-` `_` `.` 조합을 권장.
- 정한 값을 메모해 둔다. RDS 는 나중에 비밀번호를 보여주지 않는다.

## 2. RDS 인스턴스 생성

AWS 콘솔 → 리전을 **아시아 태평양(서울) `ap-northeast-2`** 로 바꾼 뒤
**RDS → 데이터베이스 → 데이터베이스 생성**.

### 2.1 입력값

| 화면 항목 | 넣을 값 | 왜 |
|---|---|---|
| 데이터베이스 생성 방식 | **표준 생성** | 손쉬운 생성은 세부 설정이 잠긴다 |
| 엔진 유형 | **PostgreSQL** | |
| 엔진 버전 | **17.x 중 최신** (17.1 이상 필수) | 로컬이 `pgvector/pgvector:pg17`. **pgvector 0.8.0 은 PG 17.1+ / 16.5+ / 15.9+ 에서 지원** |
| 템플릿 | **프리 티어** (안 보이면 개발/테스트) | |
| DB 인스턴스 식별자 | `skn29-final-2team` | |
| 마스터 사용자 이름 | `project_copilot` | **로컬과 같게.** 그래야 `DATABASE_URL` 만 갈아끼우면 된다 |
| 마스터 암호 | §1.2 에서 정한 값 | |
| 인스턴스 구성 | **db.t4g.micro** | 프리 티어 대상 |
| 스토리지 유형 | gp3 | |
| 할당된 스토리지 | **20 GiB** | 테이블 57개 + 768차원 벡터엔 충분 |
| **스토리지 자동 조정** | **체크 해제** | 켜두면 모르는 새 과금이 늘어난다 |
| **다중 AZ 배포** | **대기 인스턴스를 생성하지 마십시오** | 켜면 **비용 2배**. 시연 환경엔 불필요 |
| 컴퓨팅 리소스 | EC2 컴퓨팅 리소스에 연결 **안 함** | EC2 가 아직 없다 |
| **퍼블릭 액세스** | **예** | ⚠ §2.2 를 읽을 것 |
| VPC 보안 그룹 | **새로 생성** → 이름 `skn29-rds-sg` | |
| 데이터베이스 인증 | 암호 인증 | |

**여기서부터가 놓치기 쉬운 부분이다.** 화면 아래 **「추가 구성」을 펼친다.**

| 추가 구성 항목 | 넣을 값 | 왜 |
|---|---|---|
| **초기 데이터베이스 이름** | **`project_copilot`** | ⚠ **비워두면 DB 가 안 만들어진다.** 인스턴스만 생기고 접속하면 `database "project_copilot" does not exist` 가 난다. 제일 흔한 실수 |
| 자동 백업 | 활성화, 보존 **1일** | 수업 프로젝트에 7일은 과하다 |
| 암호화 | 기본값 유지 | |
| **삭제 방지** | **활성화** | 실수로 지우면 전원 작업이 날아간다 |

**「데이터베이스 생성」** 클릭. **상태가 「사용 가능」이 될 때까지 5~20분** 걸린다.
그동안 §3 을 읽어 두면 된다.

### 2.2 ⚠ 퍼블릭 액세스를 켜는 이유 (매뉴얼과 다름)

`AWS_이전_매뉴얼.md` §3 은 *"RDS 는 퍼블릭 액세스를 쓰지 않고 EC2 보안 그룹만
허용"* 이라고 되어 있다. **그건 EC2 배포(2단계) 기준이고 지금은 맞지 않는다** —
팀원 노트북에서 직접 붙어야 하는데 EC2 가 아직 없다.

그래서 1단계는 **퍼블릭 액세스 + IP 허용목록**으로 간다. EC2 가 생기는 2단계에
퍼블릭 액세스를 끄고 EC2 보안 그룹만 허용하도록 되돌린다.

**절대 하면 안 되는 것: 인바운드 5432 를 `0.0.0.0/0` 으로 여는 것.**
편하지만 인터넷 전체에 DB 를 여는 것이고, 실제로 몇 분 안에 스캔이 들어온다.

## 3. 보안 그룹 설정

RDS 상태가 「사용 가능」이 되면 → 해당 DB 클릭 → **「연결 및 보안」 탭** →
VPC 보안 그룹의 `skn29-rds-sg` 링크 클릭 → **인바운드 규칙 편집**.

팀원 수만큼 규칙을 추가한다.

| 유형 | 프로토콜 | 포트 | 소스 | 설명 |
|---|---|---|---|---|
| PostgreSQL | TCP | 5432 | `123.45.67.89/32` | `준` |
| PostgreSQL | TCP | 5432 | `98.76.54.32/32` | `원빈` |
| … | | | 팀원 수만큼 | 이름을 꼭 적을 것 |

**설명(Description)에 팀원 이름을 반드시 적는다.** 나중에 IP 가 바뀌었을 때
누구 것을 고쳐야 하는지 알 수 없게 된다.

## 4. 접속 확인

### 4.1 psql 을 설치하지 않고 쓰는 법

로컬에 `psql` 이 없어도 된다. **이미 받아둔 pgvector 이미지에 들어 있다.**

먼저 **엔드포인트**를 복사한다 — RDS → 데이터베이스 → `skn29-final-2team` →
「연결 및 보안」 탭의 **엔드포인트**
(`skn29-final-2team.xxxxx.ap-northeast-2.rds.amazonaws.com`).

접속 문자열을 만든다. `<PW>` 와 `<ENDPOINT>` 를 실제 값으로 바꾼다.

```
postgresql://project_copilot:<PW>@<ENDPOINT>:5432/project_copilot?sslmode=require
```

> `?sslmode=require` 를 빼지 말 것. RDS 는 기본이 SSL 이다.

**연결 테스트** — 저장소 루트에서 실행한다.

```bash
# macOS / Linux / Git Bash
docker run --rm pgvector/pgvector:pg17 \
  psql "postgresql://project_copilot:<PW>@<ENDPOINT>:5432/project_copilot?sslmode=require" \
  -c "select version();"
```

```powershell
# Windows PowerShell (한 줄로)
docker run --rm pgvector/pgvector:pg17 psql "postgresql://project_copilot:<PW>@<ENDPOINT>:5432/project_copilot?sslmode=require" -c "select version();"
```

`PostgreSQL 17.x on aarch64-...` 가 나오면 성공이다.
안 되면 **§23 문제 해결로 갈 것.** 여기서 막힌 채로 다음 단계를 진행하지 말 것.

### 4.2 pgvector 사용 가능 확인

```bash
docker run --rm pgvector/pgvector:pg17 \
  psql "<접속문자열>" \
  -c "select name, default_version from pg_available_extensions where name in ('vector','pgcrypto');"
```

`vector` 와 `pgcrypto` 두 줄이 나와야 한다. `vector` 가 안 보이면 **엔진 버전이
낮은 것이다** — 인스턴스를 지우고 17.1 이상으로 다시 만든다.

## 5. 스키마 적용

### 5.1 `DB/schema.sql` 하나만 적용한다

> **`DB/migrations/` 폴더의 파일들은 무시한다.** 그건 *이미 DB 를 만들어 둔
> 사람*이 따라잡기 위한 수동 `ALTER` 모음이다. 지금은 **빈 DB** 라
> `schema.sql` 하나에 최신 상태가 전부 들어 있다(`agent_run`·`tool_call`·
> `doc_meta` 등 8/11 추가분 포함 — 확인함).
>
> 이 저장소는 **Django Migration 을 쓰지 않는다**(`config/settings/base.py` 에
> `DATABASES = {}`). `manage.py migrate` 를 실행하지 말 것.
> `AWS_이전_매뉴얼.md` §7-8·§9 에 "migration 적용"이라고 적힌 것은 **오기**다.

저장소 루트에서 실행한다. 파일을 컨테이너에 넘겨야 하므로 현재 폴더를 마운트한다.

```bash
# macOS / Linux / Git Bash
docker run --rm -v "$PWD:/w" -w /w -e PGCLIENTENCODING=UTF8 pgvector/pgvector:pg17 \
  psql "<접속문자열>" -v ON_ERROR_STOP=1 -f DB/schema.sql
```

```powershell
# Windows PowerShell
docker run --rm -v "${PWD}:/w" -w /w -e PGCLIENTENCODING=UTF8 pgvector/pgvector:pg17 psql "<접속문자열>" -v ON_ERROR_STOP=1 -f DB/schema.sql
```

> `PGCLIENTENCODING=UTF8` 을 빼지 말 것. `schema.sql` 에 **한글 주석**이 많아서
> 인코딩이 어긋나면 중간에 깨진다.

`CREATE TABLE` 이 쭉 올라가고 에러 없이 끝나면 성공이다.
`ON_ERROR_STOP=1` 때문에 하나라도 실패하면 거기서 멈춘다 — 멈췄다면 그 메시지를
그대로 팀에 공유할 것.

### 5.2 테이블 개수 검증 (⚠ 숫자를 정확히 볼 것)

```bash
docker run --rm pgvector/pgvector:pg17 psql "<접속문자열>" -c "\dt"
docker run --rm pgvector/pgvector:pg17 psql "<접속문자열>" -c "\dt mock_hr.*"
docker run --rm pgvector/pgvector:pg17 psql "<접속문자열>" -c "\dx"
```

| 확인 | 기대값 |
|---|---|
| `\dt` (public 스키마) | **49개** |
| `\dt mock_hr.*` | **8개** (`org`·`level`·`skill`·`person`·`person_skill`·`person_link`·`sched`·`absence`) |
| 합계 | 57개 = `schema.sql` 의 `CREATE TABLE` 수 |
| `\dx` | `vector`·`pgcrypto` 가 목록에 있음 |

**`\dt` 에서 8개가 안 보인다고 실패한 게 아니다.** HR 테이블은 `mock_hr` 스키마에
따로 있어서 기본 `search_path` 에 안 잡힌다. 위 두 번째 명령으로 따로 본다.

## 6. 시드 데이터 넣기

### 6.1 People DB 목업 (⚠ 딱 한 번만)

```bash
docker run --rm -v "$PWD:/w" -w /w -e PGCLIENTENCODING=UTF8 pgvector/pgvector:pg17 \
  psql "<접속문자열>" -v ON_ERROR_STOP=1 -f DB/peopleDB/peopledb_mock.sql
```

`INSERT 0 9`, `INSERT 0 57` … 이 순서대로 나온다
(org 9 · level 8 · person 57 · skill 14 · person_skill 111 · sched 57 · absence 23 · person_link 70).

> ⚠ **이 스크립트는 멱등이 아니다**(`ON CONFLICT` 없음). 두 번 돌리면
> `duplicate key value violates unique constraint` 가 난다. **한 번만 실행한다.**
> 이미 들어갔으면 다시 넣을 필요가 없으니 그 에러는 무시해도 된다.

검증:

```bash
docker run --rm pgvector/pgvector:pg17 psql "<접속문자열>" -c "select count(*) from mock_hr.person;"
```

`57` 이 나오면 정상이다. `mock_hr.` 을 빼면 `relation "person" does not exist` 가
난다 — HR 테이블은 `public` 에 없다.

### 6.2 데모 스킬 보정 (멱등 — 여러 번 돌려도 안전)

```bash
docker run --rm -v "$PWD:/w" -w /w -e PGCLIENTENCODING=UTF8 pgvector/pgvector:pg17 \
  psql "<접속문자열>" -f DB/peopleDB/demo_skills.sql
```

팀장 자리(`PX002`)의 보유 스킬을 채운다. 이게 없으면 팀장으로 로그인했을 때
「내 프로필 → 보유 스킬」이 본인만 비어 보인다.

### 6.3 ⚠ 실명 데이터(`team_overrides.sql`)는 팀 결정 사항

`DB/peopleDB/team_overrides.sql` 은 **팀원 실명·실이메일**이라 `.gitignore` 되어
있다(저장소엔 `team_overrides.example.sql` 만 있다).

**공유 RDS 에 넣을지는 이 문서를 실행하는 사람이 혼자 정하지 말 것.**
부트캠프 제공 계정이면 계정 소유자도 볼 수 있다. 데모만 목적이면
`peopledb_mock.sql` 의 가명으로 충분하다. **팀에 물어보고 진행한다.**

### 6.4 ⚠ 에이전트 시드·운영자 지정은 「나중」이다

`seed_agents.py` 와 `grant_admin.py` 는 **지금 돌리면 아무 일도 안 일어난다.**

- `seed_agents.py --all-teams` → 새 DB 에는 **팀이 하나도 없다.** 팀은 회원가입
  (온보딩)으로 생긴다. 팀이 생긴 **뒤에** 돌려야 한다.
- `grant_admin.py <이메일>` → 그 이메일이 `user_account` 에 **이미 가입돼
  있어야** 한다.

그래서 순서가 이렇게 된다.

```
스키마 → People 목업 → 팀에 .env 배포(§7) → 누군가 회원가입해서 팀 생성
   → seed_agents.py → grant_admin.py
```

§7 이 끝난 뒤 §8 에서 실행한다.

---

# B. 팀 배포

## 7. 팀원 `.env` 교체 안내

팀에 아래 내용을 그대로 전달한다. **비밀번호가 들어가므로 Git·공개 채널이 아닌
곳으로 보낼 것.**

> **[공유 DB 전환 안내]**
>
> 오늘부터 로컬 Postgres 를 쓰지 않고 팀 공용 RDS 를 씁니다.
>
> **1. `.env` 의 `DATABASE_URL` 을 아래로 교체하세요.**
> ```
> DATABASE_URL=postgresql://project_copilot:<PW>@<ENDPOINT>:5432/project_copilot?sslmode=require
> ```
>
> **2. 로컬 `db` 컨테이너는 더 이상 띄우지 않습니다.**
> ```bash
> docker compose -f infra/docker/docker-compose.yml stop db
> docker compose -f infra/docker/docker-compose.yml up --force-recreate web frontend
> ```
> `.env` 를 바꾼 뒤에는 **재시작이 아니라 재생성**(`--force-recreate`)이어야
> 값이 반영됩니다.
>
> **3. 접속이 안 되면** 공인 IP 가 바뀐 것일 수 있습니다.
> `curl ifconfig.me` 결과를 저에게 알려주세요. 보안 그룹에 추가하겠습니다.
>
> **4. ⚠ `DB/reset_demo.sql` 을 절대 혼자 돌리지 마세요.**
> 이제 전원의 데이터가 같이 날아갑니다. 돌려야 하면 먼저 팀에 공지하세요.
>
> **5. 로컬 `postgres_data` 볼륨은 아직 지우지 마세요.**
> 옮기지 못한 데이터가 있을 수 있으니 1~2주 두고 확인한 뒤 정리합니다.

## 8. 팀 생성 후 마무리 시드

누군가 회원가입해서 팀이 만들어진 뒤에 실행한다. **이건 psql 이 아니라 Python
스크립트**라 웹 컨테이너 안에서 돌리는 게 편하다.

```bash
docker compose -f infra/docker/docker-compose.yml exec web \
  python backend/services/createDB/seed_agents.py --all-teams
```

멱등이라 여러 번 돌려도 팀당 하나이고, 이미 있으면 최신 정의로 맞춘다.
팀이 직접 만든 에이전트는 건드리지 않는다.

> **Chat 화면 에이전트 선택기에 「업무 추출 에이전트」가 안 보이면 이걸 안 돌린
> 것이다.** 새 팀이 생길 때마다 다시 돌려야 한다.

운영자 콘솔(`/ops`) 을 쓸 계정을 지정한다. **그 이메일로 먼저 가입돼 있어야 한다.**

```bash
docker compose -f infra/docker/docker-compose.yml exec web \
  python backend/services/createDB/grant_admin.py <가입된 이메일>
```

## 9. A·B 완료 검증

- [ ] 팀원 전원이 `.env` 를 바꾸고 앱이 뜬다
- [ ] **A 가 등록한 문서를 B 의 화면에서 볼 수 있다** ← 이게 이번 작업의 목적
- [ ] Chat 에이전트 선택기에 기본 제공 에이전트가 보인다
- [ ] 로컬 `db` 컨테이너가 아무도 안 떠 있다
- [ ] 원문 다운로드는 **아직 안 된다** — 정상이다(§0.1). C·E 에서 해결한다

---

# C. S3 + IAM

> D(코드)가 없으면 버킷이 놀고 있게 된다. D 담당자와 시점을 맞추고 시작할 것.

## 10. S3 버킷 생성

콘솔 → S3 → **버킷 만들기**.

| 항목 | 값 |
|---|---|
| 버킷 이름 | `skn29-final-2team-files-<임의 4자리>` — **전 세계에서 유일**해야 한다. 이미 있다는 에러가 나면 뒤 숫자를 바꾼다 |
| 리전 | **아시아 태평양(서울) ap-northeast-2** — RDS 와 같아야 한다 |
| 퍼블릭 액세스 차단 | **모두 차단 (기본값 그대로 둔다)** |
| 버킷 버저닝 | **활성화** |
| 기본 암호화 | SSE-S3 (기본값) |

**버저닝을 켜는 이유** — Drive 문서가 수정되면 같은 키에 덮어쓰는데, 버전이
없으면 옛 근거를 다시 못 본다. 문서 메타에 `version_id` 를 기록하기로 되어 있다.

**키 구조는 코드가 이미 정해 두었다** — `backend/services/storage.py` 의
`build_key()` → `{team_id}/{doc_id}.{확장자}`. 폴더를 미리 만들 필요 없다.

> `AWS_이전_매뉴얼.md` §5 의 `documents/{project_id}/...` 안은 **채택하지 않는다.**
> 문서는 등록 시점에 어느 프로젝트 것인지 정해지지 않고(코드 주석), 나중에
> 지정된다고 파일을 옮길 수 없기 때문이다.

## 11. IAM 사용자 생성

> `AWS_이전_매뉴얼.md` §6 은 **EC2 IAM Role** 전제다. 1단계엔 EC2 가 없으므로
> **로컬에서 쓸 IAM 사용자**를 만든다. 2단계에서 이 사용자를 지우고 Role 로 바꾼다.

콘솔 → IAM → 사용자 → **사용자 생성**.

1. 사용자 이름 `skn29-2team-dev`. **"AWS Management Console 에 대한 사용자 액세스
   권한 제공" 은 체크하지 않는다** (프로그래밍 방식만 필요).
2. 권한 → **직접 정책 연결** → **정책 생성** → JSON 탭에 아래를 붙여넣는다.
   `<버킷이름>` 두 군데를 실제 값으로 바꿀 것.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BucketList",
      "Effect": "Allow",
      "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
      "Resource": "arn:aws:s3:::<버킷이름>"
    },
    {
      "Sid": "ObjectRW",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:GetObjectVersion",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::<버킷이름>/*"
    }
  ]
}
```

정책 이름 `skn29-2team-s3-access`. **`AmazonS3FullAccess` 를 붙이지 말 것** —
계정의 다른 버킷까지 열린다.

3. 사용자 생성 후 → 해당 사용자 → **보안 자격 증명** 탭 → **액세스 키 만들기** →
   사용 사례 **"로컬 코드"** 선택 → 생성.
4. **액세스 키 ID 와 비밀 액세스 키를 이 화면에서만 볼 수 있다.** 복사해 둔다.

### 11.1 팀원에게 전달할 `.env` 추가분

```text
OBJECT_STORAGE_PROVIDER=s3
AWS_STORAGE_BUCKET_NAME=<버킷이름>
AWS_S3_REGION_NAME=ap-northeast-2
AWS_ACCESS_KEY_ID=<액세스 키 ID>
AWS_SECRET_ACCESS_KEY=<비밀 액세스 키>
```

> ⚠ **`.env` 는 `.gitignore` 대상이고 `.env.example` 에는 플레이스홀더만 둔다.**
> 이 저장소는 과거에 실제 키를 커밋할 뻔한 사고가 있었다. 커밋 전
> `git diff --cached` 로 키가 섞이지 않았는지 확인할 것.

---

# D. EC2 — 지금은 「만들어만」 둔다

> ⚠ **인스턴스를 만들고 Docker 를 깔고 SSH 가 되는 데까지만 한다.**
> 앱 배포·`.env`·OAuth 는 손대지 않는다. 이유는 §13.

## 13. 왜 배포까지 안 가는가

**OAuth 방향이 안 정해졌기 때문이다.** Google 은 redirect_uri 에 **http 를 받지
않는다**(`localhost`·`127.0.0.1` 만 예외). 그래서 `http://<EC2_공인IP>:8000/...` 를
redirect URI 로 등록할 수 없고, **그대로 배포하면 Drive 연동이 아예 안 된다.**
Jira 도 같다. 도메인+HTTPS 로 갈지, `cloudflared` 터널을 쓸지, 시연 때만 로컬에서
연동할지 — 이게 정해져야 배포 절차가 나온다.

거기에 `frontend/Dockerfile` 이 `CMD ["npm","run","dev"]`(Vite **개발** 서버)라
도메인을 붙이는 순간 `vite.config.ts` 의 `server.allowedHosts` 에 걸린다
(IP 는 기본 허용이라 지금은 통과한다).

**그래도 지금 미리 해둘 값어치가 있는 것은** 느리고 손 많이 가는 부분이다 —
키 페어 발급, SSH 방화벽, Docker 설치, IAM Role, 저장소 클론. 이건 OAuth 와
아무 상관이 없고, 나중에 배포할 때 이게 다 돼 있으면 30분이면 끝난다.

## 14. 키 페어 만들기

콘솔 → EC2 → **네트워크 및 보안 → 키 페어 → 키 페어 생성**.

| 항목 | 값 |
|---|---|
| 이름 | `skn29-2team-key` |
| 키 페어 유형 | RSA |
| 프라이빗 키 형식 | **`.pem`** (PuTTY 를 쓸 사람만 `.ppk`) |

**`.pem` 파일이 자동으로 다운로드되고, 이 순간이 지나면 다시 받을 수 없다.**
잃어버리면 인스턴스에 못 들어가서 새로 만들어야 한다.

macOS/Linux 는 권한을 좁혀야 SSH 가 거부하지 않는다.

```bash
chmod 400 ~/Downloads/skn29-2team-key.pem
```

> ⚠ **`.pem` 을 저장소에 넣지 말 것.** 팀원에게 줄 때도 Git 이 아닌 채널로.

## 15. 인스턴스 생성

EC2 → **인스턴스 시작**.

| 항목 | 값 | 왜 |
|---|---|---|
| 이름 | `skn29-2team-app` | |
| AMI | **Ubuntu Server 24.04 LTS** | 「프리 티어 사용 가능」 라벨 확인 |
| 아키텍처 | **x86_64** | ARM(t4g)은 이미지 빌드 시 플랫폼 문제가 생길 수 있다 |
| 인스턴스 유형 | **t3.micro** (없으면 t2.micro) | 「프리 티어 사용 가능」 라벨 확인 |
| 키 페어 | `skn29-2team-key` | §14 |
| 네트워크 → 퍼블릭 IP 자동 할당 | **활성화** | |
| 방화벽(보안 그룹) | **새로 생성** → 이름 `skn29-ec2-sg` | 규칙은 §17 에서 |
| **스토리지** | **30 GiB** gp3 | ⚠ **기본값 8GiB 로 두면 안 된다.** Docker 이미지(Python+Node)와 `node_modules` 로 금방 찬다. 프리 티어는 30GiB 까지 무료 |

**인스턴스 시작.** 1~2분이면 「실행 중」이 된다.

## 16. Elastic IP 할당 (⚠ 건너뛰지 말 것)

**EC2 를 중지했다 다시 켜면 공인 IP 가 바뀐다.** 그러면 팀원에게 알린 주소,
`ALLOWED_HOSTS`, `VITE_API_BASE_URL`, 나중에 등록할 OAuth redirect URI 가 전부
무효가 된다. **고정 IP 를 지금 붙여 둔다.**

EC2 → **네트워크 및 보안 → 탄력적 IP → 탄력적 IP 주소 할당** → 할당 →
목록에서 선택 → **작업 → 탄력적 IP 주소 연결** → 인스턴스 `skn29-2team-app` 선택 → 연결.

> 💰 **실행 중인 인스턴스에 붙어 있으면 무료지만, 인스턴스를 삭제하고 IP 만 남겨두면
> 과금된다.** 프로젝트가 끝나면 **반드시 「릴리스」** 할 것(§24).

여기서 받은 IP 를 적어 둔다: `EC2_IP = ___.___.___.___`

## 17. 보안 그룹 규칙

EC2 → 인스턴스 → 「보안」 탭 → `skn29-ec2-sg` → **인바운드 규칙 편집**.

| 유형 | 포트 | 소스 | 설명 |
|---|---|---|---|
| SSH | 22 | 팀원 IP `/32` 각각 | §1.1 에서 모은 IP. `0.0.0.0/0` 금지 |
| 사용자 지정 TCP | 8000 | (지금은 **추가하지 않는다**) | 배포할 때 연다 |
| 사용자 지정 TCP | 5173 | (지금은 **추가하지 않는다**) | 〃 |

**지금은 22번만 연다.** 앱이 아직 안 도는데 포트를 열어둘 이유가 없다.

## 18. SSH 접속 확인

```bash
# macOS / Linux / Git Bash
ssh -i ~/Downloads/skn29-2team-key.pem ubuntu@<EC2_IP>
```

```powershell
# Windows PowerShell (OpenSSH 내장)
ssh -i C:\Users\<사용자>\Downloads\skn29-2team-key.pem ubuntu@<EC2_IP>
```

사용자 이름은 Ubuntu AMI 라 **`ubuntu`** 다(`ec2-user` 아님 — Amazon Linux 용).
처음 접속하면 fingerprint 확인이 뜬다. `yes` 입력.

안 되면 §23 문제 해결로.

## 19. 서버 기본 설정 (SSH 접속한 상태에서)

### 19.1 Docker 설치

```bash
sudo apt-get update && sudo apt-get upgrade -y

# Docker 공식 설치 스크립트
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# sudo 없이 docker 를 쓰게 한다
sudo usermod -aG docker ubuntu
```

**`usermod` 이후에는 로그아웃했다 다시 들어와야 적용된다.**

```bash
exit
# 다시 ssh 접속 후
docker --version
docker compose version
```

두 명령이 버전을 출력하면 성공이다. `docker compose`(하이픈 없음)가 v2 이고
이 저장소가 쓰는 형식이다.

### 19.2 저장소 클론

```bash
cd ~
git clone <저장소 URL> SKN29-Final-2Team
cd SKN29-Final-2Team
```

> 프라이빗 저장소면 HTTPS + Personal Access Token 이 간단하다. SSH 키를 EC2 에
> 새로 만들어 GitHub 에 등록해도 된다. **`.pem` 이나 개인 GitHub 키를 EC2 로
> 복사하지는 말 것.**

**`.env` 는 아직 만들지 않는다.** 배포 시점에 만든다(§20 의 1번).

### 19.3 RDS 연결만 확인

EC2 에서 RDS 가 보이는지 지금 확인해 둔다. 나중에 배포할 때 여기서 막히면
원인 찾기가 어렵다.

먼저 **RDS 보안 그룹에 EC2 를 추가한다** — 콘솔 → RDS → `skn29-rds-sg` →
인바운드 규칙 편집 → 규칙 추가:

| 유형 | 포트 | 소스 | 설명 |
|---|---|---|---|
| PostgreSQL | 5432 | **`skn29-ec2-sg`** (보안 그룹을 소스로 선택) | `EC2` |

> 팀원 IP 규칙은 **그대로 둔다.** 로컬 개발이 계속되므로 둘 다 필요하다.
> 2단계에서 앱이 EC2 로 완전히 옮겨가면 그때 팀원 IP 규칙을 걷고 퍼블릭
> 액세스를 끈다.

EC2 에서:

```bash
docker run --rm pgvector/pgvector:pg17 \
  psql "postgresql://project_copilot:<PW>@<RDS_ENDPOINT>:5432/project_copilot?sslmode=require" \
  -c "select count(*) from mock_hr.person;"
```

`57` 이 나오면 EC2 → RDS 경로가 뚫린 것이다.

## 20. 여기서 멈춘다 — 다음에 할 일 (2단계)

아래는 **하지 않는다.** OAuth 방향이 정해진 뒤 별도 문서로 진행한다.

1. `.env` 작성 (`ALLOWED_HOSTS`·`CORS_ALLOWED_ORIGINS`·`VITE_API_BASE_URL` 에 EC2 IP 반영)
2. **OAuth redirect URI 결정** — Google/Atlassian 콘솔 등록까지. **여기가 관문이다**
3. `frontend/Dockerfile` 을 `npm run build` + 정적 서빙으로 바꿀지 결정
   (도메인을 쓰면 `vite.config.ts` 에 `server.allowedHosts` 추가 필요)
4. EC2 IAM Role 생성 → S3 권한 부여 → 인스턴스에 연결 → **IAM 사용자
   `skn29-2team-dev` 액세스 키 폐기**(§11 은 로컬 개발용 임시 조치였다)
5. 보안 그룹 8000·5173 개방
6. `docker compose -f infra/docker/docker-compose.aws.yml up --build -d`
7. `curl http://localhost:8000/api/health/` 확인
8. RunPod 재점검 — **EC2 에 공인 IP 가 생기므로 `cloudflared` 터널이 필요 없어질
   수 있다.** 지금은 RunPod 가 로컬 원문을 받으려고 터널을 쓴다

### D 파트 완료 검증

- [ ] `.pem` 을 안전한 곳에 보관했고 저장소엔 없다
- [ ] Elastic IP 를 할당하고 인스턴스에 연결했다 (IP 기록: __________)
- [ ] 팀원 IP 로만 22번이 열려 있다 (`0.0.0.0/0` 아님)
- [ ] 8000·5173 은 **아직 안 열려 있다**
- [ ] EBS 가 30GiB 다 (8GiB 아님)
- [ ] SSH 접속되고 `docker --version`·`docker compose version` 이 동작한다
- [ ] 저장소가 `~/SKN29-Final-2Team` 에 클론돼 있다
- [ ] EC2 에서 RDS 로 `select count(*) from mock_hr.person;` → `57`
- [ ] RDS 보안 그룹에 EC2 보안 그룹과 팀원 IP 가 **둘 다** 있다

---

# E. 코드 작업과 문서 이전 (개발 담당)

## 21. `storage.py` 에 S3 백엔드 추가 (⚠ 아직 없다)

`OBJECT_STORAGE_PROVIDER` 는 `config/settings/base.py:105` 에 **정의만 되어 있고
`backend/services/storage.py` 가 그 값을 읽지 않는다.** 현재 로컬 디스크 전용이다.

추상화는 되어 있다 — 호출자는 `build_key()` · `save(key, data)` · `load(key)` ·
`exists(key)` 만 쓰고 파일이 어디 있는지 모른다. **이 네 함수의 몸통만 분기하면
된다.**

- `local` → 지금 코드 그대로. `s3` → boto3 client.
- 버킷·리전은 settings 에서 읽는다. **함수 시그니처를 바꾸지 말 것** —
  `apps/projects/api_views.py`·`backend/db/document_pipeline.py`·
  `backend/db/repositories.py` 가 이미 쓰고 있다.
- `save()` 는 S3 응답의 `VersionId` 를 돌려받는다 → 문서 메타에 기록한다.
- `requirements/production.txt` 에 `boto3`·`django-storages[s3]` 는 이미 있다.
  **로컬 개발에서도 S3 를 쓰려면 `requirements/local.txt` 에도 boto3 가 필요하다** —
  확인할 것.
- `django-storages` 는 Django `FileField`/staticfiles 용이다. 이 프로젝트의 문서
  저장은 ORM 을 안 쓰므로 **`storage.py` 에서 boto3 를 직접 부르는 편이 단순하다.**
  `django-storages` 는 2단계에서 정적 파일용으로만 쓴다.
- 테스트: `tests/test_document_download.py` 가 `DocumentStorage` 를 이미 다룬다.
  분기 후 로컬 경로 테스트가 깨지지 않는지 확인.

## 22. 기존 로컬 문서 업로드

각자 로컬 볼륨(`document_storage` → `/var/lib/halil/documents`)에 있는 파일을
버킷으로 올린다. **키 구조가 같으므로 경로 그대로 복사하면 된다.**

```bash
docker compose -f infra/docker/docker-compose.yml cp web:/var/lib/halil/documents ./_migrate
aws s3 sync ./_migrate s3://<버킷이름>/ --exclude ".*"
```

올린 뒤 **DB 의 `doc` 행 수와 버킷 객체 수를 대조한다.**

```bash
docker run --rm pgvector/pgvector:pg17 psql "<접속문자열>" -c "select count(*) from doc;"
aws s3 ls s3://<버킷이름>/ --recursive --summarize | tail -3
```

어긋나면 어느 문서가 원문 없이 메타만 남았는지 목록으로 뽑아 둘 것 — 재파싱
대상이다. 여러 사람이 각자 올리므로 **중복 키는 덮어쓰기가 되지만 내용이 같아
문제 없다**(키가 `doc_id` 기준).

---

# 23. 문제 해결

| 증상 | 원인 · 해결 |
|---|---|
| 접속이 아예 안 되고 **한참 멈춰 있다가 timeout** | 보안 그룹 문제다(막혔으면 거절이 아니라 무응답이 된다). §3 에서 내 IP 가 `/32` 로 들어 있는지, 지금 IP 가 그때와 같은지(`curl ifconfig.me`) 확인 |
| `could not translate host name` | 엔드포인트 오타. 콘솔 「연결 및 보안」에서 다시 복사. 포트(`:5432`)를 엔드포인트에 붙여 넣지 않았는지 확인 |
| `database "project_copilot" does not exist` | **§2.1 「추가 구성 → 초기 데이터베이스 이름」을 비워두고 생성한 것.** 가장 흔한 실수. 인스턴스 안에서 `psql "...:5432/postgres"` 로 붙어 `CREATE DATABASE project_copilot;` 하면 복구된다 |
| `password authentication failed` | 비밀번호에 `@ : / ?` 가 들어가 URL 이 잘못 파싱된 것일 수 있다. RDS 콘솔에서 「수정 → 새 마스터 암호」로 특수문자 없는 값으로 바꾼다 |
| `no pg_hba.conf entry ... SSL off` | 접속 문자열 끝에 `?sslmode=require` 를 빼먹었다 |
| `type "vector" does not exist` | 엔진 버전이 낮다. **17.1 이상**(또는 16.5+ / 15.9+)인지 확인. 낮으면 인스턴스를 지우고 다시 만든다 |
| `schema.sql` 중간에 한글이 깨지며 실패 | `-e PGCLIENTENCODING=UTF8` 을 빼먹었다 |
| `\dt` 에 49개만 보인다 | **정상이다.** HR 8개는 `mock_hr` 스키마에 있다. `\dt mock_hr.*` 로 따로 본다 |
| `peopledb_mock.sql` 재실행 시 `duplicate key` | 이미 들어간 것이다. 무시해도 된다(§6.1) |
| 팀원이 갑자기 접속 안 됨 | 공인 IP 가 바뀐 것이 대부분이다. 새 IP 를 받아 §3 에 추가 |
| Chat 에 기본 제공 에이전트가 안 보임 | `seed_agents.py` 미실행(§8). 새 팀이 생길 때마다 필요하다 |
| `/ops` 로그인 시 「운영자 권한이 없는 계정입니다」 | `grant_admin.py` 미실행(§8) |
| 문서 다운로드가 404/500 | **E(코드) 가 끝나기 전에는 정상이다**(§0.1). 남이 등록한 문서의 원본이 내 디스크에 없다 |
| `docker run ... psql` 이 `-v "$PWD:/w"` 에서 실패 (Windows) | PowerShell 은 `"${PWD}:/w"`, CMD 는 `"%cd%:/w"` |

---

# 24. 비용과 뒷정리 (⚠ 꼭 읽을 것)

**부트캠프 제공 계정이라도 RDS 는 켜 두면 계속 과금된다.** 프리 티어는
`db.t4g.micro` **750시간/월** = 인스턴스 1개 상시가 한계다. 이 한도를 넘기는
흔한 원인 두 가지를 위에서 미리 껐다.

- **다중 AZ** → 인스턴스가 2개가 되어 한도를 즉시 초과한다
- **스토리지 자동 조정** → 모르는 새 20GB 를 넘어간다

S3 는 이 규모에서 사실상 무시할 수 있다(월 1달러 미만).

**발표가 끝나면:**

1. RDS → 「작업 → 스냅샷 생성」으로 **스냅샷을 먼저 뜬다**
2. 삭제 방지를 끄고 인스턴스 삭제
3. S3 버킷은 남겨도 저렴하지만, 정리한다면 버저닝 때문에 **이전 버전까지
   삭제**해야 완전히 지워진다
4. IAM 사용자 `skn29-2team-dev` 의 액세스 키 비활성화

---

## 관련 문서

- [AWS 이전 매뉴얼](AWS_이전_매뉴얼.md) — 2단계(EC2 배포) 최종 그림.
  단 §7-8·§9 의 "Django migration" 표기는 오기다(§5.1 참고)
- [DB 시작 가이드](DB_시작_가이드.md) — 로컬 기준. 스키마 수동 `ALTER` 관례,
  시드 스크립트 상세
- [로컬 Docker 개발환경 설치 매뉴얼](로컬_Docker_개발환경_설치_매뉴얼.md)
