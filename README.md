# AI 프로젝트 운영 코파일럿

Django·Django REST Framework를 HTTP/API 계층으로 사용하고, PostgreSQL
테이블은 `DB/schema.sql`과 직접 SQL Repository로 관리하는 PM 지원 플랫폼
베이스 코드다. React 화면은 Figma 담당 팀원이 별도로 구현한다.

## 현재 구현

- PostgreSQL 17 + pgvector 단일 DB
- `DB/schema.sql` 기반 41개 테이블
- `DB/peopleDB/peopledb_mock.sql` 기반 합성 People 데이터
- psycopg 기반 프로젝트·조직·직원·배정 실행 Repository
- DRF 기반 조회·생성 API
- Block·Chunk UUID와 `VEC_IDX` pgvector 검색 인덱스
- React + Vite + TypeScript 실행 환경

Django ORM, Migration, Admin, 기본 Auth 테이블은 사용하지 않는다. 회원가입과
권한 API는 `user_account` 테이블 기준으로 후속 구현한다.

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
- React: `http://127.0.0.1:5173/`

DB 설치·초기화 절차는
`docs/0_개발환경/로컬_Docker_개발환경_설치_매뉴얼.md`를 따른다.
