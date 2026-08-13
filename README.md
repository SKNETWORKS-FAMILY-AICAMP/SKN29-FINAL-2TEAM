# halil — 프로젝트 운영 Agent Platform

팀에 필요한 AI 에이전트를 **코딩 없이** 만들어 쓴다. 무슨 일을 하는지, 무엇을
참고할지, 어떤 도구를 쓸지 적으면 팀 전체가 쓰는 에이전트가 된다.

쓰는 도구(Google Drive·Jira·인사 시스템)를 연결해 두면 대화로 물어보고 승인
한 번으로 실제 반영까지 간다. 두 가지를 지킨다 — **답에는 원문 근거가 붙고,
실제로 바꾸는 일은 사람의 승인을 거친다.**

## 무엇으로 되어 있나

| 갈래 | 내용 |
|---|---|
| 화면 | React + Vite + TypeScript. `frontend/src/pages` 30개 |
| API | Django + DRF. `apps/` — accounts · agents · chat · connectors · mcp · ops · people · projects |
| 데이터 | PostgreSQL 17 + pgvector. `DB/schema.sql` 57개 테이블 |
| 도메인 | `services/` — harness(도구 레지스트리·실행 루프) · agent_builder · task_extraction · workload · document_pipeline · document_meta · mcp · websearch |
| 문서 처리 | `services/document_pipeline` + `runpod_worker` (파싱·청킹·임베딩) |

**Django ORM·Migration·Admin·기본 Auth 테이블을 쓰지 않는다.** 스키마는
`DB/schema.sql` 한 곳에서 관리하고, 데이터 접근은 psycopg 직접 SQL Repository
(`backend/db/`)가 맡는다. 인증도 `user_account` 테이블 기준으로 직접 구현돼
있다(회원가입·로그인·비밀번호 재설정·초대 코드 가입).

## 누가 쓰나

- **팀장·팀원** — `/chat`에서 대화하고, `/agents`에서 팀 에이전트를 만들고,
  `/settings`에서 커넥터를 연결한다. 팀이 테넌트 경계다.
- **운영자(우리)** — `/ops`에 **별도 로그인**으로 들어간다. 일반 세션과 토큰
  salt가 다르고, 매 요청 DB에서 `is_admin`을 다시 확인한다. 고객의 대화 내용과
  문서 원문은 운영자도 보지 않는다.

## 로컬 실행

```powershell
Copy-Item .env.example .env
docker compose -f infra/docker/docker-compose.yml up --build
```

최초 DB 생성 후 People 목업 데이터를 한 번 적재한다.

```powershell
Get-Content -Raw DB/peopleDB/peopledb_mock.sql |
  docker compose -f infra/docker/docker-compose.yml exec -T db `
  psql -U project_copilot -d project_copilot
```

- API 상태: `http://127.0.0.1:8000/api/health/`
- 화면: `http://127.0.0.1:5173/`

테스트는 호스트에서 돌린다. `.env`의 `DATABASE_URL`은 컨테이너 안 이름(`db`)이라
호스트에서 그대로 쓰면 DB에 닿는 테스트가 깨진다.

```powershell
$env:DATABASE_URL="postgresql://project_copilot:project_copilot@localhost:5432/project_copilot"; python manage.py test tests
```

DB 설치·초기화 절차는
`docs/개발환경/로컬_Docker_개발환경_설치_매뉴얼.md`를 따른다.

## 문서

- 화면·API의 실제 동작: `docs/AS-IS/코드설명/`
- 설계 결정과 그 이유: `docs/AS-IS/설계/`
- 작업 기록: `docs/작업기록/`
